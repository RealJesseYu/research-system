# Envelope Card — (retrosynthesis, retrosynthetic_route_search)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. DEFERRED** (heavy models + a
> reaction route database/backend, neither available here). Ruled fields +
> pure-Python input jails proven now. HUMAN-FACING ONLY. ENROLLED
> `calibrating`/`routable=False` — inert (`contract_for` raises).

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `retrosynthesis` (AiZynth/ASKCOS; **ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **retrosynthetic_route_search**: MCTS/template route search to purchasable building blocks. |
| Tool | AiZynthFinder / ASKCOS (`backend` field). **Pinned: models + backend not available here.** |
| Wrapper | `tools/run_retrosynthesis.py` (input gate proven; route search wired at provisioning) |
| Class | **filter** — a found route is TEMPLATE-feasible, a relative screen |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input gate measured; no route envelope. DEFERRED.

## 3. Validated envelope
### 3A. PENDING-PROVISIONING
No routes here. **UN-DEFER (specific — "GPU + weights" UNDERCOUNTS this tool):** a
host with the heavy models AND the **reaction ROUTE DATABASE / expansion backend**
the tool queries (AiZynth policy+stock, or ASKCOS reaction DB — name backend +
version) + a **KNOWN-ANSWER run** (a molecule with a known feasible route) before
any §3A number is trusted. The DATA dependency (the route DB) is a first-class
requirement, not just model weights.

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **R1 — models+backend gate** | `CHECKABLE` | models + route DB present + known-answer run | present → eligible; else → **defer** |
| **R2** | `CHECKABLE:membership` | valid SMILES; backend ∈ {aizynth,askcos}; quantity ∈ {synthesizability} | valid → eligible; else → **setup_error** (proven now) |
| **R3 (C1-hole)** | **JUDGMENT** | none the gate can read | a found route is TEMPLATE-feasible, NOT experimentally validated (yields/conditions/selectivity uncheckable) → **defer**. Relative screen only. |

## 4. Known failure modes
- **4A. No models/backend → can't search here.** Un-defer needs models + the route DB (§3A).
- **4B. Route read as experimentally feasible → defer (R3).**
- **4C. Bad input → setup_error (R2).** Proven now.

## 5. Diagnostics CAN/CANNOT
CAN: input validity (R2). CANNOT: whether a route actually works in the lab (R3).

## 6. Extraction contract
Input `{target_smiles, backend, quantity}`; QoI = `synthesizability` (`QOI_FIELDS`). **DEFERRED**.

## 7. Cost model — PENDING-PROVISIONING (heavy route search).

## 8. Negative space + open watches
Out of scope: experimental feasibility claims. Watches: (1) **un-defer = models +
reaction route DB/backend + known-answer run** (§3A); (2) reviewer pending; (3)
registration deferred — `contract_for` raises.
