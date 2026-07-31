# Envelope Card — (bio_db_lookup, record_db_lookup)

> **STATUS: NETWORK-UN-DEFERRED 2026-07-19 (owner-ruled). §3A FILLED from real
> calls against all four APIs.** All four endpoints (PDB, PubChem, UniProt,
> ChEMBL) are reachable, so the per-database lookup path is WIRED and returns a
> REAL round-trip resolution. LOOKUP-class: **NEVER-TRUSTED-ALONE is PERMANENT**
> and is NOT lifted by un-deferring (card D3). One endpoint down = **PARTIAL
> defer** (that database only), proven by triggering. ENROLLED `calibrating`/
> `routable=False` — promotion (routable+mature) is a SEPARATE later step on
> clean gate-track calibration; `contract_for` raises until then.

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `bio_db_lookup` (PDB/PubChem/UniProt/ChEMBL; **ENROLLED**, `calibrating`/`routable=False`; network-un-deferred, promotion pending) |
| Regime | **record_db_lookup**: retrieve a record by id from an authoritative DB (the `database` field selects which). |
| Tool | 4 network APIs, all reachable + verified 2026-07-19: PDB (`data.rcsb.org`), PubChem (`pubchem.ncbi.nlm.nih.gov`), UniProt (`rest.uniprot.org`), ChEMBL (`www.ebi.ac.uk/chembl`). A 4-API wrapper — the most expensive single wrapper in the wave. |
| Wrapper | `tools/run_bio_db_lookup.py` (input gate incl. per-namespace id form + real per-database lookup wired; injectable `http_get`/`endpoints` seams; `probe_endpoints()` reachability check) |
| Class | **lookup** — structurally NEVER-TRUSTED-ALONE (web_search precedent) |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input gate measured. Per-database lookup wired +
§3A measured from real calls against all four APIs, 2026-07-19.

## 3. Validated envelope
### 3A. Measured network-reliability envelope (from REAL calls, 2026-07-19)
`probe_endpoints()` round-tripped a known-good id against each of the four APIs —
**all four reachable + resolved → `fully_live: true`** (the un-defer condition):
- **Reachability + latency.** All four fast: PDB **~0.07–0.29 s** (4HHB), PubChem
  **~0.15 s** (CID 2244), UniProt **~0.6 s** (P0DP23), ChEMBL **~0.44 s**
  (CHEMBL25). Wrapper timeout `HTTP_TIMEOUT_S = 20 s`.
- **Success shape.** `valid=True`, `qoi=round_trip_id=1.0`; every success
  diagnostic carries the permanent NEVER-TRUSTED-ALONE note.
- **Not-found shapes (DISTINCT from a network failure) — PER NAMESPACE.** Several
  DBs answer a missing id with **HTTP 200**, so a naive 200-check would fabricate
  a resolution. Measured and handled:
  - **PDB / ChEMBL**: missing → **HTTP 404** (e.g. `0AAA`, `CHEMBL999999999`).
  - **PubChem**: missing CID → **HTTP 200** with the CID but **no
    `MolecularFormula`** (e.g. `999999999`) — resolution requires the property.
  - **UniProt**: deleted accession → **HTTP 200** with **`entryType:"Inactive"`**
    (e.g. `X0X0X0`); malformed → **HTTP 400** — resolution requires an active
    entry.
  All map to `valid=False`, `qoi=None`, a `not_found:` diagnostic — never a
  fabricated record.
- **Endpoint-unreachable / PARTIAL-defer shape (the network jail).** DNS failure /
  timeout / connection error → `BioDBLookupNetworkError` → `valid=False`, a
  `setup_error: … (PARTIAL defer)` diagnostic. Proven LIVE by overriding ONLY the
  UniProt endpoint to an unreachable host: the UniProt lookup deferred while a
  PDB lookup still resolved — one endpoint down is a per-database partial defer,
  not a full one. A 403/408/429/5xx from a reached endpoint is also
  `setup_error` (throttled / server failed to serve).

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **D1 — per-endpoint gate** | `CHECKABLE` (per database) | the requested `database`'s endpoint is reachable | reachable → the id resolves or is an honest not-found; unreachable/5xx/throttle → **setup_error/defer** (that database only = PARTIAL) |
| **D2** | `CHECKABLE:membership` (pre-run) | database ∈ allowlist; record_id well-formed FOR THAT namespace; quantity ∈ {round_trip_id} | valid → eligible; else → **setup_error** (proven, incl. per-namespace id form) |
| **D3 (C1-hole) — PERMANENT never-trust-alone + curation gap** | **JUDGMENT / STANDING** | none the gate can read | a record is NEVER TRUSTED ALONE (corroboration required, permanent); AND the DB's own curation currency/correctness is unverifiable from inside — a stale/erroneous record looks identical to a good one. **Trust-split (recalibrated 2026-07-19):** in-envelope → **REFINE** (a resolved record is usable as a corroborating cross-reference/screen, never the sole basis for a claim — a never-trust-alone lookup has no honest standalone TRUST verdict); over-reads (sole basis / assumed curation-current / fact-from-presence) → **defer**. |

## 4. Known failure modes
- **4A. Endpoint(s) unreachable / 5xx / throttle → setup_error (PARTIAL defer, per database).** Proven by triggering; all four reachable = fully live, one down = partial.
- **4B. Record trusted alone / assumed curated-correct → defer (D3, PERMANENT).** In-envelope honest use (a resolved record as a corroborating cross-reference/screen) → **REFINE**, never trust.
- **4C. Missing/absent id → honest not-found (incl. the HTTP-200 PubChem/UniProt traps), NOT a network failure.** Proven by triggering; never a fabricated record.
- **4D. Bad input (database / id form / quantity) → setup_error (D2).** Proven, per namespace.

## 5. Diagnostics CAN/CANNOT
CAN: input validity incl. per-namespace id form (D2); per-endpoint reachability +
resolved-not-found incl. the HTTP-200 traps (D1). CANNOT: whether the record is
current/correct in the source DB (D3).

## 6. Extraction contract
Input `{database, record_id, quantity}`; QoI = `round_trip_id` (`QOI_FIELDS`;
resolved = 1.0). **DEFERRED** removed; **NEVER-TRUSTED-ALONE always**; per-endpoint
partial defer.

## 7. Cost model — one network round-trip per lookup, ~0.07–0.6 s measured across the four APIs (no rate-limit hit at single-lookup cadence).

## 8. Negative space + open watches
Out of scope: trusting a record alone (D3); assuming curation currency. Watches:
(1) **all four reachable = fully live; one down = PARTIAL defer** (§3A, proven);
(2) **D3 never-trust-alone is PERMANENT** (survives un-deferring and any future
promotion); (3) reviewer pending; (4) promotion (routable+mature) deferred to a
separate flip on clean gate-track calibration — `contract_for` raises until then.
