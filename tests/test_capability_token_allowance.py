"""test_capability_token_allowance.py — in-process capabilities get a ceiling
too (2026-07-28, system-map defect 4.3).

run_experiment and call_integration hand their subprocess a token allowance;
the generic capability branch handed nothing, and capabilities.py never
mentioned one. call_ideation at depth "full" was measured at 176 model calls
and 17.5M tokens for a SINGLE move, bounded by nothing but the move pool.

These tests prove, entirely offline:

  - the env var is an absolute ceiling on the READING PROCESS's face-value
    spend, so an in-process call's ceiling is meter-now + room, not the bare
    remaining budget (which, mid-study, already reads as exhausted);
  - the director sets it around a capability call and takes it off again, so
    its own next decider call cannot inherit it;
  - spawn_sub_investigation is deliberately NOT capped this way — a child
    director is bounded by its transferred budget, and an inherited ceiling
    would gate the child's own decider call;
  - no token budget means no ceiling (unknown must widen, never cage);
  - the ceiling comes off even when the capability throws, and the throw is an
    arc row, not the end of the study.

Run directly: venv/bin/python3 tests/test_capability_token_allowance.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cost_meter  # noqa: E402
import model_call  # noqa: E402
from model_call import MOVE_ALLOWANCE_ENV, in_process_allowance_ceiling  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.free_director import (_capability_allowance,  # noqa: E402
                                    free_investigate)


class _EnvIsolated(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.pop(MOVE_ALLOWANCE_ENV, None)

    def tearDown(self):
        os.environ.pop(MOVE_ALLOWANCE_ENV, None)
        if self._saved is not None:
            os.environ[MOVE_ALLOWANCE_ENV] = self._saved


class TestCeilingArithmetic(_EnvIsolated):
    """The distinction a fresh subprocess hides."""

    def test_the_ceiling_is_the_meter_plus_the_room(self):
        original = model_call._face_value_spent
        model_call._face_value_spent = lambda: 4_000_000
        try:
            self.assertEqual(in_process_allowance_ceiling(1_000_000), 5_000_000)
        finally:
            model_call._face_value_spent = original

    def test_no_room_means_no_ceiling(self):
        for room in (0, -5, None):
            self.assertIsNone(in_process_allowance_ceiling(room))

    def test_a_nonsense_room_reads_as_no_ceiling(self):
        self.assertIsNone(in_process_allowance_ceiling("plenty"))

    def test_the_bare_remaining_budget_would_have_read_as_exhausted(self):
        # Why this function exists: mid-study the process meter is already past
        # the remaining budget, so handing the raw remainder over would refuse
        # the very first attempt (model_call._raise_if_allowance_exhausted
        # compares the env value against the whole-process meter).
        original = model_call._face_value_spent
        model_call._face_value_spent = lambda: 4_000_000
        try:
            remaining = 1_000_000
            self.assertGreater(model_call._face_value_spent(), remaining)
            self.assertGreater(in_process_allowance_ceiling(remaining),
                               model_call._face_value_spent())
        finally:
            model_call._face_value_spent = original


class TestTheContextManager(_EnvIsolated):
    def test_a_capped_capability_sees_the_ceiling_and_loses_it_after(self):
        original = model_call._face_value_spent
        model_call._face_value_spent = lambda: 1_000
        try:
            with _capability_allowance("call_ideation", token_budget=10_000,
                                       spent=6_000) as ceiling:
                self.assertEqual(ceiling, 1_000 + 4_000)
                self.assertEqual(os.environ[MOVE_ALLOWANCE_ENV], "5000")
        finally:
            model_call._face_value_spent = original
        self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)

    def test_spawn_is_deliberately_uncapped(self):
        with _capability_allowance("spawn_sub_investigation", 10_000, 1) as c:
            self.assertIsNone(c)
            self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)

    def test_no_token_budget_no_ceiling(self):
        with _capability_allowance("call_ideation", None, 5) as c:
            self.assertIsNone(c)
            self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)

    def test_an_unknown_spend_does_not_cage(self):
        # A failed meter reads as None. Unknown must widen.
        with _capability_allowance("call_ideation", 10_000, None) as c:
            self.assertIsNone(c)
            self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)

    def test_a_spent_budget_leaves_no_ceiling_rather_than_a_zero_one(self):
        with _capability_allowance("call_ideation", 10_000, 10_000) as c:
            self.assertIsNone(c)

    def test_the_ceiling_comes_off_even_when_the_body_throws(self):
        with self.assertRaises(RuntimeError):
            with _capability_allowance("call_ideation", 10_000, 1):
                self.assertIn(MOVE_ALLOWANCE_ENV, os.environ)
                raise RuntimeError("boom")
        self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)

    def test_a_pre_existing_value_is_restored_not_clobbered(self):
        os.environ[MOVE_ALLOWANCE_ENV] = "77"
        with _capability_allowance("call_ideation", 10_000, 1):
            self.assertNotEqual(os.environ[MOVE_ALLOWANCE_ENV], "77")
        self.assertEqual(os.environ[MOVE_ALLOWANCE_ENV], "77")


class TestTheLoopBindsIt(_EnvIsolated):
    """The whole point: the ceiling is on the environment while the capability
    runs, and gone by the director's next turn."""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()
        super().tearDown()

    def _act(self, action, **over):
        base = {"ack": None, "reading": "r", "reasoning": "why",
                "action": action, "domain": None, "instrument": None,
                "campaign": False, "budget_moves": None, "detail": None,
                "stop_reason": None}
        base.update(over)
        return base

    def _scripted(self, script):
        seen = {"i": 0}

        def decide(study, arc, budget_report):
            # THE DIRECTOR'S OWN CALL MUST NEVER INHERIT THE CEILING. This is
            # the assertion that the restore actually happens.
            observed_by_decider.append(os.environ.get(MOVE_ALLOWANCE_ENV))
            act = dict(script[min(seen["i"], len(script) - 1)])
            act["ack"] = study.study_id
            seen["i"] += 1
            return act
        observed_by_decider: list = []
        decide.observed = observed_by_decider
        return decide

    def test_the_capability_runs_under_a_ceiling_the_decider_never_sees(self):
        observed = {}

        def fake_exec(name, action, study, budget, seq):
            budget.spend(1)
            observed["env"] = os.environ.get(MOVE_ALLOWANCE_ENV)
            return {"succeeded": True, "outcome": "ideation_done",
                    "hypotheses": [{"id": "h1", "statement": "try X"}]}

        decide = self._scripted([
            self._act("call_ideation", domain="what to try?"),
            self._act("stop", stop_reason="done"),
        ])
        # A large token budget against a small meter, so a ceiling exists.
        spent_now = sum(
            v for v in cost_meter.read().get("tokens", {}).get("total", {}).values()
            if isinstance(v, int) and not isinstance(v, bool))
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            token_budget=spent_now + 10_000_000,
            decide_action=decide, run_move=lambda *a, **k: None,
            execute_capability=fake_exec, study_id="s",
        )
        self.assertIsNotNone(observed["env"])
        self.assertGreater(int(observed["env"]), 0)
        # Every decider turn saw no ceiling at all.
        self.assertEqual(decide.observed, [None, None])
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")

    def test_without_a_token_budget_the_capability_path_is_unchanged(self):
        observed = {}

        def fake_exec(name, action, study, budget, seq):
            budget.spend(1)
            observed["env"] = os.environ.get(MOVE_ALLOWANCE_ENV)
            return {"succeeded": True, "outcome": "ideation_done",
                    "hypotheses": []}

        decide = self._scripted([
            self._act("call_ideation", domain="q"),
            self._act("stop", stop_reason="done"),
        ])
        free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=decide, run_move=lambda *a, **k: None,
            execute_capability=fake_exec, study_id="s2",
        )
        self.assertIsNone(observed["env"])

    def test_a_capability_that_throws_leaves_no_ceiling_and_no_dead_study(self):
        def boom(name, action, study, budget, seq):
            raise model_call.TokenAllowanceExhausted("room gone")

        decide = self._scripted([
            self._act("call_ideation", domain="q"),
            self._act("stop", stop_reason="done"),
        ])
        spent_now = sum(
            v for v in cost_meter.read().get("tokens", {}).get("total", {}).values()
            if isinstance(v, int) and not isinstance(v, bool))
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            token_budget=spent_now + 10_000_000,
            decide_action=decide, run_move=lambda *a, **k: None,
            execute_capability=boom, study_id="s3",
        )
        self.assertNotIn(MOVE_ALLOWANCE_ENV, os.environ)
        rows = [e for e in report["arc"] if e["move_type"] == "call_ideation"]
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["succeeded"])
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")


if __name__ == "__main__":
    unittest.main()
