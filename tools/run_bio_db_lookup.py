"""
run_bio_db_lookup — the biological-database lookup wrapper (PDB / PubChem /
UniProt / ChEMBL). BIO Wave D.2. Plain, deterministic. NO AI in execution.

**DEFERRED (owner-ruled 2026-07-18):** a 4-API network wrapper; none of the four
endpoints is reachable/verified from this host. Enrolled INERT; card §3A
PENDING-PROVISIONING. The pure-Python INPUT gate (incl. per-database id form) is
proven now; a valid input returns the honest DEFERRED state — never a fabricated
record.

UN-DEFER REQUIREMENT (specific — this is a FOUR-endpoint tool): **ALL FOUR
endpoints (PDB, PubChem, UniProt, ChEMBL) reachable**, each with a round-trip
check. **One endpoint down = PARTIAL defer** (that database stays deferred), NOT
a full un-defer.

*** PERMANENT TRUST CLAIM ***
LOOKUP-class: even once un-deferred, a record is **NEVER TRUSTED ALONE —
corroboration required** (the web_search precedent). Standing, not a provisioning
gate. And the database's own curation currency/correctness is unverifiable from
inside — a stale/erroneous record looks identical to a good one.

Typed input: run_bio_db_lookup({"database": "uniprot", "record_id": "P0DP23",
                                "quantity": "round_trip_id"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
(round_trip_id is a 0/1 success indicator; a resolved record returns 1.0.)
"""
from __future__ import annotations
import json, re, time

_REQUIRED_FIELDS = ("database", "record_id", "quantity")
DATABASE_ALLOWLIST = ("pdb", "pubchem", "uniprot", "chembl")
QOI_FIELDS = ("round_trip_id",)

# Light per-namespace id-form checks (a real input jail: a malformed id for the
# chosen database is refused pre-run).
_ID_FORMS = {
    "pdb": re.compile(r"^[0-9][A-Za-z0-9]{3}$"),          # e.g. 1ABC
    "pubchem": re.compile(r"^\d+$"),                       # numeric CID
    "uniprot": re.compile(r"^[A-Za-z0-9]{6,10}$"),         # accession
    "chembl": re.compile(r"^CHEMBL\d+$", re.IGNORECASE),  # CHEMBL25
}


class BioDBLookupInputError(ValueError):
    """The typed input is not a runnable DB lookup request."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise BioDBLookupInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise BioDBLookupInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise BioDBLookupInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    db = spec["database"]
    if db not in DATABASE_ALLOWLIST:
        raise BioDBLookupInputError(
            f"database {db!r} is not on the allowlist "
            f"(allowed: {', '.join(DATABASE_ALLOWLIST)})")
    rid = spec["record_id"]
    if not isinstance(rid, str) or not rid.strip():
        raise BioDBLookupInputError("'record_id' must be a non-empty string")
    if not _ID_FORMS[db].match(rid.strip()):
        raise BioDBLookupInputError(
            f"'record_id' {rid!r} is not a well-formed {db} id")
    if spec["quantity"] not in QOI_FIELDS:
        raise BioDBLookupInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"database": db, "record_id": rid.strip(), "quantity": spec["quantity"]}


def endpoint_available(database: str) -> str | None:
    """None when THIS database's endpoint is reachable/verified, else the
    DEFERRED reason. On this host: no endpoint is reachable. Per-database so a
    single endpoint being down is a PARTIAL defer, not a full one."""
    return (f"the {database} endpoint is not reachable/verified from this host — "
            f"DEFERRED. Un-defer requires ALL FOUR endpoints reachable (one down "
            f"= that database stays deferred). NOTE: a record is "
            f"NEVER-TRUSTED-ALONE (corroboration required, permanent).")


def run_bio_db_lookup(spec: dict) -> dict:
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except BioDBLookupInputError as e:
        return fail(f"input rejected: {e}")
    reason = endpoint_available(clean["database"])
    if reason:
        return fail(f"substrate not ready: {reason}")
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the lookup path is wired at provisioning with a reachable endpoint; "
        "unreachable while endpoint_available() defers. When wired, the record "
        "is reported NEVER-TRUSTED-ALONE (corroboration required).")


if __name__ == "__main__":
    print(json.dumps(run_bio_db_lookup({"database": "uniprot", "record_id": "P0DP23", "quantity": "round_trip_id"}), indent=2))
