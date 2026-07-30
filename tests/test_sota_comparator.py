"""test_sota_comparator.py — the state-of-the-art comparator clause (2026-07-30).

MEASURED FAILURE. Arm C (study-20260730T034915Z, $143.97) was asked to "build a
model that beats it, and quantify the win", picked AASHTO-93, and built a
replacement that beats the 1993 chart. Pavement ME Design — the successor AASHTO
itself deployed, and the exact trap ideation had flagged three separate times in
its triage reasons — arrives in the study at MOVE 14, two moves AFTER the
replacement was already being fitted at move 12, and is used as an adoption
argument rather than as a benchmark. Nothing in the system ever asked what already
replaces the thing being replaced.

WHERE THE CLAUSE LIVES, and why it is the experimenter's SYSTEM_PROMPT rather than
the director's run_fan description. Re-derived from that study's decisions/:
run_fan fired twice (6 members at move 3, 2 at move 13) and run_experiment eight
times — and moves 9-12, where the incumbent was measured and the replacement was
fitted, were run_experiment, NOT fan members. A clause on the fan brief would have
missed exactly the moves that needed it. Every experiment move, fan member
included, is dispatched through free_experimenter, so its SYSTEM_PROMPT is the one
site with total coverage; and it reaches the agent doing the work directly instead
of relying on the director to transcribe it into each question it authors.

Run directly: venv/bin/python3 tests/test_sota_comparator.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.free_experimenter import SYSTEM_PROMPT  # noqa: E402


class TestComparatorClause(unittest.TestCase):
    def test_the_experimenter_is_asked_what_already_replaced_the_incumbent(self):
        self.assertIn("IF YOUR WORK PROPOSES TO BEAT SOMETHING, FIND OUT WHAT "
                      "ALREADY BEAT IT", SYSTEM_PROMPT)
        self.assertIn("what has already been proposed or deployed to replace this",
                      SYSTEM_PROMPT)

    def test_it_names_the_successor_as_the_benchmark_to_beat(self):
        self.assertIn("THAT is the benchmark your replacement must beat",
                      SYSTEM_PROMPT)

    def test_it_asks_early_which_is_the_whole_point(self):
        """Move 14 is too late: the value is in changing what gets built, and
        the arm-C data arrived two moves after the fitting."""
        self.assertIn("EARLY, while you can still change what you build rather "
                      "than after you have fitted it", SYSTEM_PROMPT)

    def test_a_successor_that_already_does_it_is_a_finding_not_a_dead_end(self):
        self.assertIn("that is a genuinely valuable finding", SYSTEM_PROMPT)

    def test_it_is_guidance_and_gates_nothing(self):
        """THE TRAP NAMED IN THE BRIEF. The owner rejected a mandatory novelty
        check; a required step that can fail is the cage pattern the PRIME
        DIRECTIVE forbids. This must be ignorable and must never end a run."""
        self.assertIn("guidance for doing the job well, not a step you must "
                      "complete", SYSTEM_PROMPT)
        self.assertIn("ignore it entirely", SYSTEM_PROMPT)
        self.assertIn("It gates nothing and it never ends a run", SYSTEM_PROMPT)

    def test_it_self_scopes_so_a_plain_measurement_is_unaffected(self):
        self.assertIn("a measurement, a check, a design with no incumbent",
                      SYSTEM_PROMPT)


class TestNoEnforcementWasAdded(unittest.TestCase):
    """The clause is prose. Nothing validates it, nothing scores it, and the
    result validator is untouched — a report that ignores it is still valid."""

    def test_the_result_validator_never_mentions_a_comparator(self):
        from stages import free_experimenter as FE
        errors = FE._validate_free_result({
            "summary": "did a thing",
            "findings": [{"label": "x", "value": 1.0, "verified": False}],
            "publishable": True,
        })
        self.assertEqual(errors, [])

    def test_no_new_required_schema_field(self):
        from stages import free_experimenter as FE
        self.assertEqual(FE.SCHEMA["required"],
                         ["summary", "findings", "publishable"])


if __name__ == "__main__":
    unittest.main()
