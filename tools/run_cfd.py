"""
run_cfd — the production solver wrapper (graduated, Step 11 chunk 1).

Plain, deterministic code. NO AI inside, no model calls, ever.

Provenance (prose only, no runtime reference): this file was copied from the
spike's proven run_cfd tool and adapted for production. The proven behaviors
survive unchanged: the case declares its own solver/endTime/deltaT via
system/controlDict (this tool never guesses); execution happens via docker
exec with the OpenFOAM bashrc sourced; solver output goes to log.<application>
inside the case dir; a 600 s hard timeout; the log is parsed down to a SMALL
summary with the exact converged definition (end time reached AND every
start-of-final-step residual < 1e-3); the full solver log is NEVER returned.

Production adaptations: container `of12-prod`; cases live under
~/research-system/cases (== /work/cases inside the container); and one new
OPTIONAL capability — QoI extraction (Step 11's minimal tier):

    run_cfd(case, qoi_request={"field": "U", "operation": "volAverage",
                               "component": "mag"})

Only after a run that reached its end time, the requested quantity is
extracted FROM WHAT THE CASE ALREADY WROTE (latest time directory), using
OpenFOAM's own stock post-processing machinery: the `postProcess` utility
with the parameterized volFieldValue configs shipped in
etc/caseDicts/functions/volFieldValue (volAverage / cellMin / cellMax /
volIntegrate), chained after the stock `mag` field function when
component="mag". postProcess writes
postProcessing/<funcName>/<time>/volFieldValue.dat inside the case; the last
data row of that file is parsed by deterministic Python. No new physics: no
solver changes, no new equations, no fields the case doesn't already have.
On success the summary gains qoi: {name, field, operation, value, time}; on
ANY extraction failure it gains qoi_error: "<honest reason>" and NO qoi
block. The instrument never fabricates a number.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration (the only "knobs" — kept in one place, no magic numbers buried
# in the code).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"          # the production engine (same colima VM)
CONTAINER = "of12-prod"            # the production container; never of12
SHARED_HOST = Path("/Users/jesseyu/research-system/cases")  # Mac side of the bind mount
SHARED_CONTAINER = "/work/cases"   # same folder seen from inside the container
OF_BASHRC = "/opt/openfoam12/etc/bashrc"  # sourcing this puts solvers on PATH

CONVERGENCE_TOL = 1e-3   # a run "converged" if every final residual is below this
TIMEOUT_SECONDS = 600    # hard cap so a stuck/runaway solver can't hang us forever
MAX_ERROR_LINES = 40     # bound on how many error lines we ever return

# QoI extraction: the only operations offered, each mapping to a stock
# parameterized function config under etc/caseDicts/functions/volFieldValue.
QOI_OPERATIONS = {
    "volAverage": "volAverage",
    "min": "cellMin",
    "max": "cellMax",
    "volIntegrate": "volIntegrate",
}
QOI_COMPONENTS = ("mag", 0, 1, 2)
# Field names are interpolated into a shell command line, so they are locked
# to plain identifier characters — anything else is refused, never quoted in.
_QOI_FIELD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.]*$")

# ----------------------------------------------------------------------------
# Regexes for reading the solver log. Locked to OpenFOAM v12's actual format,
# e.g.:   Time = 10s
#         smoothSolver:  Solving for Ux, Initial residual = 8.1e-05, Final ...
#         Courant Number mean: 0.12 max: 0.26
#         time step continuity errors : sum local = .., global = 1.2e-19, ..
#         ExecutionTime = 0.707 s  ClockTime = 1 s
# ----------------------------------------------------------------------------
_TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)s?\s*$")
_RESID_RE = re.compile(
    r"Solving for (\w+),\s*Initial residual = ([0-9.eE+-]+),\s*Final residual = ([0-9.eE+-]+)"
)
_COURANT_RE = re.compile(r"Courant Number mean: [0-9.eE+-]+ max: ([0-9.eE+-]+)")
_CONTINUITY_RE = re.compile(r"continuity errors : sum local = [0-9.eE+-]+, global = ([0-9.eE+-]+)")
_EXECTIME_RE = re.compile(r"ExecutionTime = ([0-9.eE+-]+) s")
_FATAL_RE = re.compile(r"FOAM FATAL (?:IO )?ERROR")


def _read_control_dict(case_host: Path) -> dict:
    """Pull `application`, `endTime`, `deltaT` out of system/controlDict."""
    cd = case_host / "system" / "controlDict"
    if not cd.is_file():
        raise FileNotFoundError(f"no system/controlDict in case '{case_host.name}'")
    text = cd.read_text()

    def grab(key):
        m = re.search(rf"^\s*{key}\s+([^;]+);", text, re.MULTILINE)
        return m.group(1).strip() if m else None

    app = grab("application")
    if not app:
        raise ValueError("controlDict has no `application` entry; cannot pick a solver")
    return {
        "application": app,
        "endTime": float(grab("endTime")) if grab("endTime") else None,
        "deltaT": float(grab("deltaT")) if grab("deltaT") else None,
    }


def _run_in_container(case_container: str, application: str) -> subprocess.CompletedProcess:
    """
    Run (optional) blockMesh + the solver inside of12-prod.

    We source the OpenFOAM env first because a `docker exec` shell does NOT load
    it automatically. Solver output goes to log.<application> in the case folder.
    The wrapper's exit code is the solver's exit code.
    """
    remote = f"""
        source {OF_BASHRC}
        cd {case_container} || exit 90
        if [ -f system/blockMeshDict ] && [ ! -f constant/polyMesh/points ]; then
            blockMesh > log.blockMesh 2>&1 || exit 91
        fi
        {application} > log.{application} 2>&1
        exit $?
    """
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)


def _parse_log(lines: list[str]) -> dict:
    """Walk the log once and pull out final residuals + key scalars + timing."""
    timesteps = []        # list of (time, {field: first Initial residual that step})
    current = None
    max_courant = None
    continuity_global = None
    exec_time = None

    for line in lines:
        mt = _TIME_RE.match(line.strip())
        if mt:
            current = {}
            timesteps.append((float(mt.group(1)), current))
            continue
        mr = _RESID_RE.search(line)
        if mr and current is not None:
            field = mr.group(1)
            if field not in current:            # keep the start-of-step value
                current[field] = float(mr.group(2))
        mc = _COURANT_RE.search(line)
        if mc:
            max_courant = float(mc.group(1))
        mk = _CONTINUITY_RE.search(line)
        if mk:
            continuity_global = float(mk.group(1))
        me = _EXECTIME_RE.search(line)
        if me:
            exec_time = float(me.group(1))

    final_time = timesteps[-1][0] if timesteps else None
    final_resids = timesteps[-1][1] if timesteps else {}
    return {
        "final_time": final_time,
        "residuals": final_resids,
        "max_courant": max_courant,
        "continuity_global": continuity_global,
        "exec_time": exec_time,
    }


def _extract_error_lines(lines: list[str]) -> list[str]:
    """Return ONLY the relevant error lines — never the whole log."""
    # Find a FOAM FATAL block and return from there to "FOAM exiting" (bounded).
    for i, line in enumerate(lines):
        if _FATAL_RE.search(line):
            block = []
            for line2 in lines[i:]:
                block.append(line2.rstrip())
                if "FOAM exiting" in line2 or len(block) >= MAX_ERROR_LINES:
                    break
            return [s for s in block if s.strip()]
    # No fatal marker: fall back to the last few non-empty lines (still bounded).
    tail = [s.rstrip() for s in lines if s.strip()][-15:]
    return tail


# ----------------------------------------------------------------------------
# QoI extraction (production-only, optional, minimal tier).
# ----------------------------------------------------------------------------

def parse_volfieldvalue_dat(text: str):
    """Parse a volFieldValue.dat written by OpenFOAM's postProcess. Pure function.

    The file is comment lines (starting '#') followed by data rows of
    "<time> <value>", where value is either a scalar ("6.4e-02") or a
    parenthesized vector ("(1.0e-02 -3.0e-03 0)"). Returns (time, value)
    from the LAST data row, value a float or a tuple of floats.
    Raises ValueError if no parseable data row exists.
    """
    data_lines = [
        ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")
    ]
    if not data_lines:
        raise ValueError("no data rows in volFieldValue output")
    parts = data_lines[-1].split(None, 1)
    if len(parts) != 2:
        raise ValueError(f"unparseable data row: {data_lines[-1]!r}")
    row_time = float(parts[0])
    raw = parts[1].strip()
    if raw.startswith("(") and raw.endswith(")"):
        return row_time, tuple(float(tok) for tok in raw[1:-1].split())
    return row_time, float(raw)


def _extract_qoi(case: str, qoi_request: dict) -> dict:
    """Extract one already-computed quantity from the case's latest time.

    Returns either {"qoi": {...}} or {"qoi_error": "<honest reason>"} —
    never both, never a fabricated number. Uses only OpenFOAM's stock
    postProcess machinery; the case's solver results are read, not re-run.
    """
    field = qoi_request.get("field")
    operation = qoi_request.get("operation")
    component = qoi_request.get("component")

    if not isinstance(field, str) or not _QOI_FIELD_RE.match(field):
        return {"qoi_error": f"invalid field name {field!r} — must be a plain OpenFOAM field identifier"}
    if operation not in QOI_OPERATIONS:
        return {"qoi_error": f"unknown operation {operation!r} — must be one of {sorted(QOI_OPERATIONS)}"}
    if component is not None and component not in QOI_COMPONENTS:
        return {"qoi_error": f"invalid component {component!r} — must be 'mag' or 0|1|2"}

    stock = QOI_OPERATIONS[operation]
    if component == "mag":
        target = f"mag({field})"
        funcs = f"(mag({field}) {stock}(mag({field})))"
    else:
        target = field
        funcs = f"({stock}({field}))"
    func_name = f"{stock}({target})"

    case_container = f"{SHARED_CONTAINER}/{case}"
    remote = (
        f"source {OF_BASHRC} && cd {case_container} && "
        f"postProcess -funcs '{funcs}' -latestTime > log.postProcess 2>&1"
    )
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"qoi_error": f"postProcess exceeded {TIMEOUT_SECONDS}s timeout and was killed"}
    if proc.returncode != 0:
        return {"qoi_error": f"postProcess failed (exit {proc.returncode}) — "
                             f"likely the case has no field {field!r} at its latest time"}

    dat_path = SHARED_HOST / case / "postProcessing" / func_name
    dat_files = sorted(dat_path.glob("*/volFieldValue.dat"))
    if not dat_files:
        return {"qoi_error": f"postProcess ran but wrote no volFieldValue output for {func_name}"}
    try:
        row_time, value = parse_volfieldvalue_dat(dat_files[-1].read_text(errors="replace"))
    except ValueError as e:
        return {"qoi_error": f"could not parse volFieldValue output: {e}"}

    if isinstance(value, tuple):
        if component in (0, 1, 2):
            value = value[component]
        else:
            return {"qoi_error": f"field {field!r} is not a scalar — "
                                 f"specify component 'mag' or 0|1|2 to reduce it"}
    elif component in (0, 1, 2):
        return {"qoi_error": f"component {component!r} requested but {target!r} is a scalar"}

    # The reported name must show a numeric component (Step-16 watch item:
    # 'cellMax(U)' hid that component 1 was taken, misleading downstream
    # judgment); func_name itself stays as postProcess writes it on disk.
    qoi_name = f"{func_name}[{component}]" if component in (0, 1, 2) else func_name
    return {"qoi": {"name": qoi_name, "field": field, "operation": operation,
                    "value": value, "time": row_time}}


def run_cfd(case: str, qoi_request: dict | None = None) -> dict:
    """
    Run an OpenFOAM case and return a SMALL summary dict.

    Success -> {status:"ok", converged, residuals, key_result, runtime, ...}
    Failure -> {status:"failed", converged:False, error_lines:[...], ...}
    With qoi_request: the success summary additionally carries either
    qoi:{name, field, operation, value, time} or qoi_error:"<reason>".
    """
    case_host = SHARED_HOST / case
    case_container = f"{SHARED_CONTAINER}/{case}"
    wall_start = time.time()

    # --- learn what to run -------------------------------------------------
    try:
        cfg = _read_control_dict(case_host)
    except (FileNotFoundError, ValueError) as e:
        return {"status": "failed", "case": case, "converged": False,
                "error_lines": [str(e)], "runtime": {"wall_clock_s": 0.0}}

    application = cfg["application"]

    # --- run it ------------------------------------------------------------
    try:
        proc = _run_in_container(case_container, application)
        returncode = proc.returncode
        infra_stderr = proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return {"status": "failed", "case": case, "solver": application,
                "converged": False,
                "error_lines": [f"solver exceeded {TIMEOUT_SECONDS}s timeout and was killed"],
                "runtime": {"wall_clock_s": round(time.time() - wall_start, 2)}}

    wall_clock = round(time.time() - wall_start, 2)

    # --- read the log we just produced ------------------------------------
    log_path = case_host / f"log.{application}"
    lines = log_path.read_text(errors="replace").splitlines() if log_path.is_file() else []

    fatal = any(_FATAL_RE.search(line) for line in lines)
    nonempty = [s for s in lines if s.strip()]   # OpenFOAM prints blank lines after "End"
    ended_cleanly = bool(nonempty) and nonempty[-1].strip() == "End"

    # --- failure path: return only the error lines ------------------------
    if returncode != 0 or fatal or not ended_cleanly:
        err = _extract_error_lines(lines) if lines else []
        if not err and infra_stderr:           # exec itself failed before any log
            err = infra_stderr.splitlines()[:MAX_ERROR_LINES]
        if not err:
            err = [f"solver exited with code {returncode} and produced no usable log"]
        summary = {"status": "failed", "case": case, "solver": application,
                   "converged": False, "error_lines": err,
                   "runtime": {"wall_clock_s": wall_clock}}
        if qoi_request is not None:
            summary["qoi_error"] = "run failed — QoI not extracted"
        return summary

    # --- success path: parse the small summary ----------------------------
    p = _parse_log(lines)
    end_time = cfg["endTime"]
    delta_t = cfg["deltaT"] or 0.0
    reached_end = (p["final_time"] is not None and end_time is not None
                   and abs(p["final_time"] - end_time) <= max(delta_t, 1e-9))
    resids_ok = bool(p["residuals"]) and all(v < CONVERGENCE_TOL for v in p["residuals"].values())
    converged = reached_end and resids_ok

    reason = (f"reached endTime={end_time} with all final residuals < {CONVERGENCE_TOL}"
              if converged else
              f"finished cleanly but {'did not reach endTime' if not reached_end else 'residuals above tolerance'}")

    summary = {
        "status": "ok",
        "case": case,
        "solver": application,
        "converged": converged,
        "reason": reason,
        "final_time": p["final_time"],
        "end_time": end_time,
        "residuals": {k: p["residuals"][k] for k in sorted(p["residuals"])},
        "key_result": {
            "max_Courant": p["max_courant"],
            "continuity_global": p["continuity_global"],
        },
        "runtime": {
            "solver_execution_time_s": p["exec_time"],
            "wall_clock_s": wall_clock,
        },
    }

    # --- optional QoI extraction (only from what the run already wrote) ---
    if qoi_request is not None:
        if reached_end:
            summary.update(_extract_qoi(case, qoi_request))
        else:
            summary["qoi_error"] = "run did not reach its end time — QoI not extracted"
    return summary


# Lets us test from the command line:  python tools/run_cfd.py cavity_baseline
if __name__ == "__main__":
    import sys
    case_arg = sys.argv[1] if len(sys.argv) > 1 else "cavity_baseline"
    print(json.dumps(run_cfd(case_arg), indent=2))
