# Envelope Card — (alphafold_db, predicted_structure_lookup)

> **STATUS: NETWORK-UN-DEFERRED 2026-07-19 (owner-ruled). §3A FILLED from real
> AFDB calls.** The AFDB endpoint is reachable; the lookup path is WIRED and
> returns a REAL mean pLDDT. LOOKUP-class: **NEVER-TRUSTED-ALONE is PERMANENT**
> and is NOT lifted by un-deferring (card A3). ENROLLED `calibrating`/
> `routable=False` — calibration pending; promotion (routable+mature) is a
> SEPARATE later step on clean gate-track calibration. `contract_for` still
> raises until that flip.

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `alphafold_db` (**ENROLLED**, `calibrating`/`routable=False`; network-un-deferred, promotion pending) |
| Regime | **predicted_structure_lookup**: retrieve a precomputed AlphaFold structure's mean pLDDT for a UniProt accession — a lookup, not a prediction. |
| Tool | AlphaFold DB REST API (`https://alphafold.ebi.ac.uk/api/prediction/{accession}`). **Reachable + verified 2026-07-19.** |
| Wrapper | `tools/run_alphafold_db.py` (input gate + real network lookup wired; injectable `http_get`/`endpoint` seams for offline tests) |
| Class | **lookup** — structurally NEVER-TRUSTED-ALONE (web_search precedent) |

**INPUT-SHAPE RULING (owner, 2026-07-19).** The typed input is
`{uniprot_accession, quantity}`, **not** `{protein_sequence, quantity}`. AFDB is
keyed ONLY by UniProt accession (there is no by-sequence endpoint; a raw sequence
returns HTTP 400 and does not resolve to an accession via any simple query), so an
accession is what makes this a true single-hop lookup. The old `protein_sequence`
shape was a mismatch inherited from a shared-signature idea with `boltz2`
(deferred, GPU) — that L1a pairing is **DROPPED**; the new `{uniprot_accession,
quantity}` signature is unique/disjoint, which also removes a latent R-B-1 tie.
`mean_pLDDT` is read directly from the record's `globalMetricValue` (the AFDB
global mean pLDDT).

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input gate measured. Network lookup wired +
§3A measured from real AFDB calls, 2026-07-19.

## 3. Validated envelope
### 3A. Measured network-reliability envelope (from REAL calls, 2026-07-19)
The "envelope" for a lookup is its network-reliability behavior, characterized
against the live endpoint:
- **Reachability + latency.** `data.rcsb`-class fast: real success calls returned
  in **~0.12–0.14 s** (P0DP23 → mean_pLDDT **85.25**; P01308 → **52.91**). Wrapper
  timeout `HTTP_TIMEOUT_S = 20 s`.
- **Success shape.** HTTP 200, JSON list; `globalMetricValue` is the global mean
  pLDDT (a float 0–100). Wrapper returns `valid=True`, `qoi=<pLDDT>`, and every
  success diagnostic carries the permanent NEVER-TRUSTED-ALONE note.
- **Not-found shape (DISTINCT from a network failure).** A well-formed accession
  with no AFDB entry (e.g. `A0A0A0A0A0`) → **HTTP 404**; a malformed identifier →
  **HTTP 400**. Both map to `valid=False`, `qoi=None`, a `not_found:` diagnostic —
  never a fabricated pLDDT.
- **Endpoint-unreachable shape (the network jail).** DNS failure / timeout /
  connection error → `AlphaFoldDBNetworkError` → `valid=False`, `qoi=None`, a
  `setup_error:` diagnostic. Triggered LIVE by pointing `endpoint` at an
  unreachable host (real `URLError`, ~0.05 s). A 5xx from a reached endpoint is
  also classed `setup_error` (server failed to serve).

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **A1 — endpoint gate** | `CHECKABLE` | AFDB endpoint reachable (round-trip) | reachable → the accession resolves or is an honest not-found; unreachable/5xx → **setup_error/defer** |
| **A2** | `CHECKABLE:membership` (pre-run) | uniprot_accession well-formed; quantity ∈ {mean_pLDDT} | valid → eligible; else → **setup_error** (proven) |
| **A3 (C1-hole) — PERMANENT never-trust-alone** | **JUDGMENT / STANDING** | none the gate can read | pLDDT is model SELF-confidence, NOT experimental accuracy; AND — permanently, even with the network working — a lookup is **NEVER TRUSTED ALONE; corroboration is REQUIRED**. A standing trust claim, not a provisioning gate. **Trust-split (recalibrated 2026-07-19):** in-envelope → **REFINE** (the retrieved pLDDT is usable as a corroborating model-confidence screen, never the sole basis for a claim — a never-trust-alone lookup has no honest standalone TRUST verdict); over-reads (experimental accuracy / sole basis / local-from-global / function) → **defer**. |

## 4. Known failure modes
- **4A. Endpoint unreachable / 5xx → setup_error (defer).** Proven by triggering.
- **4B. pLDDT trusted alone / read as experimental accuracy → defer (A3, PERMANENT).** Corroboration always required. In-envelope honest use (pLDDT as a corroborating model-confidence screen) → **REFINE**, never trust.
- **4C. Missing/malformed accession → honest not-found (404/400), NOT a network failure.** Proven by triggering; never a fabricated pLDDT.
- **4D. Bad input (field shape / quantity) → setup_error (A2).** Proven.

## 5. Diagnostics CAN/CANNOT
CAN: input validity (A2); endpoint reachability + resolved-not-found (A1). CANNOT:
whether the pLDDT matches experimental accuracy; disordered/low-pLDDT regions (A3).

## 6. Extraction contract
Input `{uniprot_accession, quantity}`; QoI = `mean_pLDDT` (`QOI_FIELDS`), read from
the prediction record's `globalMetricValue`. Signature `{uniprot_accession,
quantity}` is UNIQUE among enrolled substrates (the boltz2 `{protein_sequence,
quantity}` pairing is retired) — routes to itself with no R-B-1 tie (re-proven at
promotion). **NEVER-TRUSTED-ALONE always.**

## 7. Cost model — one network round-trip, ~0.12–0.14 s measured (no rate-limit hit observed at single-lookup cadence).

## 8. Negative space + open watches
Out of scope: trusting pLDDT alone (A3); experimental-accuracy claims. Watches:
(1) **A3 never-trust-alone is PERMANENT** (survives un-deferring and any future
promotion); (2) reviewer pending; (3) promotion (routable+mature) deferred to a
separate flip on clean gate-track calibration — `contract_for` raises until then;
(4) the routing re-proof for the new `{uniprot_accession, quantity}` signature
lands at that promotion (select_substrate uniqueness).
