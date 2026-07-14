"""
test_lesson_provenance.py — Phase-1 Lane-1: measured-vs-said backfill.
Deterministic, ZERO model calls. A fixture journal + fixture run tree are
built in a TemporaryDirectory; both tags are exercised; the journal file is
asserted byte-unchanged (read-only).

Run directly: venv/bin/python3 tests/test_lesson_provenance.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import lesson_provenance as lp


def _executed_results(qoi_value):
    return {
        "status": "executed",
        "runs": [
            {"run_index": 1, "case": "c1",
             "summary": {"converged": True, "qoi": {"name": "cellMin(U)[0]", "value": qoi_value}}},
        ],
    }


def _defer_results():
    return {"status": "skipped_defer", "runs": []}


def _executed_but_no_numeric_qoi():
    # executed but the QoI was free-text / untranslatable -> no numeric value
    return {"status": "executed", "runs": [
        {"run_index": 1, "case": "c1", "summary": {"converged": True}, "qoi_translation_error": "not extractable"}]}


class Backfill(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs = root / "runs"
        self.runs.mkdir()
        # RUN measured: executed + numeric QoI on disk
        (self.runs / "RUN_M" / "stage4").mkdir(parents=True)
        (self.runs / "RUN_M" / "stage4" / "results.json").write_text(json.dumps(_executed_results(-0.207)))
        # RUN executed-but-rescope: executed + numeric QoI, but lesson is a limitation claim
        (self.runs / "RUN_X" / "stage4").mkdir(parents=True)
        (self.runs / "RUN_X" / "stage4" / "results.json").write_text(json.dumps(_executed_results(0.4)))
        # RUN defer: no solver executed
        (self.runs / "RUN_D" / "stage4").mkdir(parents=True)
        (self.runs / "RUN_D" / "stage4" / "results.json").write_text(json.dumps(_defer_results()))
        # RUN executed with no numeric qoi (translation error)
        (self.runs / "RUN_N" / "stage4").mkdir(parents=True)
        (self.runs / "RUN_N" / "stage4" / "results.json").write_text(json.dumps(_executed_but_no_numeric_qoi()))

        self.journal = root / "journal.jsonl"
        entries = [
            {"run_id": "step7", "kind": "milestone", "text": "build milestone — must be ignored"},
            {"run_id": "RUN_D", "kind": "run_record", "text": "run record — must be ignored"},
            {"run_id": "RUN_M", "hypothesis_id": "h4", "kind": "learned_summary",
             "text": "|min(Ux)| grows superlinearly with Re (0.21/0.24/0.37), a steeper slope",
             "timestamp": "2026-07-13T00:00:01Z"},
            {"run_id": "RUN_X", "hypothesis_id": "ev2", "kind": "learned_summary",
             "text": "The substrate cannot model central-obstacle geometry; testing needs a different instrument.",
             "timestamp": "2026-07-13T00:00:02Z"},
            {"run_id": "RUN_D", "hypothesis_id": "h2", "kind": "learned_summary",
             "text": "Testing this mixing hypothesis requires a 3-D DNS the substrate lacks.",
             "timestamp": "2026-07-13T00:00:03Z"},
            {"run_id": "RUN_N", "hypothesis_id": "h9", "kind": "learned_summary",
             "text": "The peakedness ratio grows with Re but was not extractable this run.",
             "timestamp": "2026-07-13T00:00:04Z"},
            {"run_id": None, "hypothesis_id": "h1", "kind": "learned_summary",
             "text": "A lesson with no run id at all.",
             "timestamp": "2026-07-13T00:00:05Z"},
        ]
        with open(self.journal, "w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")
        self.journal_bytes = self.journal.read_bytes()
        self.out = root / "lesson_provenance.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_backfill_classifies_only_learned_summaries(self):
        records = lp.backfill(self.journal, self.runs, self.out)
        self.assertEqual(len(records), 5)  # 5 learned summaries; milestone + run_record ignored

    def test_both_tags_exercised(self):
        records = lp.backfill(self.journal, self.runs, self.out)
        by_run = {r["source_run"]: r for r in records}
        self.assertEqual(by_run["RUN_M"]["provenance"], "measured")
        self.assertEqual(by_run["RUN_X"]["provenance"], "said")  # executed but re-scope claim
        self.assertEqual(by_run["RUN_D"]["provenance"], "said")  # never executed
        self.assertEqual(by_run["RUN_N"]["provenance"], "said")  # executed, no numeric qoi
        self.assertEqual(by_run[None]["provenance"], "said")     # no run_id
        tags = {r["provenance"] for r in records}
        self.assertEqual(tags, {"measured", "said"})

    def test_measured_count_is_one(self):
        records = lp.backfill(self.journal, self.runs, self.out)
        self.assertEqual(sum(1 for r in records if r["provenance"] == "measured"), 1)

    def test_keys_stable_and_unique(self):
        records = lp.backfill(self.journal, self.runs, self.out)
        keys = [r["key"] for r in records]
        self.assertEqual(len(keys), len(set(keys)))
        # key composes run_id|hypothesis_id|timestamp
        self.assertIn("RUN_M|h4|2026-07-13T00:00:01Z", keys)

    def test_sidecar_written_and_reloadable(self):
        lp.backfill(self.journal, self.runs, self.out)
        loaded = [json.loads(l) for l in self.out.read_text().splitlines() if l.strip()]
        self.assertEqual(len(loaded), 5)
        for rec in loaded:
            self.assertEqual(set(rec.keys()), {"key", "provenance", "source_run", "basis"})

    def test_journal_untouched(self):
        lp.backfill(self.journal, self.runs, self.out)
        self.assertEqual(self.journal.read_bytes(), self.journal_bytes)

    def test_hard_gate_helper(self):
        self.assertEqual(lp.executed_numeric_qois("RUN_M", self.runs), [-0.207])
        self.assertIsNone(lp.executed_numeric_qois("RUN_D", self.runs))   # defer
        self.assertIsNone(lp.executed_numeric_qois("RUN_N", self.runs))   # no numeric qoi
        self.assertIsNone(lp.executed_numeric_qois("NOPE", self.runs))    # missing run
        self.assertIsNone(lp.executed_numeric_qois(None, self.runs))

    def test_append_helper_validates(self):
        lp.backfill(self.journal, self.runs, self.out)
        before = len(self.out.read_text().splitlines())
        lp.append_provenance("k|h|t", "measured", "RUN_Z", "a future entry", self.out)
        after = len(self.out.read_text().splitlines())
        self.assertEqual(after, before + 1)
        with self.assertRaises(ValueError):
            lp.append_provenance("k|h|t", "bogus", "RUN_Z", "bad tag", self.out)


if __name__ == "__main__":
    unittest.main()
