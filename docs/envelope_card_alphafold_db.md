# Envelope Card — (alphafold_db, predicted_structure_lookup)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. DEFERRED** (network: the AFDB
> endpoint is not reachable/verified here). Ruled fields + pure-Python input
> jails proven now. HUMAN-FACING ONLY. ENROLLED `calibrating`/`routable=False` —
> inert (`contract_for` raises).

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `alphafold_db` (**ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **predicted_structure_lookup**: retrieve a precomputed AlphaFold structure's mean pLDDT for a sequence — a lookup, not a prediction. |
| Tool | AlphaFold DB (network API). **Pinned: endpoint not reachable/verified here.** |
| Wrapper | `tools/run_alphafold_db.py` (input gate proven; lookup wired at provisioning) |
| Class | **lookup** — structurally NEVER-TRUSTED-ALONE (web_search precedent) |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input gate measured; no lookup envelope (no network). DEFERRED.

## 3. Validated envelope
### 3A. PENDING-PROVISIONING
No lookups here. **UN-DEFER (specific):** **working network + the specific AFDB
endpoint reachable** (record the endpoint URL + a round-trip check).

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **A1 — endpoint gate** | `CHECKABLE` | AFDB endpoint reachable (round-trip) | reachable → the id resolves; unreachable → **defer** |
| **A2** | `CHECKABLE:membership` (pre-run) | protein_sequence valid; quantity ∈ {mean_pLDDT} | valid → eligible; else → **setup_error** (proven now) |
| **A3 (C1-hole) — PERMANENT never-trust-alone** | **JUDGMENT / STANDING** | none the gate can read | pLDDT is model SELF-confidence, NOT experimental accuracy; AND — permanently, even once the network works — a lookup is **NEVER TRUSTED ALONE; corroboration is REQUIRED**. This is a standing trust claim, not just a provisioning gate. |

## 4. Known failure modes
- **4A. Endpoint unreachable → defer here.** Un-defer needs a reachable AFDB endpoint (§3A).
- **4B. pLDDT trusted alone / read as experimental accuracy → defer (A3, PERMANENT).** Corroboration always required.
- **4C. Bad input → setup_error (A2).** Proven now.

## 5. Diagnostics CAN/CANNOT
CAN: input validity (A2); (at provisioning) endpoint reachability. CANNOT: whether
the pLDDT matches experimental accuracy; disordered/low-pLDDT regions (A3).

## 6. Extraction contract
Input `{protein_sequence, quantity}`; QoI = `mean_pLDDT` (`QOI_FIELDS`).
**DEFERRED** now; **NEVER-TRUSTED-ALONE always**. Signature `{protein_sequence,
quantity}` SHARES with boltz2 by design (Step-41 L1a pair, distinct regime:
predicted_structure_lookup vs structure_affinity_prediction — the live L1a proof
at D.4).

## 7. Cost model — PENDING-PROVISIONING (network round-trip).

## 8. Negative space + open watches
Out of scope: trusting pLDDT alone (A3); experimental-accuracy claims. Watches:
(1) **un-defer = reachable AFDB endpoint** (§3A); (2) **A3 never-trust-alone is
PERMANENT**; (3) reviewer pending; (4) registration deferred — `contract_for` raises.
