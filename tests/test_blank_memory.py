"""
test_blank_memory.py — the BLANK_MEMORY ablation seam.

Zero model calls. Proves: (a) with the flag OFF, journal_recent_by_kind and the
downstream memory-block composition are byte-identical to reading the journal
directly (flag-off changes nothing); (b) with BLANK_MEMORY=1 every retrieval
comes back empty and the memory block composes to None; (c) the supervisor's
run_record discloses blank_memory=true prominently when on, and is byte-
identical when off.

The seam lives at the single retrieval source (memory/journal.py) so no
stages/* composition code is touched — the composition functions are exercised
here unmodified.

Run directly: python3 tests/test_blank_memory.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import memory.journal as journal
from stages.stage1_ideation import build_memory_block

FIXTURE_ENTRIES = [
    {"run_id": "r1", "kind": "learned_summary", "text": "first lesson", "extras": {}},
    {"run_id": "r2", "kind": "run_record", "text": "a run", "extras": {}},
    {"run_id": "r3", "kind": "learned_summary", "text": "second lesson", "extras": {}},
    {"run_id": "r4", "kind": "learned_summary", "text": "third lesson", "extras": {}},
]


class TempJournal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
        for e in FIXTURE_ENTRIES:
            self.tmp.write(json.dumps(e) + "\n")
        self.tmp.flush()
        self.tmp.close()
        self.path = Path(self.tmp.name)
        self._patch = mock.patch.object(journal, "JOURNAL_PATH", self.path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        self.path.unlink(missing_ok=True)

    def _read_directly(self, kind, limit=3):
        """The plain scan the function performs, computed independently here."""
        entries = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
        entries.reverse()
        return [e for e in entries if e.get("kind") == kind][:limit]


class RetrievalSource(TempJournal):
    def test_flag_off_returns_entries_identically(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            journal.os.environ.pop("BLANK_MEMORY", None)
            got = journal.journal_recent_by_kind("learned_summary", 3)
        self.assertEqual(got, self._read_directly("learned_summary", 3))
        self.assertEqual(len(got), 3)

    def test_flag_on_returns_empty(self):
        with mock.patch.dict("os.environ", {"BLANK_MEMORY": "1"}):
            got = journal.journal_recent_by_kind("learned_summary", 3)
        self.assertEqual(got, [])

    def test_flag_other_values_do_not_activate(self):
        # only "1" activates; "0"/"" behave as off (byte-identical retrieval)
        for val in ("0", "", "true", "yes"):
            with mock.patch.dict("os.environ", {"BLANK_MEMORY": val}):
                self.assertEqual(
                    journal.journal_recent_by_kind("learned_summary", 3),
                    self._read_directly("learned_summary", 3),
                )


class Composition(TempJournal):
    def test_flag_off_block_equals_current_behavior(self):
        # composed memory block with flag OFF must equal composing over the
        # directly-read entries — the seam is invisible when off.
        with mock.patch.dict("os.environ", {}, clear=False):
            journal.os.environ.pop("BLANK_MEMORY", None)
            entries = journal.journal_recent_by_kind("learned_summary", 3)
        block_off = build_memory_block(entries)
        block_reference = build_memory_block(self._read_directly("learned_summary", 3))
        self.assertEqual(block_off, block_reference)
        self.assertIsNotNone(block_off)

    def test_flag_on_block_is_none(self):
        with mock.patch.dict("os.environ", {"BLANK_MEMORY": "1"}):
            entries = journal.journal_recent_by_kind("learned_summary", 3)
        self.assertEqual(entries, [])
        self.assertIsNone(build_memory_block(entries))  # empty -> no block


class RunRecordDisclosure(TempJournal):
    def _record(self, env):
        import supervisor
        baton = SimpleNamespace(run_id="testrun", mode="human", payload={})
        with mock.patch.dict("os.environ", env, clear=False):
            if "BLANK_MEMORY" not in env:
                journal.os.environ.pop("BLANK_MEMORY", None)
            supervisor.record_run_outcome(baton, "completed")
        lines = [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]
        return lines[-1]

    def test_flag_off_record_has_no_blank_memory_key(self):
        rec = self._record({})
        self.assertNotIn("blank_memory", rec["extras"])
        self.assertEqual(rec["text"], "run testrun (human mode): completed")

    def test_flag_on_record_discloses_prominently(self):
        rec = self._record({"BLANK_MEMORY": "1"})
        self.assertTrue(rec["extras"]["blank_memory"])
        self.assertTrue(rec["text"].startswith("[BLANK_MEMORY]"))


if __name__ == "__main__":
    unittest.main()
