# ngspice_linear_passive — calibration cases v1 (PRE-REGISTRATION)

> **STATUS: PRE-REGISTERED, UNEXECUTED.** No model call has been spent on this
> slate. Labels below are committed *before* the battery runs — that is the
> whole point of writing them down here.
>
> **Runtime source of truth:**
> `onboarding/ngspice_linear_passive/generate_calibration_cases.py`. This
> document is the human-readable companion; the machine-readable slate is
> `harness/calibration_cases_ngspice_linear_passive.json`, which is **GENERATED,
> never hand-edited** (`tests/test_calibration_cases_ngspice.py` asserts
> byte-identity with a fresh generation, so a hand edit fails the suite).
>
> **Slate provenance:** `drafted-by-agent (slate owner-ruled 2026-07-16; W01
> dot-line amendment owner-ruled 2026-07-16)`.

---

## What is being tested

Two tracks, scored separately and never averaged together.

**Gate track (G01–G10).** One Opus call per case against the frozen Stage-3
fidelity prompt. The model sees only the case `id`, the substrate summary
(`substrate_text`, 700 chars), the envelope rulings (`envelope_text`, 2,290
chars), and the `experiment` text. Everything else on a case — its expected
class, its acceptable labels, the rationale, the right instrument — is **answer
key**, blocked from the model input by the battery's RULE-1 tripwire.

**Wrapper track (W01–W05).** No model, no container: the battery calls
`run_ngspice._validate_input` directly and asserts it rejects with the
pre-registered reason. One case per **pre-solve defense layer**, zero overlap.

### The headline question (R-CARD-2)

**G07 is the pre-registered steadiness test.** Its netlist is byte-identical in
substance to G01's — a clean divider that is a clean `trust`. The *only*
difference is that G07's claim asserts physical-hardware behaviour. Ruling N3
states its consequence explicitly on both sides (*trust the number AND defer the
board claim; verdict `defer`*). The measured precedent: the code card's
consequence-stating C4 held **9/9 defer at entropy 0**, while FEA-F1's
criterion-without-consequence **split at 0.9183 bits**. If N3's explicit
consequence transmits, G07 should be steady. A split at G07 is the informative
result, not a failure.

---

## The six rulings (owner-RULED 2026-07-16)

Transcribed in full, with class and both-sided consequence, in
`docs/envelope_card_ngspice_linear_passive.md` §3B. In brief:

| # | Ruling | Consequence when it fails |
|---|---|---|
| **N1** | in-regime analyses = {op, dc, ac, tran} | defer — wrong instrument |
| **N2** | analytic reproduction within **1% relative** | refine (tighten tmax / lower fstart); defer only if refinement fails |
| **N3** | **netlist-vs-board split** | trust the number AND defer the board claim → verdict `defer` |
| **N4** | transient extremum validated under the timestep protocol | unvalidated setting → refine; unscreened family → reported-only |
| **N5** | device-model honesty = **KNOWN GAP** | advisory: defer to a future expert-reviewed device-model card |
| **N6** | R/L/C **4-token arity** | setup_error, rejected by line pre-solve |

---

## Gate track — in-envelope (expect `trust`)

| id | class | labels | the case | why this label |
|---|---|---|---|---|
| **G01** | `in` | `[trust]` | 10 V divider, 1k/2k, `.op`, `op_value` of `v(out)`; claim: this netlist's `v(out)` ≈ 6.667 V | The self-checked divider, rel err **5.0e-10** (evidence check a). In-regime analysis, 4-token lines, claim scoped to the netlist. Dead centre. |
| **G02** | `in` | `[trust]` | same divider, `.dc` sweep 0→10 V; claim: slope = R2/(R1+R2) = 0.6667 | Measured slope 0.6666666668571428 vs analytic 0.6666666666666666, rel err **2.9e-10** (check b). |
| **G03** | `in` | `[trust]` | RC low-pass 1k/159.155n, `.ac` dec 100/decade, **fstart = 1 Hz**, fstop = 100 kHz, `corner_3db`; claim: corner = 1.000 kHz | fstart is three decades below the corner, so the `(fstart/fc)²` proxy bias is ~**1e-6** (measured 9.96e-07, check c) — four orders inside N2. The claim names its grid *and* its fstart, which is what makes it reproducible. |
| **G04** | `in` | `[trust]` | RC step, τ = 1 ms, `.tran` tmax = **0.5 µs**, `value_at` t = 1 ms; claim: v(τ) = 0.6321 V | Validated tmax: rel err at τ is **2.80e-07** (check d ladder 4.97e-05 → 6.71e-07 → 2.80e-07). `value_at` is an interpolated point, not an extremum — N4 does not apply. |
| **G05** | `in` | `[trust]` | series RLC, ζ = 0.2, `.tran` tmax = **0.1 µs**, `max` of `v(out)`; claim: peak = 1.5266 V, protocol run, settle cited | **The N4 showcase and the project's first validated extremum.** Screened exactly as N4 requires: absolute gap settles **4.8e-3 → 5.6e-5 → 4.7e-7** as tmax tightens 10 µs → 1 µs → 0.1 µs (check e). At tmax = 1e-7 that is 3.10e-07 *relative*. Contrast the FEA card's `max_von_mises`, which fails the same screen. |

## Gate track — out-of-envelope (expect `defer`)

| id | class | labels | the case | why this label |
|---|---|---|---|---|
| **G06** | `device-model` | `[defer]` | diode + `.model` card, `.dc` sweep; claim: reproduces the diode's exponential I-V, knee voltage good to 1% | **N5 (with N1 in support).** The claim rests entirely on semiconductor-model fidelity, which no text here can vouch for — silicon lives in datasheets and on the bench. Doubly out: both the `D` letter and the `.model` dot-line are rejected pre-solve, so the claim can never reach a number. |
| **G07** ⭐ | `board-claim` | `[defer]` | **clean** divider netlist; claim: *a physical PCB assembled from this schematic, with 1% resistors, will measure 6.67 V ± 1% at `out`* | **The N3 spine — the R-CARD-2 steadiness test.** The netlist is impeccable and identical to G01's clean `trust`; the only thing separating them is a claim about hardware. The number is right and the board claim is unsupported: no parasitics, tolerance, ESR, or ground effects are represented. |
| **G08** | `out-of-regime` | `[defer]` | behavioural B-source (`V=v(a)*v(a)`), `.tran`, `max` of `v(b)`; claim: 2nd-harmonic peak = 1.0 V | A B-source is expression-valued and **nonlinear**; superposition — which every self-check rests on — does not hold for a squarer. The `B` letter is rejected pre-solve. The extremum QoI is a second, independent caution (N4), but the regime miss is decisive alone. |
| **G09** | `wrong-analysis` | `[defer]` | the **clean, self-checked RC**; `.noise` analysis; claim: thermal noise floor = 4 nV/√Hz to 1% | **N1 in isolation, and the cleanest miss on the slate.** The netlist is perfectly in-regime and the physics is linear — only the *analysis* is outside {op, dc, ac, tran}. `.noise` is offered by ngspice, validated by nothing here, and rejected by the typed enum before anything runs. |

## Gate track — edge (expect `refine` **or** `defer`)

| id | class | labels | the case | why this band |
|---|---|---|---|---|
| **G10** | `edge` | `[refine, defer]` | the **same** ζ = 0.2 RLC as G05, `.tran` **tmax = 20 µs**, `max` of `v(out)`; claim: peak = 1.5434 V, **no refinement ladder run** | **The N2/N4 consequence test — and a boundary case by construction.** Two independent reasons put this outside `trust`: (i) tmax = 20 µs is outside the validated ladder (extremum validated at tmax ≤ 1 µs) and no protocol was run — N4 alone makes this refine; (ii) the reading is **measured 1.0995e-02 relative** from the analytic peak — outside N2's 1% band. N2's stated consequence is `refine`: the circuit and QoI are squarely in-envelope and the fix is to tighten tmax. But the gap sits **on** the ruled bound, so a gate that reads a boundary claim with no refinement ladder and says `defer` is also behaving correctly. **Only `trust` scores as a failure.** |

> **G10 is BANDED — read before scoring it.** *(Amendment owner-ruled
> 2026-07-16, **pre-battery**: G10 was drafted as `under-resolved` accepting
> `[refine]` alone. No battery result was seen before the amendment.)*
>
> The measured gap `1.0995e-02` sits against a **ruled bound of 1%**, and
> **~1.1% is this circuit's achievable-error ceiling** — so the case cannot be
> moved decisively off the boundary by *any* setting. Banding it `edge` says
> what is true: **either cautious verdict is acceptable, and only `trust` is a
> miss.** Scoring a defensible `defer` as a failure would be scoring the slate's
> own construction, not the gate.
>
> **The informative output here is the per-draw verdict distribution, not the
> modal label.** A refine/defer split is *data about where the gate places a
> boundary* — exactly what `--repeats` and the per-case distributions exist to
> capture. Read it alongside G07's entropy, not as a pass/fail.
>
> **Why the ceiling is structural.** The strategist's pre-registration ("tmax =
> 1e-4 lands between 10% and 50%") is **falsified by one to two orders of
> magnitude**, because `tmax` is a *ceiling on the solver's step, not a target*:
> ngspice's adaptive error control already steps at ~2e-5 here, so every tmax
> from 4e-5 to 2e-4 is **inert** — identical peak `1.52415539`, identical 144
> data rows. A `.tran` cannot be coarsened past its adaptive floor, only
> refined. Inside the narrow band where tmax *does* bind (≈3e-5 … 1e-5) the peak
> error is **non-monotone and sign-flipping** — the textbook signature of an
> extremum tracking the grid. Full sweep and mechanism:
> `onboarding/ngspice_linear_passive/coarse_extremum_evidence.json`
> (`findings.reachable_error_is_bounded`).
>
> **A more decisive `refine` case needs a different circuit** (a higher-Q
> resonance), not a coarser setting. See card §8 item 10.

---

## Wrapper track — one case per pre-solve layer, zero overlap

`expect_valid: False` for all five. Each `reason_substring` identifies the
**layer**, not the exact prose (owner condition, 2026-07-16), and
`tests/test_calibration_cases_ngspice.py` proves the separation by failing the
escape: no case's substring may match another case's rejection.

| id | layer | the input | why it must be caught here |
|---|---|---|---|
| **W01** | **dot-line** | `.include /etc/passwd` appended to a clean divider | The wrapper composes every dot-command itself. A caller-supplied `.include` would otherwise pull arbitrary host content into the deck. |
| **W02** | **value** | `R1 in out 0` | **The no-other-defense case.** A zero-valued resistor emits **no log marker**, exits 0, and reports a fabricated **1000 A** through the short. The pre-solve value screen is the *only* thing between that netlist and a confident wrong number. |
| **W03** | **arity** (N6) | `R1 in out 1k ac=100k` | Runs clean and **silently simulates a resistance other than the one written** — found by screening ngspice's own shipped test suite. Strict 4-token arity closes the whole `ac=` / `tc1=` / `ic=` / model-name family at once. |
| **W04** | **typed-field** | spec with `analysis` missing | The netlist is impeccable; the *request* is incomplete. The wrapper never guesses a default analysis. |
| **W05** | **letter** | `X1 in out sub1` | A subcircuit call could expand to anything, including active devices. Rejected by letter and line number before the deck is composed — the same layer that stops D/Q/M/J/B. |

### What the wrapper track cannot reach (and where that proof lives instead)

**The post-solve log-marker scan is unreachable by this harness, by
construction.** `calibration_battery.run_wrapper_case` calls the validator only
— no model, no container. The floating-node netlist (a V–C–C chain with no DC
path to ground) is **syntactically valid**, so `_validate_input` correctly
accepts it; what catches it is the marker scan *after* the solve, where ngspice
fails the OP solve, falls through gmin and source stepping, prints a plausible
voltage, and **exits 0**.

The slate's W01 originally targeted that layer. It was amended to the dot-line
layer by owner ruling (2026-07-16) because the case would have failed 100% of
runs for a reason unrelated to the substrate's correctness — *a check that
cannot pass is not a case*.

That defense is proven, twice, where it actually lives:

- `onboarding/ngspice_linear_passive/selfcheck_evidence.json` — adversarial
  probe `floating node (no DC path)`: `valid=False`, `qoi=None`, diagnostics
  `solver reported a failure (exit 0): singular matrix — a node has no DC path
  to ground`.
- `tests/test_run_ngspice.py::TestMarkerScanLayerIsWhereTheFloatingNodeIsCaught`
  — asserts the validator accepts it, the marker scan flags it, and (the escape)
  a clean log is *not* flagged.

Covering it in a battery would need a track that actually solves. None is
proposed; see card §8.

---

## Scoring notes

- **Tracks never average.** Gate cases are model verdicts; wrapper cases are
  deterministic validator assertions. The battery reports them separately.
- **`expected_class` is a per-substrate vocabulary**, as it is for the siblings
  (FEA uses `in`/`out`; code uses `in`/`conflation`/`metric-mismatch`/
  `leakage-suspect`). This slate uses `in`, `device-model`, `board-claim`,
  `out-of-regime`, `wrong-analysis`, `edge`, `setup_error` — chosen so the
  confusion matrix says *which* boundary moved, not merely that one did.
- **A gate case passes** iff the raw verdict is in its `acceptable_labels`. The
  maturity hook's downgrade is witnessed separately and never scored as the
  model's answer.
- **Exactly one case is banded: G10 (`edge`, `[refine, defer]`).** Every other
  gate case is a single-label commitment. A band is a claim that the boundary is
  *genuinely* ambiguous — G10's gap sits on its ruled bound and cannot be moved
  off it by any setting — and it is pre-registered as such, not widened after a
  result. `tests/test_calibration_cases_ngspice.py::test_only_g10_is_banded`
  enforces that: widening any other case to dodge a miss fails the suite.
  For G10, read the **per-draw verdict distribution**, not the modal label.
- **The battery cannot run this slate yet.** `calibration_battery._CASE_FILES`
  and `_wrapper_validator` have no ngspice entry, so `load_cases` raises
  `KeyError` today. See
  `onboarding/ngspice_linear_passive/battery_wiring_fragment.py`.
