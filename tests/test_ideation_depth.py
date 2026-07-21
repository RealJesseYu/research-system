"""
test_ideation_depth.py — the ideation depth switch (stages/stage1_ideation.py,
2026-07-21). depth='quick' runs ONE literature-grounded generation and delivers
it directly; depth='full' (default) runs the whole Co-Scientist apparatus.

Offline: retrieval, the single strategy, and the journal read are patched, so no
model call and no network. The full apparatus (generate_candidate_pool) is
patched to explode — proving the quick path never touches it.

Run directly: venv/bin/python3 tests/test_ideation_depth.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from baton import Baton  # noqa: E402
import stages.stage1_ideation as s1  # noqa: E402

_CANDIDATES = [
    {"statement": "stmt one", "rationale": "because one", "strategy": "literature_exploration"},
    {"statement": "stmt two", "rationale": "because two", "strategy": "literature_exploration"},
    {"statement": "stmt three", "rationale": "because three", "strategy": "literature_exploration"},
]


def _boom(*a, **k):
    raise AssertionError("the full apparatus must not run under depth='quick'")


class DepthSwitch(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = Path.cwd()
        os.chdir(self._tmp.name)

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _baton(self):
        return Baton(
            run_id="quicktest",
            created_at="2026-07-21T00:00:00+00:00",
            mode="auto",
            payload={"domain": "some domain"},
            history=[],
        )

    def _run_quick(self):
        with patch.object(s1, "journal_recent_by_kind", lambda kind, n: []), \
             patch.object(s1, "gather_literature_evidence",
                          lambda rid, dom, rd: [{"ref": "R1", "text": "snippet"}]), \
             patch.object(s1, "strategy_literature_exploration",
                          lambda rid, dom, refs, mb, mrf=None: (list(_CANDIDATES), [])), \
             patch.object(s1, "generate_candidate_pool", _boom):
            return s1.run(self._baton(), depth="quick")

    def test_quick_delivers_the_right_shape(self):
        out = self._run_quick()
        self.assertEqual(out.payload["hypotheses_ranked"], True)
        self.assertEqual(
            out.payload["hypotheses"],
            [
                {"id": "h1", "statement": "stmt one", "rationale": "because one"},
                {"id": "h2", "statement": "stmt two", "rationale": "because two"},
                {"id": "h3", "statement": "stmt three", "rationale": "because three"},
            ],
        )

    def test_quick_never_runs_the_full_apparatus(self):
        # generate_candidate_pool is patched to raise; a clean return proves it
        # was never called.
        out = self._run_quick()
        self.assertEqual(len(out.payload["hypotheses"]), 3)

    def test_quick_writes_its_own_evidence(self):
        self._run_quick()
        self.assertTrue(Path("runs/quicktest/stage1/quick_ideation.json").is_file())

    def test_quick_records_one_history_entry(self):
        out = self._run_quick()
        notes = [h for h in out.history if h.get("stage") == "stage1_ideation"]
        self.assertEqual(len(notes), 1)
        self.assertIn("quick", notes[0]["note"])

    def test_invalid_depth_raises(self):
        with self.assertRaises(ValueError):
            s1.run(self._baton(), depth="medium")

    def test_default_depth_is_full(self):
        # depth defaults to 'full'; with the apparatus patched to explode, the
        # default path must reach it (proving the default is NOT quick).
        with patch.object(s1, "journal_recent_by_kind", lambda kind, n: []), \
             patch.object(s1, "generate_candidate_pool", _boom):
            with self.assertRaises(AssertionError):
                s1.run(self._baton())


if __name__ == "__main__":
    unittest.main(verbosity=2)
