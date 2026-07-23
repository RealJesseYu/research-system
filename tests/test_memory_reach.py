"""
test_memory_reach.py — Step 18.5 (memory reach extended): Stage 2 receives a
code-authored substrate-capability lessons block from the journal, and
Reflection's initial review receives a prior-dead-ends block riding its
EXISTING call. Zero live model calls: call_stage_model is faked; the journal
is a fixture file swapped in via memory.journal.JOURNAL_PATH (the
test_journal_read pattern); every runs/ write lands in a TemporaryDirectory
the test chdirs into.

Run directly: python3 tests/test_memory_reach.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from memory import journal
from memory.journal import journal_recent_by_kind
from stages import reflection_reviews
from stages.reflection_reviews import (
    DEAD_END_HEADER,
    DEAD_END_RETRIEVAL_KIND,
    DEAD_END_RETRIEVAL_LIMIT,
    build_dead_end_block,
)

FAKE_TIMING = {"model": "fake-model", "duration_seconds": 0.0, "attempts": 1}

# 18-hygiene: the journal state these tests exercise is a COMMITTED frozen
# snapshot (tests/fixtures/journal_18_5_snapshot.jsonl), not inline constants
# nor the live memory/journal.jsonl — so journal growth can never flake them.
# The snapshot is oldest-first on disk (LESSON_A, RUN_RECORD, LESSON_B); each
# test composes the subset/order it needs from these named entries and writes
# them to a swapped tmp JOURNAL_PATH.
_SNAPSHOT_PATH = Path(__file__).resolve().parent / "fixtures" / "journal_18_5_snapshot.jsonl"
with open(_SNAPSHOT_PATH) as _f:
    _SNAPSHOT = [json.loads(line) for line in _f if line.strip()]
LESSON_A, RUN_RECORD, LESSON_B = _SNAPSHOT[0], _SNAPSHOT[1], _SNAPSHOT[2]
# The snapshot content the assertions below are pinned to (guards a fixture
# edit from silently changing what these tests mean).
assert (LESSON_A["run_id"], LESSON_A["hypothesis_id"]) == ("runA", "h2")
assert RUN_RECORD["kind"] == "run_record"
assert (LESSON_B["run_id"], LESSON_B["hypothesis_id"]) == ("runB", "ev1")


def minimal_spec(hypothesis_id: str = "h1") -> dict:
    """The minimum shape stage 2's post-call code touches (the real deep
    validator is bypassed by the faked call_stage_model, deliberately —
    validate_spec has its own tests)."""
    return {
        "hypothesis_id": hypothesis_id,
        "parameters": [
            {"name": "lid_velocity", "role": "sweep", "units": "m/s",
             "min": 0.5, "max": 2.0},
            {"name": "kinematic_viscosity", "role": "fixed", "units": "m2/s",
             "value": 0.01},
        ],
        "qoi": {"name": "mean speed", "units": "m/s",
                "definition": "d", "how_extracted": "e"},
        "mini_experiment": {
            "runs": [{"lid_velocity": 1.0, "kinematic_viscosity": 0.01}],
            "expected_observation": "x",
        },
    }


class JournalFixtureCase(unittest.TestCase):
    """chdir into a TemporaryDirectory (isolating runs/ writes) and swap
    memory.journal.JOURNAL_PATH for a fixture file — the real journal is
    never read or written."""

    run_id = "memreach-test"

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = Path.cwd()
        os.chdir(self._tmp.name)
        (Path("runs") / self.run_id).mkdir(parents=True)
        self._old_journal = journal.JOURNAL_PATH
        journal.JOURNAL_PATH = Path(self._tmp.name) / "journal.jsonl"

    def tearDown(self):
        journal.JOURNAL_PATH = self._old_journal
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def write_journal(self, entries: list[dict]) -> None:
        with open(journal.JOURNAL_PATH, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def append_journal(self, entry: dict) -> None:
        with open(journal.JOURNAL_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def log_text(self) -> str:
        return (Path("runs") / self.run_id / "log.txt").read_text()


class TestPureBlockBuilders(unittest.TestCase):
    def test_dead_end_block_none_on_empty(self):
        self.assertIsNone(build_dead_end_block([]))

    def test_dead_end_block_exact_lines(self):
        block = build_dead_end_block([LESSON_A])
        self.assertEqual(
            block,
            DEAD_END_HEADER
            + "\n- [run runA, hypothesis h2] substrate cannot extract "
            "stream-function QoIs",
        )



class TestDeadEndsRideInitialReview(JournalFixtureCase):
    POOL = [
        {"id": "h1", "statement": "s1", "rationale": "r1"},
        {"id": "h2", "statement": "s2", "rationale": "r2"},
    ]

    def _run_initial_review(self) -> tuple[list[dict], list[dict], int]:
        captured: list[dict] = []
        calls = {"n": 0}

        def fake_call(stage_name, system_prompt, stage_input, schema,
                      model=None, extra_validator=None, **kwargs):
            calls["n"] += 1
            captured.append(stage_input)
            reviews = [
                {"id": h["id"], "verdict": "pass", "reason": "ok"}
                for h in self.POOL
            ]
            return (
                {"ack_run_id": stage_input["run_id"], "reviews": reviews},
                dict(FAKE_TIMING),
            )

        with patch.object(reflection_reviews, "call_stage_model", fake_call):
            reviews = reflection_reviews.initial_review(
                self.run_id, "test domain", self.POOL
            )
        return reviews, captured, calls["n"]

    def test_block_rides_existing_call_without_adding_calls(self):
        self.write_journal([LESSON_A, LESSON_B])
        reviews, captured, n_calls = self._run_initial_review()

        self.assertEqual(n_calls, 1)  # the constraint: rides the ONE call
        block = captured[0]["prior_dead_ends"]
        self.assertTrue(block.startswith(DEAD_END_HEADER))
        self.assertIn("[run runA, hypothesis h2]", block)
        self.assertIn("[run runB, hypothesis ev1]", block)
        self.assertEqual(len(reviews), 2)
        self.assertIn("STAGE1_DEADENDS 2 journal dead-end entries provided "
                      "to initial review", self.log_text())

    def test_empty_journal_no_block_still_one_call(self):
        self.write_journal([])
        reviews, captured, n_calls = self._run_initial_review()

        self.assertEqual(n_calls, 1)
        self.assertNotIn("prior_dead_ends", captured[0])
        self.assertEqual(len(reviews), 2)
        self.assertIn("STAGE1_DEADENDS 0 journal dead-end entries provided "
                      "to initial review", self.log_text())

    def test_battery_comparability_pure_function_of_pinned_read(self):
        # The chosen comparability option (Step 18.5 step 3): the dead-end
        # block derives from the EXACT same read the battery md5 pin is
        # derived from — journal_recent_by_kind("learned_summary", 3) — so
        # under a pinned journal state every slot gets a byte-identical
        # block, and stage1/retrieved_memory.json's derivation is untouched.
        self.assertEqual(DEAD_END_RETRIEVAL_KIND, "learned_summary")
        self.assertEqual(DEAD_END_RETRIEVAL_LIMIT, 3)

        self.write_journal([LESSON_A, RUN_RECORD, LESSON_B])
        _, captured_first, _ = self._run_initial_review()
        _, captured_second, _ = self._run_initial_review()

        pinned_read = journal_recent_by_kind("learned_summary", 3)
        expected = build_dead_end_block(pinned_read)
        self.assertEqual(captured_first[0]["prior_dead_ends"], expected)
        self.assertEqual(captured_second[0]["prior_dead_ends"], expected)


if __name__ == "__main__":
    unittest.main()
