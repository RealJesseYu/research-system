"""
run_fea — the production CalculiX (FEA) solver wrapper (Step 27 DRY).

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_cfd.py holds for OpenFOAM. This wrapper is UNREGISTERED at Step 27:
nothing in stages/, the supervisor, substrates.py, or any schema imports it. It
is reachable by tests (and a __main__ CLI) only.

Shape mirrors run_cfd:
  * a typed input for ONE canonical family v1 — a linear-elastic cantilever
    beam — is turned into a CalculiX input deck by a template + deterministic
    Python mesh generator (no LLM anywhere in the execution step);
  * the deck runs inside the `ccx-prod` container (bind-mounted cases_fea/,
    mirroring of12-prod), with a hard timeout and ONE retry on transient failure;
  * the solver's raw .dat/.frd/.sta output is parsed down to a SMALL summary and
    the raw log NEVER leaves the wrapper.

Canonical family v1 — typed input:
    run_fea({"length": 1.0, "width": 0.05, "height": 0.05,
             "E": 210e9, "nu": 0.3, "tip_load": 1000.0, "mesh_density": 8})

Return (and ONLY this leaves the wrapper):
    {"valid": bool,
     "qoi": {"tip_displacement": float, "max_von_mises": float} | None,
     "diagnostics": str,        # bounded, human-readable; never the raw deck/log
     "runtime_s": float}

Geometry convention: X spans the length (beam clamped at x=0), Y the width, Z the
height and the load direction. The tip load is applied as a shear at x=length in
the -Z direction, so the analytic Euler-Bernoulli tip deflection is
delta = tip_load * length**3 / (3 * E * I), with I = width * height**3 / 12.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import time
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — the only knobs, kept in one place (mirrors run_cfd.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"           # same colima VM as the CFD substrate
CONTAINER = "ccx-prod"              # the FEA production container; NOT ccx-img
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_fea"  # Mac side of the mount
SHARED_CONTAINER = "/work/cases"    # same folder seen inside the container

TIMEOUT_SECONDS = 600               # hard cap so a stuck solver can't hang us
MAX_RETRIES = 1                     # ONE retry on a transient (infra) failure
MAX_DIAG_CHARS = 800                # bound on how much diagnostic text we return

TEMPLATE = Path(__file__).parent / "fea_templates" / "cantilever_v1.inp.tmpl"
ELEMENT_TYPE = "C3D8I"              # 8-node incompatible-modes hex: bending-capable

# Docs-RAG index for the CalculiX manual — a SEPARATE index from solver_docs,
# mirroring the OpenFOAM docs index layout under retrieval/.
_RETRIEVAL_DIR = Path(__file__).resolve().parent.parent / "retrieval"
FEA_DOCS_INDEX = _RETRIEVAL_DIR / "fea_docs_index.pkl"


# ----------------------------------------------------------------------------
# Typed input for family v1.
# ----------------------------------------------------------------------------
_REQUIRED_FIELDS = ("length", "width", "height", "E", "nu", "tip_load", "mesh_density")

# The fixed QoI-name set every valid run returns (both names, every run, no
# per-run selection). THIS WRAPPER'S OWN single source (Packet B Phase 2,
# ruled option V-A): summarize_dat derives its keys from it, and the
# fixed-summary vocabulary record imports it — never a pasted copy.
# Deliberately NOT shared with the sibling fenicsx wrapper (the two share
# no code, by design; agreement through independent copies is evidence).
QOI_FIELDS = ("tip_displacement", "max_von_mises")


class FeaInputError(ValueError):
    """The typed input is not a buildable cantilever-v1 config."""


def _validate_input(spec: dict) -> dict:
    """Return a clean float/int copy of `spec`, or raise FeaInputError."""
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise FeaInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise FeaInputError(f"unsupported field(s) for cantilever v1: {', '.join(sorted(extra))}")

    out = {}
    for k in ("length", "width", "height", "E", "nu", "tip_load"):
        try:
            out[k] = float(spec[k])
        except (TypeError, ValueError):
            raise FeaInputError(f"field {k!r} must be a number, got {spec[k]!r}")
    try:
        md = int(spec["mesh_density"])
    except (TypeError, ValueError):
        raise FeaInputError(f"mesh_density must be an integer, got {spec['mesh_density']!r}")
    out["mesh_density"] = md

    for k in ("length", "width", "height", "E", "tip_load"):
        if out[k] <= 0:
            raise FeaInputError(f"field {k!r} must be positive, got {out[k]}")
    if not (-1.0 < out["nu"] < 0.5):
        raise FeaInputError(f"nu must be in (-1, 0.5), got {out['nu']}")
    if md < 1:
        raise FeaInputError(f"mesh_density must be >= 1, got {md}")
    return out


# ----------------------------------------------------------------------------
# Deterministic mesh + deck generation. No LLM, no randomness.
# ----------------------------------------------------------------------------

def _mesh_counts(spec: dict) -> tuple[int, int, int]:
    """Element counts (nx, ny, nz). mesh_density sets nx; ny/nz scale by aspect
    ratio so a refinement study (larger mesh_density) refines every direction."""
    L, W, H, md = spec["length"], spec["width"], spec["height"], spec["mesh_density"]
    nx = md
    ny = max(1, round(md * W / L))
    nz = max(1, round(md * H / L))
    return nx, ny, nz


def _node_id(i: int, j: int, k: int, nx: int, ny: int) -> int:
    return i + j * (nx + 1) + k * (nx + 1) * (ny + 1) + 1


def build_deck(spec: dict) -> str:
    """Turn a validated typed input into a full CalculiX .inp deck (a string).

    Pure and deterministic: identical input -> byte-identical deck.
    """
    spec = _validate_input(spec)
    L, W, H = spec["length"], spec["width"], spec["height"]
    nx, ny, nz = _mesh_counts(spec)

    # Nodes (structured grid).
    node_lines = []
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                x = L * i / nx
                y = W * j / ny
                z = H * k / nz
                nid = _node_id(i, j, k, nx, ny)
                node_lines.append(f"{nid}, {x:.9g}, {y:.9g}, {z:.9g}")

    # Elements (C3D8 corner ordering: bottom face CCW, then top face CCW).
    elem_lines = []
    eid = 0
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                eid += 1
                n1 = _node_id(i, j, k, nx, ny)
                n2 = _node_id(i + 1, j, k, nx, ny)
                n3 = _node_id(i + 1, j + 1, k, nx, ny)
                n4 = _node_id(i, j + 1, k, nx, ny)
                n5 = _node_id(i, j, k + 1, nx, ny)
                n6 = _node_id(i + 1, j, k + 1, nx, ny)
                n7 = _node_id(i + 1, j + 1, k + 1, nx, ny)
                n8 = _node_id(i, j + 1, k + 1, nx, ny)
                elem_lines.append(f"{eid}, {n1}, {n2}, {n3}, {n4}, {n5}, {n6}, {n7}, {n8}")

    # Fixed face (x=0, i=0); tip face (x=L, i=nx).
    fixed = [_node_id(0, j, k, nx, ny) for k in range(nz + 1) for j in range(ny + 1)]
    tip = [_node_id(nx, j, k, nx, ny) for k in range(nz + 1) for j in range(ny + 1)]

    # Distribute the total tip load over the tip-face nodes, load in -Z (DOF 3).
    per_node = -spec["tip_load"] / len(tip)
    cload_lines = [f"{nid}, 3, {per_node:.9g}" for nid in tip]

    deck = TEMPLATE.read_text().format(
        length=f"{L:.9g}", width=f"{W:.9g}", height=f"{H:.9g}",
        E=f"{spec['E']:.9g}", nu=f"{spec['nu']:.9g}",
        tip_load=f"{spec['tip_load']:.9g}", mesh_density=spec["mesh_density"],
        nodes="\n".join(node_lines),
        elements="\n".join(elem_lines),
        fixed_nodes=_csv_wrap(fixed),
        tip_nodes=_csv_wrap(tip),
        cloads="\n".join(cload_lines),
    )
    return deck


def _csv_wrap(ids: list[int], per_line: int = 8) -> str:
    """CalculiX *NSET lines: comma-separated ids, at most `per_line` per row."""
    rows = []
    for start in range(0, len(ids), per_line):
        rows.append(", ".join(str(n) for n in ids[start:start + per_line]))
    return "\n".join(rows)


def analytic_tip_deflection(spec: dict) -> float:
    """Euler-Bernoulli tip deflection delta = P L^3 / (3 E I), I = w h^3 / 12."""
    spec = _validate_input(spec)
    I = spec["width"] * spec["height"] ** 3 / 12.0
    return spec["tip_load"] * spec["length"] ** 3 / (3.0 * spec["E"] * I)


# ----------------------------------------------------------------------------
# Log parsing — pure functions, unit-tested against frozen fixtures. The raw
# .dat text is consumed HERE and only the small numbers leave.
# ----------------------------------------------------------------------------
_DISP_HEADER_RE = re.compile(r"displacements\s+\(", re.IGNORECASE)
_STRESS_HEADER_RE = re.compile(r"stresses\s+\(", re.IGNORECASE)
_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def _blocks(dat_text: str, header_re: re.Pattern) -> list[list[str]]:
    """Return the data-line groups that follow each matching header line.

    A block runs from just after a header until the next blank line or the next
    header. Robust to CalculiX's leading-space, banner-separated .dat layout.
    """
    lines = dat_text.splitlines()
    blocks, i = [], 0
    while i < len(lines):
        if header_re.search(lines[i]):
            i += 1
            # CalculiX prints a blank line between the header and its data rows;
            # skip any such leading blanks before collecting the block body.
            while i < len(lines) and not lines[i].strip():
                i += 1
            body = []
            while i < len(lines):
                ln = lines[i]
                if not ln.strip() or _DISP_HEADER_RE.search(ln) or _STRESS_HEADER_RE.search(ln):
                    break
                body.append(ln)
                i += 1
            if body:
                blocks.append(body)
        else:
            i += 1
    return blocks


def parse_node_displacements(dat_text: str) -> list[tuple[int, float, float, float]]:
    """Every (node, u1, u2, u3) row from all *NODE PRINT U blocks."""
    out = []
    for body in _blocks(dat_text, _DISP_HEADER_RE):
        for ln in body:
            nums = _NUM_RE.findall(ln)
            if len(nums) >= 4:
                out.append((int(float(nums[0])), float(nums[1]), float(nums[2]), float(nums[3])))
    return out


def parse_element_stresses(dat_text: str) -> list[tuple[float, float, float, float, float, float]]:
    """Every stress tensor (sxx, syy, szz, sxy, sxz, syz) row from *EL PRINT S.

    CalculiX column order is (elem, int.pnt, sxx, syy, szz, sxy, sxz, syz).
    """
    out = []
    for body in _blocks(dat_text, _STRESS_HEADER_RE):
        for ln in body:
            nums = _NUM_RE.findall(ln)
            if len(nums) >= 8:
                s = [float(x) for x in nums[2:8]]
                out.append(tuple(s))
    return out


def von_mises(sxx: float, syy: float, szz: float, sxy: float, sxz: float, syz: float) -> float:
    return math.sqrt(
        0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2)
        + 3.0 * (sxy ** 2 + sxz ** 2 + syz ** 2)
    )


def summarize_dat(dat_text: str) -> dict:
    """Reduce a raw CalculiX .dat to {tip_displacement, max_von_mises} or raise.

    tip_displacement = max |u3| over all printed nodes (the tip of a cantilever
    loaded transversely). max_von_mises = max von Mises over all integration
    points. Raises ValueError if either quantity is absent — the wrapper turns
    that into valid=False rather than fabricating a number.
    """
    disps = parse_node_displacements(dat_text)
    if not disps:
        raise ValueError("no displacement rows found in solver output")
    tip_disp = max(abs(u3) for (_, _, _, u3) in disps)

    stresses = parse_element_stresses(dat_text)
    if not stresses:
        raise ValueError("no stress rows found in solver output")
    max_vm = max(von_mises(*s) for s in stresses)

    return dict(zip(QOI_FIELDS, (tip_disp, max_vm)))


# ----------------------------------------------------------------------------
# Execution — sandboxed docker exec, hard timeout, one retry on transient fail.
# ----------------------------------------------------------------------------
_CCX_ERROR_RE = re.compile(r"\*ERROR", re.IGNORECASE)


def _run_ccx(job: str) -> tuple[int, str]:
    """Run `ccx <job>` inside the container. Returns (returncode, infra_stderr).

    Raises subprocess.TimeoutExpired on the hard timeout so the caller can
    classify it as a transient failure and retry once.
    """
    job_container = f"{SHARED_CONTAINER}/{job}"
    remote = f"cd {job_container} && ccx {job}"
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    return proc.returncode, proc.stderr.strip()


def _is_transient(returncode: int, infra_stderr: str, dat_exists: bool) -> bool:
    """A failure is transient (worth one retry) when it looks like infrastructure
    rather than a bad deck: no .dat produced and a docker/exec-level stderr, or a
    nonzero exit with no solver output at all."""
    if dat_exists:
        return False
    if infra_stderr and ("docker" in infra_stderr.lower() or "cannot" in infra_stderr.lower()
                         or "Error response" in infra_stderr):
        return True
    return returncode != 0 and not dat_exists


def run_fea(spec: dict) -> dict:
    """Build, run, and summarize one cantilever-v1 case. Returns the small dict
    documented at the top of this module — and nothing else leaves the wrapper.
    """
    wall_start = time.time()

    # --- build the deck (deterministic) -----------------------------------
    try:
        deck = build_deck(spec)
    except FeaInputError as e:
        return {"valid": False, "qoi": None,
                "diagnostics": f"input rejected: {e}"[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    md = int(spec["mesh_density"])
    job = f"cantilever_md{md}_{int(wall_start * 1000)}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / f"{job}.inp").write_text(deck)

    dat_path = case_dir / f"{job}.dat"

    # --- run, with one retry on a transient failure -----------------------
    last_err = ""
    for attempt in range(MAX_RETRIES + 1):
        # Clear any stale .dat so a retry can't read an old result.
        if dat_path.exists():
            dat_path.unlink()
        try:
            returncode, infra_stderr = _run_ccx(job)
        except subprocess.TimeoutExpired:
            last_err = f"ccx exceeded {TIMEOUT_SECONDS}s timeout and was killed"
            if attempt < MAX_RETRIES:
                continue
            return {"valid": False, "qoi": None,
                    "diagnostics": last_err[:MAX_DIAG_CHARS],
                    "runtime_s": round(time.time() - wall_start, 3)}

        dat_exists = dat_path.is_file()
        if not dat_exists or returncode != 0:
            if _is_transient(returncode, infra_stderr, dat_exists) and attempt < MAX_RETRIES:
                last_err = f"transient failure (exit {returncode}); retried"
                continue
            # Non-transient: read the solver log tail for a bounded diagnostic.
            diag = _failure_diagnostic(case_dir, job, returncode, infra_stderr)
            return {"valid": False, "qoi": None,
                    "diagnostics": diag[:MAX_DIAG_CHARS],
                    "runtime_s": round(time.time() - wall_start, 3)}
        break

    # --- summarize (raw .dat consumed here; only numbers escape) -----------
    try:
        qoi = summarize_dat(dat_path.read_text(errors="replace"))
    except ValueError as e:
        return {"valid": False, "qoi": None,
                "diagnostics": f"solver ran but output was unusable: {e}"[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    nx, ny, nz = _mesh_counts(_validate_input(spec))
    diagnostics = (f"ccx {ELEMENT_TYPE} mesh {nx}x{ny}x{nz} "
                   f"({(nx + 1) * (ny + 1) * (nz + 1)} nodes, {nx * ny * nz} elements); "
                   f"solver completed, {len(parse_node_displacements(dat_path.read_text(errors='replace')))} "
                   f"displacement rows parsed")
    return {"valid": True, "qoi": qoi,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


def _failure_diagnostic(case_dir: Path, job: str, returncode: int, infra_stderr: str) -> str:
    """A bounded, honest failure line — never the whole solver log."""
    for name in (f"{job}.sta", f"{job}.log", f"{job}.dat"):
        p = case_dir / name
        if p.is_file():
            tail = [ln.rstrip() for ln in p.read_text(errors="replace").splitlines() if ln.strip()]
            err = [ln for ln in tail if _CCX_ERROR_RE.search(ln)]
            if err:
                return f"ccx error (exit {returncode}): " + " | ".join(err[:5])
    if infra_stderr:
        return f"ccx failed (exit {returncode}): {infra_stderr.splitlines()[0]}"
    return f"ccx failed (exit {returncode}) with no usable output"


# ----------------------------------------------------------------------------
# Docs RAG — search the CalculiX manual index (separate from solver_docs).
# ----------------------------------------------------------------------------

def search_fea_docs(query: str, top_k: int = 3) -> list[dict]:
    """Search the CalculiX-manual TF-IDF index. Mirrors search_index('solver_docs')
    but points at the separate fea_docs index. Offline, deterministic, no API."""
    import sys
    if str(_RETRIEVAL_DIR) not in sys.path:
        sys.path.insert(0, str(_RETRIEVAL_DIR))
    from tfidf_core import search  # noqa: E402  (retrieval/ helper, path-injected)

    if not FEA_DOCS_INDEX.exists():
        raise FileNotFoundError(
            "fea_docs index not built yet — run "
            "venv/bin/python3 retrieval/build_fea_docs_index.py"
        )
    return search(FEA_DOCS_INDEX, query, top_k=top_k)


# CLI:  venv/bin/python3 tools/run_fea.py           (runs the default cantilever)
if __name__ == "__main__":
    default = {"length": 1.0, "width": 0.05, "height": 0.05,
               "E": 210e9, "nu": 0.3, "tip_load": 1000.0, "mesh_density": 8}
    result = run_fea(default)
    result["analytic_tip_deflection"] = analytic_tip_deflection(default)
    print(json.dumps(result, indent=2))
