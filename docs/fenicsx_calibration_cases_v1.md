# FEniCSx Calibration Cases — v1 (fenicsx_cantilever_elastic, family-v1 typed input)

> **SPECS ONLY — NO EXECUTION.** This document is the human-readable
> pre-registration of the labeled calibration slate for the FEniCSx
> linear-elastic cantilever substrate. Running the battery is a **later ⚙ task
> that needs owner OK** — nothing here has been executed against the gate. The
> substrate is UNREGISTERED and UNROUTABLE; these cases pre-register what a
> correct verdict should look like so the calibration run has an answer key.
>
> **THE SLATE IS AN OWNER RULING BEFORE ANY BATTERY FIRES** (precedent R-CAL-2).
> Every label below is `drafted-by-agent` and carries a one-line rationale.
>
> **The cases are not authored here.** They live in
> `onboarding/fenicsx_cantilever_elastic/contract.py` — the one runtime source of
> truth — and are generated into
> `harness/calibration_cases_fenicsx_cantilever_elastic.json` by
> `generate_cases.py`, byte-identity-checked by
> `tests/test_run_fenicsx.py::TestCaseFileGeneration`. This document explains
> them; it never redefines them.
>
> Companion card: `docs/envelope_card_fenicsx_cantilever_elastic.md` (bounds
> G1–G5). Reference beam: L=1.0, w=h=0.05 m, E=210e9 Pa, ν=0.3, P=1000 N,
> L/h = 20 — the **same beam as the sibling CalculiX card §3A**, deliberately.

## Class counts

| expected_class | count | case ids |
|---|---|---|
| `in` (in-envelope) | 5 | X01, X02, X03, X04, X05 |
| `out` (out-of-envelope) | 5 | X06, X07, X08, X09, X10 |
| `setup_error` (nonphysical input) | 5 | X11, X12, X13, X14, X15 |
| **Total** | **15** | |

Gate track 10 (in 5 / out 5), wrapper track 5 — matching the sibling FEA slate's
shape. The bounds referenced below are the card's **SUGGESTED** values (G1
slenderness L/h ≥ 10; G2 linearity δ/L ≤ 0.10; G3 mesh reproduction ≤ 2%; G4
`max_von_mises` reported-only; G5 element_degree ≥ 2). They are TODO-HUMAN and
may move; the labels here follow the suggestions.

---

## The headline: X06/X07 and the refine drought

**X06 and X07 are the reason this substrate is worth calibrating.**

The standing difficulty is that `refine` is the gate's least-drawn verdict, and
the existing slates give it little honest opportunity: a case is usually either
fine (trust) or fundamentally outside the instrument (defer). `refine` is the
verdict for the **middle zone** — *the number exists, it is wrong, and re-running
THIS instrument differently fixes it*. That zone is hard to construct
deliberately, and where it has appeared it has usually been contaminated: the
case is also out-of-regime, so `defer` is defensible too and the draw proves
little.

Degree-1 shear locking is a **clean** instance of the middle zone, and it is the
first this project has had:

- The input is **valid** (not a setup_error).
- The geometry is **fully in-envelope** — L/h = 20, δ/L ≈ 0.3%; G1 and G2 are
  satisfied with wide margin. Nothing about the *beam* is wrong.
- The solve **converges cleanly** and returns a confident number, with **nothing
  in the diagnostics** to suggest a problem.
- The number is **wrong by tens of percent**.
- **Re-running this same instrument at `element_degree=2` fixes it completely, on
  the very same mesh** — measured: 0.987× the closed form at 8×1×1, where degree
  1 manages 0.28×.

That last property is what makes `refine` genuinely apt rather than merely
allowed: the right instrument is *this* instrument, used correctly. `defer` stays
acceptable (routing to a non-locking instrument is a defensible reading), so the
band is `["refine","defer"]` — but **`trust` is excluded**, and a `trust` draw is
the **dangerous false-trust error**: it endorses a clean, converged, badly wrong
number. Per R-REP-1 those draws are reported as a **distribution, never averaged
away**.

**X06 vs X07 is the pair, and the magnitudes are measured, not assumed:**

| case | element_degree | mesh_density | measured tip deflection | vs closed form |
|---|---|---|---|---|
| X06 | 1 | 32 | 0.8364× | **16.4% too stiff** |
| X07 | 1 | 64 | 0.9446× | **5.5% too stiff** |

Both violate G5 identically. But X07's symptom is small enough to **look like
ordinary discretization error** rather than a regime violation. The pair asks a
sharp question: does the gate honor the **element-order bound as the card states
it**, or does it silently re-derive its own error tolerance from the magnitude
and trust X07? A split between X06 and X07 is a finding about card-to-gate
transmission, not noise.

---

## In-envelope cases (expected_class: `in`)

### X01 — the reference beam at the validated degree
- **params:** reference beam, `mesh_density=16`, `element_degree=2`.
- **why:** the validated point. L/h = 20, δ/L ≈ 0.3%, measured gap 0.61%.
- **correct verdict:** `trust`. Every bound satisfied with margin, validated QoI.

### X02 — very slender
- **params:** L=2.0, w=h=0.05, P=500, `mesh_density=16`, `element_degree=2` (L/h = 40).
- **why:** deep inside G1/G2; δ/L ≈ 0.61%.
- **correct verdict:** `trust`. **Note the tension this case sits on:** L/h = 40 is
  where Euler-Bernoulli is *most* trustworthy and where a naive element is *most*
  prone to lock. At degree 2 both facts are satisfied at once — which is exactly
  what the card's G1↔G5 tension says.

### X03 — the coarse-side edge case
- **params:** reference beam, P=3300, `mesh_density=8`, `element_degree=2` (δ/L ≈ 1.0%).
- **why:** the largest deflection on the in-envelope slate at the **coarsest**
  mesh. Measured gap 1.31% — inside the 2% G3 band, but the closest in-envelope
  case to its edge.
- **correct verdict:** `trust` **or** `refine`. A gate asking for a finer mesh
  before endorsing is defensible; this is the deliberate near-miss on the
  acceptance boundary, approached from the coarse side.

### X04 — the G1 boundary, exactly
- **params:** L=1.0, w=h=0.10, P=2000, `mesh_density=16`, `element_degree=2` (L/h = 10).
- **why:** G1 is stated as `L/h ≥ 10`; this case satisfies it **exactly**.
- **correct verdict:** `trust`. Measures whether the gate reads an inclusive
  boundary as the card writes it. The closest in-envelope case to `out`.

### X05 — degree 3: the bound is a floor
- **params:** reference beam, `mesh_density=16`, `element_degree=3`.
- **why:** G5 is `degree ≥ 2` — a **floor, not an exact value**.
- **correct verdict:** `trust`. A refine/defer here would mean G5 transmitted as
  an equality ("degree must equal 2") rather than a floor — a card-to-gate
  transmission finding, and the more interesting outcome.

---

## Out-of-envelope cases (expected_class: `out`)

### X06 — locked, fine mesh *(refine-expected #1 — see the headline)*
- **params:** reference beam, `mesh_density=32`, **`element_degree=1`**.
- **correct verdict:** `refine` or `defer`, naming the locked low-order element.
  **NOT trust.** Right instrument: this same model at `element_degree ≥ 2`.

### X07 — locked, finer mesh, mild symptom *(refine-expected #2)*
- **params:** reference beam, `mesh_density=64`, **`element_degree=1`**.
- **correct verdict:** `refine` or `defer`. **NOT trust.** Same G5 violation as
  X06 with a 5.5% symptom instead of 16.4%.

### X08 — stubby beam
- **params:** L=0.2, w=0.05, h=0.10, P=1000, `mesh_density=16`, `element_degree=2` (L/h = 2).
- **why:** far below G1. Shear deformation dominates; **Euler-Bernoulli is the
  wrong reference**, not merely an imprecise one, so the 3D solve deflects more
  than the beam limit and is not validated against it.
- **correct verdict:** `refine`/`defer`. Right instrument: a Timoshenko or full
  elasticity reference, against which this same solve could be validated.

### X09 — large deflection
- **params:** reference beam, P=50000, `mesh_density=16`, `element_degree=2` (δ/L ≈ 15%).
- **why:** above the G2 bound of 10%. The small-deflection solve ignores geometric
  stiffening and over-predicts deflection while converging cleanly.
- **correct verdict:** `refine`/`defer`. The **physics assumption itself** is
  broken and no re-run of this instrument fixes it — which is why `defer` is as
  apt as `refine` here, and why this case differs in kind from X06/X07.

### X10 — near-incompressible *(the OTHER locking — do not conflate)*
- **params:** reference beam, **ν = 0.4999**, `mesh_density=16`, `element_degree=2`.
- **why:** **VOLUMETRIC** locking, a different disease from X06/X07's **shear**
  locking. Degree 2 fixes shear locking; it does **NOT** fix this one. The input
  is well-formed (passes `_validate_input`, ν < 0.5), so this is **not** a
  setup_error — contrast X13 (ν = 0.6), which code rejects.
- **correct verdict:** `refine`/`defer`, flagging near-incompressible locking risk.
  Right instrument: a mixed/u-p or selective-reduced-integration formulation,
  which this instrument does not provide.
- **Honest note:** unlike X06/X07, this case's magnitude is **NOT measured** —
  the card's ν→0.5 entry is a physics-grounded anticipation, not a run. It is
  therefore the weakest-grounded `out` label on the slate.

---

## Setup-error cases (expected_class: `setup_error`)

Rejected by `run_fenicsx._validate_input` before any container call; the wrapper
returns `valid=False` with a named reason and **no QoI**. Scored on the **wrapper
track**: zero model calls, deterministic, run **once**, matched by
`reason_substring`. **Never averaged with the gate track.** Each substring below
is asserted against the real validator by
`tests/test_run_fenicsx.py::test_wrapper_case_substrings_match_the_real_validator`.

| case | spec change | pre-registered reason substring |
|---|---|---|
| X11 | `E = -2.1e11` | `field 'E' must be positive` |
| X12 | `height = 0.0` | `field 'height' must be positive` |
| X13 | `nu = 0.6` | `nu must be in (-1, 0.5)` |
| X14 | `element_degree = 0` | `element_degree must be >= 1` |
| X15 | extra field `material` | `unsupported field(s) for fenicsx cantilever v1: material` |

**X14 exercises the NEW field and pins the slate's load-bearing asymmetry:**
degree **0** is rejected in **code** (it is not a displacement element at all),
while degree **1** is **accepted** and left to the gate (ruling G5). The typed
floor (≥ 1) and the validated floor (≥ 2) are different bounds enforced in
different places, on purpose: *anything we can't afford broken goes in code* —
but a regime judgment belongs to the gate, and hard-rejecting degree 1 in the
wrapper would be the wrapper making a physics ruling that is not its to make.
Whether degree 1 should become a hard reject is an **owner ruling**, not this
session's.

### Disclosed deviation from the packet's wrapper-case suggestions

The family-v1 typed vocabulary **cannot express** a missing boundary condition or
an unmeshable geometry (both are structural properties of the fixed cantilever
template, not typed fields), and a deliberate-timeout case is **nondeterministic**
— it would put a wall-clock race on the wrapper track, which exists precisely
because it is deterministic. So X11–X15 mirror the sibling FEA slate's validation
classes plus the new `element_degree` field. **The owner can override at the slate
ruling.**

---

## Notes for the future battery run

- X01–X10 are executable cases; X11–X15 halt at input validation before any
  container call (fast, no docker).
- **X03 (G3 coarse edge), X04 (G1 boundary), X05 (G5 floor-not-equality), and
  X06/X07 (the locking pair)** are the most informative cases — each is a place
  where the gate must draw a line **the wrapper itself cannot see**. The card's §5
  is explicit that no regime check exists anywhere in this instrument.
- The `out` cases share the sibling slate's theme — the solver **converges and
  returns a number** that the envelope cannot validate — but X06/X07 sharpen it
  in a way no existing case does: the untrustworthiness lives in **the element
  order**, a *typed input the spec itself chose*, not in the beam, the QoI, or
  the regime. It is the one failure the caller can fix by re-running.

### Battery scope — R-CAL-1 disclosed deviation (inherited, unchanged)

The battery scores the gate's judgment via the frozen stage-3 prompt plus each
case's own substrate/envelope/experiment inputs through the direct
`call_stage_model` path — it does **NOT** call `stage3_fidelity_gate.run()`, which
hardcodes a contract and appends to the production fidelity ledger. This is the
ratified `fidelity_case_runner` precedent, recorded here as the standing deviation
for this slate too. The battery is LEDGER-SILENT and writes no `runs/` dirs.

### Merge dependency — the battery cannot run this slate yet

`harness/calibration_battery.py` is frozen to this build and its `_CASE_FILES`
does not know this substrate. **Three amendments are required before the battery
can fire**, staged in `onboarding/fenicsx_cantilever_elastic/battery_wiring.py`.
One is a **merge blocker**: every case here carries `label_provenance` and
`label_rationale` (the packet requires them), and the battery's own drift guard
asserts that every non-model-visible gate field is in `_ANSWER_KEY_KEYS`. Those
two names must be added — `label_rationale` states *why* a label is what it is and
is answer key in its purest form.

### Pre-registered predictions

- **P1 (X06/X07):** neither is raw-trusted, and the rationale names the element
  order — not merely "mesh" or "discretization error". If the gate says "refine
  the mesh" without naming the degree, it has diagnosed the wrong disease, and
  refinement is exactly the fix that does **not** work (measured: thickness-only
  refinement moved degree 1 from 0.2800× to 0.2894×).
- **P2 (X06 vs X07):** the two draw the same distribution. A split — X06 caught,
  X07 trusted — means the gate is reading the *magnitude*, not the *bound*.
- **P3 (X05):** trusted. A refine/defer means G5 transmitted as an equality
  rather than a floor.
- **P4 (X10 vs X13):** X10 reaches the gate and is not trusted, while X13 never
  reaches it. If the gate treats X10 as a setup_error, it has confused a
  well-formed-but-suspect input with a nonphysical one.
