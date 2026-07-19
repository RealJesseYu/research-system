# Envelope Card — (crispr_guide_scoring, guide_activity_scoring)

> **STATUS: SKELETON — §3A PENDING-PROVISIONING. RE-TIERED T2 → DEFERRED**
> (owner-ruled 2026-07-18): no VERIFIED py3 Doench/CFD scorer runs here. The
> ruled fields (regime/class/trust-split/C1-hole) and the pure-Python input jails
> ARE proven now; the scoring envelope defers. HUMAN-FACING ONLY (R-20.5-1).
> ENROLLED `calibrating`/`routable=False` — inert (`contract_for` raises).

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `crispr_guide_scoring` (CRISPOR/CHOPCHOP class; **ENROLLED**, `calibrating`/`routable=False`, **DEFERRED**) |
| Regime | **guide_activity_scoring**: score a guide RNA's on-target efficiency for a target site under a given nuclease, via a published model (Doench/CFD). |
| Tool | Doench-2016 / CFD scoring. **Pinned attempt: NO verified py3 scorer available** — Azimuth (canonical Doench-2016) is Python-2 (`SyntaxError` on py3 import) + a compiled sklearn/model backend; `pip install cfd-score` → "No matching distribution". |
| Wrapper | `tools/run_crispr_guide_scoring.py` (deterministic Python, no AI; input gate proven, scoring wired at provisioning) |
| Class | **filter** — a RELATIVE efficiency screen, not measured cutting |
| Contract text (staged) | `onboarding/crispr_guide_scoring/contract.py` — moves to `substrates.py` at D.4 |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | pure-Python input-gate behaviour MEASURED; **no scoring envelope** — no verified scorer runs here (see §3A). |
| Signature | `unsigned` |
| Provenance state | `drafted-by-agent` — and **DEFERRED** |

## 3. Validated envelope

### 3A. Measured ranges — **PENDING-PROVISIONING (needs a verified ARTIFACT)**
**No scores appear here, by ruling.** No verified py3 Doench/CFD scorer is
installable on this host.

**THE UN-DEFER REQUIREMENT (a SOFTWARE ARTIFACT — different from the two hardware
deferrals):** three tools now defer for three different reasons —
- `cas_offinder`: wrong kernel → needs a **VALIDATED ENVIRONMENT**.
- `autodock_vina`: wrong architecture → needs an **x86 HOST**.
- `crispr_guide_scoring`: no verified scorer → needs an **ARTIFACT: a verified
  py3 Doench/CFD scorer, or model files + a maintained scorer, FROM A TRUSTED
  SOURCE.**

**FORBIDDEN — part of the spec, not a nicety.** Un-deferring by
**hand-transcribing** the Doench/CFD model coefficients or the CFD penalty matrix
(from memory or an unverified source) is **NOT ALLOWED**. A transcribed model
produces plausible-but-UNVERIFIABLE scores — the silent-wrong failure this wave
exists to prevent (a wrong guide-efficiency score reads as confident and
correct). The only valid un-defer is INSTALLING the verified artifact, then
producing real §3A + determinism from it. (This is the guide-scoring analog of
cas_offinder's "validate the kernel first" — here it is "install a verified
scorer, never transcribe one.")

### 3B. Ruled envelope bounds (R-CARD-2 — from the A-table + owner rulings)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **G1 — VERIFIED-SCORER GATE (did-it-work)** | The score must come from a verified scorer | `CHECKABLE` (in code) | a verified scorer is installed (`scorer_available()` is None) | verified scorer present → the score is eligible; absent → **defer** (never a transcribed/fabricated score) |
| **G2** | Guide valid + PAM matches the enzyme motif | `CHECKABLE:membership` (pre-run) | `guide` is 20-nt A/C/G/T; `pam` matches the enzyme's motif (SpCas9 = NGG) | valid → eligible; else → **setup_error** (proven now) |
| **G3** | Enzyme + quantity on the allowlist | `CHECKABLE:membership` | `enzyme ∈ {SpCas9}`, `quantity ∈ {activity_score}` | on list → eligible; else → **setup_error** |
| **G4 (C1-hole)** | activity_score ≠ measured cutting | **JUDGMENT / KNOWN GAP** | **none the gate can read** — the score is a model's RELATIVE efficiency prediction; whether the guide/species/context is within the model's TRAINING DISTRIBUTION, and whether the score matches actual cellular cutting, are unknowable from the spec | trust side = a **relative** efficiency screen; any claim of MEASURED cutting/editing, or that the context is within the model's training distribution → **defer**. Chromatin, delivery, and cellular context are unmodelled. |

## 4. Known failure modes
- **4A. No verified py3 scorer → can't score here (install-time, honest).** Azimuth is Python-2; no standalone CFD package. Un-defer needs a verified artifact (§3A).
- **4B. A transcribed/unverified model → the forbidden silent-wrong case (G1, §3A).** A hand-transcribed matrix produces confident, wrong scores. Prohibited by spec — the wrapper never scores without a verified scorer.
- **4C. Score read as measured cutting / out-of-training-distribution guide → defer (G4, the C1-hole).**
- **4D. Bad input (guide/PAM/enzyme/quantity) → setup_error (G2/G3).** Proven now.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Input validity: guide, PAM-vs-motif, enzyme (G2/G3) | Whether the guide is within the scoring model's training distribution (G4) |
| Whether a verified scorer is installed (G1) | Whether the score matches actual cellular cutting efficiency (G4) |
| (at provisioning) determinism of the verified scorer | — |

## 6. Extraction contract + QoI status
Typed input `{guide, pam, enzyme, quantity}`. QoI = `activity_score` (relative
on-target efficiency), returned only behind the G1 verified-scorer gate.
`ENZYME_ALLOWLIST`/`QOI_FIELDS` are the single source, imported at promotion.
**Status: DEFERRED** — no score endorsed until a verified scorer is installed
(never transcribed).

## 7. Cost model
**PENDING-PROVISIONING** — no timing here (no scorer runs).

## 8. Negative space + open watches
Out of scope: off-target specificity scoring (CFD-vs-off-target is a separate QoI);
nucleases outside the allowlist; measured-cutting claims (G4). **Open watches:**
(1) **THE UN-DEFER ARTIFACT (§3A)** — a verified py3 Doench/CFD scorer/model from
a trusted source; **transcription forbidden**. (2) External reviewer — pending.
(3) Registration deferred — `contract_for` must keep raising until a D.4 ruling.
