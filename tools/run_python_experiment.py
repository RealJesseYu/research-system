"""
run_python_experiment — the production code-execution wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_rdkit.py / run_cobrapy.py / run_ngspice.py hold. At build time
UNREGISTERED and INERT: nothing routes here until an enrollment ruling, exactly
as every bio substrate began.

WHY THIS EXISTS. Every stage in this system is a Claude Code agent with
allowed_tools=[] and Bash disallowed (model_call.py) — deliberately, because
the architecture requires a deterministic supervisor, typed batons, and tool
output summarized at the wrapper before any agent sees it. The consequence is
that no stage can write and run code as an experiment, which is precisely the
class of experiment a software/ML paper needs and precisely what agent systems
with a shell do natively.

This wrapper closes that gap WITHOUT handing any agent a shell. Model-authored
code arrives as a TYPED INPUT, like a SMILES string or a netlist; deterministic
Python runs it in an ephemeral, no-network container and returns the same small
bounded summary every other substrate returns. The agent never touches Bash,
the supervisor stays model-free, raw stdout never reaches a context, and the
run is reproducible from the recorded input. Every invariant holds.

REGIME (card unit = (python_experiment, code_execution)). A computational
experiment: caller-authored Python, executed once, reporting named scalar
metrics. It is a `direct`-class substrate — it measures exactly what the code
computes, so its fidelity is the fidelity of the code, not of a physical model.
It can support an ML/algorithms paper the way a solver supports a physics one.

*** THE STRUCTURAL METRIC GATE ***
The script does NOT report its result on stdout. Stdout is for humans and is
truncated to diagnostics; a number parsed out of prose would be a number the
wrapper invented a convention for. Instead the script MUST write a JSON object
{"metrics": {"<name>": <number>, ...}} to RESULT_PATH. The wrapper reads the
requested `quantity` from that file or returns qoi=None with an honest
diagnostic. A script that crashes, times out, writes nothing, writes malformed
JSON, or omits the requested metric CANNOT produce a number — mirroring
run_cobrapy's solver-status gate, and for the same reason: a check that cannot
fail is not a proof.

Typed input:
    run_python_experiment({
      "code": "import numpy as np ...",   # the experiment, authored upstream
      "quantity": "final_loss",           # which metric in the result file
      "timeout_s": 300,                   # OPTIONAL, bounded by the profile's max
      "profile": "heavy",                 # OPTIONAL sandbox profile (PROFILES);
    })                                    #   resource geometry only — the jail
                                          #   flags are invariant across profiles

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float,
     "metrics": dict}   # every metric the script reported, for evidence
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration (mirrors run_rdkit.py / run_cobrapy.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"
IMAGE = "code-img:latest"          # numpy / scipy / sklearn / pandas
# The atomistic shelf: ASE / PySCF / OpenMM / pymatgen / RDKit + numpy / scipy.
# Built from tools/atomistic_env/ (see the PROFILES table below).
ATOMISTIC_IMAGE = "atomistic-img:latest"
# The bio-design shelf: ProteinMPNN on CPU torch, weights baked in (the sandbox
# has no network). Built from tools/biodesign_env/.
BIODESIGN_IMAGE = "biodesign-img:latest"
# The engineering shelf: CadQuery/build123d (geometry), CoolProp (thermofluid
# properties), MuJoCo (multibody dynamics), scikit-rf (RF networks), plus
# iverilog/verilator (digital logic) as system tools. Built from
# tools/engineering_env/.
ENGINEERING_IMAGE = "engineering-img:latest"
# Scratch lives under the project root, NOT the system temp dir: colima shares
# the home tree over virtiofs and cannot see /var/folders, so a tempfile-backed
# bind mount arrives in the container empty. Same reason every other wrapper
# puts its cases_* directory here.
SCRATCH_ROOT = Path(__file__).resolve().parent.parent / "cases_python"
WORKDIR_CONTAINER = "/work"
SCRIPT_NAME = "experiment.py"
RESULT_NAME = "result.json"
RESULT_PATH = f"{WORKDIR_CONTAINER}/{RESULT_NAME}"

# A string result is a hash, an identifier or a short categorical
# outcome — never a document. Bounded so a metric cannot become a
# channel for returning a transcript from the sandbox.
MAX_STRING_QOI = 256

DEFAULT_TIMEOUT_SECONDS = 300
MAX_TIMEOUT_SECONDS = 1800
MAX_DIAG_CHARS = 800

# --- Sandbox profiles (docs/memo_heavy_verification_lane.md) -----------------
# A profile is the RESOURCE GEOMETRY of one run: image, timeout bounds, memory,
# cpus. It travels with the artifact that declares it, so a verification re-run
# executes under the same recorded conditions every time. Profiles deliberately
# CANNOT touch the jail: --network=none, --read-only, --pids-limit and the
# tmpfs live in _INVARIANT_RUN_FLAGS below, outside this table — no profile
# can express a weakening. "default" is byte-identical to the pre-profile
# behavior; "heavy" is the lane for ONE genuinely expensive evaluation (the
# search-outside/verify-winner design means the sandbox never re-runs a
# search). Heavy's numbers are sized to the colima VM (8 GiB / 4 cpus): 6 GB
# leaves daemon headroom, 3600 s is the honest ceiling for verify-every-claim
# on this machine. Same image on purpose — a bigger image is built as a pinned
# SIBLING (the scipy-img precedent) when a run actually needs it, and only this
# table's image field changes.
DEFAULT_PROFILE = "default"
PROFILES = {
    "default": {
        "image": IMAGE,
        "default_timeout_s": DEFAULT_TIMEOUT_SECONDS,
        "max_timeout_s": MAX_TIMEOUT_SECONDS,
        "memory_mb": 4096,
        "cpus": 2,
    },
    "heavy": {
        "image": IMAGE,
        "default_timeout_s": 1800,
        "max_timeout_s": 3600,
        "memory_mb": 6144,
        "cpus": 4,
    },
    # THE SIBLING IMAGE THIS TABLE'S COMMENT ANTICIPATED (2026-07-27,
    # docs/memo_atomistic_lane.md). Same jail, same runner, same result
    # contract — a different shelf of libraries: ASE, PySCF, OpenMM, pymatgen,
    # RDKit (tools/atomistic_env/). It closes the project's largest scientific
    # gap: the system could look up what is known about a molecule or a
    # material and could not COMPUTE anything about one.
    #
    # A profile is now (shelf x geometry), so both geometries are offered
    # against the new shelf: an ordinary check, and one genuinely expensive
    # evaluation. Nothing about the jail moves — --network=none, --read-only,
    # --pids-limit and the tmpfs are invariant flags outside this table, so no
    # entry here can express a weakening, and an atomistic result verifies by
    # the same re-run as any other code artifact.
    "atomistic": {
        "image": ATOMISTIC_IMAGE,
        "default_timeout_s": DEFAULT_TIMEOUT_SECONDS,
        "max_timeout_s": MAX_TIMEOUT_SECONDS,
        "memory_mb": 4096,
        "cpus": 2,
    },
    "atomistic-heavy": {
        "image": ATOMISTIC_IMAGE,
        "default_timeout_s": 1800,
        "max_timeout_s": 3600,
        "memory_mb": 6144,
        "cpus": 4,
    },
    # The bio-design shelf (2026-07-27, docs/memo_biodesign_lane.md):
    # ProteinMPNN on CPU torch with the weights BAKED IN, because the sandbox
    # has no network and a tool whose weights download at runtime cannot run
    # there. Corrects a defer whose stated reason ("needs a GPU") was wrong —
    # ProteinMPNN is ~1.7M parameters and designs a small protein in about a
    # second on CPU. Same jail, same runner, same verification as every other
    # shelf; a design run reproduces under a fixed seed.
    "biodesign": {
        "image": BIODESIGN_IMAGE,
        "default_timeout_s": DEFAULT_TIMEOUT_SECONDS,
        "max_timeout_s": MAX_TIMEOUT_SECONDS,
        "memory_mb": 4096,
        "cpus": 2,
    },
    "biodesign-heavy": {
        "image": BIODESIGN_IMAGE,
        "default_timeout_s": 1800,
        "max_timeout_s": 3600,
        "memory_mb": 6144,
        "cpus": 4,
    },
    # The engineering shelf (2026-07-27, docs/memo_engineering_lane.md):
    # geometry, thermofluid properties, multibody dynamics, RF networks and
    # digital logic. Mechanical and electrical were the two domains with almost
    # nothing — one narrow tool each and no geometry kernel at all, so the
    # instruction "if the goal asked you to design something, the thing is the
    # deliverable" had nothing behind it. Every tool here is deterministic, so
    # re-running IS the check (R-LANE-1) and none takes substrate ceremony.
    "engineering": {
        "image": ENGINEERING_IMAGE,
        "default_timeout_s": DEFAULT_TIMEOUT_SECONDS,
        "max_timeout_s": MAX_TIMEOUT_SECONDS,
        "memory_mb": 4096,
        "cpus": 2,
    },
    "engineering-heavy": {
        "image": ENGINEERING_IMAGE,
        "default_timeout_s": 1800,
        "max_timeout_s": 3600,
        "memory_mb": 6144,
        "cpus": 4,
    },
}
MAX_CODE_BYTES = 100_000
# Cap on a single captured/injected file artifact (Phase 4, R-ART-5). File
# hand-off between composition steps moves bytes host-side through the existing
# run-dir bind; a cap keeps one step from exhausting host memory. Small on
# purpose — the first brick passes modest files; raise it on evidence.
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024

# An ephemeral container per run: --rm so nothing persists between experiments
# (a stale artifact silently feeding the next run is the failure this prevents),
# --network none so a result can never depend on the internet, and hard resource
# caps so a runaway script cannot take the machine down with it.
# The jail set is taken from tools/run_code.py (Step 28.5), which hardened
# these against escape tests. This wrapper differs from that one in exactly one
# respect and it is the important one: run_code.py generates its runner from a
# FIXED TEMPLATE and states "it RUNS code, it never WRITES code" — no LLM may
# author what executes. This wrapper deliberately accepts MODEL-AUTHORED code,
# which is the whole point of the autonomy inversion, and therefore needs at
# least the jails the template-only path already carries.
#
# --read-only + a writable bind for the run dir only: the script may write its
# result and nothing else. --pids-limit bounds a fork bomb.
#
# These flags are INVARIANT across profiles by construction: a profile's dict
# holds only resource geometry (image / timeout bounds / memory / cpus), so no
# table entry can ever express "more network" or "writable rootfs".
PIDS_LIMIT = 256
TMPFS_MB = 512
_INVARIANT_RUN_FLAGS = [
    "--rm",
    "--network=none",
    f"--pids-limit={PIDS_LIMIT}",
    "--read-only",
    f"--tmpfs=/tmp:size={TMPFS_MB}m",
]


def _docker_run_flags(profile: dict) -> list:
    """The full flag set for one run: the invariant jail plus this profile's
    resource geometry. --memory-swap equal to --memory disables swap, so the
    memory cap is real rather than advisory."""
    mem = profile["memory_mb"]
    return [
        *_INVARIANT_RUN_FLAGS,
        f"--memory={mem}m", f"--memory-swap={mem}m",
        "--cpus", str(profile["cpus"]),
    ]


class PythonExperimentInputError(ValueError):
    """The typed input is not a runnable experiment."""


_REQUIRED_FIELDS = ("code", "quantity")
# input_files / output_files (Phase 4, R-ART-5): file-artifact hand-off between
# composition steps. input_files are written into the sandbox's run dir BEFORE
# the run (the script reads them from its working dir); output_files are the
# named files the wrapper captures back from that dir AFTER the run. Both move
# host-side through the EXISTING writable bind — the sandbox stays
# --network=none --read-only, reaching nothing new. Optional and default-absent:
# a call without them is byte-identical to before.
# profile (docs/memo_heavy_verification_lane.md): which sandbox profile runs
# this experiment. Optional and default-absent — a call without it is
# byte-identical to before. It is validated against PROFILES and RECORDED in
# the artifact that declares it, so a verification re-run executes under the
# same resource geometry every time.
_OPTIONAL_FIELDS = ("timeout_s", "input_files", "output_files", "profile")

# The harness preamble. Prepended to caller code so the script always has a
# sanctioned way to report metrics, and so `metrics` exists even if the code
# never assigns it. Deliberately tiny: anything larger becomes a hidden
# framework the authoring stage cannot see and would have to guess at.
def _preamble(timeout_s: int) -> str:
    """The harness preamble, parameterized by the caller's declared budget.

    The budget is enforced IN-CONTAINER with SIGALRM, not merely by the outer
    subprocess timeout. The outer timeout is a backstop for a wedged container;
    it necessarily carries docker-startup slack, and letting that slack define
    the budget meant a script declaring 2 s could run 30 and still be reported
    as a clean success. A declared budget the wrapper does not enforce is a
    lie told with a number in it.
    """
    return f'''import json as _json, atexit as _atexit, signal as _signal
metrics = {{}}
def _emit():
    try:
        with open({RESULT_PATH!r}, "w") as _f:
            _json.dump({{"metrics": metrics}}, _f)
    except Exception:
        pass
_atexit.register(_emit)
def _timeout(_sig, _frm):
    raise TimeoutError("experiment exceeded its declared {timeout_s} s budget")
_signal.signal(_signal.SIGALRM, _timeout)
_signal.alarm({timeout_s})
'''


def _validate_input(spec: dict) -> dict:
    """Return a clean copy of `spec`, or raise. Pure, pre-run."""
    if not isinstance(spec, dict):
        raise PythonExperimentInputError(
            f"spec must be a dict, got {type(spec).__name__}")

    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise PythonExperimentInputError(
            f"missing required field(s): {', '.join(missing)}")
    allowed = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
    extra = [k for k in spec if k not in allowed]
    if extra:
        raise PythonExperimentInputError(
            f"unsupported field(s) for python_experiment code_execution: "
            f"{', '.join(sorted(extra))}")

    code = spec["code"]
    if not isinstance(code, str) or not code.strip():
        raise PythonExperimentInputError("'code' must be a non-empty string")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise PythonExperimentInputError(
            f"'code' exceeds {MAX_CODE_BYTES} bytes")

    quantity = spec["quantity"]
    if not isinstance(quantity, str) or not quantity.strip():
        raise PythonExperimentInputError("'quantity' must be a non-empty string")

    profile_name = spec.get("profile", DEFAULT_PROFILE)
    if profile_name not in PROFILES:
        raise PythonExperimentInputError(
            f"'profile' must be one of {sorted(PROFILES)}, got {profile_name!r}")
    profile = PROFILES[profile_name]

    timeout = spec.get("timeout_s", profile["default_timeout_s"])
    try:
        timeout = int(timeout)
    except (TypeError, ValueError):
        raise PythonExperimentInputError(
            f"'timeout_s' must be an integer, got {timeout!r}")
    if not 1 <= timeout <= profile["max_timeout_s"]:
        raise PythonExperimentInputError(
            f"'timeout_s' must be between 1 and {profile['max_timeout_s']} "
            f"for profile {profile_name!r}, got {timeout}")

    # Phase 4 (R-ART-5): optional file-artifact I/O. Names are validated to be
    # bare filenames here, before anything is written into the run dir.
    input_files_raw = spec.get("input_files") or {}
    if not isinstance(input_files_raw, dict):
        raise PythonExperimentInputError("'input_files' must be a {name: bytes} object")
    input_files = {}
    for name, data in input_files_raw.items():
        safe = _safe_artifact_name(name)
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not isinstance(data, (bytes, bytearray)):
            raise PythonExperimentInputError(
                f"'input_files[{name!r}]' must be bytes or str, got {type(data).__name__}")
        if len(data) > MAX_ARTIFACT_BYTES:
            raise PythonExperimentInputError(
                f"'input_files[{name!r}]' is over the {MAX_ARTIFACT_BYTES}-byte cap")
        input_files[safe] = bytes(data)

    output_files_raw = spec.get("output_files") or []
    if not isinstance(output_files_raw, list):
        raise PythonExperimentInputError("'output_files' must be a list of filenames")
    output_files = [_safe_artifact_name(n) for n in output_files_raw]

    return {"code": code, "quantity": quantity.strip(), "timeout_s": timeout,
            "profile": profile_name,
            "input_files": input_files, "output_files": output_files}


def _clip(text: str) -> str:
    """Bound any text that leaves this wrapper. The full stdout NEVER leaves —
    the summarize-at-the-wrapper invariant, same as run_cfd's solver log."""
    text = (text or "").strip()
    if len(text) <= MAX_DIAG_CHARS:
        return text
    return text[:MAX_DIAG_CHARS] + f" [...truncated, {len(text)} chars total]"


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


_RESERVED_NAMES = frozenset({SCRIPT_NAME, RESULT_NAME})


def _safe_artifact_name(name) -> str:
    """A file-artifact name must be a BARE filename — no path separators, no
    '..', not absolute, and not one of the harness's own files. This is the
    guard against a recipe writing outside the run dir or clobbering the script
    / result file through the file channel."""
    if not isinstance(name, str) or not name.strip():
        raise PythonExperimentInputError("a file-artifact name must be a non-empty string")
    if name != Path(name).name or name in ("", ".", ".."):
        raise PythonExperimentInputError(
            f"file-artifact name {name!r} must be a bare filename (no path parts)")
    if name in _RESERVED_NAMES:
        raise PythonExperimentInputError(
            f"file-artifact name {name!r} is reserved by the harness")
    return name


def _capture_output_files(host_dir: Path, names) -> tuple[dict, str | None]:
    """Read the declared output files back from the run dir. Returns
    ({name: bytes}, error). A file that exceeds MAX_ARTIFACT_BYTES fails the
    whole run (an honest error, never a truncated artifact); a declared file
    that is simply absent is left out — the caller checks completeness."""
    captured: dict = {}
    for name in names:
        p = host_dir / name
        if not p.is_file():
            continue
        data = p.read_bytes()
        if len(data) > MAX_ARTIFACT_BYTES:
            return {}, (f"output file {name!r} is {len(data)} bytes, over the "
                        f"{MAX_ARTIFACT_BYTES}-byte artifact cap")
        captured[name] = data
    return captured, None


def run_python_experiment(spec: dict) -> dict:
    """Run one caller-authored computational experiment. Never raises for a
    failing experiment — a crash, a timeout, or a missing metric comes back as
    an honest valid=False summary with qoi=None, never a fabricated number.
    Only a malformed typed input raises (PythonExperimentInputError)."""
    clean = _validate_input(spec)
    started = time.monotonic()

    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=SCRATCH_ROOT) as tmp:
        host_dir = Path(tmp)
        (host_dir / SCRIPT_NAME).write_text(
            _preamble(clean["timeout_s"]) + clean["code"]
        )
        # R-ART-5: place any consumed artifacts in the run dir BEFORE the run,
        # so the script reads them from its working directory. Names were
        # validated to be bare filenames in _validate_input.
        for name, data in clean["input_files"].items():
            (host_dir / name).write_bytes(data)
        profile = PROFILES[clean["profile"]]
        cmd = [
            "docker", "--context", DOCKER_CONTEXT, "run",
            *_docker_run_flags(profile),
            "-v", f"{host_dir}:{WORKDIR_CONTAINER}",
            "-w", WORKDIR_CONTAINER,
            profile["image"], "python", f"{WORKDIR_CONTAINER}/{SCRIPT_NAME}",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                # Backstop only: the script enforces its own budget with
                # SIGALRM. This catches a container that never starts or
                # never exits, so it carries startup slack deliberately.
                timeout=clean["timeout_s"] + 60,
            )
        except subprocess.TimeoutExpired:
            return {
                "valid": False, "qoi": None, "metrics": {},
                "diagnostics": (
                    f"experiment exceeded its {clean['timeout_s']} s budget and was "
                    "killed; no metrics were read"
                ),
                "runtime_s": round(time.monotonic() - started, 3),
            }
        except (OSError, subprocess.SubprocessError) as e:
            return {
                "valid": False, "qoi": None, "metrics": {},
                "diagnostics": f"could not start the experiment container: {e}",
                "runtime_s": round(time.monotonic() - started, 3),
            }

        result_file = host_dir / RESULT_NAME
        raw = result_file.read_text() if result_file.is_file() else None
        # R-ART-5: capture declared output artifacts BEFORE the tempdir is
        # cleaned. Bytes are held in-memory for the composition orchestrator;
        # they never enter a baton or a model prompt (files off the baton).
        captured_artifacts, capture_error = _capture_output_files(
            host_dir, clean["output_files"])

    runtime = round(time.monotonic() - started, 3)
    tail = _clip((proc.stderr or proc.stdout or ""))

    if raw is None:
        return {
            "valid": False, "qoi": None, "metrics": {},
            "diagnostics": (
                f"the experiment wrote no result file (exit {proc.returncode}). "
                f"It must assign into the `metrics` dict. stderr: {tail}"
            ),
            "runtime_s": runtime,
        }
    try:
        payload = json.loads(raw)
        metrics = payload["metrics"]
        if not isinstance(metrics, dict):
            raise ValueError("'metrics' is not an object")
    except (ValueError, KeyError, TypeError) as e:
        return {
            "valid": False, "qoi": None, "metrics": {},
            "diagnostics": f"the experiment's result file was unreadable ({e}). stderr: {tail}",
            "runtime_s": runtime,
        }

    if proc.returncode != 0:
        # Metrics may still have been written by the atexit hook before the
        # crash. They are reported as evidence, but the QoI is withheld: a
        # number from a run that died is not a measurement.
        return {
            "valid": False, "qoi": None, "metrics": metrics,
            "diagnostics": (
                f"the experiment exited {proc.returncode} — any metrics it "
                f"wrote are not trustworthy. stderr: {tail}"
            ),
            "runtime_s": runtime,
        }

    quantity = clean["quantity"]
    if quantity not in metrics:
        return {
            "valid": False, "qoi": None, "metrics": metrics,
            "diagnostics": (
                f"the experiment ran cleanly but reported no metric named "
                f"{quantity!r} (reported: {', '.join(sorted(metrics)) or 'none'})"
            ),
            "runtime_s": runtime,
        }

    value = metrics[quantity]
    # A STRING METRIC IS ALLOWED and is compared exactly downstream (2026-07-27).
    # Found live: a run downloaded a real dataset and reported its SHA-256
    # beside the numeric statistic; the hash re-ran to the identical string and
    # was still refused here for not being a number, which made every hash,
    # identifier and categorical outcome permanently unverifiable. Bounded so a
    # "metric" cannot become a channel for smuggling a transcript out of the
    # sandbox — the summary is small by contract.
    if isinstance(value, str):
        if not value.strip():
            return {
                "valid": False, "qoi": None, "metrics": metrics,
                "diagnostics": f"metric {quantity!r} is an empty string; "
                               "no QoI is reported",
                "runtime_s": runtime,
            }
        if len(value) > MAX_STRING_QOI:
            return {
                "valid": False, "qoi": None, "metrics": metrics,
                "diagnostics": (
                    f"metric {quantity!r} is a string of {len(value)} chars, over "
                    f"the {MAX_STRING_QOI}-char limit; a result is a value, not a "
                    "document"
                ),
                "runtime_s": runtime,
            }
        return {
            "valid": True, "qoi": value, "metrics": metrics,
            "diagnostics": (
                f"experiment completed in {runtime} s; reported "
                f"{len(metrics)} metric(s); qoi {quantity}={value!r} (string)"
            ),
            "runtime_s": runtime,
        }
    if not _isnum(value) or not math.isfinite(value):
        return {
            "valid": False, "qoi": None, "metrics": metrics,
            "diagnostics": (
                f"metric {quantity!r} is not a finite number or a string "
                f"(got {value!r}); no QoI is reported"
            ),
            "runtime_s": runtime,
        }

    # An oversized artifact fails the run: a step that could not hand off its
    # file did not do what it declared, so no QoI is reported (R-ART-5).
    if capture_error is not None:
        return {
            "valid": False, "qoi": None, "metrics": metrics,
            "diagnostics": f"the experiment ran but {capture_error}",
            "runtime_s": runtime,
        }

    result = {
        "valid": True, "qoi": float(value), "metrics": metrics,
        "diagnostics": (
            f"experiment completed in {runtime} s; reported "
            f"{len(metrics)} metric(s); qoi {quantity}={value}"
        ),
        "runtime_s": runtime,
    }
    # Only present when artifacts were requested — a normal call is byte-identical.
    if clean["output_files"]:
        result["artifacts"] = captured_artifacts
    return result
