"""
run_bio_db_lookup — the biological-database lookup wrapper (PDB / PubChem /
UniProt / ChEMBL). BIO Wave D.2 (deferred) -> D.4-network un-defer. Plain,
deterministic. NO AI in execution.

UN-DEFERRED FOR NETWORK (owner-ruled 2026-07-19): all four endpoints are
reachable from this host, so the per-database lookup path is WIRED and returns a
REAL round-trip resolution — never a fabricated record. The original defer was
network-only (no GPU); reachable endpoints were the whole un-defer requirement.

UN-DEFER SHAPE (a FOUR-endpoint tool): the tool is FULLY live only when ALL FOUR
endpoints are reachable. **One endpoint down = PARTIAL defer** — a lookup against
the down database defers (setup_error), while the other three still resolve. Per
call, only the requested database's endpoint must be reachable.

*** PERMANENT TRUST CLAIM ***
LOOKUP-class: even with the network working, a record is **NEVER TRUSTED ALONE —
corroboration required** (the web_search precedent; card D3). Standing, not a
provisioning gate. AND the database's own curation currency/correctness is
unverifiable from inside — a stale/erroneous record looks identical to a good one.
Un-deferring on network grounds does NOT lift either; every success diagnostic
surfaces it.

Typed input: run_bio_db_lookup({"database": "uniprot", "record_id": "P0DP23",
                                "quantity": "round_trip_id"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
(round_trip_id is a 0/1 success indicator; a resolved record returns 1.0.)

THREE OUTCOMES beyond a bad input (the network jails, proven by triggering):
  * RESOLVED              -> valid=True,  qoi=1.0 (never-trust-alone noted);
  * NOT FOUND (honest)    -> valid=False, qoi=None, a not-found diagnostic DISTINCT
                             from a network failure (a well-formed id that does not
                             resolve — incl. the subtle HTTP-200-but-empty shapes
                             PubChem/UniProt return; never a fabricated record);
  * ENDPOINT UNREACHABLE  -> valid=False, qoi=None, a setup_error diagnostic (DNS
                             failure / timeout / 5xx / throttle) — this database's
                             lookup could not run (the PARTIAL-defer path).
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request

try:  # certifi is already present in venv/ (the scholar_search.py precedent).
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except Exception:  # pragma: no cover - fallback if certifi is unavailable
    _SSL_CONTEXT = ssl.create_default_context()

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

# Per-database lookup endpoints (verified reachable 2026-07-19). {id} is the
# validated record_id. A module dict so the live PARTIAL-defer proof can override
# one endpoint to an unreachable host without touching the others.
_ENDPOINTS = {
    "pdb": "https://data.rcsb.org/rest/v1/core/entry/{id}",
    "pubchem": ("https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{id}"
                "/property/MolecularFormula/JSON"),
    "uniprot": "https://rest.uniprot.org/uniprotkb/{id}.json",
    "chembl": "https://www.ebi.ac.uk/chembl/api/data/molecule/{id}.json",
}

# Known-resolvable ids per database, for the reachability probe (§3A / un-defer
# check). Real records: hemoglobin, aspirin, calmodulin, aspirin.
PROVISIONING_IDS = {
    "pdb": "4HHB", "pubchem": "2244", "uniprot": "P0DP23", "chembl": "CHEMBL25",
}

HTTP_TIMEOUT_S = 20.0
USER_AGENT = "research-system/bio-db_lookup (record lookup, corroboration-only)"

_NTA_NOTE = ("NEVER-TRUSTED-ALONE: a looked-up record is corroboration only "
             "(permanent, card D3); the DB's curation currency/correctness is "
             "unverifiable from inside — a stale record looks like a good one.")


class BioDBLookupInputError(ValueError):
    """The typed input is not a runnable DB lookup request."""


class BioDBLookupNetworkError(RuntimeError):
    """The requested database's endpoint could not be reached (DNS/timeout/
    transport) — a could-not-run condition (the partial-defer path), DISTINCT
    from a well-formed-but-absent record."""


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


def _http_get(url: str, timeout: float = HTTP_TIMEOUT_S) -> tuple[int, str]:
    """GET `url`, returning (http_status, body_text). A REACHED endpoint that
    answers with any status returns that status and body — it is not a transport
    failure. Only a genuine transport failure (DNS, timeout, connection error)
    raises BioDBLookupNetworkError, so the wrapper can tell a missing record from
    an unreachable endpoint (the partial-defer distinction)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:  # reached; answered with an error status
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        return e.code, body
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise BioDBLookupNetworkError(
            f"{type(e).__name__}: {e}") from e


def _resolved(database: str, status: int, body: str) -> bool:
    """Did the id RESOLVE to a real record? Per-namespace, because several DBs
    answer a missing id with HTTP 200 (PubChem returns 200 with the CID but no
    property; UniProt returns 200 with entryType 'Inactive' for a deleted
    accession) — a naive 200-check would read those as success and fabricate a
    resolution. Verified against real endpoints 2026-07-19."""
    if status != 200:
        return False
    if database == "pubchem":
        try:
            props = json.loads(body)["PropertyTable"]["Properties"]
            return bool(props) and "MolecularFormula" in props[0]
        except (ValueError, KeyError, IndexError, TypeError):
            return False
    if database == "uniprot":
        try:
            return json.loads(body).get("entryType") != "Inactive"
        except ValueError:
            return False
    # pdb, chembl: a 200 with a body IS the resolved record.
    return True


def run_bio_db_lookup(spec: dict, *, http_get=_http_get, endpoints=_ENDPOINTS) -> dict:
    """Round-trip a record id against its authoritative database. `http_get` and
    `endpoints` are injection seams: production uses the real ones; the offline
    suite injects a fake http_get, and the live PARTIAL-defer proof overrides one
    database's endpoint with an unreachable host to trigger the real transport
    failure for that database alone."""
    wall_start = time.time()

    def done(valid, qoi, msg):
        return {"valid": valid, "qoi": qoi, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except BioDBLookupInputError as e:
        return done(False, None, f"input rejected: {e}")

    db, rid = clean["database"], clean["record_id"]
    url = endpoints[db].format(id=rid)
    try:
        status, body = http_get(url)
    except BioDBLookupNetworkError as e:
        return done(False, None, f"setup_error: the {db} endpoint is unreachable "
                                 f"({e}) — this database's lookup could not run "
                                 "(PARTIAL defer); no record was fabricated")

    if status in (403, 408, 429) or 500 <= status < 600:
        return done(False, None, f"setup_error: the {db} endpoint returned HTTP "
                                 f"{status} — the lookup could not run (PARTIAL "
                                 "defer); no record was fabricated")

    if _resolved(db, status, body):
        return done(True, 1.0, f"round_trip_id=1 — {db} record {rid} resolved "
                               f"(HTTP {status}). {_NTA_NOTE}")

    return done(False, None, f"not_found: {db} record {rid} did not resolve (HTTP "
                             f"{status}); this is a resolved not-found, not a "
                             "network failure — no record was fabricated")


def probe_endpoints(http_get=_http_get, endpoints=_ENDPOINTS) -> dict:
    """Provisioning reachability check for §3A / the un-defer condition: round-
    trip a known-good id against EACH of the four endpoints and report per-
    database {reachable, resolved, status, note}. FULLY live iff all four
    resolve; any unreachable one is a PARTIAL-defer database. NO fabrication —
    a transport failure is reported as reachable=False."""
    report = {}
    for db, rid in PROVISIONING_IDS.items():
        url = endpoints[db].format(id=rid)
        rec = {"probe_id": rid}
        try:
            status, body = http_get(url)
            rec["reachable"] = True
            rec["status"] = status
            rec["resolved"] = _resolved(db, status, body)
        except BioDBLookupNetworkError as e:
            rec.update(reachable=False, status=None, resolved=False, note=str(e))
        report[db] = rec
    report["fully_live"] = all(
        report[db].get("resolved") for db in DATABASE_ALLOWLIST
    )
    return report


if __name__ == "__main__":
    print(json.dumps(run_bio_db_lookup({"database": "uniprot", "record_id": "P0DP23",
                                        "quantity": "round_trip_id"}), indent=2))
    print(json.dumps(probe_endpoints(), indent=2))
