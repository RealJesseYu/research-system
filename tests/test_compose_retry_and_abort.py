"""test_compose_retry_and_abort.py — Defects A & B from the 2026-07-22 director run.

Defect A: the tooled compose call had no transport retry, so one transient SDK
glitch aborted a whole investigation. It now retries (bounded) before giving up.

Defect B: a run truncated by such an error still self-labeled 'publishable'. An
ERROR-aborted investigation is now NOT publishable even if its probes reproduced
(the verified numbers are still recorded — the run is just not claimed).

Call-free: call_stage_model is patched; the probe is an in-process code
composition (no docker).
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools.compose_agent as ca  # noqa: E402
from stages.experiment_investigation import run_investigation  # noqa: E402

_VALID_DATA = ({"recipe": {"kind": "composition", "steps": [], "combine": {}},
                "predicted_value": 6.0, "reasoning": "ok", "stop": False}, {})


def _code_probe():
    return {
        "recipe": {
            "kind": "composition",
            "steps": [{"step_id": "a", "kind": "code",
                       "code": "metrics['a'] = 2.0", "quantity": "a"}],
            "combine": {"kind": "code", "code": "metrics['out'] = inputs['a'] * 3",
                        "quantity": "out", "inputs": ["a"]},
        },
        "predicted_value": 6.0,
        "reasoning": "probe",
    }


class TestComposeTransportRetry(unittest.TestCase):
    def test_transient_glitch_is_retried_not_fatal(self):
        # fail twice, then succeed — the proposal comes back, no abort
        with patch.object(ca, "call_stage_model",
                          side_effect=[RuntimeError("glitch"),
                                       RuntimeError("glitch"), _VALID_DATA]) as m:
            action = ca.propose_composition_probe({"measurements": []})
        self.assertEqual(m.call_count, 3)
        self.assertFalse(action["stop"])
        self.assertNotIn("aborted", action)
        self.assertIsNotNone(action["recipe"])

    def test_exhausted_retries_abort_honestly(self):
        with patch.object(ca, "call_stage_model",
                          side_effect=RuntimeError("Claude Code error")) as m:
            action = ca.propose_composition_probe({"measurements": []})
        self.assertEqual(m.call_count, ca.COMPOSE_MAX_TRANSPORT_ATTEMPTS)
        self.assertTrue(action["stop"])
        self.assertTrue(action["aborted"])
        self.assertIn(f"after {ca.COMPOSE_MAX_TRANSPORT_ATTEMPTS} attempts",
                      action["stop_reason"])


class _Strategy:
    def __init__(self, final_stop):
        self._final = final_stop
        self.n = 0

    def __call__(self, state):
        self.n += 1
        return _code_probe() if self.n == 1 else self._final


class TestAbortedRunIsNotPublishable(unittest.TestCase):
    def test_error_abort_sinks_publishability_but_keeps_the_finding(self):
        aborted_stop = {"stop": True, "aborted": True,
                        "stop_reason": "compose agent unavailable after 3 attempts: X"}
        summary = run_investigation(_Strategy(aborted_stop), max_iters=5)
        self.assertEqual(summary["verified"], 1)   # the probe reproduced
        self.assertEqual(summary["total"], 1)
        self.assertTrue(summary["aborted"])
        self.assertFalse(summary["publishable"])   # ...but the run does not stand

    def test_judged_stop_still_publishable(self):
        judged_stop = {"stop": True, "stop_reason": "the question is answered"}
        summary = run_investigation(_Strategy(judged_stop), max_iters=5)
        self.assertEqual(summary["verified"], 1)
        self.assertFalse(summary["aborted"])
        self.assertTrue(summary["publishable"])


if __name__ == "__main__":
    unittest.main()
