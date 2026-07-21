"""test_experiment_route.py — the exact-tool experiment path (Phase 3, R-ROUTE-2/3).

docs/memo_phase3_routing.md. Proves the seam that replaces static stages 2–5 +
the fidelity gate with the experimenter loop for an EXACT-tool run: the fidelity
skip is RECORDED (never silent), the loop runs and verifies, and the publishable
verdict is the loop's. Driven by a SCRIPTED strategy (no live model — the live
outing is the owner's Terminal job); probes are code-only compositions, so the
reproduction is a genuine sandbox re-execution.

Run directly: venv/bin/python3 tests/test_experiment_route.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.experiment_route import run_exact_investigation  # noqa: E402


def _code_composition(a=2.0, factor=3.0):
    return {
        "kind": "composition",
        "steps": [{"step_id": "a", "kind": "code",
                   "code": f"metrics['a'] = {a}", "quantity": "a"}],
        "combine": {"kind": "code",
                    "code": f"metrics['out'] = inputs['a'] * {factor}",
                    "quantity": "out", "inputs": ["a"]},
    }


class _ProbeThenStop:
    def __call__(self, state):
        if not state["measurements"]:
            return {"recipe": _code_composition(2.0, 3.0), "predicted_value": 6.0,
                    "reasoning": "cheap exact probe"}
        return {"stop": True, "stop_reason": "the probe reproduced; enough"}


class TestFidelityIsSkippedHonestly(unittest.TestCase):
    def test_the_skip_is_recorded_with_a_reason(self):
        out = run_exact_investigation(_ProbeThenStop(), max_iters=4)
        self.assertFalse(out["fidelity"]["applies"])
        self.assertEqual(out["fidelity"]["instrument_class"], "exact")
        self.assertIn("non-question", out["fidelity"]["reason"])
        # R-ROUTE-2: it is a recorded decision, not an omission
        self.assertTrue(out["fidelity"]["reason"].strip())


class TestTheLoopRunsAndVerifies(unittest.TestCase):
    def test_a_probe_then_stop_is_verified_and_publishable(self):
        out = run_exact_investigation(_ProbeThenStop(), max_iters=4)
        summary = out["investigation"]
        self.assertEqual(summary["iterations"], 1)
        self.assertTrue(out["publishable"])
        self.assertEqual(summary["verified"], 1)
        m = summary["measurements"][0]
        self.assertTrue(m["verified"])
        self.assertEqual(m["reason"], "reproduced")
        # the number of record came from run_composition, by code — 2.0 * 3.0
        self.assertEqual(m["value"], 6.0)
        self.assertEqual(m["predicted"], 6.0)

    def test_an_investigation_that_runs_nothing_does_not_stand(self):
        out = run_exact_investigation(
            lambda s: {"stop": True, "stop_reason": "nothing to do"}, max_iters=3)
        self.assertFalse(out["publishable"])
        # the fidelity skip is still recorded — the routing decision is
        # independent of whether the loop produced a result
        self.assertFalse(out["fidelity"]["applies"])


if __name__ == "__main__":
    unittest.main()
