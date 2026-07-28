"""test_novelty_priority_dial.py — the ruled dial is reachable (2026-07-28).

Owner ruling 2026-07-27 made novelty's weight THE DIRECTOR'S DIAL: an
engineering goal is often best served by a well-established method and should
rank on quality alone; a science goal needs novelty or it is not research.

Everything below the decider was built for it — capabilities.py reads
action["novelty_priority"], _run_ideation_at_depth forwards it when the runner
accepts it, stage1_ideation.filter_survivors ranks by it. But the key was never
added to _ENVELOPE_FIELDS, and the validator rejects any key not on that list.
So a director that named the dial got a re-ask telling it the field was not
allowed, and a director that did not got "balanced" forever: the ruling was
unimplemented. These tests are what keeps it wired.

Run directly: venv/bin/python3 tests/test_novelty_priority_dial.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent import free_decider  # noqa: E402
from pi_agent.capabilities import run_ideation  # noqa: E402


class _FakeBudget:
    def __init__(self, moves=4):
        self.moves = moves

    def can_spend(self, n):
        return self.moves >= n

    def spend(self, n):
        self.moves -= n


class _FakeStudy:
    study_id = "s1"
    goal = "make it hold 5 kg"
    mode = "auto"


class TestTheEnvelopeAcceptsIt(unittest.TestCase):
    def _v(self, arc_len=1):
        return free_decider.make_action_validator("study-1", arc_len, ())

    def _act(self, **over):
        base = {"ack": "study-1", "reading": "r", "reasoning": "why",
                "action": "call_ideation", "domain": "what should I try?",
                "instrument": None, "campaign": False, "budget_moves": None,
                "detail": None, "depth": None, "pool_size": None,
                "novelty_priority": None, "stop_reason": None}
        base.update(over)
        return base

    def test_the_field_is_in_the_envelope(self):
        self.assertIn("novelty_priority", free_decider._ENVELOPE_FIELDS)

    def test_each_ruled_value_is_accepted_on_call_ideation(self):
        for value in ("required", "balanced", "irrelevant"):
            self.assertEqual(self._v()(self._act(novelty_priority=value)), [],
                             value)

    def test_absent_is_valid_and_means_balanced(self):
        self.assertEqual(self._v()(self._act(novelty_priority=None)), [])
        self.assertEqual(free_decider.DEFAULT_NOVELTY_PRIORITY, "balanced")

    def test_an_unknown_value_is_refused_by_name(self):
        errors = self._v()(self._act(novelty_priority="maximum"))
        self.assertTrue(any("novelty_priority must be one of" in e
                            for e in errors), errors)

    def test_it_is_call_ideations_dial_and_nobodys_else(self):
        errors = self._v()(self._act(action="run_experiment",
                                     domain="does X hold?",
                                     novelty_priority="required"))
        self.assertTrue(any("novelty_priority must be null" in e
                            for e in errors), errors)

    def test_the_prompt_describes_it_beside_depth_and_pool_size(self):
        prompt = free_decider.SYSTEM_PROMPT
        self.assertIn("novelty_priority", prompt)
        for value in ("required", "balanced", "irrelevant"):
            self.assertIn(f'"{value}"', prompt)

    def test_the_vocabulary_has_not_drifted_from_the_ideation_stage(self):
        # free_decider mirrors the values rather than importing the ideation
        # stack. A mirror that silently diverges is worse than an import.
        from stages import stage1_ideation
        self.assertEqual(tuple(free_decider.NOVELTY_PRIORITY_VALUES),
                         tuple(stage1_ideation.NOVELTY_PRIORITIES))
        self.assertEqual(free_decider.DEFAULT_NOVELTY_PRIORITY,
                         stage1_ideation.DEFAULT_NOVELTY_PRIORITY)


class TestItReachesTheRunner(unittest.TestCase):
    """The validator letting it through is only half — it must arrive."""

    def test_a_named_priority_is_forwarded_to_a_runner_that_takes_it(self):
        seen = {}

        def fake_run(domain, study, seq, depth=None, novelty_priority=None):
            seen["depth"] = depth
            seen["novelty"] = novelty_priority
            return [{"id": "h1", "statement": "try X"}]

        result = run_ideation(
            {"domain": "how?", "novelty_priority": "irrelevant"},
            _FakeStudy(), _FakeBudget(), 1, run=fake_run)
        self.assertEqual(seen["novelty"], "irrelevant")
        self.assertTrue(result["succeeded"])
        # It rides the arc entry too: "no novel survivors under 'irrelevant'"
        # and "…under 'required'" mean opposite things to a later reader.
        self.assertEqual(result["novelty_priority"], "irrelevant")

    def test_an_older_runner_signature_is_not_broken_by_the_dial(self):
        # Trap: widening an injected callable breaks three-arg fakes silently.
        def old_run(domain, study, seq):
            return [{"id": "h1", "statement": "try X"}]

        result = run_ideation(
            {"domain": "how?", "novelty_priority": "required"},
            _FakeStudy(), _FakeBudget(), 1, run=old_run)
        self.assertTrue(result["succeeded"])
        self.assertEqual(result["novelty_priority"], "required")

    def test_no_priority_named_forwards_nothing_and_keeps_the_default(self):
        seen = {}

        def fake_run(domain, study, seq, depth=None, **kwargs):
            seen["kwargs"] = kwargs
            return [{"id": "h1", "statement": "try X"}]

        result = run_ideation({"domain": "how?"}, _FakeStudy(), _FakeBudget(),
                              1, run=fake_run)
        self.assertNotIn("novelty_priority", seen["kwargs"])
        self.assertIsNone(result["novelty_priority"])


if __name__ == "__main__":
    unittest.main()
