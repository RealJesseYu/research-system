"""test_prediction_column.py — A3 (2026-07-29): the director may record a
prediction, and later sees it against the outcome.

h13's insight moved to the ADDITIVE side of the line: h13 failed because it
used predictions to decide what to FORGET; here the prediction decides
NOTHING. It is an optional column recorded beside the outcome so subsequent
turns show expectation vs result — a calibration signal on the director's own
judgement, which is self-correction, the thing the false-record study said
matters. Nothing gates on it, nothing scores it, and a wrong prediction
changes nothing about what the director may do next.

Offline; no model calls.

Run directly: venv/bin/python3 tests/test_prediction_column.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent import free_decider  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import Move, MoveResult, MoveType  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402


class TestValidator(unittest.TestCase):
    def _v(self):
        return free_decider.make_action_validator("study-1", 1, ())

    def _act(self, **over):
        base = {"ack": "study-1", "reading": "r", "reasoning": "b",
                "action": "run_experiment", "domain": "q?", "prediction": None}
        base.update(over)
        return base

    def test_prediction_is_optional_on_any_action(self):
        self.assertEqual(self._v()(self._act()), [])
        self.assertEqual(self._v()(self._act(prediction="yield rises with T")), [])
        self.assertEqual(
            self._v()(self._act(action="stop", domain=None, stop_reason="done",
                                prediction="nothing more to find")), [])

    def test_a_blank_or_non_string_prediction_is_rejected(self):
        self.assertTrue(self._v()(self._act(prediction="   ")))
        self.assertTrue(self._v()(self._act(prediction=7)))

    def test_prediction_is_in_the_envelope(self):
        self.assertIn("prediction", free_decider._ENVELOPE_FIELDS)


class ArcTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("g", study_id="s", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _mr(self, run_id="s-m1"):
        return MoveResult("single", run_id, True, "completed", {"publishable": True})


class TestRecordMove(ArcTestCase):
    def test_prediction_is_written_beside_finding(self):
        entry = S.record_move(self.study, self._mr(), finding="went well",
                              prediction="expect X ~ 3")
        self.assertEqual(entry["prediction"], "expect X ~ 3")
        self.assertEqual(entry["finding"], "went well")

    def test_without_one_the_arc_line_is_byte_identical_to_before(self):
        S.record_move(self.study, self._mr(), finding="f")
        line = json.loads(self.study.arc_path.read_text().strip())
        self.assertNotIn("prediction", line)

    def test_study_findings_surfaces_it_only_when_present(self):
        S.record_move(self.study, self._mr("s-m1"), prediction="p1")
        S.record_move(self.study, self._mr("s-m2"))
        e1, e2 = S.study_findings(self.study)
        self.assertEqual(e1["prediction"], "p1")
        self.assertNotIn("prediction", e2)
        # the outcome sits beside it in the same entry — the comparison the
        # director reads is in one place, no cross-referencing.
        self.assertEqual(e1["outcome"], "completed")


class TestTheLoopRecordsIt(ArcTestCase):
    def _decide(self, script):
        n = {"i": 0}

        def decide(study, arc, budget):
            d = script[min(n["i"], len(script) - 1)]
            n["i"] += 1
            return d
        return decide

    def _act(self, action, **over):
        base = {"ack": "s2", "reading": "r", "reasoning": "b", "action": action,
                "domain": None, "fan_domains": None, "prediction": None,
                "stop_reason": None}
        base.update(over)
        return base

    def test_run_experiment_prediction_reaches_the_arc(self):
        def invoke(move, runs_root=None):
            return MoveResult("single", move.run_id, True, "completed",
                              {"publishable": True})

        def run_move(study, move, finding=None, runs_root=None, prediction=None):
            return S.run_study_move(study, move, finding=finding,
                                    prediction=prediction, invoke=invoke,
                                    runs_root=runs_root)
        script = [
            self._act("run_experiment", domain="q?", prediction="X should double"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=self._decide(script), run_move=run_move, study_id="s2",
        )
        entry = report["arc"][0]
        self.assertEqual(entry["prediction"], "X should double")
        self.assertEqual(entry["outcome"], "completed")

    def test_an_old_signature_fake_still_works_prediction_dropped_not_crashed(self):
        # trap 4: widening an injected callable must not break three-arg fakes.
        def old_run_move(study, move, finding=None, runs_root=None):
            return S.record_move(
                study, MoveResult("single", move.run_id or "x", True,
                                  "completed", {}), finding=finding)
        script = [
            self._act("run_experiment", domain="q?", prediction="ignored safely"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=self._decide(script), run_move=old_run_move,
            study_id="s2",
        )
        self.assertEqual(report["moves_run"], 1)
        self.assertNotIn("prediction", report["arc"][0])

    def test_fan_members_each_carry_the_prediction(self):
        def invoke(move, runs_root=None):
            return MoveResult("single", move.run_id, True, "completed", {})

        def run_fan(study, moves, findings=None, predictions=None, runs_root=None):
            return S.run_study_fan(study, moves, findings=findings,
                                   predictions=predictions, invoke=invoke,
                                   runs_root=runs_root)
        script = [
            self._act("run_fan", fan_domains=["a?", "b?"],
                      prediction="both corners hold"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=self._decide(script), run_fan=run_fan, study_id="s2",
        )
        self.assertEqual([e["prediction"] for e in report["arc"]],
                         ["both corners hold", "both corners hold"])

    def test_a_capability_row_carries_the_prediction_too(self):
        def exec_cap(name, action, study, budget, seq):
            return {"succeeded": True, "outcome": "ideation_done",
                    "hypotheses": []}
        script = [
            self._act("call_ideation", detail="ideas?",
                      prediction="mostly known methods"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=self._decide(script), execute_capability=exec_cap,
            study_id="s2",
        )
        row = [e for e in report["arc"] if e["move_type"] == "call_ideation"][0]
        self.assertEqual(row["prediction"], "mostly known methods")


if __name__ == "__main__":
    unittest.main()
