# Envelope Card — (bio_db_lookup, record_db_lookup)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. DEFERRED** (network: none of the
> four endpoints reachable here). Ruled fields + pure-Python input jails (incl.
> per-database id form) proven now. HUMAN-FACING ONLY. ENROLLED
> `calibrating`/`routable=False` — inert (`contract_for` raises).

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `bio_db_lookup` (PDB/PubChem/UniProt/ChEMBL; **ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **record_db_lookup**: retrieve a record by id from an authoritative DB (the `database` field selects which). |
| Tool | 4 network APIs (PDB, PubChem, UniProt, ChEMBL). **Pinned: no endpoint reachable here.** A 4-API wrapper — the most expensive single wrapper in the wave. |
| Wrapper | `tools/run_bio_db_lookup.py` (input gate proven; lookups wired at provisioning) |
| Class | **lookup** — structurally NEVER-TRUSTED-ALONE (web_search precedent) |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input gate measured; no lookup envelope (no network). DEFERRED.

## 3. Validated envelope
### 3A. PENDING-PROVISIONING
No lookups here. **UN-DEFER (specific — a FOUR-endpoint tool):** **ALL FOUR
endpoints (PDB, PubChem, UniProt, ChEMBL) reachable**, each with a round-trip
check. **One endpoint down = PARTIAL defer** (that database stays deferred), NOT a
full un-defer.

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **D1 — per-endpoint gate** | `CHECKABLE` (per database) | the requested `database`'s endpoint is reachable | reachable → the id resolves; unreachable → **defer** (that database only) |
| **D2** | `CHECKABLE:membership` (pre-run) | database ∈ allowlist; record_id well-formed FOR THAT namespace; quantity ∈ {round_trip_id} | valid → eligible; else → **setup_error** (proven now, incl. per-namespace id form) |
| **D3 (C1-hole) — PERMANENT never-trust-alone + curation gap** | **JUDGMENT / STANDING** | none the gate can read | a record is NEVER TRUSTED ALONE (corroboration required, permanent); AND the DB's own curation currency/correctness is unverifiable from inside — a stale/erroneous record looks identical to a good one → **defer**. |

## 4. Known failure modes
- **4A. Endpoint(s) unreachable → defer (per database).** Un-defer needs all four reachable (§3A); one down = partial.
- **4B. Record trusted alone / assumed curated-correct → defer (D3, PERMANENT).**
- **4C. Bad input (database / id form / quantity) → setup_error (D2).** Proven now, per namespace.

## 5. Diagnostics CAN/CANNOT
CAN: input validity incl. per-namespace id form (D2); (at provisioning) per-endpoint
reachability. CANNOT: whether the record is current/correct in the source DB (D3).

## 6. Extraction contract
Input `{database, record_id, quantity}`; QoI = `round_trip_id` (`QOI_FIELDS`).
**DEFERRED** now; **NEVER-TRUSTED-ALONE always**; per-endpoint partial defer.

## 7. Cost model — PENDING-PROVISIONING (4 network APIs, rate limits).

## 8. Negative space + open watches
Out of scope: trusting a record alone (D3); assuming curation currency. Watches:
(1) **un-defer = ALL FOUR endpoints reachable; one down = partial defer** (§3A);
(2) **D3 never-trust-alone is PERMANENT**; (3) reviewer pending; (4) registration
deferred — `contract_for` raises.
