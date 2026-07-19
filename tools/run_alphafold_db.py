"""
run_alphafold_db — the AlphaFold DB (predicted-structure lookup) wrapper.
BIO Wave D.2. Plain, deterministic. NO AI in execution.

**DEFERRED (owner-ruled 2026-07-18):** a network lookup against the AlphaFold DB
(AFDB) endpoint, which is not reachable/verified from this host. Enrolled INERT;
card §3A PENDING-PROVISIONING. The pure-Python INPUT gate is proven now; a valid
input returns the honest DEFERRED state — never a fabricated pLDDT.

UN-DEFER REQUIREMENT (specific): **working network + the specific AFDB endpoint
reachable** (record the endpoint URL + a round-trip check at provisioning).

*** PERMANENT TRUST CLAIM — NOT just a provisioning gate ***
This is a LOOKUP-class substrate: even once un-deferred and the network works,
the result is **NEVER TRUSTED ALONE — corroboration is required** (the web_search
precedent). That never-trust-alone status is this substrate's STANDING C1-hole,
in force forever, not merely a provisioning condition.

REGIME (predicted_structure_lookup). Retrieve a PRECOMPUTED AlphaFold structure's
mean pLDDT for a sequence — a lookup, not a prediction run.

Typed input: run_alphafold_db({"protein_sequence": "MKT...", "quantity": "mean_pLDDT"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
"""
from __future__ import annotations
import json, re, time

_REQUIRED_FIELDS = ("protein_sequence", "quantity")
QOI_FIELDS = ("mean_pLDDT",)
_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWY]+$", re.IGNORECASE)
MAX_SEQ_LEN = 5_000


class AlphaFoldDBInputError(ValueError):
    """The typed input is not a runnable AFDB lookup request."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise AlphaFoldDBInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise AlphaFoldDBInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise AlphaFoldDBInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    seq = spec["protein_sequence"]
    if not isinstance(seq, str) or not _AA_RE.match(seq or ""):
        raise AlphaFoldDBInputError("'protein_sequence' must be a protein sequence (amino acids)")
    if len(seq) > MAX_SEQ_LEN:
        raise AlphaFoldDBInputError(f"'protein_sequence' is {len(seq)} chars, over {MAX_SEQ_LEN}")
    if spec["quantity"] not in QOI_FIELDS:
        raise AlphaFoldDBInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"protein_sequence": seq.upper(), "quantity": spec["quantity"]}


def afdb_endpoint_available() -> str | None:
    """None when the AFDB endpoint is reachable/verified, else the DEFERRED
    reason. On this host: network to the AFDB endpoint is not available/verified."""
    return ("the AlphaFold DB endpoint is not reachable/verified from this host "
            "— DEFERRED. Provision working network + the specific AFDB endpoint, "
            "with a round-trip check. NOTE: even then this LOOKUP is "
            "NEVER-TRUSTED-ALONE — corroboration is required (permanent).")


def run_alphafold_db(spec: dict) -> dict:
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except AlphaFoldDBInputError as e:
        return fail(f"input rejected: {e}")
    reason = afdb_endpoint_available()
    if reason:
        return fail(f"substrate not ready: {reason}")
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the AFDB lookup path is wired at provisioning with a reachable "
        "endpoint; unreachable while afdb_endpoint_available() defers. When wired, "
        "the pLDDT is reported NEVER-TRUSTED-ALONE (corroboration required).")


if __name__ == "__main__":
    print(json.dumps(run_alphafold_db({"protein_sequence": "MKTAYIAKQR", "quantity": "mean_pLDDT"}), indent=2))
