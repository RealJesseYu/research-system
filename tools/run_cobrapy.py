"""
run_cobrapy — the production COBRApy (flux-balance analysis) wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_ngspice.py / run_rdkit.py hold. BIO Wave D.2, T1. At build time
UNREGISTERED and INERT: enrolls `calibrating` / `routable=False`; nothing
routes to it until a D.4 promotion ruling. (Truthful prose provenance; enters
no composed prompt.)

Shape mirrors run_rdkit:
  * a typed input becomes a small job (input.json + a fixed driver) by
    deterministic Python — no LLM anywhere in the execution step;
  * the job runs inside the `cobrapy-prod` container (bind-mounted
    cases_cobrapy/), with a hard timeout and ONE retry on a transient failure;
  * the models (e_coli_core, iML1515) are BAKED into the image at /opt/models/
    and loaded from local disk — no runtime network, so the LP is fully
    deterministic; the raw model never leaves the wrapper.

REGIME (card unit = (cobrapy, fba_steady_state)). Constraint-based flux-balance
analysis: a deterministic linear program over a genome-scale metabolic model at
STEADY STATE. It is a `filter`-class substrate — the growth it reports is a
feasible steady-state optimum, a RELATIVE screen, not a measured in-vivo rate.

*** THE STRUCTURAL STATUS GATE (owner-ruled 2026-07-18) ***
COBRApy returns an `objective_value` EVEN WHEN the solve is infeasible (a stale
value from the previous solve). Reading it would fabricate a growth number for a
model that has no feasible steady state — the exact "a check that cannot fail is
not a proof" trap. So the QoI is gated on SOLVER STATUS, structurally: when the
status is not `optimal`, the driver does NOT surface `objective_value` at all
(it writes no value), so the wrapper CANNOT return one. Non-optimal status ->
qoi=None. This is a D-rule / trust criterion, not an advisory note.

Typed input:
    run_cobrapy({
      "model": "e_coli_core",       # one of the baked allowlist models
      "quantity": "growth_rate",    # the fixed-summary QoI (currently the one)
      "min_growth": 0.5,            # OPTIONAL biomass lower bound (feasibility
                                    # constraint); an unachievable value forces
                                    # an infeasible solve -> qoi=None
    })

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration (mirrors run_rdkit.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"
CONTAINER = "cobrapy-prod"
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_cobrapy"
SHARED_CONTAINER = "/work/cases"
MODELS_CONTAINER = "/opt/models"     # baked into cobrapy-img — no runtime network

TIMEOUT_SECONDS = 600
MAX_RETRIES = 1
MAX_DIAG_CHARS = 800


class CobrapyInputError(ValueError):
    """The typed input is not a runnable FBA request."""


# ----------------------------------------------------------------------------
# Typed input + the fixed vocabularies.
#   MODEL_ALLOWLIST : the baked models (single source for the model signature).
#   QOI_FIELDS      : the fixed_summary QoI vocab (imported by qoi_vocab at D.4).
# ----------------------------------------------------------------------------
_REQUIRED_FIELDS = ("model", "quantity")
_OPTIONAL_FIELDS = ("min_growth",)

MODEL_ALLOWLIST = ("e_coli_core", "iML1515")
QOI_FIELDS = ("growth_rate",)


def _validate_input(spec: dict) -> dict:
    """Return a clean copy of `spec`, or raise CobrapyInputError. Pure, pre-run."""
    if not isinstance(spec, dict):
        raise CobrapyInputError(f"spec must be a dict, got {type(spec).__name__}")

    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise CobrapyInputError(f"missing required field(s): {', '.join(missing)}")
    allowed = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
    extra = [k for k in spec if k not in allowed]
    if extra:
        raise CobrapyInputError(
            f"unsupported field(s) for cobrapy fba_steady_state: "
            f"{', '.join(sorted(extra))}")

    if spec["model"] not in MODEL_ALLOWLIST:
        raise CobrapyInputError(
            f"model {spec['model']!r} is not a baked allowlist model "
            f"(allowed: {', '.join(MODEL_ALLOWLIST)})")
    if spec["quantity"] not in QOI_FIELDS:
        raise CobrapyInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")

    min_growth = spec.get("min_growth")
    if min_growth is not None:
        try:
            min_growth = float(min_growth)
        except (TypeError, ValueError):
            raise CobrapyInputError(f"'min_growth' must be a number, got {min_growth!r}")
        if min_growth < 0:
            raise CobrapyInputError(f"'min_growth' must be >= 0, got {min_growth}")

    return {"model": spec["model"], "quantity": spec["quantity"],
            "min_growth": min_growth}


# ----------------------------------------------------------------------------
# The in-container driver. cobra is imported ONLY here (host venv stays clean).
# THE STATUS GATE lives here, structurally: when status != optimal it writes NO
# objective value, so the wrapper cannot surface a stale one.
# ----------------------------------------------------------------------------
_DRIVER = r'''
import json, math, sys
from pathlib import Path

job = Path(sys.argv[1])
spec = json.loads((job / "input.json").read_text())
out = job / "result.json"

def write(obj):
    out.write_text(json.dumps(obj))

try:
    import cobra.io
except Exception as e:  # pragma: no cover
    write({"ok": False, "error": "cobra import failed: %s" % e}); sys.exit(0)

try:
    m = cobra.io.read_sbml_model(spec["model_path"])
except Exception as e:
    write({"ok": False, "error": "model load failed: %s" % e}); sys.exit(0)

# Optional biomass lower-bound feasibility constraint. The objective is the
# model's default biomass reaction; constraining it below a value the network
# cannot support makes the solve INFEASIBLE.
if spec.get("min_growth") is not None:
    try:
        obj_rxns = [r for r in m.reactions if r.objective_coefficient != 0]
        if len(obj_rxns) != 1:
            write({"ok": False, "error":
                   "expected exactly one objective reaction, got %d" % len(obj_rxns)})
            sys.exit(0)
        obj_rxns[0].lower_bound = float(spec["min_growth"])
    except Exception as e:
        write({"ok": False, "error": "applying min_growth failed: %s" % e}); sys.exit(0)

sol = m.optimize()
status = sol.status

# THE STATUS GATE: only an `optimal` solve yields a number. On any other status
# the stale objective_value is NEVER surfaced -- there is no `values` key to read.
if status != "optimal":
    write({"ok": False, "status": status,
           "error": "solver status %r is not optimal -- no feasible steady state"
                    % status})
    sys.exit(0)

growth = float(sol.objective_value)
if not math.isfinite(growth):
    write({"ok": False, "status": status,
           "error": "objective is non-finite"}); sys.exit(0)

write({"ok": True, "status": status,
       "values": {"growth_rate": growth},
       "model_info": {"reactions": len(m.reactions),
                      "metabolites": len(m.metabolites)}})
'''


# ----------------------------------------------------------------------------
# Preflight — daemon AND container (mirrors run_rdkit).
# ----------------------------------------------------------------------------
def preflight() -> str | None:
    try:
        proc = subprocess.run(["docker", "--context", DOCKER_CONTEXT, "info"],
                              capture_output=True, text=True, timeout=60)
    except FileNotFoundError:
        return "docker CLI not found on PATH"
    except subprocess.TimeoutExpired:
        return "docker daemon did not respond within 60s (is colima up?)"
    if proc.returncode != 0:
        first = (proc.stderr.strip().splitlines() or ["docker info failed"])[0]
        return f"docker daemon unreachable on context {DOCKER_CONTEXT!r}: {first}"
    try:
        proc = subprocess.run(
            ["docker", "--context", DOCKER_CONTEXT, "inspect", "-f",
             "{{.State.Running}}", CONTAINER],
            capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return f"docker inspect {CONTAINER} timed out"
    if proc.returncode != 0:
        return f"container {CONTAINER!r} does not exist (create it from cobrapy-img)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


# ----------------------------------------------------------------------------
# Execution — sandboxed docker exec, hard timeout, one retry on transient fail.
# ----------------------------------------------------------------------------
def _run_driver(job: str) -> tuple[int, str]:
    job_dir = f"{SHARED_CONTAINER}/{job}"
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER,
           "python", f"{job_dir}/driver.py", job_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    return proc.returncode, proc.stderr.strip()


def _is_transient(returncode: int, infra_stderr: str, result_exists: bool) -> bool:
    if result_exists:
        return False
    low = infra_stderr.lower()
    if infra_stderr and ("docker" in low or "cannot" in low
                         or "error response" in low or "is not running" in low):
        return True
    return returncode != 0 and not result_exists


def run_cobrapy(spec: dict) -> dict:
    """Run one FBA and return the small dict documented at the top of this
    module. The growth QoI is returned ONLY on an `optimal` solve — a
    non-optimal status returns valid=False, qoi=None, never a stale number."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except CobrapyInputError as e:
        return fail(f"input rejected: {e}")

    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    job = f"cobrapy_{int(wall_start * 1000)}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(json.dumps({
        "model_path": f"{MODELS_CONTAINER}/{clean['model']}.xml",
        "min_growth": clean["min_growth"],
    }))
    (case_dir / "driver.py").write_text(_DRIVER)
    result_path = case_dir / "result.json"

    returncode, infra_stderr = -1, ""
    for attempt in range(MAX_RETRIES + 1):
        if result_path.exists():
            result_path.unlink()
        try:
            returncode, infra_stderr = _run_driver(job)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"cobrapy driver exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        result_exists = result_path.is_file()
        if not result_exists and _is_transient(returncode, infra_stderr, result_exists) \
                and attempt < MAX_RETRIES:
            continue
        break

    if not result_path.is_file():
        return fail(f"cobrapy driver produced no result (exit {returncode}): "
                    f"{infra_stderr.splitlines()[0] if infra_stderr else 'no stderr'}")
    try:
        result = json.loads(result_path.read_text())
    except (ValueError, OSError) as e:
        return fail(f"cobrapy result unreadable: {e}")

    # THE STATUS GATE, wrapper side: a non-ok result carries NO value to read.
    if not result.get("ok"):
        status = result.get("status", "?")
        return fail(f"FBA did not yield a trustworthy growth (status={status}): "
                    f"{result.get('error', 'unknown error')}")

    quantity = clean["quantity"]
    values = result.get("values", {})
    if quantity not in values:
        return fail(f"driver returned no value for {quantity!r}")
    value = values[quantity]
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return fail(f"extracted QoI {quantity!r} is not finite ({value!r}) — refusing to return it")

    info = result.get("model_info", {})
    diagnostics = (f"cobrapy FBA on {clean['model']} "
                   f"({info.get('reactions', '?')} reactions, "
                   f"{info.get('metabolites', '?')} metabolites); status=optimal; "
                   f"{quantity}={value:g}"
                   + (f"; min_growth={clean['min_growth']:g}"
                      if clean['min_growth'] is not None else ""))
    return {"valid": True, "qoi": float(value),
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


# CLI:  venv/bin/python3 tools/run_cobrapy.py     (runs the e_coli_core self-check)
if __name__ == "__main__":
    default = {"model": "e_coli_core", "quantity": "growth_rate"}
    print(json.dumps(run_cobrapy(default), indent=2))
