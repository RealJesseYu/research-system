"""test_free_director_fan.py — A1 (2026-07-29): parallel fan-out wired into the
FREE director.

run_study_fan (pi_agent/study.py) was finished, concurrency-safe code whose only
caller was the enum loop nothing uses; the free director could not reach it —
so every move of a long study was strictly sequential (~1 hour each). This
proves, entirely offline:

  - the validator accepts a well-formed run_fan and rejects malformed ones;
  - an N-wide fan SPENDS N MOVES (budget conservation, a hard guarantee);
  - each member gets an EQUAL SHARE of the token allowance, not the whole
    remainder N times over;
  - members are recorded as ordinary "single" arc entries (nothing downstream
    learns a new shape) with distinct run ids;
  - a fan wider than the remaining pool is clamped, never over-spent;
  - a member that raises is a recorded result, never a fan (or arc) crash;
  - resume accounting counts a fan failure row at its spent width.

Run directly: venv/bin/python3 tests/test_free_director_fan.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from model_call import MOVE_ALLOWANCE_ENV  # noqa: E402
from pi_agent import free_decider  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from pi_agent.free_director import (_fan_member_allowance,  # noqa: E402
                                    _moves_consumed, free_investigate)


class TestFanValidator(unittest.TestCase):
    def _v(self):
        return free_decider.make_action_validator("study-1", 1, ("rdkit",))

    def _fan(self, **over):
        base = {
            "ack": "study-1", "reading": "r", "reasoning": "independent corners",
            "action": "run_fan", "domain": None,
            "fan_domains": ["corner A?", "corner B?", "corner C?"],
            "instrument": None, "campaign": False, "budget_moves": None,
            "detail": None, "stop_reason": None,
        }
        base.update(over)
        return base

    def test_a_well_formed_fan_passes(self):
        self.assertEqual(self._v()(self._fan()), [])

    def test_fan_requires_a_non_empty_list(self):
        self.assertTrue(self._v()(self._fan(fan_domains=None)))
        self.assertTrue(self._v()(self._fan(fan_domains=[])))
        self.assertTrue(self._v()(self._fan(fan_domains="one string")))

    def test_every_entry_must_be_a_real_question(self):
        self.assertTrue(self._v()(self._fan(fan_domains=["ok?", "  "])))
        self.assertTrue(self._v()(self._fan(fan_domains=["ok?", 7])))

    def test_width_is_bounded(self):
        too_many = [f"q{i}?" for i in range(free_decider.MAX_FAN_WIDTH + 1)]
        self.assertTrue(self._v()(self._fan(fan_domains=too_many)))
        at_cap = [f"q{i}?" for i in range(free_decider.MAX_FAN_WIDTH)]
        self.assertEqual(self._v()(self._fan(fan_domains=at_cap)), [])

    def test_fan_domains_only_on_run_fan(self):
        errs = self._v()(self._fan(action="run_experiment", domain="q?",
                                   fan_domains=["a?"]))
        self.assertTrue(errs)

    def test_run_fan_is_in_the_vocabulary(self):
        self.assertIn("run_fan", free_decider.ACTION_VALUES)
        self.assertIn("fan_domains", free_decider._ENVELOPE_FIELDS)


class TestFanMemberAllowance(unittest.TestCase):
    def test_equal_split(self):
        self.assertEqual(_fan_member_allowance(90, 3), 30)

    def test_none_stays_none(self):
        self.assertIsNone(_fan_member_allowance(None, 3))

    def test_zero_share_becomes_none_not_zero(self):
        # an allowance of 0 would mean "refuse every call"; None means untracked.
        self.assertIsNone(_fan_member_allowance(2, 3))


class TestFanInTheLoop(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scripted(self, script):
        calls = {"n": 0}

        def decide(study, arc, budget):
            d = script[min(calls["n"], len(script) - 1)]
            calls["n"] += 1
            return d
        return decide

    def _act(self, action, **over):
        base = {"ack": "s", "reading": "r", "reasoning": "because", "action": action,
                "domain": None, "fan_domains": None, "instrument": None,
                "campaign": False, "budget_moves": None, "detail": None,
                "stop_reason": None}
        base.update(over)
        return base

    def _fake_invoke(self, seen_moves=None):
        """A per-move invoke seam for the REAL run_study_fan — the branch under
        test is the production fan code, only the subprocess is faked."""
        def invoke(move, runs_root=None):
            if seen_moves is not None:
                seen_moves.append(move)
            if "boom" in (move.domain or ""):
                raise RuntimeError("member exploded")
            return MoveResult("single", move.run_id, True, "completed",
                              {"publishable": True})
        return invoke

    def _real_fan(self, seen_moves=None):
        def run_fan(study, moves, findings=None, runs_root=None):
            return S.run_study_fan(study, moves, findings=findings,
                                   invoke=self._fake_invoke(seen_moves),
                                   runs_root=runs_root)
        return run_fan

    def test_a_fan_of_three_spends_three_moves_and_records_three_entries(self):
        seen = []
        script = [
            self._act("run_fan", fan_domains=["qa?", "qb?", "qc?"]),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(10), studies_root=self.root,
            decide_action=self._scripted(script), run_fan=self._real_fan(seen),
            study_id="s",
        )
        self.assertEqual(report["moves_run"], 3)          # members are "single" rows
        self.assertEqual(report["budget_final"]["remaining"], 7)  # 10 - 3, not 10 - 1
        run_ids = [e["run_id"] for e in report["arc"]]
        self.assertEqual(run_ids, ["s-m1", "s-m2", "s-m3"])  # distinct, ordered
        # each member's brief carries ITS question (plus the study context).
        # `seen` is appended from worker THREADS, so order it by run_id first.
        for move, q in zip(sorted(seen, key=lambda m: m.run_id),
                           ["qa?", "qb?", "qc?"]):
            self.assertTrue(move.domain.startswith(q))
            self.assertIn("THE OVERALL GOAL: goal", move.domain)

    def test_token_allowance_is_divided_equally_among_members(self):
        seen = []
        script = [
            self._act("run_fan", fan_domains=["qa?", "qb?", "qc?"]),
            self._act("stop", stop_reason="done"),
        ]
        free_investigate(
            "goal", budget=Budget(10), token_budget=90_000_000,
            studies_root=self.root, decide_action=self._scripted(script),
            run_fan=self._real_fan(seen), study_id="s",
        )
        for move in seen:
            self.assertEqual(move.extra_env[MOVE_ALLOWANCE_ENV], str(30_000_000))
            self.assertIn("~30,000,000 tokens", move.domain)

    def test_a_fan_wider_than_the_pool_is_clamped_never_overspent(self):
        seen = []
        script = [self._act("run_fan", fan_domains=["qa?", "qb?", "qc?"])]
        report = free_investigate(
            "goal", budget=Budget(2), studies_root=self.root,
            decide_action=self._scripted(script), run_fan=self._real_fan(seen),
            study_id="s",
        )
        self.assertEqual(report["moves_run"], 2)
        self.assertEqual(report["budget_final"]["remaining"], 0)
        self.assertEqual(report["termination"]["reason"], "budget_spent")
        self.assertEqual(
            sorted(m.domain.split("\n")[0] for m in seen),
            ["qa?", "qb?"])  # the first two questions (seen order is threaded)

    def test_a_raising_member_is_a_recorded_result_not_a_crash(self):
        script = [
            self._act("run_fan", fan_domains=["qa?", "boom q?", "qc?"]),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(10), studies_root=self.root,
            decide_action=self._scripted(script), run_fan=self._real_fan(),
            study_id="s",
        )
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")
        outcomes = [e["outcome"] for e in report["arc"]]
        self.assertEqual(len(outcomes), 3)
        self.assertEqual(sum(1 for o in outcomes if "dispatch_error" in o), 1)
        self.assertEqual(sum(1 for o in outcomes if o == "completed"), 2)

    def test_a_fan_with_no_usable_questions_is_an_honest_refusal(self):
        # the validator prevents this from a real model reply; the loop is still
        # defensive — a blank fan spends nothing and is recorded.
        script = [
            self._act("run_fan", fan_domains=["   "]),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(5), studies_root=self.root,
            decide_action=self._scripted(script), run_fan=self._real_fan(),
            study_id="s",
        )
        self.assertEqual(report["budget_final"]["remaining"], 5)
        row = [e for e in report["arc"] if e["move_type"] == "run_fan"][0]
        self.assertEqual(row["outcome"], "insufficient_budget")

    def test_a_fan_seam_failure_row_carries_its_width(self):
        # run_study_fan itself raising (not a member) is caught by _survive and
        # the recorded row carries fan_width for resume accounting.
        def broken_fan(study, moves, findings=None, runs_root=None):
            raise OSError("disk gone")
        script = [
            self._act("run_fan", fan_domains=["qa?", "qb?", "qc?"]),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(10), studies_root=self.root,
            decide_action=self._scripted(script), run_fan=broken_fan,
            study_id="s",
        )
        self.assertEqual(report["budget_final"]["remaining"], 7)  # spent pre-dispatch
        row = [e for e in report["arc"] if e["move_type"] == "run_fan"][0]
        self.assertEqual(row["outcome"], "run_fan_failed")
        self.assertEqual(row["tool_output"]["fan_width"], 3)


class TestFanResumeAccounting(unittest.TestCase):
    def test_a_fan_failure_row_counts_its_spent_width(self):
        arc = [{"move_type": "run_fan", "outcome": "run_fan_failed",
                "tool_output": {"fan_width": 3}}]
        self.assertEqual(_moves_consumed(arc, Path(".")), 3)

    def test_a_widthless_fan_row_counts_one_conservatively(self):
        arc = [{"move_type": "run_fan", "outcome": "run_fan_failed",
                "tool_output": {}}]
        self.assertEqual(_moves_consumed(arc, Path(".")), 1)

    def test_a_fan_refusal_row_counts_zero(self):
        arc = [{"move_type": "run_fan", "outcome": "insufficient_budget",
                "tool_output": {}}]
        self.assertEqual(_moves_consumed(arc, Path(".")), 0)

    def test_fan_members_count_as_ordinary_singles(self):
        arc = [{"move_type": "single", "outcome": "completed"}] * 3
        self.assertEqual(_moves_consumed(arc, Path(".")), 3)


if __name__ == "__main__":
    unittest.main()
