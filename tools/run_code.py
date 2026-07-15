"""
run_code — the production code-execution sandbox wrapper (Step 28.5 DRY).

Plain, deterministic code. NO AI inside, no model calls, ever — and, uniquely,
NO LLM anywhere in the EXECUTION path: this wrapper RUNS code, it never WRITES
code. The runner script is generated from a FIXED template (the contract);
only validated, allowlisted spec values are filled in. Same contract run_cfd.py
and run_fea.py hold for their solvers. UNREGISTERED at Step 28.5: nothing in
stages/, the supervisor, substrates.py, or any schema imports it. It is
reachable by tests (and a __main__ CLI) only.

Why the runtime model differs from of12-prod / ccx-prod: those are long-lived
containers driven by `docker exec`. A code sandbox cannot be, because its jails
— NO network, a memory cap, a read-only rootfs, a read-only task mount — are all
container-CREATION-time properties. So every job runs in its own EPHEMERAL
container (`docker run --rm`), created with exactly these flags:

    --network=none          no network reachable from inside the job
    --memory <M>m           hard memory cap; --memory-swap=<M>m disables swap
    --read-only             the container rootfs is read-only
    --tmpfs /tmp:size=...   the only scratch, capped, discarded on exit
    -v <task>:/task:ro      the task/dataset dir, READ-ONLY
    -v <run>:/run:rw        the ONLY writable path — runner.py + result.json live here
    --pids-limit ...        fork-bomb bound
  + a hard subprocess timeout; on expiry the container is `docker kill`ed.

Each jail is proven by a failing-escape test in tests/test_run_code.py.

Task-spec v1 (typed, ONE family — the wrapper refuses anything else, honestly):

    run_code({
        "task_type": "sklearn_eval",
        "dataset": {"builtin": "breast_cancer"},       # or {"path": "d.csv", "target": "y"}
        "model":   {"name": "logreg", "params": {"C": 1.0}},   # params optional
        "split":   {"test_fraction": 0.25, "seed": 42},
        "metric":  {"name": "accuracy"},
        "budget":  {"timeout_s": 60, "mem_mb": 512},
    })

Return (and ONLY this leaves the wrapper — raw stdout/stderr NEVER escape):

    {"valid": bool,
     "qoi": {"metric_name": str, "value": float, "n_train": int, "n_test": int} | None,
     "diagnostics": str,                 # bounded <=800 chars; never a raw log
     "runtime_s": float,
     "artifacts": {"paths": [str, ...]}} # host paths under the job run dir
"""

from __future__ import annotations

import json
import math  # noqa: F401  (kept available to the template's namespace docs)
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

# ----------------------------------------------------------------------------
# Configuration — the only knobs, in one place (mirrors run_cfd.py / run_fea.py).
# ----------------------------------------------------------------------------
DOCKER_CONTEXT = "colima"                 # same colima VM as the other substrates
IMAGE = "code-img:latest"                 # the pinned Python-ML image (see code_env/)
RUNS_HOST = Path("/Users/jesseyu/research-system/cases_code")  # job scratch on the Mac

DEFAULT_TIMEOUT_S = 60                     # used when a spec omits budget.timeout_s
DEFAULT_MEM_MB = 512
MAX_TIMEOUT_S = 600                        # hard ceiling regardless of the spec
MAX_MEM_MB = 4096
MIN_MEM_MB = 64                            # below this the interpreter can't even start
PIDS_LIMIT = 256                           # fork-bomb bound
TMPFS_MB = 64                              # /tmp scratch size inside the job
MAX_DIAG_CHARS = 800                       # bound on returned diagnostic text

# ----------------------------------------------------------------------------
# Allowlists — v1 recognizes EXACTLY these. Anything else is an honest refusal,
# never a best-effort execution of an unknown shape.
# ----------------------------------------------------------------------------
TASK_TYPES = ("sklearn_eval",)

CLASSIFICATION_METRICS = ("accuracy", "f1", "auc")
REGRESSION_METRICS = ("rmse", "mae", "r2")
METRICS = CLASSIFICATION_METRICS + REGRESSION_METRICS

# model name -> the task families it is allowed to serve
MODEL_FAMILIES = {
    "logreg": ("classification",),
    "random_forest": ("classification", "regression"),
    "ridge": ("regression",),
    "knn": ("classification", "regression"),
}

# builtin dataset name -> its task family (sklearn stock loaders only)
BUILTIN_DATASETS = {
    "breast_cancer": "classification",
    "iris": "classification",
    "wine": "classification",
    "digits": "classification",
    "diabetes": "regression",
}


class CodeSpecError(ValueError):
    """The task spec is not a recognized, buildable v1 job."""


# ----------------------------------------------------------------------------
# Typed spec validation. Returns a clean copy or raises CodeSpecError. No I/O.
# ----------------------------------------------------------------------------

def _metric_family(metric_name: str) -> str:
    return "classification" if metric_name in CLASSIFICATION_METRICS else "regression"


def validate_spec(spec: dict) -> dict:
    """Deeply validate a v1 task spec. Plain-language errors, allowlists enforced.

    Every message is written to be safe to surface to a human or log verbatim.
    """
    if not isinstance(spec, dict):
        raise CodeSpecError(f"spec must be a dict, got {type(spec).__name__}")

    task_type = spec.get("task_type")
    if task_type not in TASK_TYPES:
        raise CodeSpecError(
            f"unrecognized task_type {task_type!r}; v1 supports only {list(TASK_TYPES)}"
        )

    # --- metric (drives the task family) ----------------------------------
    metric = spec.get("metric")
    if not isinstance(metric, dict) or "name" not in metric:
        raise CodeSpecError("metric must be a dict with a 'name'")
    metric_name = metric["name"]
    if metric_name not in METRICS:
        raise CodeSpecError(f"unknown metric {metric_name!r}; allowed: {list(METRICS)}")
    family = _metric_family(metric_name)

    # --- model ------------------------------------------------------------
    model = spec.get("model")
    if not isinstance(model, dict) or "name" not in model:
        raise CodeSpecError("model must be a dict with a 'name'")
    model_name = model["name"]
    if model_name not in MODEL_FAMILIES:
        raise CodeSpecError(
            f"unknown model {model_name!r}; allowed: {sorted(MODEL_FAMILIES)}"
        )
    if family not in MODEL_FAMILIES[model_name]:
        raise CodeSpecError(
            f"model {model_name!r} cannot serve a {family} metric ({metric_name!r}); "
            f"it supports {list(MODEL_FAMILIES[model_name])}"
        )
    params = model.get("params", {})
    if not isinstance(params, dict):
        raise CodeSpecError("model.params must be a dict when present")
    clean_params = {}
    for k, v in params.items():
        if not isinstance(k, str):
            raise CodeSpecError(f"model.params keys must be strings, got {k!r}")
        # v1 accepts only numeric/bool param VALUES — no strings, no nesting.
        # This keeps the runner deterministic and closes any template-injection
        # path (the spec is embedded as JSON data in the generated runner).
        if isinstance(v, bool) or isinstance(v, (int, float)):
            clean_params[k] = v
        else:
            raise CodeSpecError(
                f"model.params[{k!r}] must be a number or bool in v1, got {v!r}"
            )

    # --- dataset ----------------------------------------------------------
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        raise CodeSpecError("dataset must be a dict")
    has_builtin, has_path = "builtin" in dataset, "path" in dataset
    if has_builtin == has_path:
        raise CodeSpecError("dataset must have exactly one of 'builtin' or 'path'")
    clean_dataset = {}
    if has_builtin:
        name = dataset["builtin"]
        if name not in BUILTIN_DATASETS:
            raise CodeSpecError(
                f"unknown builtin dataset {name!r}; allowed: {sorted(BUILTIN_DATASETS)}"
            )
        ds_family = BUILTIN_DATASETS[name]
        if ds_family != family:
            raise CodeSpecError(
                f"builtin dataset {name!r} is a {ds_family} dataset but the metric "
                f"{metric_name!r} is a {family} metric"
            )
        clean_dataset["builtin"] = name
    else:
        path = dataset["path"]
        if not isinstance(path, str) or not path:
            raise CodeSpecError("dataset.path must be a non-empty string")
        # A bare filename inside the mounted task dir — no separators, no escapes.
        if "/" in path or "\\" in path or path in (".", ".."):
            raise CodeSpecError(
                f"dataset.path must be a bare filename inside the task dir, got {path!r}"
            )
        target = dataset.get("target")
        if not isinstance(target, str) or not target:
            raise CodeSpecError("dataset.path form requires a string 'target' column name")
        clean_dataset["path"] = path
        clean_dataset["target"] = target

    # --- split ------------------------------------------------------------
    split = spec.get("split", {})
    if not isinstance(split, dict):
        raise CodeSpecError("split must be a dict")
    try:
        test_fraction = float(split.get("test_fraction", 0.25))
    except (TypeError, ValueError):
        raise CodeSpecError(f"split.test_fraction must be a number, got {split.get('test_fraction')!r}")
    if not (0.0 < test_fraction < 1.0):
        raise CodeSpecError(f"split.test_fraction must be in (0, 1), got {test_fraction}")
    try:
        seed = int(split.get("seed", 0))
    except (TypeError, ValueError):
        raise CodeSpecError(f"split.seed must be an integer, got {split.get('seed')!r}")

    # --- budget -----------------------------------------------------------
    budget = spec.get("budget", {})
    if not isinstance(budget, dict):
        raise CodeSpecError("budget must be a dict")
    try:
        timeout_s = int(budget.get("timeout_s", DEFAULT_TIMEOUT_S))
    except (TypeError, ValueError):
        raise CodeSpecError(f"budget.timeout_s must be an integer, got {budget.get('timeout_s')!r}")
    if not (1 <= timeout_s <= MAX_TIMEOUT_S):
        raise CodeSpecError(f"budget.timeout_s must be in [1, {MAX_TIMEOUT_S}], got {timeout_s}")
    try:
        mem_mb = int(budget.get("mem_mb", DEFAULT_MEM_MB))
    except (TypeError, ValueError):
        raise CodeSpecError(f"budget.mem_mb must be an integer, got {budget.get('mem_mb')!r}")
    if not (MIN_MEM_MB <= mem_mb <= MAX_MEM_MB):
        raise CodeSpecError(f"budget.mem_mb must be in [{MIN_MEM_MB}, {MAX_MEM_MB}], got {mem_mb}")

    return {
        "task_type": task_type,
        "dataset": clean_dataset,
        "model": {"name": model_name, "params": clean_params},
        "split": {"test_fraction": test_fraction, "seed": seed},
        "metric": {"name": metric_name},
        "family": family,
        "budget": {"timeout_s": timeout_s, "mem_mb": mem_mb},
    }


# ----------------------------------------------------------------------------
# Runner generation. The template is FIXED bytes; the only variable is a block
# of validated JSON DATA (never code). Deterministic: same spec -> same runner.
# ----------------------------------------------------------------------------

_SPEC_TOKEN = "__SPEC_JSON__"

RUNNER_TEMPLATE = r'''"""AUTO-GENERATED sandbox runner (Step 28.5). Do not edit.

Generated by tools/run_code.py from a FIXED template. The ONLY per-job variable
is the SPEC block below, which is validated, allowlisted JSON DATA — never code.
This script runs INSIDE the no-network, read-only, memory-capped container and
writes exactly one artifact: /run/result.json.
"""
import json
import math

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.neighbors import KNeighborsClassifier, KNeighborsRegressor
from sklearn.metrics import (
    accuracy_score, f1_score, roc_auc_score,
    mean_squared_error, mean_absolute_error, r2_score,
)

SPEC = json.loads(r"""__SPEC_JSON__""")

RESULT = "/run/result.json"


def _fail(msg):
    with open(RESULT, "w") as fh:
        json.dump({"ok": False, "error": str(msg)[:500]}, fh)
    raise SystemExit(0)


def load_dataset():
    ds = SPEC["dataset"]
    if "builtin" in ds:
        from sklearn import datasets as skds
        loader = {
            "breast_cancer": skds.load_breast_cancer,
            "iris": skds.load_iris,
            "wine": skds.load_wine,
            "digits": skds.load_digits,
            "diabetes": skds.load_diabetes,
        }[ds["builtin"]]
        bunch = loader()
        return np.asarray(bunch.data, dtype=float), np.asarray(bunch.target)
    # CSV path inside the read-only /task mount.
    import pandas as pd
    df = pd.read_csv("/task/" + ds["path"])
    target = ds["target"]
    if target not in df.columns:
        _fail("target column %r not found in dataset" % target)
    y = df[target].to_numpy()
    X = df.drop(columns=[target]).select_dtypes(include="number").to_numpy(dtype=float)
    return X, y


def build_model():
    name = SPEC["model"]["name"]
    params = dict(SPEC["model"].get("params", {}))
    seed = SPEC["split"]["seed"]
    family = SPEC["family"]
    # Determinism guards applied AFTER user params: fixed seed, single thread.
    if family == "classification":
        ctor = {
            "logreg": lambda: LogisticRegression(max_iter=1000, random_state=seed, **params),
            "random_forest": lambda: RandomForestClassifier(random_state=seed, n_jobs=1, **params),
            "knn": lambda: KNeighborsClassifier(n_jobs=1, **params),
        }[name]
    else:
        ctor = {
            "ridge": lambda: Ridge(random_state=seed, **params),
            "random_forest": lambda: RandomForestRegressor(random_state=seed, n_jobs=1, **params),
            "knn": lambda: KNeighborsRegressor(n_jobs=1, **params),
        }[name]
    return ctor()


def score(model, X_test, y_test):
    name = SPEC["metric"]["name"]
    pred = model.predict(X_test)
    if name == "accuracy":
        return float(accuracy_score(y_test, pred))
    if name == "f1":
        return float(f1_score(y_test, pred, average="macro"))
    if name == "auc":
        classes = np.unique(y_test)
        if len(classes) != 2:
            _fail("auc metric supports binary targets only in v1")
        proba = model.predict_proba(X_test)[:, 1]
        return float(roc_auc_score(y_test, proba))
    if name == "rmse":
        return float(math.sqrt(mean_squared_error(y_test, pred)))
    if name == "mae":
        return float(mean_absolute_error(y_test, pred))
    if name == "r2":
        return float(r2_score(y_test, pred))
    _fail("unknown metric %r" % name)


def main():
    try:
        X, y = load_dataset()
        X_tr, X_te, y_tr, y_te = train_test_split(
            X, y,
            test_size=SPEC["split"]["test_fraction"],
            random_state=SPEC["split"]["seed"],
            shuffle=True,
        )
        model = build_model()
        model.fit(X_tr, y_tr)
        value = score(model, X_te, y_te)
    except SystemExit:
        raise
    except Exception as exc:  # any modeling error -> typed, bounded failure
        _fail("%s: %s" % (type(exc).__name__, exc))
    with open(RESULT, "w") as fh:
        json.dump({
            "ok": True,
            "metric_name": SPEC["metric"]["name"],
            "value": value,
            "n_train": int(len(y_tr)),
            "n_test": int(len(y_te)),
        }, fh)


if __name__ == "__main__":
    main()
'''


def generate_runner(spec: dict) -> str:
    """Fill the fixed template with the validated spec's JSON. Deterministic."""
    clean = validate_spec(spec)
    spec_json = json.dumps(clean, sort_keys=True)
    # Belt-and-suspenders against breaking out of the r\"\"\"...\"\"\" data block.
    if '"""' in spec_json or "\\" in spec_json:
        raise CodeSpecError("spec serialized to an unsafe form; refusing to generate a runner")
    return RUNNER_TEMPLATE.replace(_SPEC_TOKEN, spec_json)


# ----------------------------------------------------------------------------
# Result parsing — the ONLY thing read back from a job. Raises on malformed.
# ----------------------------------------------------------------------------

def parse_result(result_text: str) -> dict:
    """Parse a job's result.json into a normalized dict, or raise ValueError."""
    try:
        data = json.loads(result_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"result.json is not valid JSON: {e}")
    if not isinstance(data, dict) or "ok" not in data:
        raise ValueError("result.json missing the 'ok' field")
    if not data["ok"]:
        raise ValueError(f"job reported failure: {data.get('error', 'unknown error')}")
    for field in ("metric_name", "value", "n_train", "n_test"):
        if field not in data:
            raise ValueError(f"result.json missing field {field!r}")
    value = data["value"]
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"result.json 'value' must be a number, got {value!r}")
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"result.json 'value' is not finite: {value}")
    return {
        "metric_name": str(data["metric_name"]),
        "value": float(value),
        "n_train": int(data["n_train"]),
        "n_test": int(data["n_test"]),
    }


# ----------------------------------------------------------------------------
# The sandbox — a single ephemeral, jailed container run. Reusable and directly
# testable (the enforcement tests write their own probe runner.py and call this).
# ----------------------------------------------------------------------------

class SandboxResult:
    """Small typed outcome of one jailed container run — no raw log leaves here."""

    __slots__ = ("returncode", "timed_out", "oom_killed", "stderr_excerpt", "stdout_excerpt")

    def __init__(self, returncode, timed_out, oom_killed, stderr_excerpt, stdout_excerpt):
        self.returncode = returncode
        self.timed_out = timed_out
        self.oom_killed = oom_killed
        self.stderr_excerpt = stderr_excerpt
        self.stdout_excerpt = stdout_excerpt


def _excerpt(text: str, limit: int = MAX_DIAG_CHARS) -> str:
    """Bounded tail excerpt — the full text stays on disk, never in the return."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return "...(truncated)... " + text[-(limit - 20):]


def _docker(*args: str) -> list[str]:
    return ["docker", "--context", DOCKER_CONTEXT, *args]


def run_in_sandbox(run_dir: Path, task_dir: Path, timeout_s: int, mem_mb: int) -> SandboxResult:
    """Run /run/runner.py inside one ephemeral, fully-jailed container.

    The container is created with every jail flag (no network, memory cap, read-
    only rootfs, read-only task mount, tmpfs scratch, pids limit) and a hard wall.
    On the wall it is `docker kill`ed; --rm then removes it, leaving nothing.
    """
    run_dir = Path(run_dir)
    task_dir = Path(task_dir)
    name = f"code_job_{uuid.uuid4().hex[:12]}"
    cmd = _docker(
        "run", "--rm", "--name", name,
        "--network=none",
        f"--memory={mem_mb}m", f"--memory-swap={mem_mb}m",
        f"--pids-limit={PIDS_LIMIT}",
        "--read-only",
        f"--tmpfs=/tmp:size={TMPFS_MB}m",
        "-e", "HOME=/run",
        "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-e", "OMP_NUM_THREADS=1",
        "-e", "OPENBLAS_NUM_THREADS=1",
        "-e", "MKL_NUM_THREADS=1",
        "-v", f"{task_dir}:/task:ro",
        "-v", f"{run_dir}:/run:rw",
        "--workdir", "/run",
        IMAGE,
        "python", "/run/runner.py",
    )
    timed_out = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        returncode, stdout, stderr = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        returncode = -1
        stdout = (e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout) or ""
        stderr = (e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr) or ""
        # Kill the still-running container so nothing lingers; --rm cleans it up.
        subprocess.run(_docker("kill", name), capture_output=True, text=True)

    # Docker reports an OOM kill as exit 137 (128 + SIGKILL) from the cgroup cap.
    oom_killed = (returncode == 137) and not timed_out

    # Persist the full logs to disk (evidence), return only bounded excerpts.
    try:
        (run_dir / "stdout.log").write_text(stdout or "")
        (run_dir / "stderr.log").write_text(stderr or "")
    except OSError:
        pass
    return SandboxResult(
        returncode=returncode,
        timed_out=timed_out,
        oom_killed=oom_killed,
        stderr_excerpt=_excerpt(stderr),
        stdout_excerpt=_excerpt(stdout),
    )


# ----------------------------------------------------------------------------
# The public entry point — validate, generate, run, parse. Small typed return.
# ----------------------------------------------------------------------------

def _artifact_paths(run_dir: Path) -> dict:
    names = ("spec.json", "runner.py", "result.json", "stdout.log", "stderr.log")
    return {"paths": [str(run_dir / n) for n in names if (run_dir / n).is_file()]}


def run_code(spec: dict, task_dir: str | Path | None = None) -> dict:
    """Build, run, and summarize one v1 job. Returns the small dict documented at
    the top of this module — and nothing else leaves the wrapper."""
    wall_start = time.time()

    # --- validate + generate (deterministic, no I/O to the container) ------
    try:
        clean = validate_spec(spec)
        runner = generate_runner(spec)
    except CodeSpecError as e:
        return {"valid": False, "qoi": None,
                "diagnostics": f"spec rejected: {e}"[:MAX_DIAG_CHARS],
                "runtime_s": round(time.time() - wall_start, 3),
                "artifacts": {"paths": []}}

    # --- lay out an isolated job dir: run/ (rw) + task/ (ro) ----------------
    job = f"job_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}_{uuid.uuid4().hex[:8]}"
    job_root = RUNS_HOST / job
    run_dir = job_root / "run"
    task_dir_host = job_root / "task"
    run_dir.mkdir(parents=True, exist_ok=True)
    task_dir_host.mkdir(parents=True, exist_ok=True)

    (run_dir / "spec.json").write_text(json.dumps(clean, indent=2, sort_keys=True))
    (run_dir / "runner.py").write_text(runner)

    # Stage a path-based dataset into the read-only task mount.
    ds = clean["dataset"]
    if "path" in ds:
        if task_dir is None:
            return {"valid": False, "qoi": None,
                    "diagnostics": "dataset.path given but no task_dir provided to run_code()",
                    "runtime_s": round(time.time() - wall_start, 3),
                    "artifacts": _artifact_paths(run_dir)}
        src = Path(task_dir) / ds["path"]
        if not src.is_file():
            return {"valid": False, "qoi": None,
                    "diagnostics": f"dataset file not found: {ds['path']}",
                    "runtime_s": round(time.time() - wall_start, 3),
                    "artifacts": _artifact_paths(run_dir)}
        shutil.copy2(src, task_dir_host / ds["path"])

    # --- run in the jail ---------------------------------------------------
    sb = run_in_sandbox(run_dir, task_dir_host,
                        timeout_s=clean["budget"]["timeout_s"],
                        mem_mb=clean["budget"]["mem_mb"])

    runtime_s = round(time.time() - wall_start, 3)
    artifacts = _artifact_paths(run_dir)

    if sb.timed_out:
        return {"valid": False, "qoi": None,
                "diagnostics": (f"job exceeded the {clean['budget']['timeout_s']}s timeout "
                                f"and the container was killed")[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s, "artifacts": artifacts}
    if sb.oom_killed:
        return {"valid": False, "qoi": None,
                "diagnostics": (f"job exceeded the {clean['budget']['mem_mb']}MB memory cap "
                                f"and was OOM-killed (exit 137)")[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s, "artifacts": artifacts}

    result_path = run_dir / "result.json"
    if not result_path.is_file():
        diag = (f"job produced no result.json (exit {sb.returncode}). "
                f"stderr: {sb.stderr_excerpt}")
        return {"valid": False, "qoi": None,
                "diagnostics": diag[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s, "artifacts": artifacts}

    try:
        qoi = parse_result(result_path.read_text(errors="replace"))
    except ValueError as e:
        return {"valid": False, "qoi": None,
                "diagnostics": f"job ran but result was unusable: {e}"[:MAX_DIAG_CHARS],
                "runtime_s": runtime_s, "artifacts": artifacts}

    diagnostics = (f"sklearn_eval {clean['model']['name']} / {qoi['metric_name']} "
                   f"on {ds.get('builtin', ds.get('path'))}: "
                   f"{qoi['n_train']} train / {qoi['n_test']} test; exit {sb.returncode}")
    return {"valid": True, "qoi": qoi,
            "diagnostics": diagnostics[:MAX_DIAG_CHARS],
            "runtime_s": runtime_s, "artifacts": artifacts}


# CLI:  venv/bin/python3 tools/run_code.py    (runs the default breast_cancer job)
if __name__ == "__main__":
    default = {
        "task_type": "sklearn_eval",
        "dataset": {"builtin": "breast_cancer"},
        "model": {"name": "logreg"},
        "split": {"test_fraction": 0.25, "seed": 42},
        "metric": {"name": "accuracy"},
        "budget": {"timeout_s": 60, "mem_mb": 512},
    }
    print(json.dumps(run_code(default), indent=2))
