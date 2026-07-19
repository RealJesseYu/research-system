# Envelope Card — (proteinmpnn, backbone_conditioned_sequence_design)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. DEFERRED** (no GPU). Ruled
> fields + pure-Python input jails proven now; the design envelope defers.
> HUMAN-FACING ONLY. ENROLLED `calibrating`/`routable=False` — inert (`contract_for` raises).

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `proteinmpnn` (**ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **backbone_conditioned_sequence_design**: neural inverse-folding — a sequence for a fixed backbone. |
| Tool | ProteinMPNN (GPU neural model). **Pinned: no GPU here.** |
| Wrapper | `tools/run_proteinmpnn.py` (input gate proven; design wired at provisioning) |
| Class | **filter** — sequence-recovery is a RELATIVE design screen |

## 2. Provenance
`drafted-by-agent`, 2026-07-18; input-gate measured; no design envelope (no GPU). DEFERRED.

## 3. Validated envelope
### 3A. PENDING-PROVISIONING
No design scores here (no GPU). **UN-DEFER (specific):** a **GPU host** + the
**PINNED official ProteinMPNN weights** (record release + checksum) + a
**KNOWN-ANSWER VALIDATION RUN** (a backbone whose native sequence yields an
expected recovery) before any §3A number is trusted. Mismatched weights = confident garbage.

### 3B. Ruled bounds
| Ruling | Class | Criterion + where | Consequence |
|---|---|---|---|
| **P1 — validated-weights gate** | `CHECKABLE` | GPU + pinned weights + known-answer run | validated → eligible; else → **defer** |
| **P2** | `CHECKABLE:membership` | backbone ∈ allowlist; quantity ∈ {seq_recovery} | valid → eligible; else → **setup_error** (proven now) |
| **P3 (C1-hole)** | **JUDGMENT** | none the gate can read — whether the backbone is in-distribution is unknowable | high recovery / low perplexity ≠ the sequence folds or functions; wet-lab uncheckable → **defer**. Relative screen only. |

## 4. Known failure modes
- **4A. No GPU → can't design here.** Un-defer needs a validated GPU host (§3A).
- **4B. Unvalidated weights → confident garbage (P1).**
- **4C. Recovery read as fold/function → defer (P3).**
- **4D. Bad input → setup_error (P2).** Proven now.

## 5. Diagnostics CAN/CANNOT
CAN: input validity (P2). CANNOT: whether the sequence folds/functions; in-distribution (P3).

## 6. Extraction contract
Input `{backbone, quantity}`; QoI = `seq_recovery` (`QOI_FIELDS`, single source). **DEFERRED**.

## 7. Cost model — PENDING-PROVISIONING (GPU inference).

## 8. Negative space + open watches
Out of scope: fold/function claims; OOD backbones. Watches: (1) **un-defer =
validated GPU + pinned official weights + known-answer run** (§3A); (2) reviewer
pending; (3) registration deferred — `contract_for` raises.
