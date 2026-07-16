"""
run_fenicsx — the production FEniCSx/DOLFINx solver wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_cfd.py and run_fea.py hold for their solvers. This wrapper is
UNREGISTERED: nothing in stages/, the supervisor, substrates.py, or any schema
imports it. It is reachable by tests (and a __main__ CLI) only.

Shape mirrors run_fea (its sibling: same beam, same closed form, different
solver) — deliberately, so the two can be read side by side. It shares NO code
with run_fea: this file carries its OWN Euler-Bernoulli reference computed from
its OWN typed input, because the point of a second substrate is an INDEPENDENT
answer to the same question. An import would make agreement a tautology.

  * a typed input for ONE canonical family v1 — a linear-elastic cantilever
    beam — is turned into a mesh + solve by a fixed in-container script (no LLM
    anywhere in the execution step);
  * the solve runs inside the `dolfinx-prod` container (bind-mounted
    cases_fenicsx/, mirroring of12-prod / ccx-prod), hard timeout, ONE retry;
  * the solver's raw stdout/stderr is consumed HERE and reduced to a SMALL
    summary — the raw output NEVER leaves the wrapper.

FEniCS is two projects with one name. This wrapper is FEniCSx / DOLFINx ONLY
(`import dolfinx`). Legacy FEniCS (`from dolfin import *`, last released 2019)
does not run in this container; most cantilever tutorials on the open web are
legacy code and do not apply here. See the envelope card §1 (ruling G0).

Canonical family v1 — typed input:
    run_fenicsx({"length": 1.0, "width": 0.05, "height": 0.05,
                 "E": 210e9, "nu": 0.3, "tip_load": 1000.0,
                 "mesh_density": 8, "element_degree": 2})

Return (and ONLY this leaves the wrapper):
    {"valid": bool,
     "qoi": {"tip_displacement": float, "max_von_mises": float} | None,
     "diagnostics": str,        # bounded, human-readable; never the raw log
     "runtime_s": float}

Geometry convention (identical to the sibling FEA wrapper's, so the two are
comparable): X spans the length (beam clamped at x=0), Y the width, Z the
height and the load direction. The tip load is applied at x=length in the -Z
direction, so the analytic Euler-Bernoulli tip deflection is
delta = tip_load * length**3 / (3 * E * I), with I = width * height**3 / 12.

ELEMENT DEGREE IS A REGIME BOUNDARY, NOT AN IMPLEMENTATION DETAIL. DOLFINx has
no equivalent of CalculiX's C3D8I incompatible-modes hex. A fully-integrated
degree-1 Lagrange hex LOCKS in bending: it reports a far-too-stiff beam, and
mesh refinement does NOT rescue it. The validated path is degree >= 2. Degree 1
is ACCEPTED (never hard-rejected) and measured as a card fact — see the card's
ruling G5 and §3A/§3B. A degree-1 result being wrong is the element, not a bug
in this file.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — the only knobs, kept in one place (mirrors run_fea.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"           # same colima VM as the CFD/FEA substrates
CONTAINER = "dolfinx-prod"          # the FEniCSx production container
SHARED_HOST = Path("/Users/jesseyu/research-system/cases_fenicsx")  # Mac side
SHARED_CONTAINER = "/work/cases"    # same folder seen inside the container

TIMEOUT_SECONDS = 600               # hard cap so a stuck solver can't hang us
MAX_RETRIES = 1                     # ONE retry on a transient (infra) failure
MAX_DIAG_CHARS = 800                # bound on how much diagnostic text we return

# The in-container solve script. It is COPIED INTO EACH CASE DIR at run time
# rather than mounted, so a case dir is self-contained evidence — the input AND
# the exact script that consumed it, mirroring how run_fea.py writes its whole
# deck into the case dir. (An earlier read-only mount of tools/fenicsx_env/ was
# abandoned: this repo is checked out as several parallel git worktrees, so a
# mount of one tree's tools/ could serve a DIFFERENT branch's script than the
# wrapper doing the calling. Copying from Path(__file__) is unambiguous.)
SOLVE_SCRIPT_SRC = Path(__file__).parent / "fenicsx_env" / "solve_cantilever.py"
SOLVE_SCRIPT_NAME = "solve_cantilever.py"
RESULT_SENTINEL = "FENICSX_RESULT "  # must match solve_cantilever.py
ELEMENT_FAMILY = "Lagrange"         # degree comes from typed input, never fixed

# Docs-RAG index for the DOLFINx documentation — a SEPARATE index from
# solver_docs / fea_docs, mirroring their layout under retrieval/.
_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
FENICSX_DOCS_INDEX = _RETRIEVAL_DIR / "fenicsx_docs_index.pkl"


# ----------------------------------------------------------------------------
# Typed input for family v1.
# ----------------------------------------------------------------------------
# The seven shared fields carry the SAME units and semantics as the sibling FEA
# family v1 (see docs/envelope_card_calculix_cantilever.md §6). element_degree
# is the one field this family adds.
_REQUIRED_FIELDS = ("length", "width", "height", "E", "nu", "tip_load",
                    "mesh_density", "element_degree")


class FenicsxInputError(ValueError):
    """The typed input is not a buildable fenicsx-cantilever-v1 config."""


def _validate_input(spec: dict) -> dict:
    """Return a clean float/int copy of `spec`, or raise FenicsxInputError."""
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise FenicsxInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise FenicsxInputError(
            f"unsupported field(s) for fenicsx cantilever v1: {', '.join(sorted(extra))}"
        )

    out = {}
    for k in ("length", "width", "height", "E", "nu", "tip_load"):
        try:
            out[k] = float(spec[k])
        except (TypeError, ValueError):
            raise FenicsxInputError(f"field {k!r} must be a number, got {spec[k]!r}")
    for k in ("mesh_density", "element_degree"):
        try:
            out[k] = int(spec[k])
        except (TypeError, ValueError):
            raise FenicsxInputError(f"{k} must be an integer, got {spec[k]!r}")

    for k in ("length", "width", "height", "E", "tip_load"):
        if out[k] <= 0:
            raise FenicsxInputError(f"field {k!r} must be positive, got {out[k]}")
    if not (-1.0 < out["nu"] < 0.5):
        raise FenicsxInputError(f"nu must be in (-1, 0.5), got {out['nu']}")
    if out["mesh_density"] < 1:
        raise FenicsxInputError(f"mesh_density must be >= 1, got {out['mesh_density']}")
    # element_degree >= 1 is the TYPED bound: degree 0 is not a displacement
    # element at all. Degree 1 is ACCEPTED here and locks in bending — that is
    # a REGIME judgment recorded on the card (G5), NOT a wrapper rejection.
    if out["element_degree"] < 1:
        raise FenicsxInputError(
            f"element_degree must be >= 1, got {out['element_degree']}"
        )
    return out


# ----------------------------------------------------------------------------
# Deterministic mesh sizing. No LLM, no randomness.
# ----------------------------------------------------------------------------

def _mesh_counts(spec: dict) -> tuple[int, int, int]:
    """Element counts (nx, ny, nz). mesh_density sets nx; ny/nz scale by aspect
    ratio so a refinement study (larger mesh_density) refines every direction.

    This rule is a deliberate MIRROR of run_fea.py's `_mesh_counts` (read from
    disk, not remembered), so the two substrates' refinement ladders line up
    rung for rung: on the reference beam 8 -> 8x1x1, 16 -> 16x1x1, 32 -> 32x2x2.
    """
    L, W, H, md = spec["length"], spec["width"], spec["height"], spec["mesh_density"]
    nx = md
    ny = max(1, round(md * W / L))
    nz = max(1, round(md * H / L))
    return nx, ny, nz


def analytic_tip_deflection(spec: dict) -> float:
    """Euler-Bernoulli tip deflection delta = P L^3 / (3 E I), I = w h^3 / 12.

    THIS WRAPPER'S OWN COPY, computed from its own typed input — deliberately
    NOT imported from the sibling FEA wrapper. Two substrates agreeing with one
    shared helper proves only that the helper is a function; agreeing through
    independent copies is evidence.
    """
    spec = _validate_input(spec)
    I = spec["width"] * spec["height"] ** 3 / 12.0
    return spec["tip_load"] * spec["length"] ** 3 / (3.0 * spec["E"] * I)


def slenderness(spec: dict) -> float:
    """L/h — the ratio the card's G1 bound reads. Reported, never enforced here:
    the wrapper has NO regime check (card §5)."""
    spec = _validate_input(spec)
    return spec["length"] / spec["height"]


# ----------------------------------------------------------------------------
# Output parsing — pure function, unit-tested. The raw solver stdout is
# consumed HERE and only the small numbers leave.
# ----------------------------------------------------------------------------

def parse_solver_output(stdout: str) -> dict:
    """Reduce the solve script's raw stdout to its ONE sentinel JSON payload.

    DOLFINx/PETSc print freely to stdout; exactly one line carries the result.
    Raises ValueError when the sentinel is missing, unparseable, duplicated, or
    reports ok=false — the wrapper turns that into valid=False rather than
    fabricating a number.
    """
    lines = [ln for ln in stdout.splitlines() if ln.startswith(RESULT_SENTINEL)]
    if not lines:
        raise ValueError("solver produced no result line")
    if len(lines) > 1:
        raise ValueError(f"solver produced {len(lines)} result lines, expected 1")
    try:
        payload = json.loads(lines[0][len(RESULT_SENTINEL):])
    except json.JSONDecodeError as e:
        raise ValueError(f"result line was not valid JSON: {e}")

    if not payload.get("ok"):
        raise ValueError(f"solver reported failure: {payload.get('error', 'no reason given')}")
    for key in ("tip_displacement", "max_von_mises"):
        if key not in payload:
            raise ValueError(f"result line is missing {key!r}")
        if not isinstance(payload[key], (int, float)):
            raise ValueError(f"{key} is not a number: {payload[key]!r}")
    return payload


# ----------------------------------------------------------------------------
# Execution — sandboxed docker exec, hard timeout, one retry on transient fail.
# ----------------------------------------------------------------------------

def _run_solver(job: str) -> tuple[int, str, str]:
    """Run the fixed solve script inside the container on one case dir.

    Returns (returncode, stdout, stderr). Raises subprocess.TimeoutExpired on
    the hard timeout so the caller can classify it as transient and retry once.
    """
    case = f"{SHARED_CONTAINER}/{job}"
    remote = f"python3 {case}/{SOLVE_SCRIPT_NAME} {case}/input.json"
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    return proc.returncode, proc.stdout, proc.stderr


def preflight() -> str:
    """Check the solver substrate is actually reachable, and say WHY if not.

    Daemon up != container up: colima can be running with `dolfinx-prod` gone
    (or exited). BOTH are checked, and each failure names itself. Returns "" when
    the substrate is ready, else a named reason.
    """
    try:
        proc = subprocess.run(
            ["docker", "--context", DOCKER_CONTEXT, "ps", "--filter",
             f"name={CONTAINER}", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"docker daemon unreachable on context {DOCKER_CONTEXT!r}: {type(e).__name__}"
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["no stderr"])[0]
        return f"docker daemon unreachable on context {DOCKER_CONTEXT!r}: {first}"
    if CONTAINER not in proc.stdout.split():
        return (f"docker daemon is up but container {CONTAINER!r} is not running "
                f"(start it: see tools/fenicsx_env/README.md)")
    return ""


def _is_transient(returncode: int, stderr: str, got_result: bool) -> bool:
    """A failure is transient (worth one retry) when it looks like infrastructure
    rather than a bad case: no result line produced and a docker/exec-level
    stderr, or a nonzero exit with no solver result at all.

    Mirrors run_fea._is_transient's structure and its intent."""
    if got_result:
        return False
    if stderr and ("docker" in stderr.lower() or "cannot" in stderr.lower()
                   or "Error response" in stderr):
        return True
    return returncode != 0 and not got_result


def run_fenicsx(spec: dict) -> dict:
    """Build, run, and summarize one fenicsx-cantilever-v1 case. Returns the
    small dict documented at the top of this module — and nothing else leaves
    the wrapper.
    """
    wall_start = time.time()

    def _fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    # --- validate the typed input (deterministic, no solver) ---------------
    try:
        clean = _validate_input(spec)
    except FenicsxInputError as e:
        return _fail(f"input rejected: {e}")

    # --- preflight: daemon AND container, named reason on failure ----------
    reason = preflight()
    if reason:
        return _fail(f"solver substrate unavailable: {reason}")

    nx, ny, nz = _mesh_counts(clean)
    job = f"cantilever_md{clean['mesh_density']}_p{clean['element_degree']}_{int(wall_start * 1000)}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    payload = {**clean, "nx": nx, "ny": ny, "nz": nz}
    (case_dir / "input.json").write_text(json.dumps(payload, indent=2, sort_keys=True))
    # The case dir carries the exact script that will consume the input, so the
    # pair is self-contained evidence and cannot be served a different branch's
    # solver by a stale mount.
    try:
        (case_dir / SOLVE_SCRIPT_NAME).write_text(SOLVE_SCRIPT_SRC.read_text())
    except OSError as e:
        return _fail(f"could not stage the solve script into the case dir: {e}")

    # --- run, with one retry on a transient failure ------------------------
    result = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            returncode, stdout, stderr = _run_solver(job)
        except subprocess.TimeoutExpired:
            # KNOWN WATCH (mirrors run_fea): the host-side timeout kills the
            # `docker exec` client, NOT necessarily the solver process inside
            # the container, which may keep running as an orphan. Neither
            # wrapper reaps it today; recorded on the card §8 rather than
            # silently pretended away.
            if attempt < MAX_RETRIES:
                continue
            return _fail(f"solver exceeded {TIMEOUT_SECONDS}s timeout and was killed")

        try:
            result = parse_solver_output(stdout)
            break
        except ValueError as e:
            got_result = RESULT_SENTINEL in stdout
            if _is_transient(returncode, stderr, got_result) and attempt < MAX_RETRIES:
                result = None
                continue
            return _fail(_failure_diagnostic(e, returncode, stderr))

    if result is None:
        return _fail("solver produced no usable result after retry")

    qoi = {"tip_displacement": result["tip_displacement"],
           "max_von_mises": result["max_von_mises"]}
    diagnostics = (
        f"dolfinx {result.get('dolfinx_version', '?')} "
        f"{ELEMENT_FAMILY} degree {clean['element_degree']} "
        f"hex mesh {nx}x{ny}x{nz} ({result.get('num_cells', '?')} cells, "
        f"{result.get('num_dofs', '?')} dofs); scalar={result.get('scalar_type', '?')}; "
        f"von Mises interpolated into {result.get('vm_space', '?')}; "
        f"solve {result.get('solve_seconds', '?')}s"
    )
    return {"valid": True, "qoi": qoi,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


_TRACEBACK_NOISE_RE = re.compile(r"^\s*(File \"|\s+\^|Traceback)")


def _failure_diagnostic(err: ValueError, returncode: int, stderr: str) -> str:
    """A bounded, honest failure line — never the whole solver log."""
    detail = str(err)
    if stderr:
        tail = [ln.strip() for ln in stderr.splitlines()
                if ln.strip() and not _TRACEBACK_NOISE_RE.match(ln)]
        if tail:
            detail += f" | stderr: {tail[-1]}"
    return f"solver failed (exit {returncode}): {detail}"


# ----------------------------------------------------------------------------
# Docs RAG — search the DOLFINx docs index (separate from solver_docs/fea_docs).
# ----------------------------------------------------------------------------

def search_fenicsx_docs(query: str, top_k: int = 3) -> list[dict]:
    """Search the DOLFINx-docs TF-IDF index. Mirrors run_fea.search_fea_docs but
    points at the separate fenicsx_docs index. Offline, deterministic, no API."""
    import sys
    if str(_RETRIEVAL_DIR) not in sys.path:
        sys.path.insert(0, str(_RETRIEVAL_DIR))
    from tfidf_core import search  # noqa: E402  (retrieval/ helper, path-injected)

    if not FENICSX_DOCS_INDEX.exists():
        raise FileNotFoundError(
            "fenicsx_docs index not built yet — run "
            "venv/bin/python3 retrieval/build_fenicsx_docs_index.py"
        )
    return search(FENICSX_DOCS_INDEX, query, top_k=top_k)


# CLI:  venv/bin/python3 tools/run_fenicsx.py      (runs the default cantilever)
if __name__ == "__main__":
    default = {"length": 1.0, "width": 0.05, "height": 0.05,
               "E": 210e9, "nu": 0.3, "tip_load": 1000.0,
               "mesh_density": 8, "element_degree": 2}
    result = run_fenicsx(default)
    result["analytic_tip_deflection"] = analytic_tip_deflection(default)
    print(json.dumps(result, indent=2))
