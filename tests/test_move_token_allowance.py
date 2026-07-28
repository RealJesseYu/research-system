"""test_move_token_allowance.py — item A (2026-07-28): the token ceiling binds
INSIDE a move.

study-20260728T152819Z was given --token-budget 5000000 and spent 7,900,340 —
free_director checked the ceiling only BETWEEN moves, and one free-experimenter
move is an agentic loop of up to 200 turns. These tests prove, offline:

  - the director hands each dispatched move its remaining budget as an
    allowance (env + brief), and never hands one when the budget is unset or
    the meter failed (unknown must not cage);
  - model_call derives a tooled call's max_turns from the remaining allowance
    (the structural bound), arms the in-stream tracker, and the can_use_tool
    wrapper denies tools with a wind-up message once the room is gone — an
    honest ceiling the agent finishes inside, not a guillotine;
  - a new attempt on a spent allowance raises TokenAllowanceExhausted BEFORE
    the SDK call (a re-ask under FULL is another whole agentic run);
  - the supervisor journals that as an honest halted_token_allowance
    run_record — a RECORDED result, not a crash — and the director's arc
    records the move and the study CONTINUES rather than dying.

Run directly: venv/bin/python3 tests/test_move_token_allowance.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cost_meter  # noqa: E402
import model_call  # noqa: E402
from model_call import (  # noqa: E402
    EST_TOKENS_PER_TURN,
    FULL,
    MIN_GRANTED_TURNS,
    MOVE_ALLOWANCE_ENV,
    SEALED,
    TokenAllowanceExhausted,
    WIND_UP_RESERVE_TURNS,
    _derive_granted_turns,
    _MoveBudgetTracker,
    _wrap_can_use_tool_with_allowance,
)


class _EnvIsolated(unittest.TestCase):
    """Tests that set the allowance env var and touch the shared meter."""

    def setUp(self):
        cost_meter.reset()
        self._saved = os.environ.pop(MOVE_ALLOWANCE_ENV, None)

    def tearDown(self):
        cost_meter.reset()
        if self._saved is None:
            os.environ.pop(MOVE_ALLOWANCE_ENV, None)
        else:
            os.environ[MOVE_ALLOWANCE_ENV] = self._saved


class TestDeriveGrantedTurns(unittest.TestCase):
    def test_a_large_allowance_keeps_the_profile_ceiling(self):
        self.assertEqual(_derive_granted_turns(200 * EST_TOKENS_PER_TURN + 1, 200), 200)

    def test_a_small_allowance_derives_a_smaller_ceiling(self):
        self.assertEqual(_derive_granted_turns(10 * EST_TOKENS_PER_TURN, 200), 10)

    def test_a_tiny_allowance_still_grants_the_floor(self):
        # an agent that cannot take a turn cannot even report honestly
        self.assertEqual(_derive_granted_turns(1, 200), MIN_GRANTED_TURNS)


class TestMoveBudgetTracker(unittest.TestCase):
    def test_no_reason_while_there_is_room(self):
        t = _MoveBudgetTracker(remaining_tokens=100_000, granted_turns=50)
        t.note_assistant_message({"input_tokens": 10, "output_tokens": 5})
        self.assertIsNone(t.wind_up_reason())

    def test_measured_spend_crossing_the_allowance_trips_it(self):
        t = _MoveBudgetTracker(remaining_tokens=1000, granted_turns=50)
        t.note_assistant_message({"input_tokens": 600, "cache_read_input_tokens": 500})
        reason = t.wind_up_reason()
        self.assertIsNotNone(reason)
        self.assertIn("remaining allowance", reason)

    def test_the_wind_up_reserve_trips_before_the_hard_turn_ceiling(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=10)
        for _ in range(10 - WIND_UP_RESERVE_TURNS - 1):
            t.note_assistant_message(None)  # no usage data in the stream
        self.assertIsNone(t.wind_up_reason())
        t.note_assistant_message(None)
        self.assertIn("wind-up reserve", t.wind_up_reason())

    def test_non_int_and_bool_usage_values_are_ignored(self):
        t = _MoveBudgetTracker(remaining_tokens=1000, granted_turns=50)
        t.note_assistant_message({"input_tokens": "many", "flag": True, "ok": 3})
        self.assertEqual(t.tokens_seen, 3)


class TestCanUseToolWrapper(unittest.TestCase):
    def _inner_allowing(self, calls):
        from claude_agent_sdk import PermissionResultAllow

        async def inner(tool_name, tool_input, context):
            calls.append(tool_name)
            return PermissionResultAllow()
        return inner

    def test_delegates_while_there_is_room(self):
        from claude_agent_sdk import PermissionResultAllow
        calls = []
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        wrapped = _wrap_can_use_tool_with_allowance(
            self._inner_allowing(calls), t, "stage")
        result = asyncio.run(wrapped("Bash", {}, None))
        self.assertIsInstance(result, PermissionResultAllow)
        self.assertEqual(calls, ["Bash"])

    def test_denies_with_the_wind_up_message_once_tripped(self):
        from claude_agent_sdk import PermissionResultDeny
        calls = []
        t = _MoveBudgetTracker(remaining_tokens=100, granted_turns=200)
        t.note_assistant_message({"input_tokens": 100})  # allowance reached
        wrapped = _wrap_can_use_tool_with_allowance(
            self._inner_allowing(calls), t, "stage")
        result = asyncio.run(wrapped("Bash", {}, None))
        self.assertIsInstance(result, PermissionResultDeny)
        self.assertEqual(calls, [])  # the guard was never even consulted
        self.assertIn("TOKEN ALLOWANCE EXHAUSTED", result.message)
        self.assertIn("final answer", result.message)  # wind up, don't invent


class TestPreAttemptCheck(_EnvIsolated):
    def test_a_spent_allowance_refuses_the_attempt_before_the_sdk_call(self):
        os.environ[MOVE_ALLOWANCE_ENV] = "1000"
        cost_meter.record_call("model_call", {"input_tokens": 700,
                                              "cache_read_input_tokens": 400})
        transport_calls = []
        original = model_call._invoke_transport
        model_call._invoke_transport = (
            lambda *a, **k: transport_calls.append(a) or '{"x": 1}')
        try:
            with self.assertRaises(TokenAllowanceExhausted) as ctx:
                model_call.call_stage_model(
                    "unit_allowance_stage", "sys", {"q": "x"},
                    {"required": ["x"]}, model="m", capabilities=SEALED)
        finally:
            model_call._invoke_transport = original
        self.assertEqual(transport_calls, [])  # no agentic run was burned
        self.assertIn("move token allowance spent", str(ctx.exception))
        self.assertIn("1,100 of 1,000", str(ctx.exception))

    def test_no_env_var_changes_nothing(self):
        original = model_call._invoke_transport
        model_call._invoke_transport = lambda *a, **k: '{"x": 1}'
        try:
            data, _ = model_call.call_stage_model(
                "unit_allowance_stage", "sys", {"q": "x"},
                {"required": ["x"]}, model="m", capabilities=SEALED)
        finally:
            model_call._invoke_transport = original
        self.assertEqual(data, {"x": 1})

    def test_a_malformed_allowance_reads_as_none(self):
        os.environ[MOVE_ALLOWANCE_ENV] = "lots"
        self.assertIsNone(model_call._move_token_allowance())
        os.environ[MOVE_ALLOWANCE_ENV] = "-5"
        self.assertIsNone(model_call._move_token_allowance())


class TestMaxTurnsDerivation(_EnvIsolated):
    """The structural bound reaches the SDK options of a real tooled call."""

    def _run_ask_once(self):
        from claude_agent_sdk.types import (AssistantMessage, ResultMessage,
                                            TextBlock)
        captured = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield AssistantMessage(content=[TextBlock(text="done")], model="m")
            yield ResultMessage(subtype="success", duration_ms=1,
                                duration_api_ms=1, is_error=False, num_turns=1,
                                session_id="s", usage={"input_tokens": 1})

        original = model_call.query
        model_call.query = fake_query
        try:
            asyncio.run(model_call._ask_once("sys", "user", "m", FULL))
        finally:
            model_call.query = original
        return captured["options"]

    def test_allowance_derives_the_calls_max_turns(self):
        os.environ[MOVE_ALLOWANCE_ENV] = str(10 * EST_TOKENS_PER_TURN)
        options = self._run_ask_once()
        self.assertEqual(options.max_turns, 10)

    def test_without_an_allowance_the_profile_ceiling_stands(self):
        options = self._run_ask_once()
        self.assertEqual(options.max_turns, FULL.max_turns)


class TestSupervisorRecordsAnHonestHalt(_EnvIsolated):
    """The VERIFY case: a move that runs out of budget leaves a READABLE
    record — never a crash, never a silent truncation — and the study
    continues (nothing ends an arc except the director)."""

    def test_token_allowance_exhaustion_journals_halted_not_crashed(self):
        import supervisor
        from baton import Baton

        def raising_investigate(goal, run_id=None):
            raise TokenAllowanceExhausted(
                "move token allowance spent: 1,200,000 of 1,000,000")

        captured = {}
        original_append = supervisor.journal_append
        supervisor.journal_append = lambda entry: captured.update(entry)
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "r1"
            run_dir.mkdir()
            logger = supervisor.Logger(run_dir / "log.txt")
            baton = Baton(run_id="r1", created_at="t", mode="auto",
                          payload={"domain": "d"})
            try:
                # must NOT raise: an exhausted allowance is an honest stop
                supervisor.run_exact_route(
                    logger, baton, run_dir, "auto",
                    free_investigate=raising_investigate)
            finally:
                supervisor.journal_append = original_append
            log = (run_dir / "log.txt").read_text()
        self.assertTrue(captured["extras"]["how_far"]
                        .startswith("halted_token_allowance"))
        self.assertIn("1,200,000 of 1,000,000", captured["extras"]["how_far"])
        self.assertIn("TOKEN ALLOWANCE", log)
        self.assertNotIn("CRASH", log)


class TestDirectorHandsTheAllowanceDown(unittest.TestCase):
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
        base = {"ack": "s", "reading": "r", "reasoning": "because",
                "action": action, "domain": None, "instrument": None,
                "campaign": False, "budget_moves": None, "detail": None,
                "stop_reason": None}
        base.update(over)
        return base

    def test_the_move_carries_the_remaining_budget_as_its_allowance(self):
        import pi_agent.study as S
        from pi_agent.budget import Budget
        from pi_agent.dispatch import MoveResult
        from pi_agent.free_director import free_investigate

        seen_moves = []

        def run_move(study, move, finding=None, runs_root=None):
            seen_moves.append(move)
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or "m", True,
                           "completed",
                           {"publishable": True,
                            "cost": {"calls": 1, "tokens": 5_000_000}}),
                finding=finding)

        report = free_investigate(
            "g", budget=Budget(10), studies_root=self.root,
            token_budget=1_000_000,
            decide_action=self._scripted([self._act("run_experiment", domain="q")]),
            run_move=run_move, study_id="s")

        # the dispatched move carried the allowance in env AND in the brief
        move = seen_moves[0]
        self.assertEqual(move.extra_env, {MOVE_ALLOWANCE_ENV: "1000000"})
        self.assertIn("TOKEN ALLOWANCE FOR THIS MOVE: ~1,000,000", move.domain)
        # the over-budget move was RECORDED (a readable arc entry)...
        self.assertEqual(report["moves_run"], 1)
        self.assertEqual(report["arc"][0]["cost"]["tokens"], 5_000_000)
        # ...and the study terminated honestly on its ceiling, not by dying:
        # the report was written, the termination is the budget, not a crash.
        self.assertEqual(report["termination"]["reason"], "token_budget_spent")
        self.assertTrue((self.root / "s" / "report.json").is_file())

    def test_no_token_budget_means_no_allowance_no_cage(self):
        import pi_agent.study as S
        from pi_agent.budget import Budget
        from pi_agent.dispatch import MoveResult
        from pi_agent.free_director import free_investigate

        seen_moves = []

        def run_move(study, move, finding=None, runs_root=None):
            seen_moves.append(move)
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or "m", True,
                           "completed", {"publishable": True}),
                finding=finding)

        free_investigate(
            "g", budget=Budget(2), studies_root=self.root,
            decide_action=self._scripted([
                self._act("run_experiment", domain="q"),
                self._act("stop", stop_reason="done")]),
            run_move=run_move, study_id="s")
        self.assertIsNone(seen_moves[0].extra_env)
        self.assertNotIn("TOKEN ALLOWANCE", seen_moves[0].domain)

    def test_a_halted_allowance_move_is_read_and_the_study_continues(self):
        # The full shape of the story: move 1 comes back as an honest
        # halted_token_allowance outcome; the director reads it on the next
        # turn and still steers (here: stops deliberately). The arc holds both.
        import pi_agent.study as S
        from pi_agent.budget import Budget
        from pi_agent.dispatch import MoveResult
        from pi_agent.free_director import free_investigate

        def run_move(study, move, finding=None, runs_root=None):
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or "m", False,
                           "halted_token_allowance (move token allowance spent: "
                           "1,200,000 of 1,000,000)",
                           {"publishable": False,
                            "cost": {"calls": 2, "tokens": 1_200_000}}),
                finding=finding)

        arcs_seen = []

        def decide(study, arc, budget):
            arcs_seen.append(arc)
            if len(arcs_seen) == 1:
                return self._act("run_experiment", domain="q")
            return self._act("stop", stop_reason="budget-bound result recorded")

        report = free_investigate(
            "g", budget=Budget(10), studies_root=self.root,
            token_budget=5_000_000, decide_action=decide,
            run_move=run_move, study_id="s")

        # the next decision READ the halted move from the arc
        self.assertEqual(len(arcs_seen), 2)
        self.assertIn("halted_token_allowance", arcs_seen[1][0]["outcome"])
        # and the study ended by the DIRECTOR's judgment, not a death
        self.assertEqual(report["termination"]["reason"],
                         "director_judged_complete")


if __name__ == "__main__":
    unittest.main()
