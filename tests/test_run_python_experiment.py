"""
test_run_python_experiment — the code-execution wrapper (2026-07-20).

Input validation is tested offline. The execution tests need colima + code-img
and are skipped when the image is absent, matching how the other substrate
wrappers' live tests behave in a container-less checkout.

The load-bearing tests here are the NEGATIVE ones. A code-execution substrate
is the easiest place in the whole system to accidentally fabricate a result:
stdout is full of numbers, and any convention that reads one out of prose will
eventually read one out of a traceback. The structural gate (metrics must be
written to a result file, and are withheld on any non-clean exit) is what makes
that impossible, so it gets the most coverage.
"""

import shutil
import subprocess
import unittest

from tools.run_python_experiment import (
    PythonExperimentInputError,
    run_python_experiment,
)


def _image_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        out = subprocess.run(
            ["docker", "--context", "colima", "images", "-q", "code-img:latest"],
            capture_output=True, text=True, timeout=30,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


LIVE = _image_available()
requires_image = unittest.skipUnless(LIVE, "code-img:latest not available")


class TestInputValidation(unittest.TestCase):

    def test_missing_required_fields(self):
        with self.assertRaises(PythonExperimentInputError) as cm:
            run_python_experiment({"code": "metrics['x']=1"})
        self.assertIn("quantity", str(cm.exception))

    def test_unsupported_field_named(self):
        with self.assertRaises(PythonExperimentInputError) as cm:
            run_python_experiment(
                {"code": "x=1", "quantity": "x", "gpu": True}
            )
        self.assertIn("gpu", str(cm.exception))

    def test_empty_code_rejected(self):
        for bad in ("", "   ", None, 42):
            with self.assertRaises(PythonExperimentInputError):
                run_python_experiment({"code": bad, "quantity": "x"})

    def test_timeout_bounds_enforced(self):
        for bad in (0, -1, 10**9):
            with self.assertRaises(PythonExperimentInputError):
                run_python_experiment(
                    {"code": "x=1", "quantity": "x", "timeout_s": bad}
                )

    def test_oversized_code_rejected(self):
        with self.assertRaises(PythonExperimentInputError) as cm:
            run_python_experiment(
                {"code": "#" * 200_000, "quantity": "x"}
            )
        self.assertIn("bytes", str(cm.exception))


@requires_image
class TestHonestFailureModes(unittest.TestCase):
    """No path through this wrapper may return a number it did not measure."""

    def _run(self, code, quantity="x"):
        return run_python_experiment({"code": code, "quantity": quantity})

    def test_crash_withholds_metrics_even_when_written(self):
        """The atexit hook may well have written a value before the crash. A
        number from a run that died is not a measurement."""
        r = self._run("metrics['x'] = 1.0\nraise ValueError('boom')")
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertEqual(r["metrics"], {"x": 1.0})  # kept as evidence, not as a QoI

    def test_missing_requested_metric(self):
        r = self._run("metrics['other'] = 1.0")
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("other", r["diagnostics"])

    def test_non_finite_metric_is_not_a_measurement(self):
        for expr in ("float('nan')", "float('inf')"):
            r = self._run(f"metrics['x'] = {expr}")
            self.assertFalse(r["valid"])
            self.assertIsNone(r["qoi"])

    def test_printing_a_number_is_not_reporting_one(self):
        """stdout is diagnostics, never data — the structural gate."""
        r = self._run("print('the answer is 42')")
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])

    def test_stdout_never_returned_wholesale(self):
        r = self._run("print('X' * 50000)\nmetrics['x'] = 1.0")
        self.assertLess(len(r["diagnostics"]), 2000)

    def test_network_is_unavailable(self):
        r = self._run(
            "import urllib.request as u\n"
            "u.urlopen('http://example.com', timeout=5)\n"
            "metrics['x'] = 1.0"
        )
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])

    def test_timeout_returns_honestly(self):
        r = run_python_experiment(
            {"code": "import time\ntime.sleep(30)\nmetrics['x']=1.0",
             "quantity": "x", "timeout_s": 2}
        )
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])


@requires_image
class TestRealExperiment(unittest.TestCase):

    def test_a_real_ml_experiment_returns_its_metric(self):
        code = (
            "import numpy as np\n"
            "from sklearn.linear_model import Ridge\n"
            "from sklearn.model_selection import cross_val_score\n"
            "from sklearn.datasets import make_regression\n"
            "X, y = make_regression(n_samples=200, n_features=20, noise=10.0,"
            " random_state=0)\n"
            "s = cross_val_score(Ridge(alpha=1.0), X, y, cv=5, scoring='r2')\n"
            "metrics['mean_r2'] = float(s.mean())\n"
        )
        r = run_python_experiment({"code": code, "quantity": "mean_r2"})
        self.assertTrue(r["valid"], r["diagnostics"])
        self.assertIsInstance(r["qoi"], float)
        self.assertGreater(r["qoi"], 0.5)

    def test_identical_code_gives_identical_results(self):
        code = (
            "import numpy as np\n"
            "rng = np.random.default_rng(42)\n"
            "metrics['m'] = float(rng.normal(size=1000).mean())\n"
        )
        a = run_python_experiment({"code": code, "quantity": "m"})
        b = run_python_experiment({"code": code, "quantity": "m"})
        self.assertEqual(a["qoi"], b["qoi"])

    def test_all_metrics_returned_as_evidence(self):
        r = run_python_experiment(
            {"code": "metrics['a']=1.0\nmetrics['b']=2.0", "quantity": "a"}
        )
        self.assertEqual(r["metrics"], {"a": 1.0, "b": 2.0})
        self.assertEqual(r["qoi"], 1.0)


if __name__ == "__main__":
    unittest.main()
