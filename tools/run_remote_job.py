"""run_remote_job — dispatch a GPU job to the user's own Modal account.
Deterministic dispatch. NO AI in execution.

WHAT THIS IS FOR. Five capabilities sit on a deferred shelf for one reason:
they need hardware this laptop does not have. boltz2 and proteinmpnn were
deferred for "no GPU" (proteinmpnn's half of that was wrong — see R-BIO-1 — but
structure PREDICTION genuinely is not), autodock_vina has no aarch64 build at
all, and solid-state DFT wants a real machine. Building one wrapper per tool
would clear them one per session forever. This clears the class: any tool that
needs a GPU, a different architecture, or more machine than is here can run,
because the machine is rented by the second and thrown away.

*** THE POLICY THAT SHAPES EVERYTHING HERE (R-REMOTE-1, owner-ruled
2026-07-27): A REMOTE RESULT IS AN INPUT, NEVER A CLAIM. ***

The verification wall regenerates a number by RE-RUNNING its artifact. Make a
remote GPU job an artifact and two bad things follow: the wall pays for the GPU
again on every check, and GPU inference is frequently nondeterministic
(nondeterministic kernels, TF32, atomics), so a perfectly good result fails as a
`mismatch` through no fault of the science.

So this module is deliberately NOT wired into stages/verification.py. There is
no `remote` artifact kind and none should be added. The enforcement is
STRUCTURAL — a remote result cannot become a verified claim because nothing can
re-run it, not because a flag says so, and a flag is the kind of thing a later
edit flips.

WHAT THE AGENT DOES INSTEAD, and it is the honest shape anyway: run the
expensive thing ONCE, bring its outputs back as files, then compute the findings
FROM those files locally, where they are cheap, deterministic and verifiable.
Fold the protein remotely and report the pLDDT as a sourced caveat; compute the
contact order, the radius of gyration, the interface area from the returned
structure in the atomistic shelf, and let THOSE be the claims. This is the
"INPUTS ARE NOT CLAIMS" rule the experimenter's prompt already states, applied
to the one place where re-running is genuinely unaffordable.

Typed input:
    run_remote_job({
      "code": "<python that runs on the remote machine>",
      "gpu": "T4" | "A10G" | "A100" | "H100" | None,   # None = remote CPU
      "pip": ["torch", "fair-esm"],       # the remote environment, pinned by you
      "apt": ["git"],                     # OPTIONAL system packages
      "input_files": {"in.pdb": b"..."},  # OPTIONAL, sent to the job
      "output_files": ["out.pdb"],        # OPTIONAL, brought back
      "timeout_s": 900,                   # bounded
    })
Return: {"valid": bool, "metrics": dict, "artifacts": {name: bytes},
         "diagnostics": str, "runtime_s": float}

Note what is NOT in that return: a `qoi`. Every other wrapper in this project
returns one because every other wrapper feeds a claim. This one returns metrics
the agent may READ and must not claim — the missing field is the policy, made
visible at the type level.
"""

from __future__ import annotations

import sys
import time

# The remote job writes its metrics here, exactly as the local sandbox does, so
# a script moves between the two with no change to how it reports.
REMOTE_WORKDIR = "/work"
RESULT_NAME = "result.json"

_REQUIRED_FIELDS = ("code",)
_OPTIONAL_FIELDS = ("gpu", "pip", "apt", "input_files", "output_files",
                    "timeout_s", "app_name")

# Modal's GPU names. An allowlist, so a typo is refused before it becomes a
# billing surprise on hardware nobody meant to rent.
GPU_ALLOWLIST = ("T4", "L4", "A10G", "A100", "A100-80GB", "H100")

DEFAULT_TIMEOUT_S = 900
MAX_TIMEOUT_S = 3600
MAX_DIAG_CHARS = 800
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024

_NOT_A_CLAIM_NOTE = (
    "REMOTE RESULT — THIS IS AN INPUT, NOT A CLAIM (R-REMOTE-1). It ran on "
    "rented hardware and cannot be re-run by the verification wall, so no "
    "finding may be marked verified on the strength of it. Use it: bring the "
    "output files back and compute your findings from them locally, where they "
    "reproduce. Report any number taken directly from here with "
    "\"verified\": false and say where it came from."
)


class RemoteJobInputError(ValueError):
    """The typed input is not a runnable remote job."""


class RemoteJobUnavailable(RuntimeError):
    """Modal is not installed, not authenticated, or unreachable — a
    could-not-run condition, DISTINCT from a job that ran and failed."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise RemoteJobInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise RemoteJobInputError(f"missing required field(s): {', '.join(missing)}")
    allowed = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
    extra = sorted(set(spec) - allowed)
    if extra:
        raise RemoteJobInputError(f"unsupported field(s): {', '.join(extra)}")

    code = spec["code"]
    if not isinstance(code, str) or not code.strip():
        raise RemoteJobInputError("'code' must be a non-empty string")

    gpu = spec.get("gpu")
    if gpu is not None and gpu not in GPU_ALLOWLIST:
        raise RemoteJobInputError(
            f"gpu {gpu!r} is not on the allowlist ({', '.join(GPU_ALLOWLIST)}); "
            "use None for a CPU job")

    for field in ("pip", "apt", "output_files"):
        value = spec.get(field)
        if value is not None and not (isinstance(value, list)
                                      and all(isinstance(v, str) for v in value)):
            raise RemoteJobInputError(f"'{field}' must be a list of strings")

    input_files = spec.get("input_files") or {}
    if not isinstance(input_files, dict):
        raise RemoteJobInputError("'input_files' must be an object")
    for name, data in input_files.items():
        if not _is_bare_name(name):
            raise RemoteJobInputError(
                f"input file {name!r} must be a bare filename (no path parts)")
        if not isinstance(data, (bytes, bytearray)):
            raise RemoteJobInputError(f"input file {name!r} must be bytes")
    for name in spec.get("output_files") or []:
        if not _is_bare_name(name):
            raise RemoteJobInputError(
                f"output file {name!r} must be a bare filename (no path parts)")

    timeout = spec.get("timeout_s", DEFAULT_TIMEOUT_S)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise RemoteJobInputError(f"'timeout_s' must be an integer, got {timeout!r}")
    if not 1 <= timeout <= MAX_TIMEOUT_S:
        raise RemoteJobInputError(
            f"'timeout_s' must be between 1 and {MAX_TIMEOUT_S}, got {timeout}")

    return {
        "code": code,
        "gpu": gpu,
        "pip": list(spec.get("pip") or []),
        "apt": list(spec.get("apt") or []),
        "input_files": dict(input_files),
        "output_files": list(spec.get("output_files") or []),
        "timeout_s": timeout,
        "app_name": spec.get("app_name") or "research-system-remote",
    }


def _is_bare_name(name) -> bool:
    return (isinstance(name, str) and name != "" and "/" not in name
            and "\\" not in name and name not in (".", ".."))


# The runner that executes INSIDE the remote container. A FIXED TEMPLATE, like
# tools/run_code.py's: the caller's code is data dropped into a file, never
# spliced into this scaffolding, and the scaffolding is the only thing that
# decides how results come back.
_REMOTE_RUNNER = r'''
import json, os, pathlib, subprocess, sys, traceback

def main(code, input_files, output_files):
    work = pathlib.Path("/work"); work.mkdir(exist_ok=True); os.chdir(work)
    for name, data in (input_files or {}).items():
        (work / name).write_bytes(data)
    (work / "job.py").write_text(code)
    proc = subprocess.run([sys.executable, "job.py"], capture_output=True, text=True)
    metrics = {}
    result_path = work / "result.json"
    if result_path.is_file():
        try:
            loaded = json.loads(result_path.read_text())
            if isinstance(loaded, dict) and isinstance(loaded.get("metrics"), dict):
                metrics = loaded["metrics"]
        except ValueError:
            pass
    artifacts = {}
    for name in output_files or []:
        p = work / name
        if p.is_file():
            artifacts[name] = p.read_bytes()
    return {"returncode": proc.returncode, "metrics": metrics,
            "artifacts": artifacts,
            "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:]}
'''


def _dispatch_modal(clean: dict) -> dict:
    """Run one job on Modal and return the raw runner result. Every failure to
    REACH Modal raises RemoteJobUnavailable; a job that runs and fails returns
    normally with a non-zero returncode, because those are different facts."""
    try:
        import modal
    except ImportError as e:  # pragma: no cover - exercised by the seam in tests
        raise RemoteJobUnavailable(
            "the modal client is not installed (venv/bin/pip install modal)") from e

    # The remote interpreter MUST match this process's, because the entry point
    # is shipped as a serialized closure and Modal refuses a version mismatch
    # ("a serialized Function must be de-serialized by the same Python"). Read
    # from sys rather than pinned: a pin here silently rots the day the venv's
    # Python moves, and the failure surfaces as a confusing remote error rather
    # than as the local fact it is.
    image = modal.Image.debian_slim(
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}")
    if clean["apt"]:
        image = image.apt_install(*clean["apt"])
    if clean["pip"]:
        image = image.pip_install(*clean["pip"])

    app = modal.App(clean["app_name"])
    fn = app.function(image=image, gpu=clean["gpu"], timeout=clean["timeout_s"],
                      serialized=True)(_make_remote_entry())
    try:
        with app.run():
            return fn.remote(clean["code"], clean["input_files"],
                             clean["output_files"])
    except Exception as e:  # noqa: BLE001 — auth/transport/quota all land here
        raise RemoteJobUnavailable(f"{type(e).__name__}: {e}") from e


def _make_remote_entry():
    """Build the function object Modal ships to the remote container. The runner
    source is exec'd into a fresh namespace so the shipped closure carries the
    template and nothing else from this process."""
    namespace: dict = {}
    exec(_REMOTE_RUNNER, namespace)
    return namespace["main"]


def run_remote_job(spec: dict, *, dispatch=None) -> dict:
    """Run one job on rented hardware and hand back what it produced.

    `dispatch` is the injection seam: production dispatches to Modal; the
    offline suite injects a fake so every outcome is provable without an
    account, a token, or a bill.

    NOTE THE RETURN SHAPE: metrics and artifacts, and deliberately NO `qoi`.
    Every other wrapper in this project returns a qoi because every other
    wrapper feeds a claim. This one does not feed claims (R-REMOTE-1).
    """
    wall_start = time.time()

    def done(valid, metrics, artifacts, msg):
        return {"valid": valid, "metrics": metrics or {}, "artifacts": artifacts or {},
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except RemoteJobInputError as e:
        return done(False, {}, {}, f"input rejected: {e}")

    runner = dispatch or _dispatch_modal
    try:
        result = runner(clean)
    except RemoteJobUnavailable as e:
        return done(False, {}, {}, (
            f"setup_error: the remote backend could not be reached ({e}) — this "
            "job could not run. Authenticate once with `modal token new`; no "
            "result was fabricated"))

    if not isinstance(result, dict):
        return done(False, {}, {}, (
            f"the remote runner returned {type(result).__name__}, not a result "
            "object — nothing can be read from it"))

    artifacts = {}
    for name, data in (result.get("artifacts") or {}).items():
        if isinstance(data, (bytes, bytearray)) and len(data) <= MAX_ARTIFACT_BYTES:
            artifacts[name] = bytes(data)

    missing = [n for n in clean["output_files"] if n not in artifacts]
    returncode = result.get("returncode")

    if returncode != 0:
        stderr = (result.get("stderr") or "").strip().splitlines()
        tail = stderr[-1] if stderr else "no stderr"
        return done(False, result.get("metrics"), artifacts, (
            f"the remote job exited {returncode} — any metrics it wrote are not "
            f"trustworthy. stderr tail: {tail}"))

    if missing:
        return done(False, result.get("metrics"), artifacts, (
            f"the job completed but did not write declared output file(s): "
            f"{', '.join(missing)}"))

    metrics = result.get("metrics") or {}
    gpu = clean["gpu"] or "cpu"
    return done(True, metrics, artifacts, (
        f"remote job completed on {gpu}; {len(metrics)} metric(s), "
        f"{len(artifacts)} file(s) returned. {_NOT_A_CLAIM_NOTE}"))
