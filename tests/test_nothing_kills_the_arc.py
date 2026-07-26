"""test_nothing_kills_the_arc.py — only the director may end an investigation.

OWNER RULING 2026-07-25: nothing may kill an arc except the director. Literally
nothing.

Before this, neither run_move nor execute_capability was guarded in the loop, so
any exception anywhere beneath them propagated out and killed the whole study —
losing every verified result already in the arc. Both live crashes took that
path: a screening stage raising on zero survivors, and a validator KeyError.

A tool that fails is a RESULT, not a fatality. It is recorded to the arc with its
error, and the director reads it next turn and decides — retry differently, route
around it, or stop. That judgment belongs to the director alone.

Run directly: venv/bin/python3 tests/test_nothing_kills_the_arc.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402


def _act(action, **over):
    base = {"ack": "s", "reading": "r", "reasoning": "because", "action": action,
            "domain": "q", "instrument": None, "campaign": False,
            "budget_moves": None, "detail": "d", "depth": None, "stop_reason": None}
    base.update(over)
    return base


class ArcSurvivalTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scripted(self, script):
        it = iter(script)

        def decide(study, arc, budget):
            return next(it)
        return decide

    def _run(self, script, **kw):
        return free_investigate(
            "g", budget=Budget(6), studies_root=self.root, study_id="s",
            decide_action=self._scripted(script), **kw)


class TestAToolThatRaisesIsRecordedNotFatal(ArcSurvivalTestCase):
    def test_an_exploding_experiment_does_not_end_the_arc(self):
        def boom(*a, **k):
            raise RuntimeError("the substrate exploded")

        report = self._run(
            [_act("run_experiment"), _act("stop", stop_reason="done")],
            run_move=boom)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")
        failed = [e for e in report["arc"] if e["outcome"] == "run_experiment_failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("the substrate exploded", failed[0]["tool_output"]["error"])

    def test_an_exploding_capability_does_not_end_the_arc(self):
        """THE LIVE CASE: ideation raised on zero survivors and killed the study."""
        def boom(*a, **k):
            raise RuntimeError("all 16 hypotheses were judged known")

        report = self._run(
            [_act("call_ideation"), _act("stop", stop_reason="done")],
            run_move=lambda *a, **k: None, execute_capability=boom)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")
        failed = [e for e in report["arc"] if e["outcome"] == "call_ideation_failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("judged known", failed[0]["tool_output"]["error"])

    def test_the_director_can_read_the_failure_and_carry_on(self):
        """The point of recording rather than dying: the next decision SEES it."""
        seen = {}

        def decide(study, arc, budget):
            if not arc:
                return _act("call_ideation")
            seen["arc"] = arc
            return _act("stop", stop_reason="read the failure")

        report = free_investigate(
            "g", budget=Budget(6), studies_root=self.root, study_id="s",
            decide_action=decide, run_move=lambda *a, **k: None,
            execute_capability=lambda *a, **k: (_ for _ in ()).throw(
                ValueError("KeyError-ish validator blowup")))
        self.assertEqual(len(seen["arc"]), 1)
        self.assertFalse(seen["arc"][0]["succeeded"])
        self.assertIn("blowup", seen["arc"][0]["tool_output"]["error"])
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")

    def test_verified_work_already_in_the_arc_is_not_lost(self):
        """The real cost of the old behaviour: a crash threw away everything
        earlier moves had already verified."""
        calls = {"n": 0}

        def run_move(study, move, finding=None, runs_root=None):
            calls["n"] += 1
            if calls["n"] == 1:
                from pi_agent.dispatch import MoveResult
                return S.record_move(
                    study,
                    MoveResult("single", "s-m1", True, "completed",
                               {"findings": [{"label": "good", "value": 1,
                                              "verified": True}]}),
                    finding=finding)
            raise RuntimeError("second move dies")

        report = self._run(
            [_act("run_experiment"), _act("run_experiment"),
             _act("stop", stop_reason="done")],
            run_move=run_move)
        kept = [f for e in report["arc"] for f in (e.get("results") or [])
                if f.get("verified")]
        self.assertEqual(len(kept), 1)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")


class TestOnlyTheDirectorEndsTheArc(ArcSurvivalTestCase):
    def test_the_recognised_terminations_are_directoral_or_ceilings(self):
        """stop is the director's own call; budget_spent and decision_cap are the
        hard ceilings it was given. Nothing else may terminate."""
        report = self._run([_act("stop", stop_reason="done")],
                           run_move=lambda *a, **k: None)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")
        self.assertEqual(report["termination"]["detail"], "done")


if __name__ == "__main__":
    unittest.main(verbosity=2)
