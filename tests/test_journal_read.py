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
from memory.journal import journal_recent_by_kind, journal_search


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


class TestOneBadLineDoesNotCostTheJournal(unittest.TestCase):
    """journal_recent_by_kind is the SINGLE retrieval source every stage's
    memory block reads through, and both readers used to do an unguarded
    json.loads per line. One torn or truncated line therefore raised out of
    memory retrieval for every subsequent run, permanently, until someone
    repaired the file by hand — and the journal.jsonl.pre-correction-20260720
    sibling on disk says real damage has happened at least once.

    Skip-and-COUNT, not skip-and-hide: a corrupt line must stay visible rather
    than quietly shrink what memory knows.
    """

    GOOD_FIRST = {"run_id": "r1", "kind": "learned_summary", "text": "first"}
    GOOD_LAST = {"run_id": "r9", "kind": "learned_summary", "text": "last"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_path = journal.JOURNAL_PATH
        journal.JOURNAL_PATH = Path(self.tmp.name) / "journal.jsonl"
        with open(journal.JOURNAL_PATH, "w") as f:
            f.write(json.dumps(self.GOOD_FIRST) + "\n")
            f.write('{"run_id": "r2", "kind": "learned_su\n')   # torn mid-object
            f.write('"a bare string, not an object"\n')         # parses, wrong type
            f.write("not json at all\n")
            f.write(json.dumps(self.GOOD_LAST) + "\n")

    def tearDown(self):
        journal.JOURNAL_PATH = self._old_path
        self.tmp.cleanup()

    def test_good_entries_on_both_sides_of_the_damage_survive(self):
        got = journal_recent_by_kind("learned_summary", limit=10)
        self.assertEqual([e["text"] for e in got], ["last", "first"])

    def test_search_survives_the_same_damage(self):
        """journal_search had its own copy of the fatal loop."""
        self.assertEqual([e["run_id"] for e in journal_search(keyword="las")], ["r9"])

    def test_a_bare_string_line_is_skipped_not_returned(self):
        """It parses as JSON, so a tolerant loads() alone would let it through
        and it would raise later at the .get() filter instead."""
        for e in journal_search():
            self.assertIsInstance(e, dict)

    def test_the_damage_is_counted_and_announced(self):
        entries, unreadable = journal._read_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(unreadable, 3)


class TestAppendIsAtomicAndWholeLine(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old_path = journal.JOURNAL_PATH
        journal.JOURNAL_PATH = Path(self.tmp.name) / "journal.jsonl"

    def tearDown(self):
        journal.JOURNAL_PATH = self._old_path
        self.tmp.cleanup()

    def test_an_oversized_entry_lands_as_one_readable_line(self):
        """Larger than the platform text buffer (131072 here), which is the
        size at which a buffered writer could have split the record."""
        big = "x" * 400000
        journal.journal_append({"run_id": "r", "kind": "big", "text": big})
        lines = [l for l in journal.JOURNAL_PATH.read_text().splitlines() if l.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["text"], big)

    def test_append_still_only_appends(self):
        """The append-only invariant, which had NO test at all: flipping the
        mode to "w" would have destroyed every prior line and left the whole
        suite green."""
        journal.journal_append({"run_id": "r1", "kind": "k", "text": "first"})
        journal.journal_append({"run_id": "r2", "kind": "k", "text": "second"})
        texts = [json.loads(l)["text"]
                 for l in journal.JOURNAL_PATH.read_text().splitlines() if l.strip()]
        self.assertEqual(texts, ["first", "second"])

    def test_required_fields_still_raise(self):
        with self.assertRaises(ValueError):
            journal.journal_append({"run_id": "r", "kind": "k"})  # no text


if __name__ == "__main__":
    unittest.main()
