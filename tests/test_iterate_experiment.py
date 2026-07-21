"""
test_iterate_experiment.py — the bounded author -> run -> diagnose -> re-author
loop (tools/iterate_experiment.py).

WHAT THIS PROVES, with NO container and NO model (an injected fake runner and a
fake author):
  - a first-try success uses exactly one attempt and never re-authors;
  - an execution FAILURE feeds the wrapper's bounded diagnostic back to the next
    author call, and a recovered second attempt returns 'solved' at attempts=2;
  - a persistently failing experiment gives up HONESTLY after max_attempts with
    qoi=None and a full per-attempt trail — it never raises and never fabricates;
  - only the bounded diagnostic (never raw output) is what flows between attempts;
  - misconfiguration (empty quantity, non-callable author, bad bound, empty code)
    raises ExperimentIterationError, distinct from an experiment that fails.

Run directly: venv/bin/python3 tests/test_iterate_experiment.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.iterate_experiment import (  # noqa: E402
    ExperimentIterationError,
    iterate_experiment,
)


def _valid(qoi=1.0, diag="ok"):
    return {"valid": True, "qoi": qoi, "metrics": {"m": qoi},
            "diagnostics": diag, "runtime_s": 0.01}


def _invalid(diag="reported no metric named 'm'"):
    return {"valid": False, "qoi": None, "metrics": {},
            "diagnostics": diag, "runtime_s": 0.01}


class ScriptedRunner:
    """A fake wrapper: returns a pre-scripted summary per call, recording the
    specs it was handed so a test can assert what the author produced."""

    def __init__(self, summaries):
        self._summaries = list(summaries)
        self.specs_seen = []

    def __call__(self, spec):
        self.specs_seen.append(spec)
        return self._summaries[len(self.specs_seen) - 1]


class RecordingAuthor:
    """A fake code author: returns a pre-scripted code string per attempt and
    records the (attempt, prior_diagnostic) it was called with."""

    def __init__(self, codes):
        self._codes = list(codes)
        self.calls = []

    def __call__(self, attempt, prior_diagnostic):
        self.calls.append((attempt, prior_diagnostic))
        return self._codes[attempt - 1]


class FirstTrySuccess(unittest.TestCase):
    def test_one_attempt_no_reauthor(self):
        runner = ScriptedRunner([_valid(qoi=42.0)])
        author = RecordingAuthor(["metrics['m']=42"])
        out = iterate_experiment("m", author, runner=runner, max_attempts=3)

        self.assertEqual(out["outcome"], "solved")
        self.assertEqual(out["attempts"], 1)
        self.assertEqual(out["qoi"], 42.0)
        self.assertEqual(len(out["trail"]), 1)
        self.assertTrue(out["trail"][0]["valid"])
        # authored exactly once, with no prior diagnostic
        self.assertEqual(author.calls, [(1, None)])
        # ran exactly once
        self.assertEqual(len(runner.specs_seen), 1)


class RecoverAfterFailure(unittest.TestCase):
    def test_diagnostic_fed_back_and_second_attempt_solves(self):
        first_diag = "the experiment exited 1 — NameError: np is not defined"
        runner = ScriptedRunner([_invalid(first_diag), _valid(qoi=7.5)])
        author = RecordingAuthor(["broken code", "fixed code"])
        out = iterate_experiment("m", author, runner=runner, max_attempts=3)

        self.assertEqual(out["outcome"], "solved")
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(out["qoi"], 7.5)
        self.assertEqual(len(out["trail"]), 2)
        self.assertFalse(out["trail"][0]["valid"])
        self.assertTrue(out["trail"][1]["valid"])

        # THE load-bearing assertion: attempt 2's author saw attempt 1's
        # bounded diagnostic — the failure fed the fix.
        self.assertEqual(author.calls[0], (1, None))
        self.assertEqual(author.calls[1], (2, first_diag))

        # The two attempts ran different code (a real re-author, not a retry).
        self.assertNotEqual(
            runner.specs_seen[0]["code"], runner.specs_seen[1]["code"])


class GiveUpHonestly(unittest.TestCase):
    def test_bounded_and_no_fabricated_qoi(self):
        runner = ScriptedRunner([_invalid("fail 1"), _invalid("fail 2")])
        author = RecordingAuthor(["c1", "c2"])
        out = iterate_experiment("m", author, runner=runner, max_attempts=2)

        self.assertEqual(out["outcome"], "gave_up")
        self.assertEqual(out["attempts"], 2)
        self.assertIsNone(out["qoi"])                  # never fabricated
        self.assertFalse(out["summary"]["valid"])
        self.assertEqual(len(out["trail"]), 2)         # full evidence trail
        self.assertEqual(len(runner.specs_seen), 2)    # stopped at the bound
        # each retry carried the prior diagnostic forward
        self.assertEqual(author.calls[1][1], "fail 1")

    def test_never_raises_for_a_failing_experiment(self):
        runner = ScriptedRunner([_invalid()] * 3)
        author = RecordingAuthor(["c"] * 3)
        # no assertRaises — a persistently failing experiment is a result, not
        # an error.
        out = iterate_experiment("m", author, runner=runner, max_attempts=3)
        self.assertEqual(out["outcome"], "gave_up")


class Misconfiguration(unittest.TestCase):
    def test_empty_quantity_raises(self):
        with self.assertRaises(ExperimentIterationError):
            iterate_experiment("  ", RecordingAuthor(["c"]), runner=ScriptedRunner([]))

    def test_non_callable_author_raises(self):
        with self.assertRaises(ExperimentIterationError):
            iterate_experiment("m", "not-callable", runner=ScriptedRunner([]))

    def test_bad_max_attempts_raises(self):
        with self.assertRaises(ExperimentIterationError):
            iterate_experiment("m", RecordingAuthor(["c"]),
                               runner=ScriptedRunner([]), max_attempts=0)

    def test_author_returning_empty_code_raises(self):
        runner = ScriptedRunner([_valid()])
        with self.assertRaises(ExperimentIterationError):
            iterate_experiment("m", RecordingAuthor([""]), runner=runner)


if __name__ == "__main__":
    unittest.main(verbosity=2)
