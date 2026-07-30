# Is the arm-C replacement real, or is it noise?

Move 16 of `study-20260730T034915Z` was cut off before it could write the small
producer files its own blocker asked for, so the study's central claim — an
LTPP-calibrated replacement for AASHTO-93 flexible pavement design — never
reproduced. This does what m16 was cut off before doing: **twelve small,
independent, self-contained scalar producers** over the cached tables, run
offline, in `docs/armc_core_producers/`.

**This is NOT retroactive verification, and nothing here changes the study
record.** `study-20260730T034915Z` stands exactly as it is: 50/136 claims
verified, its own paper already reporting the replacement's out-of-sample case as
unreproduced. This answers a *scientific* question the study left open — is the
replacement real? — using data that was already on disk. No wall verdict is being
retro-fitted, and no finding in `verification.json` changes.

**Method.** Inputs copied read-only out of
`runs/study-20260730T034915Z-m16/workspace/` (`ltpp_sdr39_segments.csv`, 365
segments; `runs/` is append-only evidence and was never written to). Each producer
embeds only the column slice it needs as a gzip+base64 literal, imports nothing
local, runs in an empty directory in seconds, and sets `metrics[...]`. All twelve
were run twice and produced byte-identical output; one was re-run in a fresh
`mktemp -d` to prove standalone execution. Sample: the **252** segments with a
measured subgrade modulus (`lab_Mr`, `lab_Mr_wksht`, `CBR`, `Rvalue`), and for the
observed-ΔPSI numbers the **212** of those with ΔPSI ≥ 0.3 — the same filters
`analysis_all.py` applies.

---

## The headline: the comparison was never like-for-like

The claim under test is a replacement σ of ~0.36–0.42 against the incumbent's
1.46. **Those two numbers are not in the same units.** Reproduced:

| quantity | value | what it is |
|---|---|---|
| `null_constant_only_sigma_esal_domain` | **1.0960** | fit ONE constant to log₁₀(ESALs to failure). No predictors. |
| `null_constant_only_sigma_years_domain` | **0.3767** | fit ONE constant to log₁₀(**years** to failure). No predictors. |

The paper's headline rule predicts **years**; the incumbent predicts **ESALs**.
Simply changing which one you predict moves σ from ~1.10 to ~0.38 **before any
model exists at all**, because log₁₀(years) spans a far narrower range than
log₁₀(cumulative traffic). The reported "≈0.36 against 1.46" is, to first order,
that change of response variable.

And in the years domain the replacement's own structure adds nothing:

| model (interval-censored AFT, years domain) | σ |
|---|---|
| constant only, no predictors | **0.3767** |
| + log₁₀(SN+1) + log₁₀(MR) — *the replacement's regressors* | **0.3772** |

**Adding every structural term the replacement contains makes σ slightly worse
than predicting a single constant.** The paper's σ = 0.3585, offered as "a fitted
residual spread [that] replaces the assumed S0 entirely", is — to within a few
percent, and in the wrong direction — the spread of the data about its own mean.

## In one domain, honestly: the replacement's real margin is ~6%

Held-out-section 10-fold cross-validation, observed-ΔPSI ESAL domain, identical
folds and seed for every row (`_cv_sd`, seed 7; checked across seeds 1/2/3/7/11,
range 0.492–0.4955):

| model | out-of-sample sd |
|---|---|
| **null** — one constant, no predictors | **0.5281** |
| AASHTO-93's own prediction + a free intercept and gain | **0.5054** |
| **the replacement** — 4 coefficients on the Guide's own regressors | **0.4954** |

The replacement's entire out-of-sample advantage over *predicting a single
number* is 0.5281 → 0.4954, about **6% in sd**. Its advantage over **just
recalibrating the Guide's existing equation with two free parameters** is 0.5054
→ 0.4954, about **2%**.

And in the one genuinely apples-to-apples comparison — both models fitted through
the *same* interval-censored likelihood for life to a fixed 1.0-PSI loss:

| model, interval-censored, ΔPSI = 1.0 | σ |
|---|---|
| incumbent AASHTO-93 (coefficients fixed as published) | **1.5593** |
| replacement (3 free coefficients) | **0.9750** |
| null — constant only | **1.0960** |

The replacement (0.9750) beats the null (1.0960) by 11%. The incumbent's 1.5593
is worse than the null, which is the study's genuinely solid result and is
discussed below.

## What the incumbent's poor showing actually is

| quantity | value |
|---|---|
| `incumbent_sd_as_published` (observed-ΔPSI domain) | **0.9720** |
| `incumbent_median_bias_log10` | **+0.7257** (a factor of 5.3× over-prediction) |
| the same equation, given a free intercept and gain, cross-validated | **0.5054** |

Most of the incumbent's apparent inaccuracy is **calibration, not form**:
re-centring and re-scaling its own published prediction takes it from 0.9720 to
0.5054, which is within 2% of the four-coefficient replacement. The defensible
version of the study's claim is therefore *"AASHTO-93 is badly miscalibrated on
LTPP"* — which is real, reproduced, and useful — not *"a learned model beats
it"*.

## The three-way coefficient disagreement: which one is right?

The paper flags this itself (§5.2: "a first-order unresolved problem, and it is
the single strongest reason this replacement is not ready to use"), reporting
`b_sn` = 0.3215, 3.6537 and 7.4314. Move 16 added two more, 1.61 and 4.98, and
move 12 a sixth, −0.532. **I used the pooled observed-ΔPSI OLS and the
within-project censored AFT, because those are the two the shipped kernel
(`analysis_all.py`) actually computes, and I state both rather than choosing:**

| estimator | reproduced | claimed |
|---|---|---|
| pooled, observed-ΔPSI OLS, state-clustered SE | **1.6100 ± 0.3730** | 1.61 (m16) ✔ · 0.3215 (m15) ✘ · −0.532 (m12) ✘ |
| within-SPS-project censored AFT (11 projects, n=59) | **1.0754** | 4.98 (m16) ✘ · 3.654 (m12) ✘ · 0.4711 (m15) ✘ |

The pooled figure reproduces m16's exactly. The within-project figure does not
reproduce any of the three published values; it is a converged optimum, not an
optimiser artefact — I restarted the MLE from `b_sn` ∈ {0, 1, 5, 9.36} and all
four returned `b_sn` = 1.0754, σ = 0.4030, log-likelihood −27.8287 to four
decimals.

**The one thing every estimate agrees on** is that the Guide's 9.36 is far too
large: every reproduced value lies between 1.0 and 1.7, and the pooled estimate
rejects 9.36 at more than 20 standard errors. That conclusion survives. *"How much
does thickness actually help?"* does not — the estimates that would answer it
disagree by a factor of five and rest on 59 sections in 11 projects.

## What reproduced and what did not

| claim | source | reproduced | measured |
|---|---|---|---|
| replacement out-of-sample sd, held-out sections | m16 (0.4954) | ✔ exact | 0.4954 |
| replacement σ, interval-censored, ΔPSI=1.0 | m16 (0.975) | ✔ exact | 0.9750 |
| pooled `b_sn` | m16 (1.61) | ✔ exact | 1.6100 |
| incumbent σ, interval-censored, ΔPSI=1.0 | m16 (1.4624) | ✘ | **1.5593** |
| within-project `b_sn` | m16 (4.98) | ✘ | **1.0754** |
| replacement out-of-sample σ 0.898 / 1.009 | m12 | ✘ | 0.4954 / 0.4988 |
| pooled `b_sn` = 0.3215, −0.532 | m15, m12 | ✘ | 1.6100 |
| within-project `b_sn` = 3.654, 0.4711 | m12, m15 | ✘ | 1.0754 |
| replacement σ = 0.3585 (years) | m15 | ≈ | 0.3772 — **and the null is 0.3767** |

The incumbent σ of 1.4624 could not be reproduced under any sample or convention
I tried: {measured-Mr 252, measured & ΔPSI≥0.3 212, all-with-Mr 311} × {ΔPSI
0.5/0.75/1.0/1.5} × {face value, C=0.33} gave 1.2451–2.5383, with 1.5593 at the
stated configuration. Every number m16 reported for the **replacement**
reproduced exactly; the two that did not are the incumbent's σ and the
within-project elasticity — the two that make the margin look largest.

## The answer

**The replacement is not noise, and it is not what the study claimed.**

It is a real but small effect: about **6% better out-of-sample than predicting a
constant**, and about **2% better than recalibrating AASHTO-93's own equation**,
in the domain where the comparison can be made honestly. The "4× more accurate"
reading of 0.36 vs 1.46 does not survive: those numbers are in different response
variables, and in the years domain where the headline σ lives, the replacement's
regressors do not beat a constant at all.

What does survive, and is worth keeping:

1. **AASHTO-93 is badly miscalibrated on LTPP** — median bias +0.7257 in log₁₀
   (5.3×), residual sd 0.9720 against an assumed S₀ of 0.45.
2. **The Guide's 9.36 structural elasticity is far too large** — every reproduced
   estimate is between 1.0 and 1.7.
3. **Most of the incumbent's error is level, not shape** — two free parameters on
   its own prediction recover nearly all the replacement's accuracy.

That is a worthwhile negative result about a widely used design equation. It is
not "a model that beats it, and the win quantified", which is what the goal
asked for.

## What this cost, and what it says about the run

Twelve producers, about 20 minutes, no network, no model calls, on data that had
been sitting in the workspace since the study ended. The one thing that would
have settled whether the study's central claim was real was available for free
the whole time — which is exactly what m15's and m16's blockers said, in the
channel that reached nobody (fixed in `8df1379`), after both moves were cut off
by a turn counter that was counting content blocks (fixed in `3861628`).

**Reproduce any number here:** `venv/bin/python3 docs/armc_core_producers/<file>.py`
— each is self-contained, offline, and runs in seconds.
