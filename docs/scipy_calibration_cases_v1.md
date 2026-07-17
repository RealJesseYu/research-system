# sci-Python Regime A (`sympy_symbolic_exact`) — calibration pre-registration + PROPOSED slate

> **STATUS: PROPOSED.** The slate is an **owner ruling (R-CAL-2)** and is not
> decided here. Battery execution is a **separate ⚙ owner-approved run** and did
> NOT happen in the build session. Every case carries
> `label_provenance: drafted-by-agent`.
>
> Case file (**GENERATED, never hand-authored**):
> `harness/calibration_cases_sympy_symbolic_exact.json`
> Generator: `onboarding/sympy_symbolic_exact/generate_cases.py`
> Source of truth: `onboarding/sympy_symbolic_exact/contract.py`
> Card: `docs/envelope_card_sympy_symbolic_exact.md`

---

## 1. PRE-REGISTRATION (verbatim, as registered by the sci-Python branch chat 2026-07-16, BEFORE the build session started)

> Registered by the sci-Python branch chat 2026-07-16, **before** the build session started.
> Score in the debrief: predicted vs happened, **misses first**.

**Structural (expect right):**
- P1 wrapper return field set exactly: `valid, state, result, residual, crosscheck, reason, diagnostics, runtime_s`.
- P2 rejection taxonomy as listed in Task 3a (deltas reported by name).
- P3 all six escapes fail as required; **E6 passes the allowlist first, then is contained by the jail.**
- P4 docs corpus: 120–500 pages → 500–2,200 chunks (wide, low confidence, registered anyway).
- P5 tests ADDED: 28–45.
- P6 typical per-op wall time 0.3–3 s (startup-dominated); E6 contained in <30 s.
- P7 `integrate_indefinite` of `x**x` → state `unevaluated` (an `Integral` survives), result null.

**Cost (for the later battery ask):**
- P8 Regime A card shorter than the code card ⇒ ≤ ~5.5 s/gate-call ⇒ 30 gate calls ≈ **2.5–4.5 min**
  at N=3. (Measured anchor: FEA's 2026-07-16 battery ran 428.55 s / 30 calls = 14.3 s/call on a much
  longer card.) Re-predict from the drafted card's measured length in the debrief.

**Behavioral (expect wrong; register anyway):**
- P9 the two S3 probes (B3, B4) each go **unanimous defer 3/3** — the C4-steadiness transplant
  works (confidence ~55%).
- P10 the S4 probe (B1, `unevaluated`) goes **modal defer**, predicted unanimous 3/3; the named
  risk is the gate narrating it as an error (confidence ~50%).
- P11 ≥8/10 gate cases unanimous at N=3 (a screen, not a stability proof).

---

## 2. P8's premise is contradicted by disk — the re-prediction

**P8's reasoning chain does not survive measurement, and the correction matters
for the battery ask.** P8 assumes card length drives per-gate-call wall time.
Measured, from the on-disk battery reports and the cards themselves:

| Card | Length (chars) | Battery s/call at N=3 | Source |
|---|---|---|---|
| `calculix_cantilever` (FEA) | **13,865** (the SHORTEST) | **14.29** (the SLOWEST) | `calibration_calculix_cantilever_fea_20260716T053643Z.json` — 428.551 s / 30 calls |
| `code_sklearn_eval` | 18,166 | **7.61** | `calibration_code_sklearn_eval_20260716T053650Z.json` — 258.882 s / 34 calls |
| `cavity2d` (CFD) | 20,514 | — | — |
| **`sympy_symbolic_exact` (this draft)** | **26,508** (~6,627 tokens) | *to be measured* | this session |

Two corrections:

1. **The prompt's parenthetical is wrong about the card.** FEA's 14.3 s/call is
   arithmetically right (428.551 / 30), but it did **not** run "on a much longer
   card" — the FEA card is the **shortest of the three**, 24% shorter than the
   code card.
2. **The correlation runs the wrong way.** The shorter card produced the slower
   calls: FEA's card is 24% shorter than code's, yet its calls took **88%
   longer**. Card length is **not** the driver of per-call latency. (A plausible
   driver is output length — FEA's physics rationales run long — but this
   session did not measure that and does not claim it.)

**Honest re-prediction.** Since the premise is false, predicting from this card's
length would be unfounded in either direction. The defensible anchor is the
**observed range across the two real batteries, 7.6–14.3 s/call**:

> **30 gate calls (10 gate cases × N=3) ≈ 228–429 s ≈ 3.8–7.2 minutes.**

P8's 2.5–4.5 min is **likely optimistic**; its floor (5.5 s/call) was the code
battery's *N=1* rate, and the same battery rose to 7.61 s/call at N=3. This card
being the longest yet is **recorded as a fact, not converted into a slower
prediction** — the measured relationship does not license that inference.

---

## 3. Battery scope note

- Gate cases are judged via the **frozen stage-3 `SYSTEM_PROMPT`** + per-case
  inputs through `call_stage_model`, **not** `stage3.run()` — a disclosed
  deviation (**R-CAL-1**), because `run()` hardcodes `CAVITY_2D_CONTRACT` and
  appends to the production fidelity ledger.
- **Calibration ledger only**; the fidelity ledger stays **0/0**.
- **`--repeats N` is mandatory on gate cases** (R-REP-1): the gate is stochastic,
  a split verdict is DATA, and it is reported as a per-case distribution, never
  collapsed to a point.
- Wrapper cases are deterministic, **zero model calls**, and run **once**; they
  are scored **separately** and never averaged into gate accuracy.

### 3.1 ⚠ THE SLATE IS NOT YET LOADABLE — a named, unbuilt seam

`harness/calibration_battery.py` selects a case file and a validator through two
**module-level dicts hardcoded to the FEA and code substrates**:

```python
_CASE_FILES = {
    "calculix_cantilever_fea": "calibration_cases_fea.json",
    "code_sklearn_eval": "calibration_cases_code.json",
}
```
…and `_wrapper_validator()`, an `if/elif` over the same two ids, which
`raise KeyError` for anything else. `--substrate` is further constrained by
`choices=sorted(_CASE_FILES)`, so `--substrate sympy_symbolic_exact` is rejected
at argument parsing.

**`harness/calibration_battery.py` is OUTSIDE this session's scope**, so the
registration was **staged, not merged** (see
`onboarding/sympy_symbolic_exact/registry_row.md`). The generated JSON validates
against the battery's own `load_cases` contract and its RULE-1 answer-key
tripwire (both replicated and passed this session), but the battery **cannot
load it** until the Wave Guide merges the three-line registration.

---

## 4. THE PROPOSED SLATE (15 cases — an OWNER ruling, R-CAL-2; NOT presented as decided)

**10 gate cases** (judged by the real fidelity gate) + **5 wrapper cases**
(the wrapper's own validator; zero model calls; scored separately).

### 4.1 Gate / clearly in-envelope (5) — expected `trust`

Each is verified by back-substitution; A1 additionally by the quad cross-check.
**All five were RUN live this session** — the measured residuals are in the card §3A.

| id | operation | case | expected | verification (measured) |
|---|---|---|---|---|
| **A1** | `integrate_definite` | `x*sin(x)` on `[0, π]` | `trust` | diff-back → residual **0.0**; quad cross-check delta **0.0** |
| **A2** | `diff` | `x**2 * exp(x)` | `trust` | central-difference spot-check → **1.83e-10** |
| **A3** | `limit` | `sin(x)/x` as `x→0` | `trust` | approach sequence → **1.67e-13**. **⚠ A FAVOURABLE SAMPLE — see the note below.** |
| **A4** | `dsolve` | `y' + 2y = 0`, `y(0)=3` | `trust` | `checkodesol` → **0.0**; **independent `solve_ivp` arm: max rel dev 2.31e-11, agrees — 4/4 ODEs agree, worst 2.90e-10** |
| **A5** | `solve` | `x**2 - 5x + 6 = 0` | `trust` | root substitution → **0.0** |

**A4's independent arm, in full.** A4 is one of only **two** cases in the slate
whose operation carries an independent-ALGORITHM arm (A1's `quad` is the other).
Because A4 declares an `ics`, `scipy.integrate.solve_ivp` (RK45) re-integrates
`y' = -2y` from `y(0)=3` across a stated `[0, 1]` and compares to the closed form
at 5 points **without ever consulting it**: **max relative deviation 2.31e-11,
agrees**. Across all four ODEs measured, **4/4 agree**, worst deviation
**2.90e-10** — and without an `ics` the arm **declines by name**
(`attempted: false`) rather than guessing. *Honest bound (card watch 13): the arm
is DIAGNOSTIC ONLY by ruling S6 and gates nothing, and `checkodesol` — which does
gate — verifies the **equation**, not the declared initial condition. A4's `ics`
is therefore checked by the arm that flags and not by the arm that gates.*

**A3 is a FAVOURABLE sample of the `limit` op, and the slate should say so.**
`sin(x)/x` converges **quadratically**, which is the only reason the arm closes
on it at 1.67e-13. The `limit` arm's residual is `|f(probe) − L|` at a **finite**
probe — the function's genuine remaining distance from its limit, not a
verification error — so it only closes for quadratic-or-faster convergence, and
correct-but-slower limits are **rejected**: `(exp(x)-1)/x` measures **5.00e-07**
and `atan(x)→∞` **1.00e-06**, both `verification_failed` while SymPy is exactly
right (card watch 6). **This does not touch A3** — A3's convergence is exactly
the case the arm handles, so its `trust` expectation stands on its own
measurement. The caveat is about **generalizing from A3 to the `limit`
operation**, which the slate must not do: A3 measures the arm at its best.

### 4.2 Gate / clearly out-of-envelope (5) — expected `defer`

| id | probe | case | why out |
|---|---|---|---|
| **B1** | **S4** | `integrate_indefinite` of `x**x` | → `unevaluated`. An **honest non-answer**, not a failure. Measured: `state=unevaluated`, `result=null`, surviving form `Integral(x**x, x)`. Named risk: the gate narrating it as an error. |
| **B2** | **S1** | a minimization request | Off-allowlist operation; the substrate cannot express it. Should defer to an optimizer, not reach for a stationary-point workaround. |
| **B3** | **S3 i** | claim = "the **mean value** of `sin(x)` on `[0, π]`"; typed = `integrate(sin(x), (x, 0, π))` | Solved exactly (**= 2**, measured `solved_verified`) — but the mean is **2/π ≈ 0.6366**. **True and worthless.** |
| **B4** | **S3 ii** | claim asserts **degrees** ("sin(30) = 0.5"); typed expression is radians | Exact result (`sin(30) = -0.988031...`), **wrong model of the claim**. |
| **B5** | **S5** | claim: `sqrt(x**2) = x` for all x; default complex assumptions | The declared **KNOWN GAP**. Measured: defaults → `x*sqrt(x**2)/2`; `positive=True` → `x**2/2`. Both exact; intent is unreadable. |

### 4.3 Wrapper / setup-error (5) — deterministic, run once, **scored separately, never averaged into gate accuracy**

| id | case | expect | pre-registered reason |
|---|---|---|---|
| **W1** | `sin(x` | reject | `parse_error` |
| **W2** | expression `x+y`, symbols `[x]` | reject | `undefined_symbol` — **the typo trap**; SymPy would auto-create `y` silently, so this check is the wrapper's own |
| **W3** | **= Escape 5** — `().__class__.__mro__` | reject | `ast_node_disallowed:Attribute`, **pre-container** |
| **W4** | **= Escape 6** — `10**10**100` | **ACCEPT** | *(see the deviation below)* |
| **W5** | an off-allowlist operation (`minimize`) | reject | `op_not_allowlisted:minimize` *(see the deviation below)* |

#### Two disclosed slate deviations (both forced by what the battery track can actually do)

The battery's wrapper track calls the substrate's **validator only** — it makes
**zero container calls** (`run_wrapper_case` → `validate(spec)`). Two
pre-registered wrapper cases assume container behavior the track cannot reach:

- **W4 (`10**10**100`) is labeled `expected_class: jail_contained`, NOT
  `setup_error`, and `expect_valid: true`.** The validator **deliberately
  accepts** it — that is the point of E6: bounding literal magnitude at layer 1
  would be a fake safety property. Calling a deliberate allowlist-pass a
  "setup_error" would misdescribe the very property the case exists to prove.
  The **containment** is proven live in
  `tests/test_run_scipy.py::TestEscape6ResourceBomb::test_jail_CONTAINS_the_bomb`
  (measured: `reason='timeout'`, `result=None`, 10.131 s, zero lingering
  containers), **not** by this battery track.
- **W5 is an off-allowlist operation, not the pre-registered timeout case.** A
  timeout is a **jail** property; the validator-only track cannot exercise it
  (an injected `timeout_s=2` never reaches a container). The timeout is proven
  live instead by
  `tests/test_run_scipy.py::TestJails::test_E4_timeout_kills_and_leaves_zero_lingering_containers`
  (killed under an injected 5 s wall, **zero lingering containers**). W5 was
  repurposed to the off-allowlist refusal so the slot still buys a real,
  in-track proof.

---

## 5. What this slate is designed to measure

1. **S3's transplant (B3, B4) — the headline experiment.** R-CARD-2's measured
   claim is that a ruling stating its **consequence** transmits steadily
   (code-C4: 9/9 defer, entropy 0) while one stating only a criterion splits
   (FEA-F1: entropy 0.9183 bits). S3 deliberately transplants C4's
   consequence-carrying **form** onto a different substrate. **Whether the
   steadiness travels with the form or was a property of the code card's content
   is exactly what B3/B4 would measure.** This is the evidence-visibility
   hypothesis, and it is **Open**.
2. **S4's honest non-answer (B1).** Does the gate defer an `unevaluated` result,
   or narrate it as an error? A substrate that correctly declines is a *working*
   substrate; misfiling that as failure would be the system slandering its own
   instrument.
3. **S5's declared gap (B5).** A JUDGMENT ruling cannot be enforcement. B5 tests
   what an explicitly-declared known gap transmits.
4. **S1's membership boundary (B2).** The cheapest checkable class — a
   sanity floor for the other four.
