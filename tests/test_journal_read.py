"""
test_journal_read.py — standalone tests of journal_recent_by_kind (Step 14
JC2 read-side). Stdlib only: a temporary journal file replaces
memory.journal.JOURNAL_PATH for each test, so the real journal is never
touched.

Run directly: python3 tests/test_journal_read.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory.journal as journal
from memory.journal import journal_recent_by_kind


class TestJournalRecentByKind(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_path = journal.JOURNAL_PATH
        journal.JOURNAL_PATH = Path(self.tmp.name) / "journal.jsonl"
        entries = [
            {"run_id": "r1", "kind": "learned_summary", "text": "oldest summary"},
            {"run_id": "r2", "kind": "run_record", "text": "a run record"},
            {"run_id": "r3", "kind": "learned_summary", "text": "middle summary"},
            {"run_id": "r4", "kind": "learned_summary", "text": "newer summary"},
            {"run_id": "r5", "kind": "learned_summary", "text": "newest summary"},
        ]
        with open(journal.JOURNAL_PATH, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def tearDown(self):
        journal.JOURNAL_PATH = self._old_path
        self.tmp.cleanup()

    def test_kind_filter_is_exact(self):
        results = journal_recent_by_kind("learned_summary", limit=10)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(e["kind"] == "learned_summary" for e in results))

    def test_limit_respected(self):
        results = journal_recent_by_kind("learned_summary", limit=2)
        self.assertEqual(len(results), 2)

    def test_most_recent_first(self):
        results = journal_recent_by_kind("learned_summary")  # default limit=3
        self.assertEqual([e["run_id"] for e in results], ["r5", "r4", "r3"])

    def test_empty_when_no_matches(self):
        self.assertEqual(journal_recent_by_kind("no_such_kind"), [])


if __name__ == "__main__":
    unittest.main()
