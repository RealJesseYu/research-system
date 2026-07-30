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

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.run_python_experiment import (
    MAX_ARTIFACT_BYTES,
    PythonExperimentInputError,
    _capture_output_files,
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
        """The cap still refuses — sized off MAX_CODE_BYTES rather than a literal,
        because it was RAISED 100_000 -> 2_000_000 on 2026-07-30 (a 200 kB
        reproducer that is mostly embedded data is legitimate; see the constant's
        comment and tests/test_cost_and_code_cap.py)."""
        from tools.run_python_experiment import MAX_CODE_BYTES

        with self.assertRaises(PythonExperimentInputError) as cm:
            run_python_experiment(
                {"code": "#" * (MAX_CODE_BYTES + 1), "quantity": "x"}
            )
        self.assertIn("bytes", str(cm.exception))

    def test_a_data_heavy_reproducer_under_the_cap_is_accepted(self):
        """The regression this cap change exists to prevent: a 200 kB artifact
        that is mostly an embedded data literal must reach the sandbox, not be
        refused at validation. It must fail LATER (no docker here) or run — the
        one thing it must not raise is the size error."""
        code = "metrics = {}\nDATA = '" + ("A" * 200_000) + "'\nmetrics['x'] = 1\n"
        try:
            run_python_experiment({"code": code, "quantity": "x"})
        except PythonExperimentInputError as exc:  # pragma: no cover - guard
            self.fail(f"a 200 kB data-heavy reproducer was refused at input: {exc}")
        except Exception:  # noqa: BLE001 — anything downstream (no image) is fine
            pass


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


class TestOutputCaptureCannotEscapeTheSandbox(unittest.TestCase):
    """The jail (--network=none, --read-only) was never the weak point — the
    READBACK was.

    /work is bind-mounted read-write, and _safe_artifact_name validates only the
    NAME, saying nothing about what the name points at. is_file() and
    read_bytes() both FOLLOW symlinks, so sandboxed code doing
    os.symlink('<any host path>', '/work/out.txt') and declaring out.txt made the
    HOST read the host's own file and hand the bytes to the orchestrator.
    Verified exploitable against the pre-fix logic with a decoy file before the
    guard was added; these run offline, no container needed.
    """

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())
        self.outside = Path(tempfile.mkdtemp()) / "host_secret.txt"
        self.outside.write_text("SENTINEL-outside-the-sandbox")

    def test_a_symlinked_output_is_refused_not_followed(self):
        os.symlink(self.outside, self.run_dir / "out.txt")
        captured, error = _capture_output_files(self.run_dir, ["out.txt"])
        self.assertEqual(captured, {})
        self.assertIn("symbolic link", error)

    def test_the_refusal_leaks_nothing(self):
        os.symlink(self.outside, self.run_dir / "out.txt")
        captured, error = _capture_output_files(self.run_dir, ["out.txt"])
        self.assertNotIn("SENTINEL", repr(captured))
        self.assertNotIn("SENTINEL", error)

    def test_a_symlink_to_a_directory_is_also_refused(self):
        os.symlink(self.outside.parent, self.run_dir / "out.txt")
        captured, error = _capture_output_files(self.run_dir, ["out.txt"])
        self.assertEqual(captured, {})
        self.assertIn("symbolic link", error)

    def test_an_ordinary_output_file_still_captures(self):
        (self.run_dir / "out.txt").write_bytes(b"42")
        captured, error = _capture_output_files(self.run_dir, ["out.txt"])
        self.assertIsNone(error)
        self.assertEqual(captured, {"out.txt": b"42"})

    def test_an_absent_declared_file_is_left_out_not_an_error(self):
        """Completeness is the caller's check; absence is not a capture failure."""
        captured, error = _capture_output_files(self.run_dir, ["never_written.txt"])
        self.assertIsNone(error)
        self.assertEqual(captured, {})

    def test_the_size_cap_is_checked_before_the_read(self):
        """It used to run AFTER read_bytes(), so an oversized declared output
        exhausted host memory before the cap that exists to stop that could
        fire. stat() first means the bytes are never loaded."""
        big = self.run_dir / "out.txt"
        with open(big, "wb") as f:
            f.seek(MAX_ARTIFACT_BYTES + 1)
            f.write(b"\0")
        captured, error = _capture_output_files(self.run_dir, ["out.txt"])
        self.assertEqual(captured, {})
        self.assertIn("artifact cap", error)


if __name__ == "__main__":
    unittest.main()
