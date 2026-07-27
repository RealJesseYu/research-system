"""
run_rdkit — the production RDKit (deterministic molecular-descriptor) wrapper.

Plain, deterministic code. NO AI inside, no model calls, ever — the same
contract run_cfd.py holds for OpenFOAM, run_ngspice.py for ngspice, and
run_fea.py for CalculiX. This is the first BIO-wave substrate (BIO Wave D.2,
T1). At build time it is UNREGISTERED and UNROUTABLE: it enrolls at
`calibrating` / `routable=False`; nothing routes to it until an owner
promotion ruling. (Truthful prose provenance; this docstring enters no
composed prompt.)

Shape mirrors run_ngspice:
  * a typed input is turned into a small job (input.json + a fixed driver) by
    deterministic Python — no LLM anywhere in the execution step;
  * the job runs inside the `rdkit-prod` container (bind-mounted cases_rdkit/,
    mirroring ngspice-prod / ccx-prod), with a hard timeout and ONE retry on a
    transient (infrastructure) failure;
  * RDKit's output is parsed down to a SMALL summary; nothing else leaves the
    wrapper.

REGIME (card unit = (rdkit, descriptor_computation)). RDKit here computes a
FIXED allowlist of DETERMINISTIC 2D descriptors from a single parsed,
sanitized molecule. It is an `answer`-class substrate: the descriptor IS the
tool's exact computed output, not a prediction. Out of regime, by
construction: any ML-PREDICTED property (e.g. a solubility/ADMET model), 3D
conformer-dependent quantities, or a descriptor outside the allowlist. The
one KNOWN GAP (C1-hole): a computed descriptor is a PROXY, never a measured
property — Crippen `MolLogP` is a computed logP, not an experimental logP.

Typed input:
    run_rdkit({
      "smiles": "CCO",
      "quantity": "MolWt",          # which allowlist descriptor is THE QoI
    })

Return (and ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}

WHO OWNS WHAT. The CALLER supplies a SMILES string and names one allowlist
descriptor. The WRAPPER owns parsing, sanitization, the descriptor set, and
the extraction. A SMILES that does not parse-and-sanitize under RDKit's own
model returns valid=False, qoi=None — the wrapper never fabricates a
descriptor for an unparseable molecule.

THE JAILS (proven by failing the escape, never by reading config):
  1. UNPARSEABLE / UNSANITIZABLE SMILES  -> Chem.MolFromSmiles returns None
     (RDKit sanitizes by default) -> valid=False, qoi=None. Measured.
  2. DESCRIPTOR OFF THE ALLOWLIST        -> rejected pre-run by name.
  3. NON-FINITE descriptor value         -> refused, never returned.
  4. CONTAINER DOWN / TIMEOUT            -> transient: one retry, then honest fail.
"""

from __future__ import annotations

import json
import math
import subprocess
import time
from pathlib import Path

from tools.docker_exec import exec_bounded

# ----------------------------------------------------------------------------
# Configuration — the only knobs, in one place (mirrors run_ngspice.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"           # same colima VM as the CFD/FEA/ngspice substrates
CONTAINER = "rdkit-prod"            # the production container; built from rdkit-img
# Derived from this file's location, not hardcoded: the literal
# /Users/jesseyu/research-system prefix bound every containerized substrate
# to one developer's home directory, so a fresh checkout by anyone else
# failed here rather than at a missing container. This is the Mac side of
# the docker bind mount; the container side is unchanged.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHARED_HOST = _PROJECT_ROOT / "cases_rdkit"  # Mac side
SHARED_CONTAINER = "/work/cases"    # same folder seen inside the container

TIMEOUT_SECONDS = 600               # hard cap so a stuck job can't hang us
MAX_RETRIES = 1                     # ONE retry on a transient (infra) failure
MAX_DIAG_CHARS = 800               # bound on returned diagnostic text
MAX_SMILES_BYTES = 4_000           # sanity cap on the caller's SMILES string


class RdkitInputError(ValueError):
    """The typed input is not a runnable descriptor request."""


# ----------------------------------------------------------------------------
# Typed input + the FIXED descriptor allowlist (the fixed_summary QoI vocab).
#
# Every name here is a DETERMINISTIC RDKit 2D descriptor. The values are the
# QoI vocabulary's single source of truth: tools/qoi_vocab.py imports
# QOI_FIELDS from THIS module (never a pasted copy), exactly as the cantilever
# wrappers export QOI_FIELDS. Curated deliberately small — a fixed summary,
# not RDKit's full ~200-descriptor surface; widening is a card ruling.
# ----------------------------------------------------------------------------
_REQUIRED_FIELDS = ("smiles", "quantity")

# name -> (rdkit module attr path) the driver resolves inside the container.
# Kept as a plain tuple of names here (the wrapper's own vocabulary); the
# driver holds the name->callable map so RDKit is imported only in-container.
QOI_FIELDS = (
    "MolWt",             # average molecular weight
    "ExactMolWt",        # monoisotopic weight
    "HeavyAtomCount",    # non-hydrogen atom count
    "NumHDonors",        # Lipinski H-bond donors
    "NumHAcceptors",     # Lipinski H-bond acceptors
    "NumRotatableBonds", # rotatable bond count
    "TPSA",              # topological polar surface area
    "MolLogP",           # Crippen COMPUTED logP (a proxy — the C1-hole)
    "NumAromaticRings",  # aromatic ring count
    "RingCount",         # total ring count
    "FractionCSP3",      # fraction of sp3 carbons
    "NOCount",           # nitrogen+oxygen count
)


def _validate_input(spec: dict) -> dict:
    """Return a clean copy of `spec`, or raise RdkitInputError naming the field.
    Pure, pre-run: nothing here touches the container."""
    if not isinstance(spec, dict):
        raise RdkitInputError(f"spec must be a dict, got {type(spec).__name__}")

    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise RdkitInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise RdkitInputError(
            f"unsupported field(s) for rdkit descriptor_computation: "
            f"{', '.join(sorted(extra))}")

    smiles = spec["smiles"]
    if not isinstance(smiles, str) or not smiles.strip():
        raise RdkitInputError("'smiles' must be a non-empty string")
    n_bytes = len(smiles.encode("utf-8"))
    if n_bytes > MAX_SMILES_BYTES:
        raise RdkitInputError(
            f"'smiles' is {n_bytes} bytes, over the {MAX_SMILES_BYTES}-byte cap")

    quantity = spec["quantity"]
    if quantity not in QOI_FIELDS:
        raise RdkitInputError(
            f"quantity {quantity!r} is not an allowlist descriptor "
            f"(allowed: {', '.join(QOI_FIELDS)})")

    return {"smiles": smiles, "quantity": quantity}


# ----------------------------------------------------------------------------
# The in-container driver. Written to the job dir per run; RDKit is imported
# ONLY here, inside rdkit-prod — the host venv never imports rdkit (the
# clean-venv invariant). Deterministic: identical input -> identical output.
# It computes the WHOLE allowlist (a fixed_summary) and reports every value;
# the wrapper selects the requested one as the scalar QoI.
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
    from rdkit import Chem
    from rdkit.Chem import Descriptors, Crippen, Lipinski, rdMolDescriptors
except Exception as e:  # pragma: no cover - container misbuild
    write({"ok": False, "error": "rdkit import failed: %s" % e}); sys.exit(0)

# name -> deterministic callable(mol) -> float. Single source: this driver.
FUNCS = {
    "MolWt": Descriptors.MolWt,
    "ExactMolWt": Descriptors.ExactMolWt,
    "HeavyAtomCount": lambda m: float(m.GetNumHeavyAtoms()),
    "NumHDonors": lambda m: float(Lipinski.NumHDonors(m)),
    "NumHAcceptors": lambda m: float(Lipinski.NumHAcceptors(m)),
    "NumRotatableBonds": lambda m: float(Descriptors.NumRotatableBonds(m)),
    "TPSA": Descriptors.TPSA,
    "MolLogP": Crippen.MolLogP,
    "NumAromaticRings": lambda m: float(rdMolDescriptors.CalcNumAromaticRings(m)),
    "RingCount": lambda m: float(rdMolDescriptors.CalcNumRings(m)),
    "FractionCSP3": Descriptors.FractionCSP3,
    "NOCount": lambda m: float(Lipinski.NOCount(m)),
}

names = spec["descriptors"]
# RDKit sanitizes by default; an unparseable OR unsanitizable SMILES -> None.
mol = Chem.MolFromSmiles(spec["smiles"])
if mol is None:
    write({"ok": False, "error": "SMILES did not parse-and-sanitize under RDKit"})
    sys.exit(0)

values = {}
for n in names:
    try:
        v = float(FUNCS[n](mol))
    except Exception as e:
        write({"ok": False, "error": "descriptor %s failed: %s" % (n, e)}); sys.exit(0)
    if not math.isfinite(v):
        write({"ok": False, "error": "descriptor %s is non-finite" % n}); sys.exit(0)
    values[n] = v

write({"ok": True, "values": values,
       "canonical_smiles": Chem.MolToSmiles(mol)})
'''


# ----------------------------------------------------------------------------
# Preflight — daemon AND container (mirrors run_ngspice; the two failures want
# different human actions).
# ----------------------------------------------------------------------------
def preflight() -> str | None:
    """Return None when the substrate is ready, else an honest reason string."""
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
        return f"container {CONTAINER!r} does not exist (create it from rdkit-img)"
    if proc.stdout.strip() != "true":
        return f"container {CONTAINER!r} exists but is not running (docker start {CONTAINER})"
    return None


# ----------------------------------------------------------------------------
# Execution — sandboxed docker exec, hard timeout, one retry on transient fail.
# ----------------------------------------------------------------------------
def _run_driver(job: str) -> tuple[int, str]:
    """Run the driver on the job dir inside the container. Returns
    (returncode, infra_stderr). Raises subprocess.TimeoutExpired on the hard
    timeout so the caller can classify it as transient and retry once.

    BOUNDED INSIDE THE CONTAINER (tools/docker_exec.py). A plain subprocess
    timeout on `docker exec` kills only the local client — the driver keeps
    running in the shared prod container. That matters here specifically because
    the retry below DELETES result.json and re-runs into the SAME job dir, so a
    timed-out driver could still be writing there while the retry reads: the
    retry would then report the ghost's output as a clean success. The container
    now kills its own work first, and TimeoutExpired is still raised on the
    client-timeout path so the caller's transient classification is unchanged.
    """
    job_dir = f"{SHARED_CONTAINER}/{job}"
    result = exec_bounded(
        DOCKER_CONTEXT, CONTAINER,
        ["python", f"{job_dir}/driver.py", job_dir],
        timeout_s=TIMEOUT_SECONDS,
        # Unique to this job (jobs are named tool_<ms>), so a reap can only ever
        # match this driver — never another job's, never container services.
        kill_marker=job_dir,
    )
    if result.timed_out:
        raise subprocess.TimeoutExpired(
            cmd=f"docker exec {CONTAINER} python {job_dir}/driver.py",
            timeout=TIMEOUT_SECONDS,
            output=result.stdout, stderr=result.stderr)
    return result.returncode, (result.stderr or "").strip()


def _is_transient(returncode: int, infra_stderr: str, result_exists: bool) -> bool:
    """A failure is transient (worth one retry) when it looks like infrastructure
    rather than a bad input: no result.json produced and a docker/exec-level
    stderr."""
    if result_exists:
        return False
    low = infra_stderr.lower()
    if infra_stderr and ("docker" in low or "cannot" in low
                         or "error response" in low or "is not running" in low):
        return True
    return returncode != 0 and not result_exists


def run_rdkit(spec: dict) -> dict:
    """Compute one allowlist descriptor for one molecule, deterministically,
    inside rdkit-prod. Returns the small dict documented at the top of this
    module — and nothing else leaves the wrapper. A QoI is NEVER returned for
    an unparseable molecule, a driver error, or a non-finite value."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3)}

    # --- validate (pure, pre-run) -----------------------------------------
    try:
        clean = _validate_input(spec)
    except RdkitInputError as e:
        return fail(f"input rejected: {e}")

    # --- preflight: daemon AND container ----------------------------------
    reason = preflight()
    if reason:
        return fail(f"substrate not ready: {reason}")

    job = f"rdkit_{int(wall_start * 1000)}"
    case_dir = SHARED_HOST / job
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "input.json").write_text(json.dumps(
        {"smiles": clean["smiles"], "descriptors": list(QOI_FIELDS)}))
    (case_dir / "driver.py").write_text(_DRIVER)
    result_path = case_dir / "result.json"

    # --- run, with one retry on a transient failure -----------------------
    returncode, infra_stderr = -1, ""
    for attempt in range(MAX_RETRIES + 1):
        if result_path.exists():
            result_path.unlink()          # a retry must not read a stale result
        try:
            returncode, infra_stderr = _run_driver(job)
        except subprocess.TimeoutExpired:
            if attempt < MAX_RETRIES:
                continue
            return fail(f"rdkit driver exceeded {TIMEOUT_SECONDS}s timeout and was killed")
        result_exists = result_path.is_file()
        if not result_exists and _is_transient(returncode, infra_stderr, result_exists) \
                and attempt < MAX_RETRIES:
            continue
        break

    # --- summarize (no result file, no number) ----------------------------
    if not result_path.is_file():
        return fail(f"rdkit driver produced no result (exit {returncode}): "
                    f"{infra_stderr.splitlines()[0] if infra_stderr else 'no stderr'}")
    try:
        result = json.loads(result_path.read_text())
    except (ValueError, OSError) as e:
        return fail(f"rdkit result unreadable: {e}")

    if not result.get("ok"):
        return fail(f"rdkit could not compute the descriptors: "
                    f"{result.get('error', 'unknown error')}")

    values = result.get("values", {})
    quantity = clean["quantity"]
    if quantity not in values:
        return fail(f"driver returned no value for {quantity!r}")
    value = values[quantity]
    if not isinstance(value, (int, float)) or not math.isfinite(value):
        return fail(f"extracted QoI {quantity!r} is not finite ({value!r}) — refusing to return it")

    # A bounded, honest summary of the whole fixed set — never a raw dump.
    summary = ", ".join(f"{n}={values[n]:g}" for n in QOI_FIELDS if n in values)
    diagnostics = (f"rdkit descriptor_computation on "
                   f"{result.get('canonical_smiles', clean['smiles'])!r}; "
                   f"quantity {quantity}={value:g}; fixed summary: {summary}")
    return {"valid": True, "qoi": float(value),
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": round(time.time() - wall_start, 3)}


# CLI:  venv/bin/python3 tools/run_rdkit.py     (runs the ethanol self-check)
if __name__ == "__main__":
    default = {"smiles": "CCO", "quantity": "MolWt"}
    print(json.dumps(run_rdkit(default), indent=2))
