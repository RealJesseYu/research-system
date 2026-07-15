"""
test_run_code.py — tests for the code-execution sandbox wrapper (Step 28.5 DRY).

ZERO model calls. Two tiers:

  * PURE tests (always run): spec validation + allowlists, runner-template
    generation determinism, result.json parsing, refusal of unknown shapes, and
    the return-carries-no-raw-log bound. No docker.

  * JAIL tests (@skipUnless docker + code-img present): each proves a container
    jail by FAILING an escape — no network, memory cap, read-only workdir — plus
    a hard timeout, and the end-to-end sklearn_eval path with twice-run
    determinism. These are the permitted local sandbox smoke executions; they run
    live here and skip cleanly where docker is unavailable, keeping the offline
    suite green.

Run directly:  venv/bin/python3 -m pytest tests/test_run_code.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_code  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
VALID_RESULT = (FIXTURES / "code_result_valid.json").read_text()
MALFORMED_RESULT = (FIXTURES / "code_result_malformed.json").read_text()

GOOD_SPEC = {
    "task_type": "sklearn_eval",
    "dataset": {"builtin": "breast_cancer"},
    "model": {"name": "logreg", "params": {"C": 1.0}},
    "split": {"test_fraction": 0.25, "seed": 42},
    "metric": {"name": "accuracy"},
    "budget": {"timeout_s": 60, "mem_mb": 512},
}


def _docker_ready() -> bool:
    """True only if the colima docker context answers AND code-img exists."""
    try:
        out = subprocess.run(
            ["docker", "--context", run_code.DOCKER_CONTEXT, "images", "-q", run_code.IMAGE],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


DOCKER = _docker_ready()

# A project-tree scratch base: colima only bind-mounts paths under $HOME, so
# tests MUST NOT use /tmp — they stage job dirs under the wrapper's runs root.
_TEST_BASE = run_code.RUNS_HOST / "_pytest"


def _fresh_job_dirs():
    d = _TEST_BASE / uuid.uuid4().hex[:10]
    run_dir, task_dir = d / "run", d / "task"
    run_dir.mkdir(parents=True)
    task_dir.mkdir(parents=True)
    return d, run_dir, task_dir


# ---------------------------------------------------------------------------
# PURE tests — validation, allowlists, template, parser, refusals. No docker.
# ---------------------------------------------------------------------------
class TestValidation(unittest.TestCase):
    def test_good_spec_normalizes(self):
        clean = run_code.validate_spec(GOOD_SPEC)
        self.assertEqual(clean["family"], "classification")
        self.assertEqual(clean["model"]["name"], "logreg")
        self.assertEqual(clean["budget"], {"timeout_s": 60, "mem_mb": 512})

    def test_unknown_task_type_refused(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "task_type": "shell_exec"})

    def test_unknown_model_refused(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "model": {"name": "xgboost"}})

    def test_unknown_metric_refused(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "metric": {"name": "perplexity"}})

    def test_model_metric_family_mismatch_refused(self):
        # ridge is regression-only; accuracy is a classification metric.
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "model": {"name": "ridge"}})

    def test_builtin_dataset_family_mismatch_refused(self):
        # diabetes is a regression dataset; accuracy is classification.
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "dataset": {"builtin": "diabetes"}})

    def test_dataset_both_or_neither_refused(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "dataset": {}})
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC,
                                    "dataset": {"builtin": "iris", "path": "x.csv"}})

    def test_path_traversal_refused(self):
        for bad in ("../secrets.csv", "sub/dir.csv", "/etc/passwd", ".."):
            with self.assertRaises(run_code.CodeSpecError):
                run_code.validate_spec({**GOOD_SPEC,
                                        "dataset": {"path": bad, "target": "y"},
                                        "model": {"name": "ridge"},
                                        "metric": {"name": "rmse"}})

    def test_non_numeric_param_refused(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC,
                                    "model": {"name": "logreg", "params": {"solver": "liblinear"}}})

    def test_budget_bounds_enforced(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "budget": {"timeout_s": 0, "mem_mb": 512}})
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "budget": {"timeout_s": 60, "mem_mb": 8}})
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "budget": {"timeout_s": 99999, "mem_mb": 512}})

    def test_test_fraction_bounds_enforced(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.validate_spec({**GOOD_SPEC, "split": {"test_fraction": 1.5, "seed": 0}})


class TestRunnerTemplate(unittest.TestCase):
    def test_generation_is_deterministic(self):
        a = run_code.generate_runner(GOOD_SPEC)
        b = run_code.generate_runner(dict(GOOD_SPEC))
        self.assertEqual(a, b)

    def test_generation_independent_of_key_order(self):
        reordered = {k: GOOD_SPEC[k] for k in reversed(list(GOOD_SPEC))}
        self.assertEqual(run_code.generate_runner(GOOD_SPEC),
                         run_code.generate_runner(reordered))

    def test_token_fully_replaced_and_spec_embedded(self):
        runner = run_code.generate_runner(GOOD_SPEC)
        self.assertNotIn(run_code._SPEC_TOKEN, runner)
        self.assertIn('"task_type": "sklearn_eval"', runner)
        self.assertIn("def main()", runner)  # the fixed template body is present

    def test_unknown_spec_cannot_generate(self):
        with self.assertRaises(run_code.CodeSpecError):
            run_code.generate_runner({**GOOD_SPEC, "model": {"name": "xgboost"}})


class TestResultParser(unittest.TestCase):
    def test_valid_result_parses(self):
        qoi = run_code.parse_result(VALID_RESULT)
        self.assertEqual(qoi["metric_name"], "accuracy")
        self.assertAlmostEqual(qoi["value"], 0.958041958, places=6)
        self.assertEqual((qoi["n_train"], qoi["n_test"]), (426, 143))

    def test_malformed_json_raises(self):
        with self.assertRaises(ValueError):
            run_code.parse_result(MALFORMED_RESULT)

    def test_reported_failure_raises(self):
        with self.assertRaises(ValueError):
            run_code.parse_result('{"ok": false, "error": "boom"}')

    def test_missing_field_raises(self):
        with self.assertRaises(ValueError):
            run_code.parse_result('{"ok": true, "metric_name": "accuracy", "value": 0.9}')

    def test_non_finite_value_raises(self):
        with self.assertRaises(ValueError):
            run_code.parse_result('{"ok": true, "metric_name": "r2", "value": NaN, '
                                  '"n_train": 10, "n_test": 5}')


class TestRefusalsAndBounds(unittest.TestCase):
    def test_run_code_refuses_unknown_task_type_without_docker(self):
        # Refusal happens at validation, BEFORE any container is created.
        out = run_code.run_code({**GOOD_SPEC, "task_type": "arbitrary_shell"})
        self.assertFalse(out["valid"])
        self.assertIsNone(out["qoi"])
        self.assertIn("unrecognized task_type", out["diagnostics"])
        self.assertEqual(out["artifacts"], {"paths": []})

    def test_diagnostics_are_bounded(self):
        out = run_code.run_code({**GOOD_SPEC, "model": {"name": "z" * 5000}})
        self.assertLessEqual(len(out["diagnostics"]), run_code.MAX_DIAG_CHARS)

    def test_excerpt_truncates_long_text(self):
        long = "X" * 10000
        ex = run_code._excerpt(long)
        self.assertLessEqual(len(ex), run_code.MAX_DIAG_CHARS)
        self.assertNotEqual(ex, long)  # a raw log never escapes whole


# ---------------------------------------------------------------------------
# JAIL tests — each proves a jail by failing an escape. Require live docker.
# ---------------------------------------------------------------------------
def _probe(run_dir, task_dir, code, timeout_s=20, mem_mb=256):
    (run_dir / "runner.py").write_text(code)
    return run_code.run_in_sandbox(run_dir, task_dir, timeout_s=timeout_s, mem_mb=mem_mb)


@unittest.skipUnless(DOCKER, "docker/colima + code-img not available")
class TestJails(unittest.TestCase):
    def test_network_is_blocked(self):
        _, run_dir, task_dir = _fresh_job_dirs()
        sb = _probe(run_dir, task_dir,
                    'import urllib.request\n'
                    'urllib.request.urlopen("http://example.com", timeout=5)\n'
                    'print("REACHED_NETWORK")\n')
        self.assertNotEqual(sb.returncode, 0)
        self.assertNotIn("REACHED_NETWORK", sb.stdout_excerpt)
        self.assertRegex(sb.stderr_excerpt.lower(), r"name resolution|unreachable|urlerror")

    def test_memory_cap_is_enforced(self):
        _, run_dir, task_dir = _fresh_job_dirs()
        sb = _probe(run_dir, task_dir,
                    'x = bytearray(600 * 1024 * 1024)\nprint("ALLOCATED", len(x))\n',
                    mem_mb=256)
        self.assertTrue(sb.oom_killed)
        self.assertEqual(sb.returncode, 137)
        self.assertNotIn("ALLOCATED", sb.stdout_excerpt)

    def test_workdir_is_jailed(self):
        _, run_dir, task_dir = _fresh_job_dirs()
        sb = _probe(run_dir, task_dir,
                    'open("/task/escape.txt", "w").write("x")\nprint("WROTE_OUTSIDE")\n')
        self.assertNotEqual(sb.returncode, 0)
        self.assertNotIn("WROTE_OUTSIDE", sb.stdout_excerpt)
        self.assertIn("Read-only file system", sb.stderr_excerpt)

    def test_timeout_kills_container_and_leaves_nothing(self):
        _, run_dir, task_dir = _fresh_job_dirs()
        sb = _probe(run_dir, task_dir, 'import time\ntime.sleep(30)\nprint("SLEPT")\n',
                    timeout_s=3)
        self.assertTrue(sb.timed_out)
        self.assertNotIn("SLEPT", sb.stdout_excerpt)
        lingering = subprocess.run(
            ["docker", "--context", run_code.DOCKER_CONTEXT, "ps", "-a",
             "--filter", "name=code_job_", "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=30).stdout.strip()
        self.assertEqual(lingering, "", f"lingering containers: {lingering!r}")


@unittest.skipUnless(DOCKER, "docker/colima + code-img not available")
class TestEndToEnd(unittest.TestCase):
    def test_sklearn_eval_logreg(self):
        out = run_code.run_code(GOOD_SPEC)
        self.assertTrue(out["valid"], out["diagnostics"])
        self.assertEqual(out["qoi"]["metric_name"], "accuracy")
        self.assertTrue(0.8 < out["qoi"]["value"] < 1.0)
        self.assertEqual(out["qoi"]["n_train"] + out["qoi"]["n_test"], 569)

    def test_twice_run_determinism(self):
        a = run_code.run_code(GOOD_SPEC)
        b = run_code.run_code(GOOD_SPEC)
        self.assertEqual(a["qoi"]["value"], b["qoi"]["value"])

    def test_random_forest_plausible(self):
        out = run_code.run_code({**GOOD_SPEC,
                                 "model": {"name": "random_forest", "params": {"n_estimators": 50}}})
        self.assertTrue(out["valid"], out["diagnostics"])
        self.assertTrue(0.8 < out["qoi"]["value"] < 1.0)

    def test_csv_path_form(self):
        task_dir = Path(__file__).resolve().parent.parent / "tools" / "code_tasks" / "datasets"
        spec = {
            "task_type": "sklearn_eval",
            "dataset": {"path": "tiny_regression.csv", "target": "y"},
            "model": {"name": "ridge", "params": {"alpha": 1.0}},
            "split": {"test_fraction": 0.25, "seed": 7},
            "metric": {"name": "rmse"},
            "budget": {"timeout_s": 60, "mem_mb": 512},
        }
        out = run_code.run_code(spec, task_dir=task_dir)
        self.assertTrue(out["valid"], out["diagnostics"])
        self.assertEqual(out["qoi"]["metric_name"], "rmse")
        self.assertGreaterEqual(out["qoi"]["value"], 0.0)

    def test_return_carries_no_raw_log(self):
        # A job whose runner prints a loud marker to stdout/stderr; that raw text
        # must reach the on-disk logs but NEVER the returned dict.
        _, run_dir, task_dir = _fresh_job_dirs()
        marker = "RAWLOGSENTINEL_" + uuid.uuid4().hex
        (run_dir / "runner.py").write_text(
            f'import sys\nprint("{marker}")\nsys.stderr.write("{marker}\\n")\n'
            'raise SystemExit(3)\n')
        sb = run_code.run_in_sandbox(run_dir, task_dir, timeout_s=20, mem_mb=256)
        # The marker landed in the on-disk logs (evidence kept)...
        self.assertIn(marker, (run_dir / "stdout.log").read_text())
        self.assertIn(marker, (run_dir / "stderr.log").read_text())
        # ...and the wrapper's public return holds only the documented, bounded keys.
        out = run_code.run_code(GOOD_SPEC)
        self.assertEqual(set(out.keys()),
                         {"valid", "qoi", "diagnostics", "runtime_s", "artifacts"})
        self.assertLessEqual(len(out["diagnostics"]), run_code.MAX_DIAG_CHARS)


if __name__ == "__main__":
    unittest.main()
