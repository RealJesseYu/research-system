# Envelope Card — (cobrapy, fba_steady_state)

> **STATUS: DRAFT — signed-from-real-runs, external review pending.**
> Provenance: `drafted-by-agent`; §3A numbers are MEASURED in `cobrapy-prod`
> (COBRApy + GLPK, models baked into the image), not literature-quoted. This
> card is **HUMAN-FACING ONLY** (R-20.5-1). The substrate is **ENROLLED but
> `calibrating` / `routable=False`** (BIO Wave D.2, Option A) — inert:
> `contract_for("cobrapy")` raises, nothing routes to it, until a D.4 ruling.

---

## 1. Identity
| Field | Value |
|---|---|
| Card unit | (substrate, compute-regime) pair |
| Substrate | `cobrapy` (**ENROLLED**, `calibrating`/`routable=False`) |
| Regime | **fba_steady_state**: constraint-based flux-balance analysis (a deterministic LP) over a genome-scale metabolic model at steady state. No kinetics, no regulation, no dynamics. |
| Tool | **COBRApy** (PyPI) + GLPK LP solver, in container `cobrapy-prod` (from `cobrapy-img` = python:3.12-slim + cobra + libexpat1/libxml2). Models `e_coli_core` and `iML1515` **baked into the image** at `/opt/models/` — loaded from local disk, **no runtime network** (deterministic). |
| Wrapper | `tools/run_cobrapy.py` (deterministic Python, no AI; cobra imported ONLY in-container) |
| Class | **filter** — the growth it reports is a feasible steady-state optimum, a RELATIVE screen, not a measured rate |
| Contract text (staged) | `onboarding/cobrapy/contract.py` — moves to `substrates.py` at D.4 (pointed at, never pasted) |

## 2. Provenance
| Field | Value |
|---|---|
| Drafted by | agent (Claude Code), 2026-07-18 |
| Sources | `onboarding/cobrapy/selfcheck_evidence.json` — the five cases in §3A, all measured in `cobrapy-prod`. |
| Signature | `unsigned` — owner provisional signature requested |
| Reviewer sign-off | `pending` |
| Provenance state | `drafted-by-agent` (weakest rung; battery not yet run) |

## 3. Validated envelope

### 3A. Cases actually exercised (disk-cited, MEASURED)
Two models — the small `e_coli_core` and the genome-scale `iML1515` (same
organism, full-scale, canonical) — proven optimal, and the **infeasible
status-gate proven by triggering it on BOTH**.

| Case | Model | Input | Result | Growth (QoI) |
|---|---|---|---|---|
| optimal | `e_coli_core` (95 rxns) | default biomass | **status=optimal** | **0.873922** |
| optimal | `iML1515` (2712 rxns) | default biomass | **status=optimal** | **0.876997** |
| **infeasible JAIL** | `e_coli_core` | `min_growth=1000` (unachievable) | **status=infeasible** | **None** (the stale ~0.8739 is NOT surfaced) |
| **infeasible JAIL** | `iML1515` | `min_growth=1000` | **status=infeasible** | **None** (stale ~0.877 NOT surfaced) |
| feasible constraint | `e_coli_core` | `min_growth=0.5` | status=optimal | 0.873922 |

`e_coli_core` reproduces the canonical textbook biomass flux **0.873922**;
`iML1515` the canonical **0.876997**. Determinism: an identical repeat returns a
bit-identical value (measured). **The infeasible cases return `None`, not the
stale objective — that is the proof the gate can fail.**

### 3B. Ruled envelope bounds (R-CARD-2 — Class / Criterion / Consequence both sides)
| Ruling | Value | Class | Criterion (what the gate evaluates + where) | Consequence (both sides) |
|---|---|---|---|---|
| **F1 — THE STATUS GATE** | Solver status must be `optimal` | `CHECKABLE:membership` (in code, structural) | `sol.status`, read from the LP solve; the objective is UNREACHABLE unless status is `optimal` (the driver surfaces no value otherwise) | **status `optimal` AND objective well-formed → TRUST as a feasibility/relative-growth screen**; **status not `optimal` (infeasible / unbounded / solver-error) → defer** (qoi=None, never the stale objective) |
| **F2** | Model on the baked allowlist | `CHECKABLE:membership` (pre-run) | `model ∈ {e_coli_core, iML1515}` | on list → **eligible for trust**; off list → **setup_error**, rejected pre-run |
| **F3** | Objective must be finite | `CHECKABLE:numeric` | `math.isfinite(objective)` at extraction | finite → **trust the number**; non-finite → **refused**, no number |
| **F4 (C1-hole)** | FBA optimum ≠ measured growth | **JUDGMENT / KNOWN GAP** | **none the gate can read** — the map from a steady-state LP optimum to an in-vivo growth rate depends on regulation, kinetics, and media the model does not encode | any claim that the number is an ABSOLUTE measured growth rate, or a transient/kinetic question → **defer**; the number stays a RELATIVE feasibility screen. Whether the model, media, and objective suit the biological question is not checkable from the spec. |

## 4. Known failure modes
- **4A. Infeasible / non-optimal solve read as a number → `defer` (structural, F1).** COBRApy exposes a STALE `objective_value` after an infeasible solve (measured: ~0.8739 for e_coli_core, ~0.877 for iML1515). The wrapper's driver surfaces NO value unless status is `optimal`, so the wrapper cannot return the stale number — it returns `None`. Proven by triggering (`min_growth=1000`) on both models. This is the substrate's "exit code proves nothing."
- **4B. Model off the allowlist → `setup_error` (F2).** Rejected by name pre-run.
- **4C. FBA optimum read as absolute growth → `defer` (F4, the C1-hole).** Invisible to every diagnostic: the LP is perfectly healthy; the number is simply a relative screen, not a measurement. Only the card's honesty defends this.
- **4D. Container down / driver timeout → transient.** One retry, then an honest failure — never a number.

## 5. What the diagnostics CAN and CANNOT see
| CAN see | CANNOT see |
|---|---|
| Whether the LP solved `optimal` (F1) — the load-bearing signal | Whether the FBA optimum matches an in-vivo measured growth rate (F4) |
| Whether the model is on the allowlist (F2) | Whether the model / media / objective suit the biological question |
| Whether the objective is finite (F3) | Any kinetic / transient / regulatory behaviour (out of regime) |
| A missing/unreadable result → `valid=False`, no number | — |

*The wrapper checks that the LP found a feasible optimum — not that the optimum
is a measurement of real growth.*

## 6. Extraction contract + QoI status
Typed input `{model, quantity[, min_growth]}`. `model` ∈ the baked allowlist;
`quantity` ∈ `QOI_FIELDS` (the `fixed_summary` vocab — currently the single
`growth_rate`); `min_growth` is an OPTIONAL biomass lower-bound feasibility
constraint (its over-setting is the infeasible path). ONE scalar per run:
`growth_rate`, the optimal biomass flux, **gated on `status=optimal`** (F1).
`QOI_FIELDS`/`MODEL_ALLOWLIST` are the single source, imported by
`tools/qoi_vocab.py` / `tools/substrate_selection.py` at promotion, never pasted.

## 7. Cost model (measured)
| Operating point | Measured wall-clock |
|---|---|
| `e_coli_core` FBA (95 reactions) | **~2.6 s/run** |
| `iML1515` FBA (2712 reactions) | **~2–4 s/run** |
| Hard kill limit | 600 s → reported failure |
*Cost is container-exec + model-load overhead; the LP itself solves in
milliseconds. The genome-scale model is not dramatically slower than the small
one over the exercised set.*

## 8. Negative space + open watches
Out of scope (family v1): kinetics / dynamics / regulation; any model outside the
baked allowlist; absolute in-vivo growth-rate claims; multi-objective or
transient (dFBA) analysis; gene-level knockouts (reaction-level `min_growth`
constraint only). **Open watches:** (1) external reviewer dispatch — pending. (2)
Registration deferred — the row stays `calibrating`/`routable=False`;
`contract_for("cobrapy")` MUST keep raising until a D.4 promotion ruling. (3)
Calibration battery assembled-later, on the owner's manifest. (4) The allowlist is
two models by ruling (a small + a genome-scale); widening it is a card ruling.
