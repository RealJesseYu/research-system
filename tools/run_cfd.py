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
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases"  # Mac side of the bind mount
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
    # SORT NUMERICALLY, NOT LEXICOGRAPHICALLY. postProcessing/ is never cleaned
    # between runs, and the directories under it are named by simulation TIME. A
    # plain sorted() compares them as strings, so a case post-processed at t=5 and
    # later re-run to t=20 gives ["20", "5"] and [-1] picks "5" — the wrapper
    # returned the OLD value as this run's measurement, silently, on the success
    # path. _latest_time_dir fifty lines below already sorts by float; this is the
    # same job and now does the same thing.
    timed = []
    for f in dat_path.glob("*/volFieldValue.dat"):
        try:
            timed.append((float(f.parent.name), f))
        except ValueError:
            # Not a time directory. Skipped rather than sorted as a string,
            # because a non-numeric name cannot be the latest time.
            continue
    if not timed:
        return {"qoi_error": f"postProcess ran but wrote no volFieldValue output for {func_name}"}
    dat_time, dat_file = max(timed, key=lambda pair: pair[0])
    try:
        row_time, value = parse_volfieldvalue_dat(dat_file.read_text(errors="replace"))
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


# ----------------------------------------------------------------------------
# Multi-QoI extraction, field export, and deterministic masked reductions
# (MULTIQOI-A). This is a CAPABILITY-ONLY layer, strictly ADDITIVE to the
# single-QoI postProcess path above:
#
#   * the single-QoI run_cfd(case, qoi_request=...) path is UNCHANGED and its
#     return stays byte-identical on the same inputs (nothing above this line
#     was touched);
#   * instead of asking OpenFOAM to reduce a field, this layer reads the fields
#     the solved case ALREADY WROTE (U, p) plus cell centres/volumes it asks
#     OpenFOAM's stock utilities to write (C, V), and computes reductions in
#     deterministic Python. No LLM anywhere, no new physics — nothing is
#     re-solved, only read;
#   * the full arrays NEVER leave the wrapper. Field export returns a file PATH
#     plus summary statistics; masked reductions return a value plus the
#     masked/total cell counts. Raw solver output still never escapes.
#
# numpy is imported lazily inside these functions so the untouched single-QoI /
# run path never depends on it.
# ----------------------------------------------------------------------------

REDUCTIONS = ("min", "max", "volAverage")
MASK_TYPES = ("corner_exclusion", "boundary_exclusion", "box")


def _latest_time_dir(case_host: Path) -> Path:
    """Return the case's latest (numerically largest) time directory."""
    times = []
    for d in case_host.iterdir():
        if d.is_dir():
            try:
                times.append((float(d.name), d))
            except ValueError:
                continue
    if not times:
        raise FileNotFoundError(f"no time directories in case '{case_host.name}'")
    times.sort(key=lambda t: t[0])
    return times[-1][1]


def parse_internal_field(text: str):
    """Parse an OpenFOAM field file's nonuniform internalField into a numpy
    array. Pure function. Scalars -> shape (n,); vectors -> shape (n, 3).
    Raises ValueError on a uniform or unrecognized internalField.
    """
    import numpy as np

    m = re.search(
        r"internalField\s+nonuniform\s+List<(scalar|vector)>\s*\n?\s*(\d+)\s*\(",
        text,
    )
    if not m:
        raise ValueError("internalField is not a nonuniform List (uniform or unrecognized)")
    kind = m.group(1)
    n = int(m.group(2))

    # Depth-count from the '(' the regex consumed to find the matching close.
    open_idx = m.end() - 1
    depth = 0
    close_idx = None
    for j in range(open_idx, len(text)):
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                close_idx = j
                break
    if close_idx is None:
        raise ValueError("unterminated internalField list")
    inner = text[open_idx + 1:close_idx]

    if kind == "scalar":
        vals = np.array([float(t) for t in inner.split()], dtype=float)
        if vals.shape[0] != n:
            raise ValueError(f"expected {n} scalars, parsed {vals.shape[0]}")
        return vals
    tuples = re.findall(r"\(([^()]*)\)", inner)
    arr = np.array([[float(x) for x in t.split()] for t in tuples], dtype=float)
    if arr.shape[0] != n:
        raise ValueError(f"expected {n} vectors, parsed {arr.shape[0]}")
    return arr


def _write_geometry_fields(case: str) -> None:
    """Ask OpenFOAM's stock utilities to write cell centres (C) and cell
    volumes (V) at the latest time. Deterministic geometry, no solve."""
    case_container = f"{SHARED_CONTAINER}/{case}"
    remote = (
        f"source {OF_BASHRC} && cd {case_container} && "
        f"postProcess -funcs '(writeCellCentres writeCellVolumes)' -latestTime "
        f"> log.writeGeometry 2>&1"
    )
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if proc.returncode != 0:
        raise RuntimeError(
            f"failed to write cell centres/volumes for case '{case}' (exit {proc.returncode})"
        )


def _load_case_fields(case: str) -> dict:
    """Load C, V and available solved fields (U, p) at the case's latest time
    into numpy arrays. Writes C/V via stock utilities if they are absent."""
    import numpy as np

    def _vol_file(td: Path):
        # OpenFOAM v12's writeCellVolumes writes 'Vc'; older/other builds 'V'.
        for name in ("Vc", "V"):
            if (td / name).is_file():
                return td / name
        return None

    case_host = SHARED_HOST / case
    tdir = _latest_time_dir(case_host)
    if not (tdir / "C").is_file() or _vol_file(tdir) is None:
        _write_geometry_fields(case)
        tdir = _latest_time_dir(case_host)

    vfile = _vol_file(tdir)
    if not (tdir / "C").is_file() or vfile is None:
        raise FileNotFoundError(
            f"cell centre/volume fields missing in {tdir} after writing geometry"
        )
    fields = {
        "C": parse_internal_field((tdir / "C").read_text(errors="replace")),
        "V": parse_internal_field(vfile.read_text(errors="replace")),
    }
    for f in ("U", "p"):
        fp = tdir / f
        if fp.is_file():
            try:
                fields[f] = parse_internal_field(fp.read_text(errors="replace"))
            except ValueError:
                pass  # a uniform/absent field is simply not offered
    fields["time"] = float(tdir.name)
    fields["n_cells"] = int(fields["C"].shape[0])
    return fields


def _domain_bbox(C):
    """Domain bounding box (xmin, xmax, ymin, ymax) inferred from cell centres,
    extended by half the (minimum) cell spacing so a structured cavity mesh
    recovers its true extent. Exact for a uniform mesh; deterministic."""
    import numpy as np

    xs = np.unique(C[:, 0])
    ys = np.unique(C[:, 1])
    dx = float(np.min(np.diff(xs))) if xs.size > 1 else 0.0
    dy = float(np.min(np.diff(ys))) if ys.size > 1 else 0.0
    return (float(xs[0] - dx / 2), float(xs[-1] + dx / 2),
            float(ys[0] - dy / 2), float(ys[-1] + dy / 2))


def mask_keep(mask: dict, C, bbox):
    """Return a boolean keep-array (True = cell retained in the reduction) for
    one mask spec. Deterministic geometry in code; no solver involved.

    Mask types (fractions are of the cavity length):
      corner_exclusion  {radius_frac r}  -> drop cells within r*L of any of the
                                            four cavity corners
      boundary_exclusion{distance_frac d}-> keep only cells at least d*L from
                                            every wall
      box               {x_min,x_max,y_min,y_max} -> keep cells inside the
                                            fractional box, drop the rest
    """
    import numpy as np

    xmin, xmax, ymin, ymax = bbox
    Lx = xmax - xmin
    Ly = ymax - ymin
    L = Lx  # square-cavity length reference
    x = C[:, 0]
    y = C[:, 1]
    kind = mask.get("type")

    if kind == "corner_exclusion":
        r = float(mask["radius_frac"]) * L
        excluded = np.zeros(C.shape[0], dtype=bool)
        for cx, cy in ((xmin, ymin), (xmax, ymin), (xmin, ymax), (xmax, ymax)):
            excluded |= np.hypot(x - cx, y - cy) < r
        return ~excluded
    if kind == "boundary_exclusion":
        d = float(mask["distance_frac"])
        return ((x >= xmin + d * Lx) & (x <= xmax - d * Lx) &
                (y >= ymin + d * Ly) & (y <= ymax - d * Ly))
    if kind == "box":
        xf0 = float(mask["x_min"]); xf1 = float(mask["x_max"])
        yf0 = float(mask["y_min"]); yf1 = float(mask["y_max"])
        return ((x >= xmin + xf0 * Lx) & (x <= xmin + xf1 * Lx) &
                (y >= ymin + yf0 * Ly) & (y <= ymin + yf1 * Ly))
    raise ValueError(f"unknown mask type {kind!r} — must be one of {list(MASK_TYPES)}")


def _field_values(fields: dict, field: str, component):
    """Reduce a field to a per-cell scalar array per the requested component."""
    import numpy as np

    if field not in fields or not isinstance(fields.get(field), np.ndarray):
        have = [k for k in ("U", "p") if isinstance(fields.get(k), np.ndarray)]
        raise ValueError(f"field {field!r} not available in case (have {have})")
    arr = fields[field]
    if arr.ndim == 1:
        if component is not None:
            raise ValueError(f"field {field!r} is scalar; component {component!r} not applicable")
        return arr
    if component == "mag":
        return np.linalg.norm(arr, axis=1)
    if component in (0, 1, 2):
        return arr[:, component]
    raise ValueError(f"vector field {field!r} needs component 'mag' or 0|1|2")


def _reduce(values, reduction: str, keep, volumes):
    """Apply a reduction over the kept cells (volume-weighted for volAverage)."""
    import numpy as np

    v = values[keep]
    if v.size == 0:
        raise ValueError("mask excluded every cell — nothing to reduce over")
    if reduction == "min":
        return float(v.min())
    if reduction == "max":
        return float(v.max())
    if reduction == "volAverage":
        w = volumes[keep] if volumes is not None else np.ones_like(v)
        return float(np.sum(w * v) / np.sum(w))
    raise ValueError(f"unknown reduction {reduction!r} — must be one of {list(REDUCTIONS)}")


def _auto_name(field: str, component, reduction: str, mask) -> str:
    """A deterministic, human-legible name for an unnamed QoI request."""
    if component == "mag":
        fexpr = f"mag({field})"
    elif component in (0, 1, 2):
        fexpr = f"{field}[{component}]"
    else:
        fexpr = field
    name = f"{reduction}({fexpr})"
    if mask is not None:
        name += f"|{mask.get('type')}"
    return name


def _export_fields(case: str, fields: dict, out_dir: Path | None = None) -> dict:
    """Write a compact on-disk artifact (npz) of C/V and available solved
    fields, and return ONLY {path, fields, n_cells, summary_stats} — never the
    arrays themselves."""
    import numpy as np

    dest = (out_dir or (SHARED_HOST / case))
    path = dest / "fields_export.npz"
    arrays = {"C": fields["C"], "V": fields["V"]}
    exported = ["C", "V"]
    for f in ("U", "p"):
        if isinstance(fields.get(f), np.ndarray):
            arrays[f] = fields[f]
            exported.append(f)
    np.savez(path, **arrays)

    stats: dict = {}
    if "p" in arrays:
        p = arrays["p"]
        stats["p"] = {"min": float(p.min()), "max": float(p.max()), "mean": float(p.mean())}
    if "U" in arrays:
        magU = np.linalg.norm(arrays["U"], axis=1)
        stats["magU"] = {"min": float(magU.min()), "max": float(magU.max()),
                         "mean": float(magU.mean())}
    return {"path": str(path), "fields": exported, "n_cells": int(fields["n_cells"]),
            "summary_stats": stats}


def extract_qois(case: str, requests: list, export: bool = True) -> dict:
    """Extract a LIST of QoIs from ONE solved case in a single pass.

    Each request is a dict: {field, reduction, component?, mask?, name?}.
    Returns {"case", "time", "n_cells", "qois": {name: entry}, "values":
    {name: value}} and, when export=True, "field_export": {path, fields,
    n_cells, summary_stats}. Every entry is small — a value plus counts, never
    an array. A bad request yields a per-QoI {"qoi_error": ...}, mirroring the
    single-QoI path; it never fabricates a number.
    """
    import numpy as np

    fields = _load_case_fields(case)
    C = fields["C"]
    V = fields["V"]
    bbox = _domain_bbox(C)
    n_total = int(fields["n_cells"])

    results: dict = {}
    values: dict = {}
    for req in requests:
        field = req.get("field")
        component = req.get("component")
        reduction = req.get("reduction")
        mask = req.get("mask")
        name = req.get("name") or _auto_name(str(field), component, str(reduction), mask)
        try:
            if not isinstance(field, str) or not _QOI_FIELD_RE.match(field):
                raise ValueError(f"invalid field name {field!r}")
            if reduction not in REDUCTIONS:
                raise ValueError(f"unknown reduction {reduction!r} — must be one of {list(REDUCTIONS)}")
            vals = _field_values(fields, field, component)
            keep = mask_keep(mask, C, bbox) if mask is not None else np.ones(n_total, dtype=bool)
            value = _reduce(vals, reduction, keep, V)
            n_masked = int((~keep).sum())
            results[name] = {
                "value": value, "field": field, "component": component,
                "reduction": reduction, "mask": mask,
                "n_cells_masked": n_masked, "n_cells_total": n_total,
            }
            values[name] = value
        except (ValueError, KeyError) as e:
            results[name] = {"qoi_error": str(e)}
            values[name] = None

    out = {"case": case, "time": fields["time"], "n_cells": n_total,
           "qois": results, "values": values}
    if export:
        out["field_export"] = _export_fields(case, fields)
    return out


def run_cfd(case: str, qoi_request: dict | None = None,
            qois: list | None = None) -> dict:
    """
    Run an OpenFOAM case and return a SMALL summary dict.

    Success -> {status:"ok", converged, residuals, key_result, runtime, ...}
    Failure -> {status:"failed", converged:False, error_lines:[...], ...}
    With qoi_request: the success summary additionally carries either
    qoi:{name, field, operation, value, time} or qoi_error:"<reason>".
    With qois=[...]: after a run that reached its end time, the summary also
    carries qois:{name: entry} and field_export:{path, ...} from extract_qois
    (values + cell counts only — never raw arrays), or qois_error:"<reason>".
    The qoi_request path is unchanged; passing neither leaves both off.
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

    # --- optional multi-QoI vector + field export (additive; never arrays) ---
    if qois is not None:
        if reached_end:
            try:
                multi = extract_qois(case, qois)
                summary["qois"] = multi["qois"]
                summary["field_export"] = multi["field_export"]
            except Exception as e:  # extraction must never mask a good solve
                summary["qois_error"] = f"multi-QoI extraction failed: {e}"
        else:
            summary["qois_error"] = "run did not reach its end time — multi-QoI not extracted"
    return summary


# Lets us test from the command line:  python tools/run_cfd.py cavity_baseline
if __name__ == "__main__":
    import sys
    case_arg = sys.argv[1] if len(sys.argv) > 1 else "cavity_baseline"
    print(json.dumps(run_cfd(case_arg), indent=2))
