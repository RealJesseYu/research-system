"""
run_autodock_vina — the AutoDock Vina (molecular docking) wrapper.
BIO Wave D.2. **RE-TIERED T2 -> DEFERRED (owner-ruled 2026-07-18):** AutoDock
Vina is a compiled x86 C++ tool with NO aarch64 build — no bioconda package
("No entries matching autodock-vina") and no pip wheel (`pip install vina` on
aarch64: "No matching distribution ... from versions: none"). It will not
install on this colima/aarch64 host, so it cannot run here. Enrolled INERT
(`calibrating`/`routable=False`), card §3A PENDING-PROVISIONING.

This differs from cas_offinder's deferral: cas_offinder INSTALLS anywhere but
computes silently wrong on aarch64 (needs a runtime known-answer guard); Vina
WON'T INSTALL on aarch64 at all — a total, honest failure at the install step,
nothing to run and nothing to mislead, so no runtime guard is buildable here.
THE UN-DEFER REQUIREMENT IS DIFFERENT (see the card): Vina needs a DIFFERENT
ARCHITECTURE (an x86 host), not merely a validated environment.

The wrapper below is WRITTEN with the intended docking logic — a FIXED SEED
(determinism), a convergence gate (a valid pose must be returned), and input
validation — ready to run once provisioned on x86. Only the pure-Python INPUT
jails are proven now; the docking §3A / determinism / convergence-jail proof is
produced at provisioning.

REGIME (card unit = (autodock_vina, rigid_pocket_dock)). Dock a flexible ligand
into a RIGID receptor pocket within a defined search box, empirical scoring.
FILTER-class: the docking score is a RELATIVE screen within a GIVEN,
human-validated receptor+box — never absolute affinity, never "the pose is
correct" (see the C1-hole).

Typed input:
    run_autodock_vina({
      "receptor": "demo_receptor",   # a baked allowlist receptor (PDBQT)
      "ligand": "demo_ligand",       # a baked allowlist ligand (PDBQT)
      "box": {"center_x": .., "center_y": .., "center_z": ..,
              "size_x": .., "size_y": .., "size_z": ..},
      "quantity": "docking_score",
    })

Return (ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import time
from pathlib import Path

DOCKER_CONTEXT = "colima"
CONTAINER = "vina-prod"                # created at provisioning on an x86 host
SHARED_HOST = Path("/Users/jesseyu/research-system/cases_vina")
SHARED_CONTAINER = "/work/cases"

TIMEOUT_SECONDS = 600
MAX_RETRIES = 1
MAX_DIAG_CHARS = 800

# FIXED SEED — determinism (Vina's search is stochastic). Un-defer proves an
# identical repeat returns an identical score with this seed.
VINA_SEED = 42
EXHAUSTIVENESS = 8
MAX_BOX_SIZE = 100.0                    # Angstroms (a sane cap)


class VinaInputError(ValueError):
    """The typed input is not a runnable docking config."""


_REQUIRED_FIELDS = ("receptor", "ligand", "box", "quantity")
_BOX_FIELDS = ("center_x", "center_y", "center_z", "size_x", "size_y", "size_z")

# Baked allowlists (real PDBQT receptors/ligands baked at provisioning on x86).
RECEPTOR_ALLOWLIST = ("demo_receptor",)
LIGAND_ALLOWLIST = ("demo_ligand",)
QOI_FIELDS = ("docking_score",)


def _validate_input(spec: dict) -> dict:
    """Return a clean copy, or raise VinaInputError. Pure, pre-run — PROVEN now
    (no tool needed)."""
    if not isinstance(spec, dict):
        raise VinaInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise VinaInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise VinaInputError(f"unsupported field(s): {', '.join(sorted(extra))}")

    if spec["receptor"] not in RECEPTOR_ALLOWLIST:
        raise VinaInputError(
            f"receptor {spec['receptor']!r} is not a baked allowlist receptor "
            f"(allowed: {', '.join(RECEPTOR_ALLOWLIST)})")
    if spec["ligand"] not in LIGAND_ALLOWLIST:
        raise VinaInputError(
            f"ligand {spec['ligand']!r} is not a baked allowlist ligand "
            f"(allowed: {', '.join(LIGAND_ALLOWLIST)})")
    if spec["quantity"] not in QOI_FIELDS:
        raise VinaInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")

    box = spec["box"]
    if not isinstance(box, dict):
        raise VinaInputError("'box' must be a dict with center_x/y/z and size_x/y/z")
    bmissing = [k for k in _BOX_FIELDS if k not in box]
    if bmissing:
        raise VinaInputError(f"'box' is missing field(s): {', '.join(bmissing)}")
    bextra = [k for k in box if k not in _BOX_FIELDS]
    if bextra:
        raise VinaInputError(f"'box' has unsupported field(s): {', '.join(sorted(bextra))}")
    clean_box: dict = {}
    for k in _BOX_FIELDS:
        v = box[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise VinaInputError(f"box field {k!r} must be a finite number, got {v!r}")
        if k.startswith("size"):
            if not (0 < v <= MAX_BOX_SIZE):
                raise VinaInputError(
                    f"box field {k!r} must be in (0, {MAX_BOX_SIZE}] Angstroms, got {v}")
        clean_box[k] = float(v)

    return {"receptor": spec["receptor"], "ligand": spec["ligand"],
            "box": clean_box, "quantity": spec["quantity"]}


def preflight() -> str | None:
    """Return None when the substrate is ready, else an honest reason. On this
    aarch64 host `vina-prod` does not exist (Vina has no aarch64 build) — the
    honest DEFERRED state."""
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
        return (f"container {CONTAINER!r} does not exist — AutoDock Vina has no "
                "aarch64 build (DEFERRED); provision on an x86 host per the card's "
                "un-defer requirement")
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


_AFFINITY_RE = re.compile(r"^\s*1\s+(-?\d+\.\d+)")  # mode 1 (best) affinity line


def _run_vina(job: str, clean: dict) -> tuple[int, str, str]:
    """Run one docking (INTENDED logic, exercised at provisioning on x86). Fixed
    seed for determinism; parses the best-mode affinity from Vina's table."""
    job_dir = f"{SHARED_CONTAINER}/{job}"
    b = clean["box"]
    remote = (
        f"export PATH=/opt/conda/bin:$PATH; "
        f"vina --receptor /opt/vina/{clean['receptor']}.pdbqt "
        f"--ligand /opt/vina/{clean['ligand']}.pdbqt "
        f"--center_x {b['center_x']} --center_y {b['center_y']} --center_z {b['center_z']} "
        f"--size_x {b['size_x']} --size_y {b['size_y']} --size_z {b['size_z']} "
        f"--seed {VINA_SEED} --exhaustiveness {EXHAUSTIVENESS} "
        f"--out {job_dir}/out.pdbqt")
    cmd = ["docker", "--context", DOCKER_CONTEXT, "exec", CONTAINER, "bash", "-c", remote]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    return proc.returncode, proc.stdout, proc.stderr


def run_autodock_vina(spec: dict) -> dict:
    """Dock a ligand into a rigid pocket and return the best docking score. On
    this aarch64 host it returns the honest DEFERRED failure at preflight (Vina
    won't install); the input jails still fire pre-flight. On an x86 host the
    docking runs with a fixed seed and the QoI is gated on the search converging
    to a valid pose."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except VinaInputError as e:
        return fail(f"input rejected: {e}")

    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    job = f"vina_{int(wall_start * 1000)}"
    (SHARED_HOST / job).mkdir(parents=True, exist_ok=True)

    rc, out, err = -1, "", ""
    for attempt in range(MAX_RETRIES + 1):
        try:
            rc, out, err = _run_vina(job, clean)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"vina exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        if not out and rc != 0 and attempt < MAX_RETRIES:
            continue
        break

    # CONVERGENCE GATE: a failed/degenerate search (error, or no scored pose)
    # yields no number. Proven by triggering at provisioning.
    if rc != 0 or "error" in err.lower():
        first = (err.strip().splitlines() or ["vina error"])[0]
        return fail(f"docking search did not run cleanly: {first}")
    best = None
    for line in out.splitlines():
        m = _AFFINITY_RE.match(line)
        if m:
            best = float(m.group(1))
            break
    if best is None:
        return fail("docking produced no scored pose — the search did not "
                    "converge to a valid pose (not a number)")
    if not math.isfinite(best):
        return fail(f"docking score is not finite ({best!r})")

    diagnostics = (f"vina rigid_pocket_dock: receptor {clean['receptor']!r}, "
                   f"ligand {clean['ligand']!r}, seed {VINA_SEED}; "
                   f"docking_score={best:g} kcal/mol [RELATIVE screen within THIS "
                   f"human-validated receptor+box — not absolute affinity]")
    return {"valid": True, "qoi": best,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


# CLI: venv/bin/python3 tools/run_autodock_vina.py  (DEFERRED here — no aarch64 Vina)
if __name__ == "__main__":
    default = {
        "receptor": "demo_receptor", "ligand": "demo_ligand",
        "box": {"center_x": 0.0, "center_y": 0.0, "center_z": 0.0,
                "size_x": 20.0, "size_y": 20.0, "size_z": 20.0},
        "quantity": "docking_score",
    }
    print(json.dumps(run_autodock_vina(default), indent=2))
