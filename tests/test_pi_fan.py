"""test_pi_fan.py — the director's parallel fan-out (run_fan).

Call-free: the subprocess invoke and the decider are injected. Proves the fan
records every parallel run in order with distinct run-ids, survives a failed
run, the decider validates a run_fan envelope, and the loop dispatches a fan
capped to the move budget.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent.decider import make_decision_validator  # noqa: E402
from pi_agent.dispatch import Move, MoveType  # noqa: E402
from pi_agent.loop import investigate  # noqa: E402
from pi_agent.study import create_study, run_study_fan, study_arc  # noqa: E402


class _FakeResult:
    def __init__(self, run_id, findings=None):
        self.run_id = run_id
        self._findings = findings or []

    def as_dict(self):
        return {"move_type": "single", "run_id": self.run_id, "succeeded": True,
                "outcome": "completed",
                "raw": {"publishable": True, "findings": self._findings}}


class TestRunStudyFan(unittest.TestCase):
    def test_parallel_moves_recorded_in_order_with_distinct_run_ids(self):
        with tempfile.TemporaryDirectory() as d:
            study = create_study("goal", studies_root=Path(d))

            def fake_invoke(move, runs_root=None):
                return _FakeResult(move.run_id,
                                   [{"label": move.domain, "verified": True}])

            moves = [Move(type=MoveType.SINGLE, domain=q) for q in ("A", "B", "C")]
            run_study_fan(study, moves, invoke=fake_invoke)
            arc = study_arc(study)
        self.assertEqual(len(arc), 3)                          # all recorded
        self.assertEqual(len({e["run_id"] for e in arc}), 3)   # distinct ids
        self.assertEqual([e["seq"] for e in arc], [1, 2, 3])   # ordered
        self.assertEqual([e["results"][0]["label"] for e in arc], ["A", "B", "C"])

    def test_a_failed_run_is_recorded_not_a_fan_crash(self):
        with tempfile.TemporaryDirectory() as d:
            study = create_study("goal", studies_root=Path(d))

            def flaky_invoke(move, runs_root=None):
                if move.domain == "B":
                    raise RuntimeError("boom")
                return _FakeResult(move.run_id)

            moves = [Move(type=MoveType.SINGLE, domain=q) for q in ("A", "B", "C")]
            run_study_fan(study, moves, invoke=flaky_invoke)
            arc = study_arc(study)
        self.assertEqual(len(arc), 3)  # B recorded as a failed result, not lost
        b = [e for e in arc if e["run_id"].endswith("-m2")][0]
        self.assertFalse(b["succeeded"])
        self.assertIn("dispatch_error", b["outcome"])


class TestFanValidator(unittest.TestCase):
    def _v(self):
        return make_decision_validator("s1", arc_len=1)

    def _base(self, **kw):
        d = {"ack": "s1", "reading": "r", "decision": "run_fan", "rationale": "x",
             "next_domain": None, "fan_domains": ["Q1", "Q2"], "instrument": None,
             "stop_reason": None}
        d.update(kw)
        return d

    def test_valid_fan(self):
        self.assertEqual(self._v()(self._base()), [])

    def test_fan_needs_at_least_two_questions(self):
        errs = self._v()(self._base(fan_domains=["only one"]))
        self.assertTrue(any("fan_domains" in e for e in errs))

    def test_fan_rejects_a_named_instrument(self):
        errs = self._v()(self._base(instrument="rdkit"))
        self.assertTrue(any("instrument must be null" in e for e in errs))


class TestLoopFanBranch(unittest.TestCase):
    def test_run_fan_dispatches_a_parallel_fan_capped_to_budget(self):
        calls = {}
        decisions = iter([
            {"decision": "run_fan", "rationale": "explore",
             "fan_domains": ["Q1", "Q2", "Q3", "Q4", "Q5"]},
            {"decision": "stop", "stop_reason": "done"},
        ])

        def fake_decide(study, arc, budget):
            return next(decisions)

        def fake_run_fan(study, moves, findings=None, runs_root=None):
            calls["domains"] = [m.domain for m in moves]
            return []

        with tempfile.TemporaryDirectory() as d:
            investigate("goal", max_moves=3, studies_root=Path(d),
                        decide=fake_decide, run_move=lambda *a, **k: None,
                        run_fan=fake_run_fan)
        # 5 requested, capped to the remaining budget of 3
        self.assertEqual(calls["domains"], ["Q1", "Q2", "Q3"])


if __name__ == "__main__":
    unittest.main()
