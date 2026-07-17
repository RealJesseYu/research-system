# Envelope Card — (ngspice_linear_passive, ideal lumped linear passive networks)

> **STATUS: DRAFT — unsigned, not yet reviewed.**
> Provenance: `drafted-by-agent` (see §2). The §3B rulings N1–N6 are
> owner-**RULED** 2026-07-16; the card's **signature is not**.
> This card is **HUMAN-FACING ONLY** (R-20.5-1 doctrine): no code reads it, no
> model sees it. The substrate is **UNREGISTERED and UNROUTABLE** — nothing in
> `stages/`, the supervisor, `substrates.py`, or any schema imports
> `tools/run_ngspice.py`.

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `ngspice_linear_passive` (**UNREGISTERED** — registry row is STAGED, not merged) |
| Physics regime | **ideal lumped linear passive networks**: R, L, C, ideal independent V/I sources, and linear controlled sources (E/F/G/H). Analyses `.op`, `.dc`, `.ac`, `.tran` per **N1**. No nonlinearity, no device physics, no distributed elements. |
| Solver | **ngspice-42** (dpkg `42+ds-3build1`), compiled with the **KLU** direct linear solver, aarch64, in container `ngspice-prod` |
| Wrapper | `tools/run_ngspice.py` (deterministic Python, no AI) |
| Wrapper sha (last touch) | `e79afa6274c801e4da2abb80011a5177968102e01a66f3910632171f53483b34` (was `53bf1d09…` before this session's additive `corner_3db` bias note) |
| Contract text (last touch) | `onboarding/ngspice_linear_passive/contract.py::NGSPICE_LINEAR_PASSIVE_CONTRACT` — **STAGING PATH; merges to `substrates.py`.** Pointed at, never pasted (one runtime source of truth). |
| Docs index | ngspice-42 manual, `retrieval/ngspice_docs_index.pkl`, **2,018 chunks** — **ZERO version skew** (see below) |
| Card drafted against repo HEAD | `07816ba` (branch `build-ngspice`; **the ngspice tree is uncommitted** — see `onboarding/ngspice_linear_passive/MERGE_NOTES.md` §0) |
| Maturity | **`calibrating`** (unroutable; battery assembled, unexecuted) |

**Docs/solver version skew: none — and that is worth one sentence.** The manual's
title page reads *"Ngspice User's Manual / Version 42 / … / December 27th, 2023"*
against a binary that self-reports `ngspice-42`. This is the improvement over the
FEA card, whose manual is v2.23 against a v2.17 solver and which therefore has to
treat its own reference as a superset. Here a worked example from the manual
describes *this* solver, so its reference numbers can be used without a
version-check caveat.

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, session 2 — card + slate + staging) |
| Drafted date | 2026-07-16 |
| Sources | `onboarding/ngspice_linear_passive/selfcheck_evidence.json` (six checks + adversarial probes, all measured this substrate); `coarse_extremum_evidence.json` (31 measured runs incl. the tmax/tstep characterization); the wrapper's own analytic self-checks. **No V&V literature applied** — every number here is from this substrate's own runs. |
| Signature | **`unsigned` — owner provisional signature requested at session-2 report-back** |
| Reviewer sign-off | `pending` — external expert-review dispatch not yet scheduled |
| **Provenance state** | **`drafted-by-agent`** |

*Provenance state is the load-bearing field: it sets how much grounding authority
this card carries. It is `drafted-by-agent` — the weakest rung. The §3B rulings
are owner-ruled, which is what makes them bounds rather than suggestions, but the
card as a whole has no signature and no external review, and the calibration
battery that would test whether these rulings actually transmit has **not been
run**. Nothing here should be leaned on as validated instrument authority yet.*

---

## 3. Validated envelope

### 3A. Ranges actually exercised (disk-cited)

All evidence: `onboarding/ngspice_linear_passive/selfcheck_evidence.json`
(checks a–f) and `coarse_extremum_evidence.json`. Every analytic reference is
computed in Python from the same numbers the netlist carries — never a
hard-coded expected result, because a hard-coded number cannot fail when the
wrapper is wrong.

| Check | Exercised | Result vs closed form | Evidence |
|---|---|---|---|
| **(a) resistive divider, `.op`** | 10 V, R1 = 1k, R2 = 2k; `op_value` of `v(out)` | measured **6.66666667** vs analytic 6.666666666666667 → **rel err 5.0e-10** | check `a. resistive divider, .op` |
| **(b) resistive divider, `.dc`** | V1 swept 0→10 V, step 1 V; slope fit over 6 points | slope **0.6666666668571428** vs R2/(R1+R2) = 0.6666666666666666 → **rel err 2.9e-10** | check `b. resistive divider, .dc sweep` |
| **(c) RC low-pass, `.ac` corner** | R = 1k, C = 159.155n (f_c ≈ 1 kHz); dec sweep, grids 10 and 100 pts/decade; fstart 10 / 1 / 0.1 Hz | see **the fstart finding** below | check `c. RC low-pass, .ac corner vs grid density` |
| **(d) RC step, `.tran`** | τ = 1 ms; tstep 10 µs, tstop 5 ms; tmax 50 / 5 / 0.5 µs | rel err at t = τ: **4.97e-05 → 6.71e-07 → 2.80e-07**; worst rel err over [0, 5τ]: **2.60e-03 → 2.88e-05 → 4.79e-06** — monotone | check `d. RC step, .tran convergence vs tmax` |
| **(e) series RLC peak, `.tran`** | ζ = 0.2 (R = 12.649, L = 1 mH, C = 1 µF); tmax 10 / 1 / 0.1 µs; `max` of `v(out)` | see **the extremum result** below | check `e. series RLC step overshoot (D.5 discretization screen)` |
| **(f) adversarial probes** | 5 setup-error probes + 12 regime escapes | **all 17 pass**; `all_pass: true` | check `f. adversarial probes (jails proven by failing the escape)` |

#### The fstart finding (check c) — the card's §4G-class artifact

This is the finding that motivated this session's wrapper change.

| fstart | corner measured | rel err vs analytic | predicted (fstart/f_c)² |
|---|---|---|---|
| 10 Hz | 1000.099080038621 | **+9.94e-05** | 1.00e-04 |
| 1 Hz | 1000.0006383969074 | **+9.96e-07** | 1.00e-06 |
| 0.1 Hz | 999.9996499468248 | **+7.51e-09** | 1.00e-08 |

**Confirmed to 3 digits at every point.** `|H_dc|` is *proxied* by the magnitude
at the lowest solved frequency, which biases a one-pole corner **HIGH** by a
relative (fstart/f_c)².

**The trap:** refining the grid 10 → 100 pts/decade moved the same corner by only
**3.79e-06** relative (`delta_rel`). That is **~26× smaller than the fstart bias
it was sitting inside**. A caller who refines the grid, sees the corner barely
move, and reads that as the error bar **understates the real error by 26×** — and
the reassurance is the danger. This is why the bias is now reported **per run**
(§4G, and Task C in §6).

#### The extremum result (check e) — the anti-FEA result

| tmax | peak measured | gap to analytic (**absolute**) | gap (**relative**) |
|---|---|---|---|
| 10 µs | 1.531468 | +4.844e-03 | 3.173e-03 |
| 1 µs | 1.52667938 | +5.570e-05 | 3.649e-05 |
| 0.1 µs | 1.52662415 | +4.737e-07 | 3.103e-07 |

Analytic peak **1.5266236763247512**; `monotone_settle: true`; settled value
1.0 with residual 0.0 at every tmax.

**This is the first VALIDATED extremum on this board, and it is worth stating
against the FEA card explicitly.** `max_von_mises` on
`docs/envelope_card_calculix_cantilever.md` is an extremum that *rises* with
refinement (2.521e7 → 2.609e7 → 3.848e7) — it tracks the clamped-corner stress
singularity and is **reported-only** to this day. `max(v_out)` here is the same
*class* of QoI — an extremum, a discretization-artifact suspect by default — and
it **settles monotonically onto its closed form across three decades of tmax**.
Same screen, opposite outcome. That is what makes it trustworthy at tmax ≤ 1 µs,
and it is the screen, not the tidy number, that earns it.

> **UNITS — a real trap, recorded because it bit this session.** Check (e)'s
> `gap_to_analytic_peak` is an **ABSOLUTE** difference. **N2's tolerance is
> RELATIVE.** The two differ by a factor of ~1.527 here, which is small enough to
> look like rounding and large enough to matter at a 1% bar. Both columns are
> given above and never mixed.

#### The tmax/tstep mechanism (`coarse_extremum_evidence.json`, this session)

Measured while establishing G10's setting; it revises how the refinement lever
should be described.

- **`tmax` is a CEILING on the solver's step, not a target.** ngspice's adaptive
  local-truncation-error control already steps at ~2e-5 on the ζ = 0.2 RLC, so
  every tmax from **4e-5 to 2e-4 is inert** — identical peak `1.52415539` from an
  identical **144 data rows**. *A `.tran` run cannot be coarsened past its
  adaptive floor; it can only be refined.*
- **`tstep` does not control the written grid at all.** `wrdata` emits one row
  per **internal** timestep (30,023 rows at tmax = 1e-7 ≈ tstop/tmax), unchanged
  across a 50× tstep range (5e-5 … 1e-6 → identical row count, bit-identical
  peak). **An extremum is always sampled on the solver's grid, never the print
  grid.**
- **Consequence:** the band where tmax binds *and* is still too coarse is narrow
  (≈3e-5 … 1e-5), and inside it the peak error is **non-monotone and
  sign-flipping** (undershoot −2.47e-03 on the plateau; +9.94e-03 at 3e-5;
  −7.53e-03 at 2.5e-5; +1.10e-02 at 2e-5; +1.72e-03 at 1.5e-5). **N4's
  monotone-settle screen is only meaningful on a ladder wholly inside the fine
  region** — check (e)'s ladder is, which is why its result stands.
- **The reachable error is bounded at ~1.1%** on this circuit, precisely because
  tmax saturates.

### 3B. Ruled envelope bounds (owner-RULED 2026-07-16)

**R-CARD-1 / R-CARD-2 compliance:** every ruling below carries **Class**,
**Criterion**, and **Consequence on both sides**. A ruling the gate cannot
evaluate is marked a **KNOWN GAP**, not left to read as a rule.

| Ruling | Ruled value | **Class** | **Criterion (what the gate evaluates, and where it reads it)** | **Consequence (both sides, in verdict vocabulary)** |
|---|---|---|---|---|
| **N1** | In-regime analyses = {`op`, `dc`, `ac`, `tran`} | `CHECKABLE:membership` | `analysis.type`, read from the spec's typed field | in-list → **eligible for trust**; any other analysis (`noise`, `pz`, `disto`, …) → **defer — wrong instrument** |
| **N2** | Analytic-reproduction tolerance **1% RELATIVE** | `CHECKABLE:numeric` | the measured-vs-analytic gap at the case's stated settings | inside → **eligible for trust**; outside → **refine** (tighten `tmax`; lower `fstart` for a corner); **defer only if refinement fails** |
| **N3** | **Netlist-vs-board split** (the card's spine) | `CHECKABLE:semantic` | does the claim text assert *physical-hardware* behaviour? — read from the claim/success-criterion text | netlist claim → **trust path**; board claim → **trust the number AND defer the board claim** (verdict: **defer**). The wrapper's N6 arity screen is what makes "as typed" literally enforced in code rather than promised in prose. |
| **N4** | Transient extremum (`max`/`min`) **VALIDATED within family v1 under the timestep protocol** | `CHECKABLE:membership` + `CHECKABLE:numeric` | `qoi.reduction ∈ {max, min}` → the case must meet N2 at its stated `tmax`. Evidence: monotone settle, absolute gap 4.8e-3 → 5.6e-5 → 4.7e-7 (`selfcheck_evidence.json`, check e) | screened-and-settling extremum meeting N2 → **eligible for trust**; extremum at an **unvalidated setting** → **refine** (per N2); an **UNSCREENED new extremum family** → **reported-only**, never trusted |
| **N5** | Device-model honesty = **KNOWN GAP, out of regime by construction** | **JUDGMENT / KNOWN GAP** | **KNOWN GAP: none the gate can read.** Silicon fidelity lives in datasheets and on the bench — outside every text this system holds. No threshold can be stated because the thing to check is not in the text. | **advisory only:** any spec resting on device-model fidelity → **defer** to a future expert-reviewed device-model card. Enforcement does not rest on this ruling transmitting: the **letter screen rejects every such element pre-solve**, so the claim cannot reach a number regardless. |
| **N6** | **R/L/C 4-token arity rule ADOPTED** | `CHECKABLE:membership` (**in code, pre-solve**) | token count == 4 and a strictly-positive parsed value on every R/L/C line — checked by `_validate_input`, not by a prompt | conforming → **eligible for trust**; violating → **setup_error**, rejected **by line, before any solve**. Closes the measured `ac=` / `tc1=` / `ic=` / model-name override family. |

---

## 4. Known failure modes

Each: the mode, the class it produces, **its detection class per R-CARD-1**, and
its evidence.

- **4A. Fabrication trap — zero-valued resistor.** → `setup_error`.
  **`CHECKABLE:membership` (pre-solve value screen; NO other defense exists).**
  `R1 a 0 0` emits **no log marker**, exits **0**, and reports a fabricated
  **1000 A** through the short. Confident, plausible, wrong, exit 0. The
  pre-solve value screen is the only thing between that netlist and a believed
  number. *Evidence: `selfcheck_evidence.json` probe `zero-value resistor`;
  slate case W02.*
- **4B. Fabrication trap — per-analysis value override.** → `setup_error`.
  **`CHECKABLE:membership` (N6 arity screen).** `R1 in out 1k ac=100k` runs
  clean, exits 0, and **silently simulates a resistance other than the one
  written**. Found by screening ngspice's own shipped test suite — i.e. this is
  a documented ngspice feature, not a bug, which is what makes it dangerous.
  Same family: `tc1=`, `ic=`, a model name on a passive. *Evidence:
  `regime_escapes` probes 8–11; slate case W03.*
- **4C. Floating node → fabricated voltage at exit 0.** → `setup_error`.
  **`CHECKABLE:semantic` (POST-solve log-marker scan — NOT a pre-solve check).**
  A node with no DC path fails the OP solve, falls through gmin stepping and
  source stepping, then succeeds at a transient operating point, **prints a
  plausible voltage, and exits 0**. Caught only by scanning the log for failure
  markers — which is why the wrapper never trusts the exit code. *Evidence:
  `selfcheck_evidence.json` probe `floating node (no DC path)`;
  `tests/test_run_ngspice.py::TestMarkerScanLayerIsWhereTheFloatingNodeIsCaught`.
  **Not covered by the battery — see §5.***
- **4D. Out-of-regime element class → pre-solve rejection.** → `setup_error` /
  `defer`. **`CHECKABLE:membership` (letter screen, by letter and line
  number).** Every one rejected before the deck is composed: `D` diode, `.model`
  card, `B` behavioural source, `POLY` controlled source, `.include`, `{}`
  expression interpolation, `X` subcircuit, `K` coupled inductors, negative
  values. *Evidence: `regime_escapes` probes 0–7; slate cases W01, W05, G06,
  G08.*
- **4E. Under-resolved extremum → converged-but-wrong.** → `refine` (or `defer`
  at the bound — see §8 item 10). **`CHECKABLE:numeric` (N2 + N4) — but only if
  the claim states its `tmax`.** An extremum read at a `tmax` outside the
  validated ladder can be off by up to ~1.1% on the exercised circuit while the
  solve itself is perfectly healthy. **No internal diagnostic flags it.** Worse,
  in the binding-but-coarse band the error is **non-monotone and
  sign-flipping**, so a two-point check can show "improvement" that is
  coincidence. *Evidence: `coarse_extremum_evidence.json`; slate case G10, which
  is banded `edge` `[refine, defer]` precisely because ~1.1% is this circuit's
  achievable-error ceiling.*
- **4F. `corner_3db` contaminated by fstart bias** (the **§4G artifact class**).
  → `refine`. **`CHECKABLE:numeric`, and now SELF-REPORTED.** The corner reads
  HIGH by (fstart/f_c)², a bias that **dominates grid density ~26×**. The
  natural error bar (refine the grid, watch the corner) understates it by that
  factor. **Mitigated this session:** every `corner_3db` run now appends its own
  estimated bias to `diagnostics` (§6). *Evidence: check c; slate case G03 pins
  fstart three decades below the corner.*
- **4G. Board claim on a clean netlist → right number, wrong question.** →
  `defer`. **`CHECKABLE:semantic` (N3).** The netlist result is correct *and*
  says nothing about an assembled board: no parasitics, tolerance, ESR, or
  ground effects exist in the model. This mode is invisible to every diagnostic
  the wrapper has, because nothing is wrong with the *run*. *Slate case G07 —
  the pre-registered R-CARD-2 test.*
- **4H. `+` continuation lines rejected in v1.** → `setup_error`.
  **`CHECKABLE:membership` (line screen).** A legal SPICE continuation is
  rejected because v1 screens line-by-line on the first character. **A known
  over-rejection, not a physics limit** — it fails safe (a rejection, never a
  wrong number) and is on the §8 watch list.

---

## 5. What the diagnostics CAN and CANNOT see

The wrapper returns `valid` (bool), `qoi` (scalar or `None`), a bounded
`diagnostics` string (≤ 800 chars), and `runtime_s`. **Never the raw deck or
log.**

| CAN see | CANNOT see |
|---|---|
| Every pre-solve rejection, **by name and by line number**: banned element letter, dot-command, `{` expression, non-positive value, R/L/C arity violation, `POLY`/`TABLE`/`value=` form | **Whether a clean number is timestep-independent** — unless the refinement protocol was actually run (N4). One reading is never evidence of convergence. |
| Solver failure markers **even at exit 0** — singular matrix, gmin-stepping failure, source-stepping failure (the exit code is never trusted) | **Whether the netlist represents any physical board** (N3). The idealized answer and the board answer are both silent about each other. |
| Missing/empty output file; the requested vector absent; a non-finite extracted value → `valid=False`, **no number** | **Whether the idealization suits the underlying question.** A perfect linear-passive answer to a question that needed device physics looks identical to a good answer. |
| Missing / unknown / ill-typed input fields, rejected by name before anything runs | **Regime-assumption certainty** — whether the assumption placing a case in-envelope is itself sound. This axis is uncovered here and is not pretended otherwise. |
| The 600 s timeout kill, reported as a failure | **The fstart bias's true size relative to the answer's needs** — the run now *reports* its estimate, but only the caller knows what precision the claim requires. |

*Overclaiming diagnostic reach is the most dangerous error a card can make: the
wrapper checks that the solver **ran and produced parseable output** — not that
the physics was the right physics.*

> **A layer the battery cannot reach, stated plainly.** The **post-solve
> marker-scan layer (§4C) is unreachable by the calibration harness by
> construction**: `calibration_battery.run_wrapper_case` calls the substrate's
> validator only — *"No model, no container"*. `_validate_input` **correctly
> accepts** a floating-node netlist (it is syntactically valid; no pre-solve
> screen can know DC-path topology), so a battery case targeting that defense
> would fail 100% of runs for a reason unrelated to the substrate's correctness.
> The slate's W01 was amended to the dot-line layer by owner ruling (2026-07-16)
> for exactly this reason. **The defense is proven elsewhere, twice:**
> `selfcheck_evidence.json` probe `floating node (no DC path)`, and
> `tests/test_run_ngspice.py::TestMarkerScanLayerIsWhereTheFloatingNodeIsCaught`.
> Covering it in a battery would need a track that actually solves; none is
> proposed. See §8.

---

## 6. Extraction contract + QoI status

**Typed input vocabulary** — pointed at, never pasted. The one runtime source of
truth is
`onboarding/ngspice_linear_passive/contract.py::NGSPICE_LINEAR_PASSIVE_CONTRACT`
§5 (**staging path — merges to `substrates.py`**; the card and generator
reference the onboarding path until then, per `MERGE_NOTES.md`).

In brief: the **circuit itself is the parameterization**. There is no named
physical-parameter dictionary — component values live inside `netlist_body` in
SPICE notation. The wrapper honors exactly `netlist_body`, `analysis.type` +
that type's fields, and `qoi.{kind, target, reduction, at}`. A circuit QoI is
*(kind, target, reduction[, at])* — "which quantity, at which node, reduced
how".

**QoI status table** — ONE scalar per run; no vector, no time series, no second
quantity from the same solve.

| QoI | what it is | status | basis |
|---|---|---|---|
| `op_value` | the single operating-point value (`.op` only) | **VALIDATED (family v1)** | divider `.op`, rel err **5.0e-10** (check a) |
| `final` | value at the last solved point | **VALIDATED (family v1)** | same extraction path as `op_value`/`value_at`; exercised by the RC step's settled value (residual 0.0, check e) |
| `value_at` | interpolated at `at` (linear in the sweep variable; log-frequency for `.ac`) | **VALIDATED (family v1)** | RC step at t = τ, rel err **2.80e-07** at tmax = 0.5 µs (check d) |
| dc-slope (`value_at` across a sweep) | linearity across a `.dc` sweep | **VALIDATED (family v1)** | divider `.dc`, slope rel err **2.9e-10** (check b) |
| `max` / `min` (transient extremum) | extremum over all solved points | **VALIDATED under the N4 timestep protocol** — the **first validated extremum on this board** | series RLC ζ = 0.2: monotone settle onto the closed form, absolute gap 4.8e-3 → 5.6e-5 → 4.7e-7 across tmax 10 → 1 → 0.1 µs (check e). **Trustworthy at tmax ≤ 1 µs; unvalidated elsewhere.** |
| `corner_3db` | −3 dB corner (`.ac` only), by log-frequency interpolation at \|H_dc\|/√2 | **VALIDATED — with the fstart-bias note attached per run** | check c: bias confirmed to 3 digits at 10 / 1 / 0.1 Hz. **Only as good as its fstart is low.** |

**QoI screening rule (REQUIRED slot).** Restated **verbatim** from the CFD card
(`docs/envelope_card_cavity2d.md` §6, ruling 2026-07-15), which the FEA card also
adopts:

> "every extremum QoI must be screened for boundary-singularity contamination at
> design vet, not merely for contract fit."

**On this substrate the screen is the timestep-refinement ladder (N4), and it has
teeth in both directions.** `max(v_out)` passes it — the settle is monotone across
three decades of `tmax` (§3A). The FEA card's `max_von_mises` fails the identical
screen and is reported-only. **Passing the extraction contract's mechanical fit is
not passing the screen.** And per the tmax/tstep mechanism (§3A), the ladder is
only meaningful **wholly inside the fine region** — a ladder that reaches into the
saturated or binding-but-coarse band produces a non-monotone, sign-flipping trend
that the screen would (correctly) reject.

**The `corner_3db` per-run bias note (added this session, Task C).** Every
`corner_3db` extraction now appends its own estimated bias to `diagnostics`:

```
… ; corner_3db of v(out); estimated fstart bias 1.00e-06 relative, HIGH
((fstart/corner)^2 with fstart=1 Hz, 3.0 decades below the corner) — this
dominates grid density (~26x on the self-checked RC), so do NOT read a
grid-refinement delta as the error bar; lower fstart to shrink it
```

Live, on the real solver: at fstart = 10 Hz it estimates **1.00e-04** against a
**measured 9.94e-05**; at 1 Hz, **1.00e-06** against **9.96e-07**. *The wrapper
now reports its own dominant error term, to three digits, on every run that
carries it* — turning a documented trap into a number the caller cannot miss.
The note **never raises**: diagnostics must not be what fails an otherwise good
run, so an inestimable bias degrades to an honest string.

---

## 7. Cost model (measured rates)

Per the D5 doctrine: **a range with its per-point evidence, never a constant.**

| Operating point | Measured wall-clock | Evidence |
|---|---|---|
| divider `.op` (3 elements, 1 data row) | **0.282 s** | check a |
| RC `.ac`, 10 pts/decade | **0.253 s** | check c |
| RC `.ac`, 100 pts/decade | **0.256 s** | check c |
| RC `.tran`, tmax 50 µs | **0.255 s** | check d |
| RC `.tran`, tmax 0.5 µs | **0.263 s** | check d |
| RLC `.tran`, tmax 10 µs | **0.409 s** | check e |
| RLC `.tran`, tmax 0.1 µs (30,023 rows — the heaviest) | **0.667 s** | check e |
| **Range (family v1, n = 31 single runs)** | **0.19 – 0.85 s / run** (median **0.26 s**) | checks a–e + `coarse_extremum_evidence.json` |
| Hard kill limit | **600 s** → reported failure | `run_ngspice.py` `TIMEOUT_SECONDS` |

**Note (honest):** the cost is **container-exec overhead, not solve time** — the
circuits solve in milliseconds. A 30,023-row transient and a 3-element steady
solve differ by **well under 3×**, so *do not model this substrate's cost as
proportional to circuit size or simulated duration*; over the exercised envelope
it is close to a fixed per-invocation toll. No per-element or per-row rate is
quoted. `selfcheck_evidence.json` check b's `runtime_s_total` of 1.535 s is a
**six-run sweep total**, not a single run, and is excluded from the range above.
If a case ever approaches the 600 s kill, that is a signal it has left this
regime — not a cost-model refinement.

---

## 8. Negative space + open watches

**What this card does NOT cover** (out of scope for family v1 as drafted):
semiconductor devices of any kind; behavioural/expression-valued sources;
transmission lines; subcircuits; any nonlinearity; noise/pz/disto and every
analysis outside {op, dc, ac, tran}; phase (only `.ac` magnitude is offered);
multi-QoI, time-series, or vector returns; and **anything about a physical
board**.

**Open watches:**

1. **`K` coupled inductors — OPEN.** Mutual coupling is **linear and would fit
   this regime**, but it is **untested here**, so v1 rejects `K` by letter. This
   is a deliberate exclusion pending evidence, **not** a physics limit — the one
   place this card is narrower than its own regime. *Evidence:
   `regime_escapes` probe `K coupled inductors`.*
2. **`+` continuation lines rejected (§4H).** A known over-rejection: legal SPICE
   that v1's line-by-line screen refuses. Fails safe. Widen only when a real case
   needs it.
3. **Device-model card (N5).** A future **demand-driven** (substrate, regime)
   pair with an **expert reviewer** — device fidelity cannot be validated from
   inside this system. Not started; wake on real demand.
4. **External reviewer dispatch — pending.** Not yet scheduled. Until it lands,
   provenance stays `drafted-by-agent` and this card carries the weakest
   grounding authority.
5. **Registration deferred until after calibration.** The substrate stays
   `calibrating` / unroutable. `contract_for("ngspice_linear_passive")` **must
   keep raising `LookupError`** — the registry row is staged **without** a
   `_CONTRACTS` entry, exactly as FEA and code are. *That raise is the invariant,
   not a gap to fill.* See `onboarding/ngspice_linear_passive/
   registry_row_fragment.py`.
6. **The staged `.gitignore` line** (`/cases_ngspice/`). Case evidence lands in
   the **`build-scipy` worktree** regardless of where the code runs, because
   `run_ngspice.py:119` pins an absolute `SHARED_HOST` that the container mount
   matches. See `MERGE_NOTES.md` §0.
7. **Battery assembled but UNEXECUTED.** `docs/ngspice_calibration_cases_v1.md`
   pre-registers 15 cases; **zero model calls have been spent.** An owner-OK'd
   slot on the shared Wave-2 evening is pending. The battery also **cannot run
   until** `calibration_battery` is wired (`battery_wiring_fragment.py`).
8. **The marker-scan layer has no battery coverage (§5).** Unreachable by the
   harness by construction; proven by evidence + unit test instead. Would need a
   battery track that actually solves.
9. **Stage-2 schema is CFD-pinned.** `stages/stage2_spec.py` imports its QoI
   vocabulary from `tools.run_cfd`; ngspice's QoI shape is not a superset.
   Nothing blocks today (ngspice is unroutable and Stage 2 never authors an
   ngspice spec), but routing would require dispatch-by-substrate. See
   `schema_fragment.py`.
10. **G10 sits ON its bound (1.0995e-02 vs a ruled 1%), and that is
    structural — so the case is BANDED.** Because `tmax` saturates, **~1.1% is
    the achievable-error ceiling** on that circuit: no setting produces a
    decisively-over-tolerance reading. *Amended owner-ruled 2026-07-16,
    pre-battery* (was `under-resolved` / `[refine]`): G10 is now
    `expected_class: edge`, `acceptable_labels: [refine, defer]`. **Either
    cautious verdict is correct; only `trust` scores as a failure**, and the
    **per-draw verdict distribution is the informative output**, not the modal
    label. Scoring a defensible `defer` as a miss would be scoring the slate's
    construction rather than the gate. If the battery ever needs a *decisive*
    `refine` case, it needs a **different circuit** (a higher-Q resonance), not
    a coarser setting. G10 is the **only** banded case on the slate, enforced by
    `tests/test_calibration_cases_ngspice.py::test_only_g10_is_banded`.
