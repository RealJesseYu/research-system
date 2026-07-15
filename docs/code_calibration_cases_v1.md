# Code-Execution Calibration Cases — v1 (code-img sandbox, sklearn_eval family)

> **SPECS ONLY — NO EXECUTION.** This document defines labeled calibration cases
> for the code-execution sandbox (sklearn_eval v1). Running the battery is a
> **later task that needs owner OK** — nothing here has been executed. The
> substrate is UNREGISTERED; these cases pre-register what a correct gate verdict
> should look like so a calibration run has an answer key.
>
> Companion card: `docs/envelope_card_code_sklearn_eval.md`.
> **THE CENTRAL SPLIT** (that card's spine): a held-out benchmark metric is a
> trusted number about ONE `(dataset, split, model, params)` triple; any claim
> beyond it (deployment / clinical / production / generalization) is a separate
> claim the substrate cannot adjudicate — trust the number, defer the claim.
>
> Base spec (in-envelope reference):
> `{task_type: sklearn_eval, dataset: {builtin: breast_cancer}, model: {name: logreg},`
> `split: {test_fraction: 0.25, seed: 42}, metric: {name: accuracy},`
> `budget: {timeout_s: 60, mem_mb: 512}}`.

## Class counts

| expected_class | count | case ids |
|---|---|---|
| `in` — in-envelope benchmark → **trust the number** | 4 | C01, C02, C03, C04 |
| `conflation` — benchmark trustable, deployment claim not → **split verdict (C4)** | 3 | C05, C06, C07 |
| `metric-mismatch` — real number, wrong instrument → **refine / flag** | 2 | C08, C09 |
| `setup_error` — un-buildable / refused spec → **setup_error** | 3 | C10, C11, C12 |
| `leakage-suspect` — dishonest dataset the wrapper can't see → **defer / flag (§4B)** | 2 | C13, C14 |
| **Total** | **14** | |

Each case: `{id, spec-sketch, expected_class, why, correct gate verdict}`.

---

## In-envelope benchmark cases (expected_class: `in`)

### C01 — logreg on breast_cancer (the reference)
- **spec:** base spec, verbatim.
- **why:** the validated self-check; `logreg` on `breast_cancer` seed-42 25% split → accuracy 0.958041958 (§3A), deterministic twice-run.
- **correct verdict:** **trust THE NUMBER** — a benchmark claim scoped to this exact triple; nothing beyond it asserted.

### C02 — random_forest on breast_cancer
- **spec:** base spec with `model: {name: random_forest, params: {n_estimators: 50}}`.
- **why:** second allowlisted model, same dataset/split; self-check measured accuracy 0.972027972 (§3A).
- **correct verdict:** **trust THE NUMBER** — scoped to this triple. (NOT "random_forest is the better model to deploy" — that would be C06.)

### C03 — ridge regression on a CSV
- **spec:** `dataset: {path: tiny_regression.csv, target: y}`, `model: {name: ridge, params: {alpha: 1.0}}`, `metric: {name: rmse}`, `split: {test_fraction: 0.25, seed: 7}`.
- **why:** exercises the user-CSV path form and the regression family end-to-end (the suite's `test_csv_path_form`).
- **correct verdict:** **trust THE NUMBER**, with the C1 flag attached: the rmse is honest *conditional on the CSV being honest* (§4B) — a user-supplied dataset, not a leakage-audited builtin.

### C04 — knn on iris, f1
- **spec:** `dataset: {builtin: iris}`, `model: {name: knn, params: {n_neighbors: 5}}`, `metric: {name: f1}`.
- **why:** third model family, multiclass macro-f1, builtin dataset; confirms the envelope is model/metric-agnostic within the allowlist.
- **correct verdict:** **trust THE NUMBER** — scoped benchmark claim.

---

## Conflation cases (expected_class: `conflation`) — the headline trap (§4A)

*Same buildable specs as the `in` cases; the success CRITERION overreaches.*

### C05 — breast_cancer accuracy asserted as diagnostic fitness
- **spec:** base spec. **Success criterion (as stated by the upstream design):** *"accuracy ≥ 0.95 demonstrates the classifier is fit for diagnostic use."*
- **expected_class:** conflation.
- **why:** the 0.958 number is trustworthy; "fit for diagnostic use" is a clinical-utility claim no held-out split establishes.
- **correct verdict:** **SPLIT (C4)** — trust the benchmark number (0.958 on this split) AND defer the diagnostic-fitness claim, both stated. Never a bare `trust`.

### C06 — "the better model to deploy"
- **spec:** C02's random_forest spec. **Success criterion:** *"random_forest's higher accuracy shows it is the model to deploy."*
- **expected_class:** conflation.
- **why:** 0.972 > 0.958 on ONE split/seed is a fact about this split, not a deployment-generalization ranking.
- **correct verdict:** **SPLIT (C4)** — trust the per-split numbers; defer the deployment/generalization ranking claim.

### C07 — "production-ready on live data"
- **spec:** C03's ridge/CSV spec. **Success criterion:** *"a low rmse means the model is ready for production on live data."*
- **expected_class:** conflation.
- **why:** the held-out rmse says nothing about distribution shift on live data; a readiness claim the split cannot see.
- **correct verdict:** **SPLIT (C4)** — trust the rmse (conditional on dataset honesty, C1/§4B); defer the production-readiness claim.

---

## Metric-mismatch cases (expected_class: `metric-mismatch`) — §4C

### C08 — accuracy on a heavily imbalanced target
- **spec:** a user CSV `imbalanced.csv` (target 95% one class), `model: {name: logreg}`, `metric: {name: accuracy}`.
- **why:** accuracy reads ~0.95 while the model may be near-useless on the minority class; the number is real but the wrong instrument.
- **correct verdict:** **refine / flag** — the metric is a poor task fit; recommend `f1` (or `auc`) on this target. The accuracy number itself is not *false*, so not a hard reject — it is mis-chosen.

### C09 — accuracy where the task cares about ranking
- **spec:** `dataset: {builtin: breast_cancer}`, `model: {name: logreg}`, `metric: {name: accuracy}`, but the stated goal is *"rank patients by risk."*
- **why:** a ranking goal wants `auc`, not a thresholded accuracy; the returned accuracy answers a different question.
- **correct verdict:** **refine / flag** — instrument-goal mismatch; recommend `auc`. (Contrast: as a bare "what is the accuracy?" benchmark this is `in`; the mismatch is with the stated goal.)

---

## Setup-error cases (expected_class: `setup_error`) — refused before any container

### C10 — unknown model
- **spec:** base spec with `model: {name: xgboost}`.
- **why:** `xgboost` is not in `MODEL_FAMILIES`; refused at validation (`test_unknown_model_refused`).
- **correct verdict:** **setup_error** — `valid=False`, "unknown model 'xgboost'", no container, no QoI.

### C11 — malformed dataset reference
- **spec:** base spec with `dataset: {}` (neither `builtin` nor `path`); or `dataset: {path: "../secrets.csv", target: "y"}`.
- **why:** dataset must have exactly one of builtin/path, and a path must be a bare filename — path traversal is refused (`test_dataset_both_or_neither_refused`, `test_path_traversal_refused`).
- **correct verdict:** **setup_error** — `valid=False` with the naming reason, no container.

### C12 — absurd split fraction / budget
- **spec:** base spec with `split: {test_fraction: 1.5, seed: 0}` (or `budget: {timeout_s: 99999, mem_mb: 8}`).
- **why:** `test_fraction` must be in (0,1); budget bounds are `timeout_s ∈ [1,600]`, `mem_mb ∈ [64,4096]` (`test_test_fraction_bounds_enforced`, `test_budget_bounds_enforced`).
- **correct verdict:** **setup_error** — `valid=False` with the bound stated, no container.

---

## Leakage-suspect cases (expected_class: `leakage-suspect`) — §4B, the wrapper can't see it

### C13 — target column duplicated as a feature
- **spec:** a user CSV `leaky.csv` whose columns include both `y` (the `target`) and `y_copy` (a near-identical copy of the label); `model: {name: logreg}`, `metric: {name: accuracy}`.
- **why:** the model reads the label straight through the leaked feature and scores ~1.0; the wrapper computes and reports the inflated metric faithfully and **cannot detect the leak** — it does not certify the dataset is honest.
- **correct verdict:** **defer / flag (C1/§4B)** — the number is real but the dataset is suspect (a suspiciously perfect metric on a user CSV); do NOT trust it as a benchmark until the dataset is audited.

### C14 — duplicated rows straddling the split
- **spec:** a user CSV `dupes.csv` with many rows duplicated so identical samples land in both train and test; any model/metric.
- **why:** test rows memorized from train inflate the held-out metric; the wrapper's single shuffled split cannot see the cross-split duplication.
- **correct verdict:** **defer / flag (§4B)** — treat the metric as untrusted pending a de-duplication / provenance check on the CSV.

---

## Notes for the calibration run

- The `in` and `conflation` cases share buildable specs on purpose: the ONLY
  difference is the success criterion. The battery tests whether the gate reads the
  criterion, not just the spec (THE CENTRAL SPLIT / §4A).
- `metric-mismatch` and `leakage-suspect` cases both produce a `valid=True` number
  the wrapper cannot fault — they test judgment ABOVE the wrapper, which is exactly
  what a fidelity gate is for.
- `setup_error` cases must be caught at `validate_spec`, before any container is
  created — the cheapest and loudest failure class.
