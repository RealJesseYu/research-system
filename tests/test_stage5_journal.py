"""
test_stage5_journal.py — standalone tests of stage 5's pure JC6 function
decide_journal_entry. Zero model calls, zero journal writes: the function
maps a validated thought to a journal entry dict (or None); appending is
the live stage path's job, not tested here.

Run directly: python3 tests/test_stage5_journal.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage5_thought_layer import decide_journal_entry


def make_thought(decision: str) -> dict:
    return {
        "assessment": "Both runs converged and matched the prediction.",
        "surprise_triage": "none",
        "iterate_decision": decision,
        "justification": "The measured value sits where the spec predicted.",
        "learned_summary": "Baseline cavity mean speed scales sub-linearly with lid speed.",
    }


class TestDecideJournalEntry(unittest.TestCase):
    def test_exit_gives_none(self):
        self.assertIsNone(decide_journal_entry(make_thought("exit"), "run-x", "h3"))

    def test_each_non_exit_decision_gives_entry(self):
        for decision in ("back_to_ideation", "back_to_design", "more_data"):
            thought = make_thought(decision)
            entry = decide_journal_entry(thought, "run-x", "h3")
            self.assertEqual(
                entry,
                {
                    "kind": "learned_summary",
                    "run_id": "run-x",
                    "hypothesis_id": "h3",
                    "text": thought["learned_summary"],
                },
                f"decision {decision!r} produced the wrong entry",
            )


if __name__ == "__main__":
    unittest.main()
