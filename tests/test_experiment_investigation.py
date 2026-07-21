"""test_experiment_investigation.py — the investigation loop over verified probes.

Phase 2, T2.1/T2.2/T2.3 scaffolding. The strategy proposes; the controller runs
AND verifies each probe; the verified result feeds the next decision. Proven
here with a SCRIPTED strategy (no live model — the live FULL agent's outing is a
Terminal job, per the run-venue rule), exactly as bench_agent's judgment is
faked in every test.

What these tests pin:
  * small-before-big is a strategy decision that reads a VERIFIED result — not a
    threshold hardcoded in the controller;
  * the proposes-not-measures boundary: the recorded number comes from
    run_composition, never from a value the strategy states;
  * an un-reproducible probe is caught and sinks the investigation's `publishable`
    flag — un-verifiable is un-publishable, the whole point.

Probes are code-only compositions (deterministic, seeded), so the reproduction
assertions are genuine re-executions in the sandbox.

Run directly: venv/bin/python3 tests/test_experiment_investigation.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.experiment_investigation import (  # noqa: E402
    InvestigationError,
    run_investigation,
)


def _estimator_recipe(n_samples, seeded=True):
    """A composition: one code step estimates a statistic over n_samples draws,
    the combine passes its magnitude through. Seeded => reproducible."""
    rng = "np.random.default_rng(0)" if seeded else "np.random.default_rng()"
    step_code = (
        "import numpy as np\n"
        f"metrics['est'] = float({rng}.standard_normal({n_samples}).mean())\n"
    )
    return {"kind": "composition",
            "steps": [{"step_id": "est", "kind": "code",
                       "code": step_code, "quantity": "est"}],
            "combine": {"kind": "code",
                        "code": "metrics['out'] = abs(inputs['est'])",
                        "quantity": "out", "inputs": ["est"]}}


class SmallBeforeBigStrategy:
    """Scripted experimenter: probe cheap, read the VERIFIED result, and only
    then scale up. The scaling is decided from `state`, not baked into the
    controller — which is the property T2.2 is about."""

    SMALL, BIG = 100, 5000

    def __init__(self):
        self.sizes_chosen = []

    def __call__(self, state):
        prior = state["measurements"]
        if not prior:
            self.sizes_chosen.append(self.SMALL)
            return {"recipe": _estimator_recipe(self.SMALL),
                    "reasoning": "cheap probe first to see if this is worth scaling"}
        last = prior[-1]
        # the decision reads a VERIFIED result off the state
        if len(prior) == 1 and last["verified"] and last["value"] is not None:
            self.sizes_chosen.append(self.BIG)
            return {"recipe": _estimator_recipe(self.BIG),
                    "predicted_value": last["value"],
                    "reasoning": "small probe reproduced; scale up for precision"}
        return {"stop": True, "stop_reason": "have both the cheap and scaled estimates"}


class TestSmallBeforeBig(unittest.TestCase):
    def test_strategy_scales_after_reading_a_verified_probe(self):
        strat = SmallBeforeBigStrategy()
        summary = run_investigation(strat, max_iters=6)
        self.assertEqual(summary["iterations"], 2)
        self.assertEqual(strat.sizes_chosen, [100, 5000])   # cheap, then big
        self.assertTrue(summary["publishable"])
        self.assertEqual(summary["verified"], 2)
        # both probes reproduced end-to-end
        for m in summary["measurements"]:
            self.assertTrue(m["verified"], m)
            self.assertEqual(m["reason"], "reproduced")
            self.assertIsNotNone(m["value"])
        self.assertIn("both", summary["stop_reason"])


class TestBoundary(unittest.TestCase):
    """The strategy proposes; the controller measures. A number the strategy
    states is never the measurement."""

    def test_a_stated_value_is_ignored_the_prediction_is_only_compared(self):
        def liar(state):
            if state["measurements"]:
                return {"stop": True, "stop_reason": "done"}
            return {"recipe": _estimator_recipe(200),
                    # both of these are the strategy trying to inject a number
                    "value": 999.0, "observed_value": 999.0,
                    "predicted_value": 999.0,
                    "reasoning": "predicting nonsense on purpose"}

        summary = run_investigation(liar, max_iters=3)
        m = summary["measurements"][0]
        self.assertTrue(m["verified"])
        self.assertNotEqual(m["value"], 999.0)          # the real number stands
        self.assertEqual(m["predicted"], 999.0)         # kept only as a prediction
        self.assertGreater(m["prediction_abs_error"], 900)


class TestUnreproducibleSinksPublishable(unittest.TestCase):
    def test_an_unseeded_probe_is_caught_and_the_run_does_not_stand(self):
        def one_shot(state):
            if state["measurements"]:
                return {"stop": True, "stop_reason": "done"}
            return {"recipe": _estimator_recipe(500, seeded=False),
                    "reasoning": "unseeded on purpose — must not reproduce"}

        summary = run_investigation(one_shot, max_iters=3)
        self.assertEqual(summary["iterations"], 1)
        m = summary["measurements"][0]
        self.assertFalse(m["verified"])
        self.assertEqual(m["reason"], "mismatch")
        self.assertFalse(summary["publishable"])


class TestActionValidation(unittest.TestCase):
    def test_a_non_stopping_action_needs_a_composition_recipe(self):
        with self.assertRaises(InvestigationError):
            run_investigation(lambda s: {"recipe": {"kind": "code"}}, max_iters=1)

    def test_stop_needs_a_reason(self):
        with self.assertRaises(InvestigationError):
            run_investigation(lambda s: {"stop": True}, max_iters=1)

    def test_no_probes_does_not_stand(self):
        summary = run_investigation(
            lambda s: {"stop": True, "stop_reason": "nothing to do"}, max_iters=3)
        self.assertEqual(summary["iterations"], 0)
        self.assertFalse(summary["publishable"])
        self.assertIn("note", summary)


if __name__ == "__main__":
    unittest.main()
