"""
run_boltz2 — the Boltz-2 (neural structure + binding-affinity prediction)
wrapper. BIO Wave D.2. Plain, deterministic code. NO AI inside the execution
step, ever.

**DEFERRED (owner-ruled 2026-07-18):** Boltz-2 is a large neural model requiring
a GPU and downloaded weights; this colima/aarch64 host has no GPU. Enrolled
INERT (`calibrating`/`routable=False`), card §3A PENDING-PROVISIONING. The
pure-Python INPUT gate is proven now; a valid input returns the honest DEFERRED
state — never a fabricated prediction.

UN-DEFER REQUIREMENT (specific — a GPU tool with mismatched weights produces
confident garbage, the cas_offinder lesson): a **GPU host** + the **SPECIFIC
PINNED Boltz-2 weights from the official source** (Boltz-2, github.com/
jwohlwend/boltz — pin the release + checksum in this card at provisioning) + a
**KNOWN-ANSWER VALIDATION RUN** (a target with a known reference structure/
affinity must reproduce it) BEFORE any §3A number is trusted.

REGIME (structure_affinity_prediction, FILTER-class): predicted RMSD/affinity is
a RELATIVE screen within the model's training distribution — never absolute Kd,
never "the structure is correct".

Typed input:
    run_boltz2({"protein_sequence": "MKT...", "ligand": "CCO"|absent,
                "quantity": "affinity"|"rmsd"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
"""

from __future__ import annotations

import json
import re
import time

_REQUIRED_FIELDS = ("protein_sequence", "quantity")   # ligand is OPTIONAL
_OPTIONAL_FIELDS = ("ligand",)
QOI_FIELDS = ("affinity", "rmsd")
_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$", re.IGNORECASE)
MAX_SEQ_LEN = 5_000


class Boltz2InputError(ValueError):
    """The typed input is not a runnable prediction request."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise Boltz2InputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise Boltz2InputError(f"missing required field(s): {', '.join(missing)}")
    allowed = set(_REQUIRED_FIELDS) | set(_OPTIONAL_FIELDS)
    extra = [k for k in spec if k not in allowed]
    if extra:
        raise Boltz2InputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    seq = spec["protein_sequence"]
    if not isinstance(seq, str) or not _AA_RE.match(seq or ""):
        raise Boltz2InputError("'protein_sequence' must be a protein sequence (amino acids)")
    if len(seq) > MAX_SEQ_LEN:
        raise Boltz2InputError(f"'protein_sequence' is {len(seq)} chars, over {MAX_SEQ_LEN}")
    if spec["quantity"] not in QOI_FIELDS:
        raise Boltz2InputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    if "ligand" in spec and (not isinstance(spec["ligand"], str) or not spec["ligand"].strip()):
        raise Boltz2InputError("'ligand', when present, must be a non-empty SMILES string")
    return {"protein_sequence": seq.upper(), "quantity": spec["quantity"],
            "ligand": spec.get("ligand")}


def gpu_and_weights_available() -> str | None:
    """None when a GPU + validated pinned weights are present, else the honest
    DEFERRED reason. On this host: no GPU."""
    return ("no GPU + validated Boltz-2 weights on this host — DEFERRED. "
            "Provision a GPU host, install the PINNED official Boltz-2 weights, "
            "and pass a KNOWN-ANSWER validation run before trusting any number.")


def run_boltz2(spec: dict) -> dict:
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except Boltz2InputError as e:
        return fail(f"input rejected: {e}")
    reason = gpu_and_weights_available()
    if reason:
        return fail(f"substrate not ready: {reason}")
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the prediction path is wired at provisioning with the validated GPU "
        "+ pinned weights; unreachable while gpu_and_weights_available() defers")


if __name__ == "__main__":
    print(json.dumps(run_boltz2({"protein_sequence": "MKTAYIAKQR", "quantity": "affinity"}), indent=2))
