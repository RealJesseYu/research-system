"""test_wind_up_turn_counter.py — a turn is a turn (2026-07-30, owner-ruled).

THE BUG. _MoveBudgetTracker.note_assistant_message counted one "turn" per SDK
AssistantMessage, and the SDK yields ONE PER CONTENT BLOCK — every block of a
single API message carrying that message's identical usage. Measured on
study-20260730T034915Z move 16: 199 assistant events for 97 unique message ids
(blocks per message {2:47, 1:24, 3:23, 4:3}). The turn wind-up tripped at "turn
197 of 200" after 97 real turns, and tokens_seen reached 34.7M against a metered
17.1M. Nine of that study's twelve completed moves were cut off this way; m14 and
m15 tripped at "turn 230 of 200" and "221 of 200", which is the proof the counter
was not counting turns. See docs/finding_m16_stopping_mechanism.md.

THE SECOND BUG, and the one that cost a whole session: _WIND_UP_MESSAGE hardcoded
"TOKEN ALLOWANCE EXHAUSTED" and then interpolated a reason that might say "turn
197 of 200". m16 reported "the token budget ran out" having spent 17.1M of 52.9M —
it was quoting the harness faithfully.

WHAT MUST NOT CHANGE: the TOKEN condition. Only the turn condition was wrong.

Run directly: venv/bin/python3 tests/test_wind_up_turn_counter.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call  # noqa: E402
from model_call import (WIND_UP_TOKEN_HEADLINE, WIND_UP_TURN_HEADLINE,  # noqa: E402
                        _MoveBudgetTracker)

USAGE = {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 100}


class TestATurnIsATurn(unittest.TestCase):
    def test_one_api_message_over_four_blocks_counts_once(self):
        """The exact shape from m16's transcript: one id, four events."""
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        for _block in range(4):
            t.note_assistant_message(USAGE, "msg_011CdXzpeyFqmN3TaMqgsjZ1")
        self.assertEqual(t.turns_seen, 1)

    def test_usage_is_counted_once_per_message_not_once_per_block(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        for _block in range(4):
            t.note_assistant_message(USAGE, "msg_a")
        self.assertEqual(t.tokens_seen, sum(USAGE.values()))

    def test_distinct_messages_still_each_count(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        for i in range(10):
            t.note_assistant_message(USAGE, f"msg_{i}")
        self.assertEqual(t.turns_seen, 10)
        self.assertEqual(t.tokens_seen, 10 * sum(USAGE.values()))

    def test_the_m16_profile_no_longer_trips_early(self):
        """97 real messages spread over 199 block events, granted 200 turns: the
        old counter tripped at 197 and denied the Write that would have produced
        the study's producer files."""
        blocks_per_message = [2] * 47 + [1] * 24 + [3] * 23 + [4] * 3
        self.assertEqual(len(blocks_per_message), 97)
        self.assertEqual(sum(blocks_per_message), 199)
        t = _MoveBudgetTracker(remaining_tokens=53_000_000, granted_turns=200)
        for i, blocks in enumerate(blocks_per_message):
            for _b in range(blocks):
                t.note_assistant_message(USAGE, f"msg_{i}")
        self.assertEqual(t.turns_seen, 97)
        self.assertIsNone(t.wind_up())          # would have been a turn trip

    def test_no_message_id_keeps_the_old_counting_honestly(self):
        """An older SDK or a positional test fake cannot be deduped; guessing
        would be worse than the documented fallback."""
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        t.note_assistant_message(USAGE)
        t.note_assistant_message(USAGE)
        self.assertEqual(t.turns_seen, 2)


class TestTheTwoConditionsAreDistinguishable(unittest.TestCase):
    """THE REGRESSION THAT MATTERS: the old message could not tell a turn trip
    from a token trip, and neither could anyone reading it."""

    def _turn_tripped(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=10)
        for i in range(6):                      # soft_stop = 10 - 4 = 6
            t.note_assistant_message(USAGE, f"msg_{i}")
        return t

    def _token_tripped(self):
        t = _MoveBudgetTracker(remaining_tokens=100, granted_turns=200)
        t.note_assistant_message({"input_tokens": 500}, "msg_a")
        return t

    def test_a_turn_trip_names_turns(self):
        headline, detail = self._turn_tripped().wind_up()
        self.assertEqual(headline, WIND_UP_TURN_HEADLINE)
        self.assertIn("TURN", headline)
        self.assertIn("turn 6 of 10", detail)

    def test_a_turn_trip_says_the_token_budget_is_NOT_gone(self):
        """m16's exact failure: it was told its budget ran out and said so."""
        _headline, detail = self._turn_tripped().wind_up()
        self.assertIn("NOT a spend limit", detail)
        self.assertIn("is NOT exhausted", detail)
        self.assertIn("do not report that you ran out of budget", detail)

    def test_a_token_trip_names_tokens(self):
        headline, detail = self._token_tripped().wind_up()
        self.assertEqual(headline, WIND_UP_TOKEN_HEADLINE)
        self.assertIn("TOKEN", headline)
        self.assertIn("face-value", detail)

    def test_the_two_headlines_differ(self):
        self.assertNotEqual(WIND_UP_TURN_HEADLINE, WIND_UP_TOKEN_HEADLINE)

    def test_the_message_the_agent_reads_carries_the_right_headline(self):
        for tracker, expected in ((self._turn_tripped(), WIND_UP_TURN_HEADLINE),
                                  (self._token_tripped(), WIND_UP_TOKEN_HEADLINE)):
            headline, reason = tracker.wind_up()
            msg = model_call._WIND_UP_MESSAGE.format(headline=headline,
                                                     reason=reason)
            self.assertTrue(msg.startswith(expected), msg[:80])
        # and the turn message must not open by claiming a spent allowance
        headline, reason = self._turn_tripped().wind_up()
        turn_msg = model_call._WIND_UP_MESSAGE.format(headline=headline,
                                                      reason=reason)
        self.assertFalse(turn_msg.startswith(WIND_UP_TOKEN_HEADLINE))


class TestTheTokenConditionIsUntouched(unittest.TestCase):
    """Only the turn condition was wrong. Pinned per the brief."""

    def test_trips_at_exactly_the_allowance_not_before(self):
        t = _MoveBudgetTracker(remaining_tokens=100, granted_turns=200)
        t.note_assistant_message({"input_tokens": 99}, "msg_a")
        self.assertIsNone(t.wind_up())
        t.note_assistant_message({"input_tokens": 1}, "msg_b")
        self.assertEqual(t.wind_up()[0], WIND_UP_TOKEN_HEADLINE)

    def test_it_still_sums_every_integer_usage_field_at_face_value(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        t.note_assistant_message(
            {"input_tokens": 1, "output_tokens": 2,
             "cache_creation_input_tokens": 4, "cache_read_input_tokens": 8,
             "not_a_number": "x", "a_bool": True}, "msg_a")
        self.assertEqual(t.tokens_seen, 15)   # bools and strings excluded

    def test_tokens_win_over_turns_when_both_would_trip(self):
        """Order is unchanged: the token condition is checked first."""
        t = _MoveBudgetTracker(remaining_tokens=1, granted_turns=2)
        t.note_assistant_message({"input_tokens": 99}, "msg_a")
        self.assertEqual(t.wind_up()[0], WIND_UP_TOKEN_HEADLINE)

    def test_derive_granted_turns_is_unchanged(self):
        from model_call import (MIN_GRANTED_TURNS, _derive_granted_turns)
        self.assertEqual(_derive_granted_turns(53_000_000, 200), 200)
        self.assertEqual(_derive_granted_turns(1_000_000, 200), 50)
        self.assertEqual(_derive_granted_turns(0, 200), MIN_GRANTED_TURNS)


class TestItLeavesADurableRecord(unittest.TestCase):
    def test_the_wind_up_writes_to_the_run_log_and_the_meter(self):
        import tempfile
        import os
        import cost_meter

        cost_meter.reset()
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                (Path(d) / "runs" / "r1").mkdir(parents=True)
                model_call._CURRENT_RUN_ID = "r1"
                t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=10)
                headline, reason = WIND_UP_TURN_HEADLINE, "turn 6 of 10"
                model_call._announce_wind_up(t, "free_experimenter",
                                             headline, reason)
                log = (Path(d) / "runs" / "r1" / "log.txt").read_text()
            finally:
                model_call._CURRENT_RUN_ID = None
                os.chdir(cwd)
        self.assertIn("WIND_UP", log)
        self.assertIn(WIND_UP_TURN_HEADLINE, log)
        self.assertIn("turn 6 of 10", log)
        self.assertEqual(cost_meter.read()["signals"].get("wind_up_turn_budget"), 1)
        cost_meter.reset()

    def test_it_announces_once_per_call(self):
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=10)
        model_call._announce_wind_up(t, "s", WIND_UP_TURN_HEADLINE, "r")
        self.assertTrue(t.announced)
        model_call._announce_wind_up(t, "s", WIND_UP_TURN_HEADLINE, "r")
        self.assertTrue(t.announced)   # second call is a no-op, not a crash

    def test_it_never_raises_without_a_run_id(self):
        model_call._CURRENT_RUN_ID = None
        t = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=10)
        model_call._announce_wind_up(t, "s", WIND_UP_TURN_HEADLINE, "r")


class TestTheRunRecordSaysCutOff(unittest.TestCase):
    def test_a_wind_up_signal_becomes_extras_cut_off(self):
        import cost_meter
        import supervisor
        from baton import Baton

        cost_meter.reset()
        cost_meter.record_signal("wind_up_turn_budget")
        captured = {}
        real = supervisor.journal_append
        supervisor.journal_append = lambda e: captured.update(e)
        try:
            supervisor.record_run_outcome(
                Baton(run_id="r", created_at="t", mode="auto", payload={}),
                "completed free investigation")
        finally:
            supervisor.journal_append = real
            cost_meter.reset()
        self.assertEqual(captured["extras"]["cut_off"],
                         {"wind_up_turn_budget": 1})
        self.assertIn("cut_off=wind_up_turn_budget", captured["text"])

    def test_no_wind_up_leaves_the_record_unchanged(self):
        import cost_meter
        import supervisor
        from baton import Baton

        cost_meter.reset()
        captured = {}
        real = supervisor.journal_append
        supervisor.journal_append = lambda e: captured.update(e)
        try:
            supervisor.record_run_outcome(
                Baton(run_id="r", created_at="t", mode="auto", payload={}),
                "completed free investigation")
        finally:
            supervisor.journal_append = real
        self.assertNotIn("cut_off", captured["extras"])
        self.assertNotIn("cut_off", captured["text"])

    def test_it_reaches_the_director_through_the_arc(self):
        import tempfile
        from pi_agent.dispatch import read_run_result

        with tempfile.TemporaryDirectory() as d:
            r = read_run_result(Path(d), "run-1", 0, {"extras": {
                "how_far": "completed free investigation",
                "cut_off": {"wind_up_turn_budget": 1}}})
        self.assertEqual(r.cut_off, {"wind_up_turn_budget": 1})
        self.assertEqual(r.as_dict()["cut_off"], {"wind_up_turn_budget": 1})


if __name__ == "__main__":
    unittest.main()
