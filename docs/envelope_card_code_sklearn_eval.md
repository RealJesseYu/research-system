# Envelope Card — (code-img sandbox, sklearn_eval v1)

> **STATUS: DRAFT — not yet reviewed.**
> Provenance: `drafted-by-agent` (see §2). The §3B envelope bounds (C1–C4) are
> agent-SUGGESTED TODO-HUMAN judgment slots — **none decided.** No external
> reviewer is currently scheduled for this card — **flag for the owner.**
> This card is **HUMAN-FACING ONLY** (R-20.5-1 doctrine): no code reads it, no
> model sees it. The substrate is **UNREGISTERED** — nothing in `stages/`, the
> supervisor, `substrates.py`, or any schema imports `tools/run_code.py`.

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, regime) pair |
| Substrate | `code-img` code-execution sandbox — ephemeral, no-network, memory-capped, read-only containers (**UNREGISTERED**: no router/`substrates.py` entry exists) |
| Regime | `sklearn_eval` **v1** family: a single train/test split of ONE allowlisted sklearn model on ONE allowlisted dataset, scored by ONE allowlisted metric. Not free-form code. |
| Allowlisted models | `logreg`, `random_forest`, `ridge`, `knn` (family-gated: classification and/or regression per `MODEL_FAMILIES`) |
| Allowlisted metrics | classification `accuracy`, `f1`, `auc`; regression `rmse`, `mae`, `r2` |
| Allowlisted datasets | builtin sklearn loaders `breast_cancer`, `iris`, `wine`, `digits`, `diabetes`; or a user-supplied bare-filename CSV in the read-only task mount with a named `target` |
| Image | `code-img:latest` (`python:3.11-slim` + pinned ML stack), colima context |
| Pinned stack (live prints, this session) | `numpy 1.26.4` · `scipy 1.13.1` · `pandas 2.2.2` · `scikit-learn 1.5.1` — identical to `tools/code_env/requirements.txt` pins; the image is byte-reproducible from them |
| Wrapper | `tools/run_code.py` (deterministic Python, no AI, **no LLM anywhere in the execution path** — it RUNS code from a fixed template, never WRITES code) |
| Wrapper commit (last touch) | `90b4696` (STEP28.5-DRY) |
| Contract text | **none** — substrate is UNREGISTERED; the typed v1 spec lives only in `run_code.py` (`validate_spec` + the allowlists), not in `substrates.py` |
| Card drafted against repo HEAD | `90b4696` |
| Maturity | **calibrating** (pre-registration; judgment slots open) |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, doc-only measurement-capture session) |
| Drafted date | 2026-07-15 |
| Sources | wrapper self-check runs captured this session (3 live sandbox executions: logreg, random_forest, a version-print probe); the four jail proofs + refusal behavior in `tests/test_run_code.py`; the pinned manifest `tools/code_env/requirements.txt`; the valid fixture `tests/fixtures/code_result_valid.json` |
| Signature | `unsigned` — provisionally-signed slot **empty** (awaits owner ruling on C1–C4) |
| Reviewer sign-off | `pending — no external reviewer scheduled` (**owner: this card has no dispatch date; the FEA/CFD cards do — flag**) |
| **Provenance state** | `drafted-by-agent` |

*Provenance state is the load-bearing field: it sets how much grounding authority
the card carries. It is `drafted-by-agent` — the §3B slots (C1–C4) are suggestions,
not decided bounds, and a human sits at every trust call on this UNREGISTERED
substrate regardless.*

---

## THE CENTRAL SPLIT (the spine of this card)

**A held-out benchmark metric from this substrate is a TRUSTED number about one
`(dataset, split, model, params)` triple — nothing more.** Here the code *is* the
experiment: there is no simulation and therefore **no sim-to-real gap** to
adjudicate. When the wrapper returns `accuracy = 0.958…` on `breast_cancer`'s
seed-42 25%-held-out split with logreg, that number is exactly what it says — the
fraction of that held-out split this fitted model got right. Trust THE NUMBER.

**Any claim BEYOND that triple is a SEPARATE claim this substrate cannot
adjudicate** — real-world performance, deployment readiness, clinical/production
utility, generalization to other data, fairness, calibration. For those the gate
may trust the benchmark number **and must, in the same breath, defer the utility
claim.** Never let a trusted benchmark number launder an untrusted deployment
claim. Worked contrasts:

| A claim the substrate CAN adjudicate (trust THE NUMBER) | The conflated claim it CANNOT (defer) |
|---|---|
| "logreg scores **0.958** accuracy on `breast_cancer`'s seed-42 held-out split" | "this classifier is **fit for diagnostic use**" — a clinical-utility claim; no held-out split establishes it |
| "random_forest scores **0.972** accuracy on the same split" | "random_forest is **the better model to deploy**" — deployment generalization beyond this one split/seed |
| "ridge scores **rmse X** on `tiny_regression.csv`'s held-out rows" | "this model is **ready for production** on live data" — a distribution-shift / readiness claim the split cannot see |

The benchmark number is trustworthy *and narrow*. The card exists so the narrow
truth is never read as the broad one.

---

## 3. Validated envelope

Two sections, deliberately separate. §3A is disk-cited evidence actually exercised
this session; §3B is the set of envelope bounds left as TODO-HUMAN judgment slots —
**none pre-filled as decided.**

### 3A. Self-check runs (live this session — 3 sandbox executions)

| model | dataset / split | metric | value | n_train / n_test | runtime_s |
|---|---|---|---|---|---|
| `logreg` (C=1.0) | `breast_cancer`, seed 42, 25% test | accuracy | **0.958041958041958** | 426 / 143 | 2.515 (cold first job) |
| `random_forest` (n_estimators=50) | `breast_cancer`, seed 42, 25% test | accuracy | **0.972027972027972** | 426 / 143 | 1.496 (warm second job) |

- **Determinism (twice-run):** logreg reproduced `0.958041958041958` **exactly** —
  identical to the on-disk fixture `tests/fixtures/code_result_valid.json`; the
  suite's `test_twice_run_determinism` asserts value equality across two live runs.
  Determinism rests on the single-thread guard (§4D).
- **The four container jail proofs** (`tests/test_run_code.py::TestJails`, each
  proves a jail by FAILING an escape, run live where docker is present):
  1. **No network** — `urllib.request.urlopen` fails; no `REACHED_NETWORK`; stderr shows name-resolution/unreachable (`--network=none`).
  2. **Memory cap** — a 600 MB allocation under a 256 MB cap is **OOM-killed at exit 137**; no `ALLOCATED` (`--memory` / `--memory-swap`).
  3. **Read-only workdir** — a write to `/task` fails `Read-only file system`; no `WROTE_OUTSIDE` (`--read-only` + `:ro` task mount).
  4. **Hard timeout** — a `sleep(30)` under a 3 s timeout is `docker kill`ed and leaves **zero lingering containers** (`--rm`).
- **Refusal behavior** (before any container is created): unknown `task_type` /
  model / metric / dataset, model↔metric family mismatch, dataset↔metric family
  mismatch, path traversal, non-numeric params, and out-of-bounds budget all raise
  `CodeSpecError` and return `valid=False` with a bounded, human-safe message and
  **no QoI** (`tests/test_run_code.py::TestValidation`, `::TestRefusalsAndBounds`).

### 3B. Envelope bounds — TODO-HUMAN judgment slots

Each carries an agent-SUGGESTED value and a one-line reason. **None is a decided
bound** — each awaits an owner ruling (mirrors the CFD/FEA cards).

- **(C1) Dataset-provenance classes trusted for the benchmark claim.**
  `TODO-HUMAN` — **suggested: builtin sklearn loaders + user-supplied CSV files,
  with user files flagged "metric conditional on dataset honesty — see §4B."**
  *Reason:* builtin loaders are fixed, versioned, and leakage-audited upstream, so
  their benchmark number is trustworthy as-is; a user CSV's number is only as
  honest as the CSV — the substrate computes the metric it was given, it cannot
  certify the dataset is clean.

- **(C2) Minimum `n_test` below which the metric is too noisy to headline.**
  `TODO-HUMAN` — **suggested: report `n_test` on every run; flag `n_test < 30`.**
  *Reason:* a metric on a tiny held-out split has wide confidence bounds (a handful
  of misclassifications swings accuracy by whole points); below ~30 test rows the
  number is real but not headline-grade, and the gate should say so rather than
  suppress it.

- **(C3) Allowlist-drift rule.**
  `TODO-HUMAN` — **suggested: any new model/metric/dataset family requires a card
  amendment + a determinism re-proof before its numbers count.**
  *Reason:* the trust story rests on the pinned stack + single-thread determinism
  (§4D); a new family (especially a threaded/GPU one) can silently break
  reproducibility, so it must re-earn the determinism proof before its numbers
  enter the trusted class.

- **(C4) The deployment-claim rule.**
  `TODO-HUMAN` — **suggested: ANY spec whose success criterion references
  real-world / production / clinical / deployment utility → the gate MAY trust the
  benchmark number AND MUST defer the utility claim — both stated explicitly.**
  *Reason:* this is THE CENTRAL SPLIT made operational; it is the single rule that
  stops a trusted narrow number from being read as a broad readiness claim (§4A).

---

## 4. Known failure modes

For each: name it, the class it produces, and its evidence.

- **4A. Benchmark–deployment conflation → SPLIT verdict (trust the number, defer the claim).**
  THE HEADLINE TRAP. A spec pairs an in-envelope benchmark with a success
  criterion that asserts real-world/clinical/production utility. The number is
  trustworthy; the utility claim is not adjudicable here. The gate must issue both
  halves per C4 — never a bare `trust`. (Evidence: THE CENTRAL SPLIT; calibration
  class *conflation*, cases C05–C07.)
- **4B. Leakage / overfitting the wrapper cannot see → defer-or-flag.**
  Target leakage in a provided CSV (a column that trivially encodes the target),
  duplicated rows straddling the train/test split, or an otherwise-dishonest
  dataset all yield an inflated metric the wrapper reports faithfully **and cannot
  detect** — it computes the metric it was given; it does not certify the dataset
  is honest. (Anticipated; C1 flags user CSVs; calibration class *leakage-suspect*,
  cases C13–C14.)
- **4C. Metric–task mismatch → refine / flag.**
  `accuracy` on a heavily class-imbalanced target reads high while the model is
  near-useless on the minority class (a 95%-negative dataset scores 0.95 by always
  predicting negative). The number is real; it is the wrong instrument for the
  task. (Anticipated; calibration class *metric-mismatch*, cases C08–C09.)
- **4D. Single-thread determinism guard — LOAD-BEARING.**
  Reproducibility rests on a fixed seed + single-thread execution
  (`n_jobs=1`, `OMP/OPENBLAS/MKL_NUM_THREADS=1`). Twice-run identity (§3A) holds
  under it. It **breaks silently if a threaded/GPU model family is added without
  revisiting this guard** — parallel float reductions reorder and the twice-run
  metric would diverge. Any allowlist growth (C3) must re-prove determinism.
  (Evidence: `run_code.py` `build_model` + `run_in_sandbox` env; §3A twice-run.)

---

## 5. What the diagnostics CAN and CANNOT see

The wrapper returns `valid` (bool), `qoi` (or None), a bounded `diagnostics`
string (≤800 chars, never a raw log), `runtime_s`, and on-disk `artifacts` paths.

| CAN see | CANNOT see |
|---|---|
| Spec refused before any container (unknown/mismatched/out-of-bounds shape, §3A) | Whether the benchmark number generalizes beyond this one split/seed (THE CENTRAL SPLIT) |
| Job crash: no `result.json`, non-zero exit, unparseable/`ok:false` result → `valid=False`, no number | Whether the dataset is honest — target leakage, duplicated rows, contrived features (§4B) |
| Jail trips: OOM (exit 137), wall-timeout kill, read-only/network denials | Whether the metric is the RIGHT instrument for the task (accuracy on imbalance, §4C) |
| `n_train` / `n_test` reported every run | Whether `n_test` is large enough for the number to be headline-grade (C2 is a rule, not an internal check) |

*Overclaiming diagnostic reach is the most dangerous error a card can make: the
wrapper checks that the job **ran cleanly and produced a finite metric**, not that
the metric is meaningful, honest, or deployment-relevant.*

---

## 6. Extraction contract (verbatim)

**Typed v1 spec vocabulary** (`tools/run_code.py` `validate_spec` + allowlists) —
the wrapper honors exactly these; anything else is refused by name, before any
container:

| Field | Meaning |
|---|---|
| `task_type` | must be `"sklearn_eval"` (the only v1 family) |
| `dataset` | exactly one of `{"builtin": <name>}` or `{"path": <bare filename>, "target": <col>}` |
| `model` | `{"name": <allowlisted>, "params": {…}}` — params numeric/bool only (no strings, no nesting) |
| `metric` | `{"name": <allowlisted>}` — drives the classification/regression family |
| `split` | `{"test_fraction": (0,1), "seed": int}` |
| `budget` | `{"timeout_s": [1,600], "mem_mb": [64,4096]}` |

**QoI extraction path** — verbatim capability:
- ONE metric per run, on ONE train/test split, single-shot. On success:
  `qoi {metric_name, value (finite float), n_train, n_test}`.
- On ANY failure (spec refused, job crash, timeout, OOM, unparseable/`ok:false`
  result, non-finite value): `valid=False`, a bounded `diagnostics` string, and
  **no number** — never a fabricated metric.
- Raw stdout/stderr NEVER leave the wrapper; full logs persist on disk as
  evidence, the return carries only bounded excerpts.

**Benchmark-scope rule (REQUIRED slot).** Every returned metric is scoped to its
`(dataset, split, model, params)` triple and to that alone (THE CENTRAL SPLIT).
Any candidate success criterion is screened at design vet for whether it asks
*only about that triple* (trustable) or *beyond it* (defer per C4) — the analogue
of the CFD/FEA cards' QoI-screening rule, applied to the benchmark→deployment
boundary rather than to numerical-artifact contamination.

---

## 7. Cost model (measured this session)

Per the standing doctrine (never a single rate), the two measured runtimes are
published as a **range plus per-job points** — and **container startup dominates**
at v1 job sizes, so the wall-clock is non-monotonic.

| Operating point | Measured wall-clock `runtime_s` | Evidence |
|---|---|---|
| `logreg` on `breast_cancer` (cold first job) | **2.515 s** | this session |
| `random_forest` (50 trees) on `breast_cancer` (warm second job) | **1.496 s** | this session |
| **Range (v1, these jobs)** | **≈1.5 – 2.5 s / job** | this session |
| Hard kill limit | `budget.timeout_s`, default 60 s, ceiling **600 s** → reported failure | `run_code.py` `MAX_TIMEOUT_S` |

**Note (honest):** each job spins up its OWN ephemeral container (jails are
creation-time properties), so per-job cost is dominated by container
startup/teardown, not model compute — which is why the cold first job (logreg,
2.515 s) measured **slower** than the warm second (random_forest, 1.496 s) despite
random_forest doing more fitting work. No per-model compute rate is quoted; the
range above is the honest v1 cost statement. (A strategist-noted ~1.1–1.2 s logreg
figure is a warm-path estimate; this session's cold logreg measured 2.515 s.)

---

## 8. Negative space + open watches

**What this card does NOT cover** (out of scope for v1 as drafted):

- **No training-cost / compute-efficiency claims** — runtimes are wall-clock jail
  cost, not FLOPs or training economics.
- **No GPU** — CPU-only, single-thread by design (§4D).
- **No network-dependent datasets** — `--network=none`; builtin loaders + local
  CSVs only.
- **No free-form code** — v1 runs a fixed template filled with allowlisted spec
  DATA; arbitrary user code is refused, not sandboxed-and-run.
- **No cross-validation, no time-series / grouped / stratified schemes** — a single
  shuffled train/test split only.
- **No fairness, calibration, subgroup, or robustness properties** — one scalar
  metric on one split; none of these is measured or claimed.

**Open watches:**

1. **Judgment slots C1–C4 (§3B) are undecided.** Each needs an owner ruling before
   the card advances past `drafted-by-agent`.
2. **rf value discrepancy (disclosed).** A strategist-noted "~0.965" self-check
   for random_forest; this session's live n_estimators=50 run measured
   **0.972027972027972**. Recorded as the measured truth; the ~0.965 likely
   reflects different tree count / defaults.
3. **Determinism guard vs allowlist growth (§4D / C3).** Adding any threaded or GPU
   family must re-prove twice-run determinism before its numbers count.
4. **Leakage detection (§4B).** The wrapper cannot see a dishonest dataset; whether
   a lightweight leakage screen (e.g. a perfect-predictor / duplicate-row check)
   should be added is a later, evidence-gated decision.
5. **No reviewer scheduled.** Unlike the FEA card (Sunday 2026-07-19 dispatch) and
   the CFD card, this card has **no external-review date** — flag for the owner.
6. **Registration.** Substrate stays UNREGISTERED; no code reads this card and no
   model sees it (R-20.5-1). Registration is a later, separate decision after
   calibration.
7. **Calibration battery unexecuted.** `docs/code_calibration_cases_v1.md` defines
   the labeled cases; running them is a later task needing owner OK.
