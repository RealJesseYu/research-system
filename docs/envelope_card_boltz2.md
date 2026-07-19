# Envelope Card — (boltz2, structure_affinity_prediction)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. DEFERRED** (owner-ruled
> 2026-07-18): Boltz-2 is a large neural model needing a GPU + downloaded
> weights; this aarch64 host has no GPU. Ruled fields + pure-Python input jails
> proven now; the prediction envelope defers. HUMAN-FACING ONLY (R-20.5-1).
> ENROLLED `calibrating`/`routable=False` — inert (`contract_for` raises).

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `boltz2` (**ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **structure_affinity_prediction**: neural prediction of structure + binding affinity from sequence(+ligand). |
| Tool | Boltz-2 (GPU neural model). **Pinned: no GPU on this host.** |
| Wrapper | `tools/run_boltz2.py` (input gate proven; prediction wired at provisioning) |
| Class | **filter** — predicted RMSD/affinity is a RELATIVE screen |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input-gate behaviour measured; **no prediction
envelope** (no GPU). Signature `unsigned`. DEFERRED.

## 3. Validated envelope
### 3A. Measured ranges — **PENDING-PROVISIONING**
No predictions here, by ruling (no GPU).
**UN-DEFER REQUIREMENT (specific — mismatched weights = confident garbage, the
cas_offinder lesson):** a **GPU host** + the **SPECIFIC PINNED Boltz-2 weights
from the official source** (github.com/jwohlwend/boltz — record the release tag +
checksum here at provisioning) + a **KNOWN-ANSWER VALIDATION RUN** (a target with
a known reference structure/affinity must be reproduced) BEFORE any §3A number is
trusted. Generic "GPU + weights" is insufficient — name the weights, the source,
and pass the known-answer run.

### 3B. Ruled bounds (R-CARD-2)
| Ruling | Class | Criterion + where | Consequence (both sides) |
|---|---|---|---|
| **B1 — validated-weights gate** | `CHECKABLE` | GPU + pinned weights present + known-answer run passed | present+validated → eligible; else → **defer** (never an unvalidated prediction) |
| **B2** | `CHECKABLE:membership` (pre-run) | protein_sequence valid; quantity ∈ {affinity, rmsd} | valid → eligible; else → **setup_error** (proven now) |
| **B3 (C1-hole)** | **JUDGMENT** | none the gate can read — whether the target is within the model's training distribution (OOD) is unknowable | predicted affinity ≠ experimental Kd; a **relative** screen only; OOD generalization + absolute calibration → **defer**. Never "the structure is correct". |

## 4. Known failure modes
- **4A. No GPU → can't predict here (honest).** Un-defer needs a validated GPU host (§3A).
- **4B. Unvalidated/mismatched weights → confident garbage (B1).** Prevented by the known-answer gate at provisioning.
- **4C. Prediction read as experimental affinity / OOD target → defer (B3).**
- **4D. Bad input → setup_error (B2).** Proven now.

## 5. Diagnostics CAN/CANNOT
CAN: input validity (B2); (at provisioning) known-answer validation. CANNOT:
whether the target is in-distribution; whether the affinity is experimentally real (B3).

## 6. Extraction contract
Input `{protein_sequence, ligand?, quantity}`; QoI ∈ `{affinity, rmsd}`
(`QOI_FIELDS`, single source). **DEFERRED** — no number until B1 holds.

## 7. Cost model — PENDING-PROVISIONING (GPU inference).

## 8. Negative space + open watches
Out of scope: absolute Kd; OOD targets; "the structure is correct". Watches:
(1) **un-defer = validated GPU + pinned official weights + known-answer run** (§3A);
(2) external reviewer pending; (3) registration deferred — `contract_for` raises.
