# Envelope Card — (rdkit, descriptor_computation)

> **STATUS: DRAFT — signed-from-real-runs, external review pending.**
> Provenance: `drafted-by-agent`; §3A numbers are MEASURED in `rdkit-prod`
> (rdkit 2026.03.4), not literature-quoted. This card is **HUMAN-FACING ONLY**
> (R-20.5-1): no code reads it, no model sees it. The substrate is **ENROLLED
> but `calibrating` / `routable=False`** (BIO Wave D.2, Option A) — inert:
> `contract_for("rdkit")` raises, nothing routes to it, until a D.4 promotion
> ruling.

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, physics/compute-regime) pair |
| Substrate | `rdkit` (**ENROLLED**, `calibrating`/`routable=False`) |
| Regime | **descriptor_computation**: deterministic 2D molecular descriptors of one valid, sanitizable small molecule (SMILES). No ML prediction, no 3D/conformer quantity, no reactions. |
| Tool | **RDKit 2026.03.4** (PyPI wheel), in container `rdkit-prod` (from `rdkit-img` = python:3.12-slim + rdkit) |
| Wrapper | `tools/run_rdkit.py` (deterministic Python, no AI; RDKit imported ONLY in-container) |
| Class | **answer** — the descriptor IS the tool's exact computed output, not a prediction |
| Contract text (staged) | `onboarding/rdkit/contract.py::RDKIT_DESCRIPTOR_CONTRACT` — moves to `substrates.py` at D.4 promotion (pointed at, never pasted) |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | `onboarding/rdkit/selfcheck_evidence.json` — 6 molecules, the full allowlist each, plus a MolWt cross-check against INDEPENDENT IUPAC-2021 atomic weights (not RDKit's), so the cross-check can actually fail. |
| Signature | `unsigned` — owner provisional signature requested |
| Reviewer sign-off | `pending` |
| Provenance state | `drafted-by-agent` (weakest rung; battery not yet run) |

## 3. Validated envelope

### 3A. Ranges actually exercised (disk-cited, MEASURED in rdkit-prod)
Every number below is from `selfcheck_evidence.json` (rdkit 2026.03.4). The
MolWt column is cross-checked against a formula weight computed from independent
atomic weights — a check that fails if the wrapper or RDKit is wrong.

| Molecule | SMILES | MolWt (RDKit) | MolWt indep. ref | rel err | TPSA | MolLogP | Ar. rings |
|---|---|---|---|---|---|---|---|
| water | `O` | 18.015 | 18.015 | **0.0** | 31.50 | −0.825 | 0 |
| ethanol | `CCO` | 46.069 | 46.069 | **0.0** | 20.23 | −0.001 | 0 |
| benzene | `c1ccccc1` | 78.114 | 78.114 | **0.0** | 0.00 | 1.687 | 1 |
| acetic acid | `CC(=O)O` | 60.052 | 60.052 | **0.0** | 37.30 | 0.091 | 0 |
| aspirin | `CC(=O)Oc1ccccc1C(=O)O` | 180.159 | 180.159 | **0.0** | 63.60 | 1.310 | 1 |
| caffeine | `Cn1cnc2c1c(=O)n(C)c(=O)n2C` | 194.194 | 194.194 | **0.0** | 61.82 | −1.029 | 2 |

**MolWt reproduces independent formula weights to rel err 0.0 across all six.**
Determinism: an identical repeat returns a bit-identical value (benzene MolLogP
1.6866 == 1.6866, measured). The full 12-descriptor allowlist is captured per
molecule in the evidence file.

### 3B. Ruled envelope bounds (R-CARD-2 — Class / Criterion / Consequence both sides)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **D1** | Molecule must parse AND sanitize | `CHECKABLE:membership` (in code) | `Chem.MolFromSmiles(smiles) is not None` — RDKit sanitizes by default | parses+sanitizes → **eligible for trust**; else → **setup_error**, no number |
| **D2** | Descriptor on the fixed allowlist | `CHECKABLE:membership` (pre-run) | `quantity ∈ QOI_FIELDS`, read from the typed input | on list → **eligible for trust**; off list → **setup_error**, rejected pre-run |
| **D3** | Value must be finite | `CHECKABLE:numeric` | `math.isfinite(value)` at extraction | finite → **trust the number**; non-finite → **refused**, no number |
| **D4** | 2D descriptors only | `CHECKABLE:membership` | the allowlist is 2D graph/constitution descriptors — no 3D/conformer term is in it | a request needing 3D/conformer or an ML-predicted property → **out of regime**, unrepresentable (no allowlist entry) |
| **D5 (C1-hole)** | Descriptor ≠ measured property | **JUDGMENT / KNOWN GAP** | **none the gate can read** — the map from a computed descriptor to an experimental property is outside every text this system holds | any claim resting on a descriptor being an EXPERIMENTAL measurement (esp. `MolLogP` as measured logP, `TPSA` as measured PSA) → **defer** to wet-lab/expert; the number itself stays RDKit's exact computation |

## 4. Known failure modes
- **4A. Unparseable / unsanitizable SMILES → `setup_error`.** `CHECKABLE:membership` (D1). `MolFromSmiles` returns `None` for a syntax error OR a valence violation (e.g. pentavalent carbon `C(C)(C)(C)(C)C`). Measured: both return `valid=False`, `qoi=None`. No number is ever fabricated for a molecule RDKit could not build.
- **4B. Descriptor off the allowlist → `setup_error`.** `CHECKABLE:membership` (D2). Rejected by name pre-run; never reaches the container.
- **4C. Computed proxy read as a measurement → `defer`.** `JUDGMENT` (D5, the C1-hole). Invisible to every diagnostic: nothing about the RUN is wrong — `MolLogP` for caffeine (−1.029) is RDKit's exact Crippen logP, but it is not an experimental logP. The only defense is the card's honesty, which is why D5 is a KNOWN GAP, not a checkable rule.
- **4D. Container down / driver timeout → transient.** One retry, then an honest `substrate not ready` / timeout failure — never a number.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the SMILES parsed and sanitized (D1) | Whether the descriptor is the RIGHT descriptor for the question |
| Whether the requested descriptor is on the allowlist (D2) | Whether a computed descriptor matches the EXPERIMENTAL property (D5) |
| Whether the extracted value is finite (D3) | Whether a 2D descriptor suffices where 3D/conformer effects matter |
| A missing/unreadable result file → `valid=False`, no number | — |

*The wrapper checks that RDKit built the molecule and produced a finite number —
not that the descriptor is a measurement of anything.*

## 6. Extraction contract + QoI status
Typed input `{smiles, quantity}`; `quantity` ∈ the fixed allowlist (the
`fixed_summary` QoI vocab, `QOI_FIELDS` — the single source, imported by
`tools/qoi_vocab.py` at promotion, never pasted). ONE scalar per run; the wrapper
computes the whole fixed set and reports the selected one, the others in the
bounded diagnostics. Allowlist (all VALIDATED, family v1, deterministic):
`MolWt`, `ExactMolWt`, `HeavyAtomCount`, `NumHDonors`, `NumHAcceptors`,
`NumRotatableBonds`, `TPSA`, `MolLogP` (Crippen computed logP — the D5 proxy),
`NumAromaticRings`, `RingCount`, `FractionCSP3`, `NOCount`.

## 7. Cost model (measured)
| Operating point | Measured wall-clock |
|---|---|
| single descriptor request (ethanol) | **~1.1 s/run** |
| Hard kill limit | 600 s → reported failure |
*The cost is container-exec overhead, not compute: RDKit computes the whole
allowlist in milliseconds. Do NOT model cost as proportional to molecule size —
it is close to a fixed per-invocation toll over the exercised set.*

## 8. Negative space + open watches
Out of scope (family v1): any ML-PREDICTED property (solubility/ADMET/activity);
3D/conformer-dependent quantities; reactions/retrosynthesis; descriptors outside
the allowlist; multi-molecule or reaction inputs; any claim that a computed
descriptor is an experimental measurement.
**Open watches:** (1) external reviewer dispatch — pending; provenance stays
`drafted-by-agent`. (2) Registration deferred until after calibration — the row
stays `calibrating`/`routable=False`; `contract_for("rdkit")` MUST keep raising
until a D.4 promotion ruling. (3) Calibration battery assembled-later, on the
owner's manifest; no draws spent. (4) Allowlist is deliberately small; widening
it is a card ruling, not a silent change.
