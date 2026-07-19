"""
run_alphafold_db — the AlphaFold DB (predicted-structure lookup) wrapper.
BIO Wave D.2 (deferred) -> D.4-network un-defer. Plain, deterministic. NO AI in
execution.

UN-DEFERRED FOR NETWORK (owner-ruled 2026-07-19): the AlphaFold DB (AFDB) REST
endpoint is reachable from this host, so the lookup path is WIRED and returns a
REAL mean pLDDT — never a fabricated one. The original defer was network-only
(no GPU involved); working network was the whole un-defer requirement.

INPUT SHAPE RULING (owner, 2026-07-19): the typed input is
{uniprot_accession, quantity}, NOT {protein_sequence, quantity}. AFDB is keyed
ONLY by UniProt accession (there is no by-sequence endpoint), so an accession is
what makes this a true single-hop LOOKUP. The old protein_sequence shape was a
mismatch inherited from a shared-signature idea with boltz2 (deferred, GPU); the
pairing bought nothing here and is dropped. mean_pLDDT is read directly from the
prediction record's globalMetricValue (the AFDB global mean pLDDT).

*** PERMANENT TRUST CLAIM — NOT just a provisioning gate ***
This is a LOOKUP-class substrate: even with the network working, the result is
**NEVER TRUSTED ALONE — corroboration is required** (the web_search precedent).
That never-trust-alone status is this substrate's STANDING C1-hole (card A3), in
force forever. Un-deferring on network grounds does NOT lift it — every success
diagnostic surfaces it.

REGIME (predicted_structure_lookup). Retrieve a PRECOMPUTED AlphaFold structure's
mean pLDDT for a UniProt accession — a lookup, not a prediction run.

Typed input: run_alphafold_db({"uniprot_accession": "P0DP23", "quantity": "mean_pLDDT"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}

THREE OUTCOMES beyond a bad input (the network jails, proven by triggering):
  * SUCCESS               -> valid=True,  qoi=mean_pLDDT (never-trust-alone noted);
  * NOT FOUND (honest)    -> valid=False, qoi=None, a not-found diagnostic that is
                             DISTINCT from a network failure (a well-formed
                             accession with no AFDB entry — never a fabricated
                             pLDDT);
  * ENDPOINT UNREACHABLE  -> valid=False, qoi=None, a setup_error diagnostic (DNS
                             failure / timeout / 5xx) — the search could not run.
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

_REQUIRED_FIELDS = ("uniprot_accession", "quantity")
QOI_FIELDS = ("mean_pLDDT",)

# UniProt accession grammar (the official pattern), upper-cased before match:
# a 6- or 10-char accession. AFDB is keyed by exactly this identifier.
_ACCESSION_RE = re.compile(
    r"^[OPQ][0-9][A-Z0-9]{3}[0-9]$"
    r"|^[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$"
)

# AFDB prediction endpoint (UniProt-accession-keyed). The global mean pLDDT is
# the record's `globalMetricValue`.
AFDB_ENDPOINT = "https://alphafold.ebi.ac.uk/api/prediction/{accession}"
HTTP_TIMEOUT_S = 20.0
USER_AGENT = "research-system/bio-alphafold_db-lookup (predicted-structure lookup)"

# Permanent never-trust-alone note appended to every success diagnostic.
_NTA_NOTE = ("NEVER-TRUSTED-ALONE: a looked-up pLDDT is AlphaFold model "
             "self-confidence, NOT experimental accuracy; corroboration is "
             "required (permanent, card A3).")


class AlphaFoldDBInputError(ValueError):
    """The typed input is not a runnable AFDB lookup request."""


class AlphaFoldDBNetworkError(RuntimeError):
    """The AFDB endpoint could not be reached (DNS/timeout/transport) — a
    could-not-run condition, DISTINCT from a well-formed-but-absent accession."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise AlphaFoldDBInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise AlphaFoldDBInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise AlphaFoldDBInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    acc = spec["uniprot_accession"]
    if not isinstance(acc, str) or not _ACCESSION_RE.match((acc or "").strip().upper()):
        raise AlphaFoldDBInputError(
            "'uniprot_accession' must be a well-formed UniProt accession "
            "(e.g. P0DP23) — AFDB is keyed by accession, not by sequence")
    if spec["quantity"] not in QOI_FIELDS:
        raise AlphaFoldDBInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"uniprot_accession": acc.strip().upper(), "quantity": spec["quantity"]}


def _http_get(url: str, timeout: float = HTTP_TIMEOUT_S) -> tuple[int, str]:
    """GET `url`, returning (http_status, body_text). A REACHED endpoint that
    answers with an error status (400/404/5xx) returns that status and body — it
    is not a transport failure. Only a genuine transport failure (DNS, timeout,
    connection refused/reset) raises AlphaFoldDBNetworkError, so the wrapper can
    tell a missing record from an unreachable endpoint."""
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
        raise AlphaFoldDBNetworkError(
            f"AFDB endpoint unreachable ({type(e).__name__}: {e})") from e


def run_alphafold_db(spec: dict, *, http_get=_http_get,
                     endpoint: str = AFDB_ENDPOINT) -> dict:
    """Look up a UniProt accession's AlphaFold mean pLDDT. `http_get` and
    `endpoint` are injection seams: production uses the real ones; the offline
    test suite injects a fake http_get, and the live network-jail proof points
    `endpoint` at an unreachable host to trigger the real transport failure."""
    wall_start = time.time()

    def done(valid, qoi, msg):
        return {"valid": valid, "qoi": qoi, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except AlphaFoldDBInputError as e:
        return done(False, None, f"input rejected: {e}")

    url = endpoint.format(accession=clean["uniprot_accession"])
    try:
        status, body = http_get(url)
    except AlphaFoldDBNetworkError as e:
        return done(False, None, f"setup_error: {e} — the lookup could not run; "
                                 "no pLDDT was fabricated")

    if status != 200:
        # A REACHED endpoint answering 400/404 is a not-found for a well-formed
        # accession with no AFDB entry (honest, DISTINCT from unreachable). A 5xx
        # is the server failing to serve -> could-not-run (setup_error class).
        if 500 <= status < 600:
            return done(False, None, f"setup_error: AFDB endpoint returned HTTP "
                                     f"{status} — the lookup could not run; no "
                                     "pLDDT was fabricated")
        return done(False, None, f"not_found: no AlphaFold entry for accession "
                                 f"{clean['uniprot_accession']} (HTTP {status}); "
                                 "this is a resolved not-found, not a network "
                                 "failure — no pLDDT was fabricated")

    try:
        records = json.loads(body)
        value = records[0]["globalMetricValue"]
        plddt = float(value)
    except (ValueError, KeyError, IndexError, TypeError):
        return done(False, None, f"not_found: AFDB returned no usable pLDDT for "
                                 f"accession {clean['uniprot_accession']} — no "
                                 "pLDDT was fabricated")

    return done(True, plddt, f"mean_pLDDT={plddt} for {clean['uniprot_accession']} "
                             f"via AFDB. {_NTA_NOTE}")


if __name__ == "__main__":
    print(json.dumps(run_alphafold_db({"uniprot_accession": "P0DP23",
                                       "quantity": "mean_pLDDT"}), indent=2))
