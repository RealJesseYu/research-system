# Envelope Card — (sci-Python `scipy-img`, `sympy_symbolic_exact` / Regime A)

> **STATUS: DRAFT — not yet reviewed.**
> Provenance: `drafted-by-agent` (see §2). **Every §3B slot (S1–S6) is
> TODO-HUMAN** — each carries a SUGGESTED value and a one-line reason, and
> **none is decided**. An unresolved `TODO-HUMAN` in a load-bearing section
> (§3, §5, §6) blocks sign-off per `docs/reviewer_rubric.md`.
> This card is **HUMAN-FACING ONLY** (R-20.5-1 doctrine): no code reads it, no
> model sees it. The substrate is **UNREGISTERED and UNROUTABLE** — nothing in
> `stages/`, the supervisor, `substrates.py`, or any schema imports
> `tools/run_scipy.py`.
> **Card unit = the (substrate, physics-regime) pair.** sci-Python is TWO
> regimes; this card is Regime A only. **Regime B (`scipy_numeric_quad`) is
> QUEUED by owner ruling 2026-07-16** and has no card. SciPy is present in this
> regime ONLY as the cross-check diagnostic (§3A, §8).

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `scipy-img` sci-Python sandbox — ephemeral, no-network, memory-capped, read-only containers (**UNREGISTERED**: no router / `substrates.py` entry exists) |
| Physics regime | `sympy_symbolic_exact` **Regime A**: exact symbolic computer algebra over ONE closed-form expression, ONE allowlisted operation per job, over explicitly declared symbols. Not free-form CAS; not numerics. |
| Allowlisted operations | `integrate_definite`, `integrate_indefinite`, `diff`, `limit`, `series`, `solve`, `dsolve` (**SUGGESTED — see S1**) |
| Solver | SymPy **1.14.0** (exact CAS), with mpmath **1.3.0** as its arbitrary-precision backend |
| Cross-check arms | SciPy **1.18.0** `integrate.quad` (definite integrals) and `integrate.solve_ivp` RK45 (ODEs with a declared `ics`) — both **DIAGNOSTIC ONLY**, never a result (owner ruling 2026-07-16; Regime B queued). See §5 for the per-op independence table. |
| Image | `scipy-img:latest` (`python:3.12-slim` + pinned symbolic stack), colima context |
| Pinned stack (read from the BUILT IMAGE, this session) | Python **3.12.13** · `sympy 1.14.0` · `scipy 1.18.0` · `numpy 2.5.1` (resolver-selected, ≥2.0.0) · `mpmath 1.3.0` — captured by `pip freeze` into `tools/scipy_env/RESOLVED_VERSIONS.md`; **not copied from any prompt** |
| Image digest | `sha256:f1531c11bb6475d066d5a2d9e2ae49890353968ef9fd7205c91f5dbd3fcb6826` (593 MB) |
| Wrapper | `tools/run_scipy.py` (deterministic Python, no AI, **no LLM anywhere in the execution path** — it runs a FIXED job template, never writes code) |
| **Contract text** | **POINTER, never a paste → `onboarding/sympy_symbolic_exact/contract.py`** (constant `SYMPY_SYMBOLIC_EXACT_CONTRACT`). That module is the ONE runtime source of truth: the wrapper imports it, `generate_cases.py` generates the slate from it, this card points at it. |
| Card drafted against repo HEAD | `07816ba` (branch `build-scipy`) |
| Maturity | **calibrating** (unroutable; pre-registration — S1–S6 all TODO-HUMAN) |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, sci-Python build session 1) |
| Drafted date | 2026-07-16 |
| **Amended** | **session 1b, 2026-07-16** — independent verification arms (Task 2). Changed: §1 cross-check arms; §3A (re-measured residual floor over 33 jobs on all seven ops; the `solve_ivp` arm; the `limit` regression tried-and-reverted; a `limit` side-bug fixed); §3B S2 (margin re-measured — CONFIRMED at a thinner margin) and S6 (scope widened to two arms, value unchanged); §5A (new per-op independence table); §8 watches 5–9 (four NEW ⚠ items, three of them defects this session found but did **not** fix). **No §3B value was decided — every slot remains TODO-HUMAN.** |
| Sources | wrapper self-check runs captured live this session (the worked integral, diff, limit, solve, dsolve, series, the `x**x` non-answer, the assumptions pair); the six escape proofs in `tests/test_run_scipy.py`; `pip freeze` inside the built image (`tools/scipy_env/RESOLVED_VERSIONS.md`); SymPy 1.14.0 official docs archive |
| Signature | `unsigned` — S1–S6 await owner ruling |
| Reviewer sign-off | `pending — no external reviewer scheduled` |
| **Provenance state** | `drafted-by-agent` |

*Provenance state is the load-bearing field: it sets how much grounding authority
the card carries. It is `drafted-by-agent`, the lowest rung — **every §3B slot is
a SUGGESTION awaiting an owner ruling, not a bound that may be leaned on.***

---

## THE CENTRAL SPLIT (the spine of this card)

**A `solved_verified` result from this substrate is a TRUSTED statement about
EXACTLY THE EXPRESSION AS TYPED — nothing more.** Where it succeeds it is
*exact*, not approximate: an antiderivative is differentiated back and compared
to the integrand, a root is substituted back, an ODE goes through `checkodesol`.
When the wrapper returns `pi` for `integrate(x*sin(x), (x, 0, pi))`, that is the
exact value of that integral. **Trust the expression.**

**Whether that expression MODELS THE QUESTION THE CALLER MEANT is a SEPARATE
claim this substrate cannot adjudicate.** The gate may trust the symbolic result
**and must, in the same breath, defer the modeling/utility claim.** This is not
hypothetical — both worked contrasts below were RUN this session and both
returned `solved_verified` with a true number:

| A claim the substrate CAN adjudicate (trust THE EXPRESSION) | The conflated claim it CANNOT (defer) |
|---|---|
| "`integrate(sin(x), (x, 0, pi))` = **2**" — measured, exact, residual 0 | "the **mean value** of sin(x) on [0, π] is 2" — it is 2/π ≈ 0.6366; the integral was never divided by the interval length. **True and worthless.** (case B3) |
| "`sin(30)` = **-0.988031...**" — exact, in radians | "**sin(30°) = 0.5**" — true in DEGREES; the typed expression models a different unit convention. (case B4) |
| "`integrate(sqrt(x**2), x)` = **x*sqrt(x**2)/2**" — measured, exact under SymPy's defaults | "**sqrt(x²) = x** for all x" — false over ℝ (it is `Abs(x)`); under `positive=True` the same job returns **x²/2**. Which assumption set was meant lives nowhere the gate can read. (case B5 / S5) |

The symbolic answer is trustworthy *and narrow*. **This card exists so the narrow
truth is never read as the broad one.**

---

## 3. Validated envelope

Two sections, deliberately separate. §3A is disk-cited evidence actually run
**this session**; §3B is the set of envelope bounds, **all six TODO-HUMAN**.

### 3A. Self-check runs (live this session)

Every row below was executed through `tools/run_scipy.py` against `scipy-img`.
**Residual** is the wrapper's own back-substitution check; a result is returned
ONLY if it closes.

| # | operation | expression | result | residual | method | runtime_s |
|---|---|---|---|---|---|---|
| A1 | `integrate_definite` | `x*sin(x)` on `[0, π]` | **`pi`** | **0.0** (exact) | `symbolic_simplify_to_zero` | 1.246–1.751 |
| A2 | `diff` | `x**2*exp(x)` | `x**2*exp(x) + 2*x*exp(x)` | **1.8276e-10** | `numeric_central_difference_lambdify_numpy` | 0.946 |
| A3 | `limit` | `sin(x)/x` → 0 | `1` | **1.67e-13** | `numeric_approach_sequence_evalf` | 0.928 |
| A4 | `dsolve` | `y' + 2y = 0`, `y(0)=3` | `Eq(y(x), 3*exp(-2*x))` | **0.0** (exact) | `checkodesol` **+ `solve_ivp` arm: max rel dev 2.31e-11, agrees** | 1.263 |
| A5 | `solve` | `x**2 - 5*x + 6` | `[2, 3]` | **0.0** (exact) | `root_back_substitution` | 0.766 |
| — | `series` | `exp(x)` at 0 | `x**5/120 + x**4/24 + x**3/6 + x**2/2 + x + 1` | **0.0** | `numeric_truncation_comparison_lambdify_numpy` | 1.114 |
| B1 | `integrate_indefinite` | `x**x` | **null** — state `unevaluated` | n/a | n/a | 0.832 |

**The residual floor, re-measured across all seven ops (session 1b).** 33 jobs:
16 `diff` samples, 5 `limit`, 3 `series`, 3 `solve`, 5 `dsolve`, 4
`integrate_definite`, 3 `integrate_indefinite`.

| what | measured |
|---|---|
| Worst residual on any **verified** result | **4.05e-10** — `diff` of `sin(10*x)` |
| Margin to `VERIFY_RESIDUAL_TOL = 1e-9` (S2) | **2.47×** |
| The binding arm | `diff`'s central difference: error is **truncation-dominated** (`O(h²)`), so it is **unchanged by the evaluator** — HEAD's 50-dps `evalf` measured 4.12e-10 on the same expression, and `x**2*exp(x)` measures 1.8276e-10 under **both** to six significant figures |
| `series` / `solve` / `dsolve` / `integrate_*` | exactly **0.0** on 15 of 26 verified rows; worst non-zero elsewhere **6.55e-17** (`series` of `log(1+x)`) |

**The `solve_ivp` independent arm, measured** (`y' = f(x,y)` re-integrated from the
declared `ics` across a stated `[x0, x0+1]`, 5 sample points, never consulting
the closed form):

| ODE | closed form | max relative deviation | agrees |
|---|---|---|---|
| `y' + 2y = 0`, `y(0)=3` | `3*exp(-2*x)` | **2.31e-11** | true |
| `y' - y = 0`, `y(0)=1` | `exp(x)` | **2.90e-11** | true |
| `y' - x*y = 0`, `y(0)=2` | `2*exp(x**2/2)` | **2.90e-10** | true |
| `y' + y = sin(x)`, `y(0)=0` | `sin(x)/2 - cos(x)/2 + exp(-x)/2` | **3.68e-12** | true |
| `y' + 2y = 0`, **no `ics`** | `C1*exp(-2*x)` | — | **`attempted: false`** — "no initial condition declared; the solve_ivp arm needs one". The arm **declines rather than guessing**, and the symbolic answer still stands on `checkodesol` alone. |

**⚠ THE `limit` ARM: A MEASURED REGRESSION, TRIED AND REVERTED.** Session 1b's
brief was to move the `diff`/`limit`/`series`/`solve` spot-checks onto
`lambdify(..., 'numpy')`. For `limit` that is **actively harmful and the move was
reverted** — a limit spot-check evaluates an *indeterminate form* next to its
singularity, which is precisely where float64 catastrophic cancellation is the
rule, not the exception:

| `limit` | HEAD (`evalf`, 50 dps) | float64 (`lambdify+numpy`) | verdict |
|---|---|---|---|
| `sin(x)/x` → 0 | 1.666e-13 ✅ | 1.666e-13 ✅ | unaffected |
| `(1-cos(x))/x**2` → 0 | **4.169e-14 ✅** | **4.445e-05 ❌** | **a CORRECT limit rejected** |

At `x=1e-6`, `1 - cos(x)` loses ~11 of float64's ~16 digits. **No probe distance
rescues it**: cancellation grows as the probe shrinks and truncation grows as it
widens, and float64's best case for that expression is ~1e-8 — still outside S2.
Arbitrary precision is load-bearing for this arm, and the only
arbitrary-precision evaluator available is SymPy's own `evalf`. **Independence
lost to correctness**, deliberately; §5 records the resulting gap, and
`TestLimitArmStaysOnArbitraryPrecision` fails if anyone moves it back.

**⚠ A PRE-EXISTING `limit` DEFECT, exposed by re-measuring (NOT introduced this
session, NOT fixed).** The arm's residual is `|f(probe) − L|` at a **finite**
probe — the function's genuine remaining distance from its limit, which is **not
a verification error at all**. It closes only for limits converging
**quadratically or faster**. Measured, on *both* evaluators:

| `limit` | residual | outcome | SymPy's answer |
|---|---|---|---|
| `sin(x)/x` → 0 | 1.67e-13 | `solved_verified` | **correct** (quadratic approach) |
| `(exp(x)-1)/x` → 0 | **5.00e-07** | **`verification_failed`** | **correct** (`1`) — linear approach |
| `atan(x)` → ∞ | **1.00e-06** | **`verification_failed`** | **correct** (`pi/2`) — linear approach |

This **fails CLOSED** — it withholds correct answers rather than certifying wrong
ones — so it is a false-negative problem, not a safety one. But it means **A3
(`sin(x)/x`) is a FAVOURABLE sample of the `limit` op, not a typical one**, and
session 1's single limit measurement could not have revealed that. Fixing it
needs a convergence/extrapolation test, which is a redesign this session did not
have scope to make.

**A `limit` side-bug, found and FIXED.** The approach sequence probed `+10**k`
for *either* infinity. Measured at HEAD, `atan(x)` as `x → -oo` scored residual
**3.14159** — it was measuring `|atan(+1e6) − (−π/2)|`, i.e. approaching from the
wrong side of the number line. Both infinities now measure **9.9999e-07**.

**The independent cross-check (A1), measured:**

| field | value |
|---|---|
| `symbolic_value` | `3.141592653589793` |
| `quad_value` | `3.141592653589793` |
| `quad_abserr_estimate` | `3.487868498008632e-14` — **an ESTIMATE, not a bound** |
| `delta` | `0.0` |
| `agrees` | `true` (vs provisional `CROSSCHECK_AGREE_TOL = 1e-8`) |

**The assumptions pair (S5's gap, demonstrated live).** The same expression,
`sqrt(x**2)`, integrated indefinitely:

| declared assumptions | result | state |
|---|---|---|
| *(SymPy defaults — complex)* | `x*sqrt(x**2)/2` | `solved_verified` |
| `x: [positive]` | `x**2/2` | `solved_verified` |

Two different exact answers to the same typed expression. **Both are correct.
Nothing the wrapper or the gate can read says which one the caller meant.**

**The six escape proofs** (`tests/test_run_scipy.py`; each proves a jail by
FAILING an escape — reading the config would prove nothing):

1. **E1 no network** — `socket.gethostbyname('pypi.org')` inside the job fails
   `gaierror: [Errno -3] Temporary failure in name resolution` (`--network=none`).
2. **E2 memory cap** — a 600 MB allocation under a 256 MB cap is **OOM-killed at
   exit 137**; the named reason reaches the caller.
3. **E3 read-only workdir** — a write to `/job/escape.txt` fails **Errno 30,
   "Read-only file system"** (`--read-only` + `:ro` workdir mount).
4. **E4 timeout** — a `sleep(120)` under an injected 5 s wall is `docker kill`ed
   and leaves **zero lingering containers**.
5. **E5 parser** — `().__class__.__mro__` → `ast_node_disallowed:Attribute` and
   `__import__('os')` → `function_not_allowlisted`, both **before any container
   starts**.
6. **E6 resource bomb (the headline)** — `10**10**100` **PASSES the allowlist**
   (asserted: it is legal mathematics) and is then **contained by the jail**:
   `state=error`, `reason='timeout'`, `result=None`, 10.131 s under an injected
   10 s wall, zero lingering containers.
   **MEASURED, and it corrects the expected story:** the bomb does **NOT** OOM.
   CPython grinds CPU-bound building the integer and ran **>3 minutes under a
   256 MB cap** without tripping the memory cgroup. **The containment path is
   the WALL, not the cap.**

Also proven: the in-jail parse namespace is restricted — a non-allowlisted SymPy
name (`Poly`) does not resolve inside `parse_expr`'s eval, because the runner
overrides SymPy's default `global_dict` (which is `from sympy import *`).

### 3B. Envelope bounds — **ALL SIX ARE TODO-HUMAN**

Each carries a SUGGESTED value and a one-line reason. **None is decided.**
Per **R-CARD-1** every ruling states whether the gate can check it; per
**R-CARD-2** every ruling states its **CONSEQUENCE** as well as its criterion —
a criterion with no stated consequence transmits as a boundary with no teeth.

| Ruling | SUGGESTED value | **Class** | **Criterion (what the gate evaluates, and where it reads it)** | **Consequence (what follows when it holds — and when it fails)** |
|---|---|---|---|---|
| **S1** operation allowlist | `integrate_definite, integrate_indefinite, diff, limit, series, solve, dsolve` | `CHECKABLE:membership` | Is the requested operation a member of the allowlist? Read from the spec's `operation` field, checked against `contract.OPERATIONS`. | **Inside → eligible for trust** (the substrate can express the request at all). **Outside → defer**, routing to the right instrument; never a best-effort translation into a nearby operation. *(Probe: B2, a minimization request.)* |
| **S2** verification residual tolerance | `VERIFY_RESIDUAL_TOL = 1e-9` — **re-measured session 1b and CONFIRMED, on a thinner margin than session 1 claimed** | `CHECKABLE:numeric` | Is the wrapper's back-substitution residual ≤ 1e-9? Read from the wrapper's own `residual` field. | **Inside → `solved_verified`**, the result may be returned. **Outside (or absent) → `error:verification_failed`, result null** — a solved-but-unverified answer is an error; no number leaves unverified. **Margin, measured (§3A): the worst verified residual across 33 jobs on all seven ops is 4.05e-10 (`diff` of `sin(10*x)`) — only 2.47× inside. `diff` is the binding arm and its error is truncation-dominated, so this floor pre-exists the session-1b arm change and is not cured by it. Session 1's "at or below ~1e-10" rested on ONE `diff` sample (1.83e-10); 16 samples put the floor ~4× higher. 1e-9 still holds — but "far below" (§3B's original wording) is not what the measurements say, and a stiffer derivative could cross it.** |
| **S3** ⭐ **THE SPINE** — the modeling-claim rule | **ANY spec whose success criterion asserts something beyond the expression as typed → the gate MAY trust the symbolic result AND MUST defer the modeling/utility claim — both stated explicitly.** | `CHECKABLE:semantic` | Does the success-criterion text make a claim about anything other than the typed expression itself (a mean vs an integral, a unit convention, a domain, a real-world quantity)? Read from the success-criterion text under judgment. | **Trust the result about exactly the expression as typed; inside → the result is eligible for trust as a statement about the typed expression. Whether that expression models the intended question is a separate claim → always defer the utility/modeling claim.** Never a bare `trust`. *(Probes: B3 mean-vs-integral, B4 degrees-vs-radians.)* |
| **S4** the `unevaluated` verdict | **`defer` — explicitly NOT a failure** | `CHECKABLE:membership` | Did the wrapper return `state == "unevaluated"` (result null, reason null)? Read from the wrapper's `state` field. | **→ defer**, reported as an honest non-answer: the substrate worked correctly and this question has no closed form here. **It must NEVER be narrated as an error or a setup failure, and never leak as a QoI.** *(Probe: B1, `x**x`.)* |
| **S5** assumptions / branch cuts | *(no checkable bound exists)* | **JUDGMENT → KNOWN GAP** | **KNOWN GAP: whether the declared assumption set matches the caller's INTENT.** The wrapper validates that declared assumptions are allowlist members, but intent lives nowhere the wrapper or the gate can read. SymPy's defaults are COMPLEX: `sqrt(x**2)` ≠ `x`, and `log`/`sqrt` carry branch cuts. Measured: the same job returns `x*sqrt(x**2)/2` under defaults and `x**2/2` under `positive=True` — both exact. | **Advisory only, NOT enforcement.** The gate can transmit: "the answer is exact under the assumptions AS DECLARED; if the intended domain differs, the answer changes." It **may never be signed as if it were a check.** *(Probe: B5.)* |
| **S6** cross-check agreement | `CROSSCHECK_AGREE_TOL = 1e-8` (relative) — **scope widened session 1b: now covers TWO arms, value unchanged** | `CHECKABLE:numeric` | **Definite integrals:** is `delta / max(1, \|symbolic_value\|)` ≤ 1e-8? **ODEs with a declared `ics` (new):** is `max_relative_deviation` over the `solve_ivp` sample points ≤ 1e-8? Both read from the wrapper's `crosscheck` diagnostic. **No new provisional constant was introduced — the ODE arm reports against this same slot, so the owner rules once.** | **Agreement → corroborating EVIDENCE for the symbolic result, never independent proof.** Disagreement → a flag that one arm is wrong, resolved by a human, not by preferring the numeric arm. **Row present but bounded: Regime B (`scipy_numeric_quad`) card is QUEUED (owner ruling 2026-07-16); recorded here ONLY as the cross-check diagnostic's provisional agreement constant. quad's abserr ≠ a bound, and `solve_ivp`'s `rtol`/`atol` are error CONTROLS, not bounds — the same honest limit in a second costume.** Measured (§3A): 4 of 4 ODEs agree, worst deviation 2.90e-10. |

> **Both provisional constants (S2, S6) currently GATE the wrapper's behavior**
> so the machinery is exercisable now. They are labeled
> `SUGGESTED-pending-owner-ruling` at their definition in `contract.py`. A
> provisional constant that gates behavior is honest only while it is labeled
> one — **neither may be promoted by deleting its label.**

---

## 4. Known failure modes

For each: the name, the class it produces, **its detection class per R-CARD-1**,
and its evidence.

- **4A. Modeling conflation → SPLIT verdict (trust the expression, defer the claim).**
  **THE HEADLINE TRAP.** A spec pairs an exactly-solvable expression with a
  success criterion asserting something else (a mean, a unit convention, a
  domain). The expression is exact; the claim is not adjudicable here. The gate
  must issue both halves per S3 — never a bare `trust`.
  *`CHECKABLE:semantic` (the claim lives in the criterion text).* Evidence: THE
  CENTRAL SPLIT; cases B3, B4 — both measured `solved_verified` this session.
- **4B. `unevaluated` mistaken for failure → wrong class.**
  SymPy declines rather than inventing: `x**x` returns `Integral(x**x, x)`
  intact. Reporting this as an error would slander a correctly-working
  instrument; reporting it as a result would fabricate one. It is its own state.
  *`CHECKABLE:membership` (the `state` field).* Evidence: B1, measured
  `state=unevaluated`, `result=null`, `reason=null`.
- **4C. Assumption mismatch → silently different exact answer.**
  The default assumption set is COMPLEX. A caller who means "x is a positive
  real" and does not say so gets a different — still exact, still verified —
  answer. Nothing flags it.
  ***JUDGMENT / KNOWN GAP (S5).*** Evidence: the assumptions pair in §3A
  (`x*sqrt(x**2)/2` vs `x**2/2`).
- **4D. Symbol auto-creation on a typo → a free variable nobody declared.**
  SymPy AUTO-CREATES a symbol for any undeclared name, so `x+y` where `y` was a
  typo silently becomes a two-variable problem. **This check is the wrapper's
  own** — nothing in SymPy would complain.
  *`CHECKABLE:membership` (every free name must appear in `symbols`).* Evidence:
  case W2 → `undefined_symbol:y`, measured.
- **4E. Resource bomb → jail containment, never a wrapper answer.**
  A syntactically legal expression (`10**10**100`) can be computationally
  unbounded. Layer 1 correctly passes it; only the container stops it.
  *`CHECKABLE:structural` at layer 2 (a jail property, not a spec property).*
  Evidence: E6 — contained by the **wall**, not the cap, `reason='timeout'`.
- **4F. `parse_expr` is `eval` → arbitrary-code risk on unsanitized input.**
  SymPy's own docs say the parser uses `eval` and is unsafe. Two independent
  layers answer this: the AST allowlist (tripwire) and the container (what
  holds), plus a restricted parse namespace overriding `from sympy import *`.
  *`CHECKABLE:membership` at layer 1 (node/name allowlist).* Evidence: E5, and
  the restricted-namespace proof in §3A.
- **4G. quad cross-check read as proof → false confidence.**
  quad returns an error **estimate**, not a bound, and can be badly wrong on
  oscillatory/singular integrands while reporting a small abserr. Agreement is
  evidence; disagreement is a flag.
  *`CHECKABLE:numeric` (S6), with a JUDGMENT caveat on the estimate's meaning.*
  Evidence: A1 (`abserr_estimate = 3.49e-14`, an estimate).

---

## 5. What the diagnostics CAN and CANNOT see

The wrapper returns `valid`, `state`, `result`, `residual`, `crosscheck`,
`reason`, a bounded `diagnostics` string (≤800 chars, never raw container
output), and `runtime_s`.

### 5A. Per-operation verification, and how independent each check actually is

**Three independence tiers, and the difference is the whole point of this table:**

- **`symbolic-internal`** — SymPy checking SymPy's own work with SymPy's own
  evaluator. A bug shared between the operation and its check is **invisible**.
- **`numeric-partial (lambdify+numpy)`** — the expression is evaluated by
  **numpy's** arithmetic, a genuinely different evaluator from `.evalf()`. But
  the translation from the SymPy tree to a numpy callable is **`sympy.lambdify`**
  — SymPy's own translator. **The arithmetic is numpy's; the translation is not.**
- **`independent (quad, solve_ivp)`** — a genuinely different **ALGORITHM**
  (adaptive quadrature; RK45 time-stepping) recomputes the answer **without ever
  consulting the symbolic result**. This is the strongest tier available here —
  and it is **algorithm-independence, not translation-independence**: both arms
  still reach numpy through `lambdify`.

| operation | what is checked | method (as reported in `residual_method`) | **independence** | measured residual (§3A) |
|---|---|---|---|---|
| `integrate_definite` | differentiate the antiderivative back to the integrand | `symbolic_simplify_to_zero`, else `numeric_sampling_evalf` | `symbolic-internal` | **0.0** (4/4 samples) |
| ″ (second arm) | re-integrate the integrand numerically | `scipy.integrate.quad` | **`independent (quad)`** | delta **0.0 – 1.11e-16**, 4/4 agree |
| `integrate_indefinite` | differentiate the result back to the integrand | `symbolic_simplify_to_zero`, else `numeric_sampling_evalf` | `symbolic-internal` | **0.0** (2/2 verified) |
| `diff` | central difference of the (order−1)-th derivative vs the closed form | `numeric_central_difference_lambdify_numpy` (fallback: `..._evalf_fallback`) | **`numeric-partial (lambdify+numpy)`** | **4.48e-11 – 4.05e-10** (16 samples) — **binds S2** |
| `limit` | approach sequence toward the point at 50-digit precision | `numeric_approach_sequence_evalf` | `symbolic-internal` — **deliberately; the numpy move was measured to reject correct limits (§3A)** | **4.17e-14 – 1.67e-13** verified; **5e-07 / 1e-06 REJECTED though correct** |
| `series` | truncation comparison near the expansion point | `numeric_truncation_comparison_lambdify_numpy` | **`numeric-partial (lambdify+numpy)`** | **0.0 – 6.55e-17** (3 samples) |
| `solve` | substitute each root back into the expression | `root_back_substitution` (exact zero), else `root_back_substitution_lambdify_numpy` | `symbolic-internal`, **`numeric-partial`** fallback | **0.0** on both verified samples (`x**2-5x+6`, `x**3-2x-5`); **the numpy fallback has never fired live** — every root closed symbolically. A third sample, `cos(x)-x`, returned `error` — see watch 9 |
| `dsolve` | `checkodesol` on the returned solution | `checkodesol` (fallback: `checkodesol_numeric_fallback`) | `symbolic-internal` | **0.0** (5/5) |
| ″ (second arm) | re-integrate `y' = f(x,y)` from the declared `ics` over `[x0, x0+1]`, compare to the closed form at 5 points | `scipy.integrate.solve_ivp` (RK45) | **`independent (solve_ivp)`** | max rel dev **3.68e-12 – 2.90e-10**, 4/4 agree; **declines without an `ics`** |

**Reading this table honestly:** **2 of 7** operations carry an
independent-algorithm arm (`integrate_definite`, and `dsolve` *only when an
`ics` is declared*). **5 of 7** — `integrate_indefinite`, `diff`, `limit`,
`series`, `solve` — have **none**, and for three of those the strongest
available check is SymPy grading its own homework. Neither independent arm is a
proof: quad's `abserr` is an **estimate** and `solve_ivp`'s `rtol`/`atol` are
**controls**, so agreement is evidence and disagreement is a flag.

| CAN see | CANNOT see |
|---|---|
| Whether the returned closed form survives back-substitution (`residual`, S2) | **Whether the expression models the intended question (S3)** — the mean-vs-integral and degrees-vs-radians traps both return `solved_verified` |
| Whether SymPy declined to evaluate (`state == unevaluated`, S4) | **Whether the declared assumption set matches intent (S5)** — the KNOWN GAP; both assumption variants are exact |
| Whether an independent numeric arm agrees on a definite integral (`crosscheck`, S6) | Whether quad itself is right — its abserr is an **estimate, not a bound** (§4G) |
| Spec refused before any container (unknown/missing field, off-allowlist op, undeclared symbol, disallowed AST node) | Whether an undeclared name was a TYPO or intentional — only that it was undeclared (§4D) |
| Jail trips: OOM (exit 137), wall-timeout kill, read-only/network denials | Whether an expression will terminate — halting is undecidable; the wall is the only answer (§4E) |

*Overclaiming diagnostic reach is the most dangerous error a card can make: the
wrapper checks that the operation ran, produced a closed form, and that the
closed form survived back-substitution — **not that the closed form answers the
caller's actual question**.*

---

## 6. Extraction contract (verbatim)

**Contract text lives at `onboarding/sympy_symbolic_exact/contract.py`
(`SYMPY_SYMBOLIC_EXACT_CONTRACT`) — the ONE runtime source of truth. This card
POINTS at it; it is never pasted here, and the calibration slate is GENERATED
from it.** The table below names the vocabulary; the module is authoritative.

| Field | Meaning |
|---|---|
| `operation` | an S1 allowlist member |
| `expression` | the expression, as text; goes through the layer-1 AST allowlist |
| `symbols` | **every free name in the expression must appear here** — SymPy auto-creates symbols for typos, so this check is the wrapper's own (§4D) |
| `assumptions` | optional `{symbol: [allowlisted assumptions]}` — **changes the mathematical meaning** (§4C / S5) |
| `var`, `lower`, `upper`, `point`, `order`, `func`, `ics` | per-operation fields; `lower`/`upper`/`point`/`ics` keys are expressions and are allowlist-checked too |

Unknown fields are rejected **by name**, before any container.

**QoI extraction path** — verbatim capability, **three states, never collapsed**:

- **`solved_verified`** — a closed form was found AND independently verified
  (residual ≤ S2). `result` = the expression as a string. **This is the ONLY
  state that carries a result out of the wrapper.**
- **`unevaluated`** — SymPy returned the operation unperformed (an `Integral` /
  `Derivative` / `Limit` survived, or `solve` found no roots). `result` = **null**.
  An honest non-answer: **not an answer, not an error.**
- **`error`** — invalid input, allowlist rejection, container kill, timeout, or
  **`verification_failed`**. `result` = **null**, with a named `reason`.

Raw container output NEVER leaves the wrapper.

**QoI screening rule (REQUIRED slot).** Two screens, both mandatory before any
number from this substrate is used as a QoI:

1. **The three-state screen.** An `unevaluated` result is **screened out of ever
   being a QoI** — it is null by construction, and dressing it as either an
   answer or a failure is the failure mode (§4B / S4). A `verification_failed`
   result is likewise never a QoI: no number leaves unverified (S2).
2. **The cross-check screen (definite integrals).** Every definite-integral QoI
   is screened against the independent `quad` arm; disagreement beyond S6 flags
   the value for a human rather than silently preferring either arm.

*This is the Regime-A analogue of the CFD/FEA cards' numerical-artifact
screening (the corner-singularity family) and of the code card's benchmark-scope
rule — applied here to the exact-but-wrong-question boundary rather than to mesh
contamination. **The disease is the same shape: a number that is locally
impeccable and globally misleading.***

---

## 7. Cost model (measured this session)

Per standing doctrine, published as a **RANGE plus per-op points**, never a
single rate. **Container startup dominates** at Regime-A job sizes — as it does
for the code sandbox — so the wall-clock is essentially flat across operations
and is NOT a measure of symbolic difficulty.

| Operating point | Measured `runtime_s` | Evidence |
|---|---|---|
| `solve` (`x**2-5x+6`) | **0.617 s** | this session |
| `limit` (`sin(x)/x`) | **0.622 s** | this session |
| `series` (`exp(x)`) | **0.647 s** | this session |
| `diff` (`x**2*exp(x)`) | **0.660 s** | this session |
| `dsolve` (`y'+2y=0`, `y(0)=3`) | **0.730 s** | this session |
| `integrate_indefinite` (`x**x` → unevaluated) | **0.844 s** | this session |
| `integrate_definite` (`sin(x)`, `[0,π]`) | **1.162 s** | this session |
| `integrate_definite` (`x*sin(x)`, `[0,π]`, + quad cross-check) | **1.246 – 1.751 s** | this session |
| **Range (Regime A, these jobs)** | **≈0.6 – 1.8 s / job** | n = 8, this session |
| Hard kill limit | `timeout_s`, default **600 s**, ceiling `MAX_TIMEOUT_S = 600` → reported failure | `run_scipy.py` |
| Contained resource bomb (E6) | **10.131 s** under an injected 10 s wall | this session |

**Note (honest):** every job spins up its own ephemeral container (jails are
creation-time properties), so per-job cost is dominated by container
startup/teardown, not symbolic compute — which is why `integrate_definite`
(1.2–1.8 s, the only op paying for a quad cross-check) is the slowest while
`solve` and `limit` sit at the ~0.62 s floor. **No per-operation compute rate is
quoted**; the range above is the honest Regime-A cost statement. An unevaluated
result costs the same as a solved one — SymPy spends the effort either way.

---

## 8. Negative space + open watches

**What this card does NOT cover:**

- **Regime B (`scipy_numeric_quad`) — QUEUED** (owner ruling 2026-07-16). No
  SciPy operation is exposed as a standalone callable operation. SciPy's numbers
  appear **only** in the `crosscheck` diagnostic field and may never be returned
  as a result. Regime B gets its own card; **this one does not speak for it.**
- **No arm is independent of SymPy's TRANSLATION layer** (revised session 1b;
  see §5A for the per-op table). Two arms — `quad` for definite integrals and
  `solve_ivp` for ODEs with a declared `ics` — run a genuinely different
  **algorithm** and never consult the symbolic answer. But **both reach numpy
  through `sympy.lambdify`**, as do the `numeric-partial` spot-checks, so a bug
  in SymPy's translation is invisible to *every* check this substrate has.
  **`integrate_indefinite`, `diff`, `limit`, `series` and `solve` (5 of 7) have
  no independent-algorithm arm at all.** *(Session 1's version of this bullet
  called `quad` "the ONLY independent arm" and put the gap at "5 of 7" while
  naming six ops — the count is now exact because `dsolve` gained an arm.)*
- **No multi-expression / systems work** — one expression, one operation, one job.
- **No numerical analysis claims** — no conditioning, stability, or error-propagation
  statements.
- **No proof of termination** — halting is undecidable; the wall is the only answer.
- **No free-form CAS** — the operation set is closed (S1); arbitrary SymPy calls
  are refused, not sandboxed-and-run.

**Open watches:**

1. **Judgment slots S1–S6 (§3B) — ALL UNDECIDED.** Each needs an owner ruling
   before this card advances past `drafted-by-agent`. **S3 and S5 are the
   load-bearing pair.**
2. **The evidence-visibility hypothesis is OPEN — S3/S5 are an experiment on it.**
   R-CARD-2's measured claim is that a ruling stating its **consequence**
   transmits steadily while one stating only a criterion splits (code-C4: 9/9
   defer, entropy 0; FEA-F1: split, entropy 0.9183 bits). **S3 is a deliberate
   transplant of code-C4's consequence-carrying form** onto a different
   substrate; **S5 is a JUDGMENT gap declared up front.** Whether S3's steadiness
   travels with the *form* or was a property of the code card's *content* is
   exactly what the battery would measure. Pre-registered: B3/B4 unanimous defer
   3/3 (~55% confidence); B1 modal defer (~50%).
3. **E6's containment path is the WALL, not the cap (measured).** The bomb never
   OOMs — CPython grinds CPU-bound. If a future bomb class *does* OOM, both
   paths are named and handled, but the cap is **not** the load-bearing jail for
   this family. Worth re-measuring if the memory cap is ever tuned.
4. **`quad`'s abserr is an ESTIMATE, not a bound (§4G).** It can be small and
   wrong on oscillatory/singular integrands. S6 agreement is corroboration, not
   proof — and the temptation to read it as proof grows precisely when the
   symbolic arm is hardest.
5. **The remaining gap is TRANSLATION-independence, not evaluation-independence**
   (rewritten session 1b — the old wording, "no independent arm for 5 of 7", is
   now the §5A table's job). Session 1b bought **evaluation**-independence for
   `diff`/`series`/`solve` (numpy's arithmetic, not `.evalf()`'s) and
   **algorithm**-independence for `dsolve` (`solve_ivp` re-integrates from the
   `ics`). What no arm has is **translation**-independence: every check —
   including `quad` and `solve_ivp` — reaches numpy through `sympy.lambdify`. A
   lambdify translation bug would be invisible to the entire verification
   apparatus. Closing it needs a parser/evaluator outside SymPy's stack
   (re-parsing the expression text independently), which is unbuilt and is the
   honest next rung.
6. **⚠ The `limit` arm's residual is not a verification error** (NEW, session 1b;
   pre-existing defect, exposed by re-measuring, **NOT fixed**). It measures
   `|f(probe) − L|` at a finite probe, so it closes only for
   quadratically-or-faster convergence. `(exp(x)-1)/x` and `atan(x)→∞` are
   **rejected as `verification_failed` at ~5e-07 and ~1e-06 while SymPy is
   exactly right** (§3A). It fails **closed**, so this is a false-negative
   problem, not a safety one — but **A3 (`sin(x)/x`) is a favourable sample, not
   a typical one**, and session 1 measured exactly one limit. A convergence or
   extrapolation test would fix it; that is a redesign, not a re-measurement.
7. **⚠ The `series` arm has ~7 orders of unused slack** (NEW, session 1b,
   observation only). It probes within `1e-3…1e-5` of the expansion point, where
   the truncation difference measures **0.0 – 6.55e-17** against a 1e-9 gate. A
   check whose signal sits ~7 decades below its threshold cannot discriminate
   much; whether it would catch a genuinely wrong series is **untested** — that
   needs fault injection, which this session had no scope for.
8. **⚠ S2's margin is 2.47×, not "far below"** (NEW, session 1b). The `diff`
   arm's truncation-dominated floor measures 4.05e-10 against `1e-9`. See §3B S2.
9. **⚠ `solve` on a transcendental equation is classed `error`, not
   `unevaluated`** (NEW, session 1b; found while re-measuring, **NOT fixed** —
   out of this session's scope). Measured: `solve(cos(x) - x)` makes SymPy raise
   `NotImplementedError: No algorithms are implemented to solve equation
   -x + cos(x)`, and the wrapper's `except Exception` maps that to
   `error:evaluation_error`. But that message is SymPy **declining**, which is
   the definition of the `unevaluated` state — the contract's own wording is
   "SymPy returned the operation without performing it … or `solve` returned no
   roots". **This is failure mode §4B — an honest non-answer dressed as a
   failure — occurring inside the wrapper, which is exactly what S4 exists to
   prevent.** It errs safely for QoI leakage (no number escapes either way), but
   it *slanders a correctly-working instrument*, and a gate reading
   `evaluation_error` would reasonably conclude the substrate broke rather than
   that the question has no closed-form answer. `x**x` (B1) takes the honest
   path only because `integrate` **returns** an `Integral` object instead of
   raising. **The three-state discipline is enforced for returns and not for
   raises** — a real hole, needing an owner ruling on which exception types are
   declines.
10. **Registration.** The substrate stays UNREGISTERED and UNROUTABLE; no code
   reads this card and no model sees it (R-20.5-1). Registration is a separate
   owner ruling. The staged row/schema/router fragments sit in
   `onboarding/sympy_symbolic_exact/`.
11. **Calibration battery unexecuted, and NOT YET LOADABLE.**
   `harness/calibration_cases_sympy_symbolic_exact.json` is generated and
   committed, but `harness/calibration_battery.py` hardcodes its `_CASE_FILES`
   and `_wrapper_validator` to the FEA and code substrates and was **out of
   scope this session**. The two-line registration is **staged, not merged** —
   the seam is named, not built. Running the battery is a separate ⚙
   owner-approved run.
12. **Card length (drives battery cost).** See the debrief §9 for the measured
   character/token count and the re-predicted battery wall-time.
