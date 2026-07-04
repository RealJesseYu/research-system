"""
test_stage1_filter.py — standalone test of stage1_ideation's deterministic
novelty/quality filter. Zero model calls: filter_survivors is pure Python,
so this exercises it directly against fake reflection data.

Run directly: python3 tests/test_stage1_filter.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage1_ideation import filter_survivors


class TestFilterHalt(unittest.TestCase):
    def test_all_known_halts_loudly(self):
        reflections = [
            {"hypothesis_id": "h1", "novelty": "known", "critique": "seen before", "quality": 4},
            {"hypothesis_id": "h2", "novelty": "known", "critique": "not new", "quality": 2},
            {"hypothesis_id": "h3", "novelty": "known", "critique": "textbook", "quality": 5},
        ]
        with self.assertRaises(RuntimeError) as ctx:
            filter_survivors(reflections)
        message = str(ctx.exception)
        self.assertIn("all 3 hypotheses were judged 'known'", message)
        self.assertIn("Zero survivors", message)


class TestFilterHappyPath(unittest.TestCase):
    def test_mixed_novel_known_ranked_with_tiebreak_and_cap(self):
        # Generation order 0..6. Novel: h1(3), h3(5), h4(5), h6(2), h7(4).
        # Known (excluded): h2(5), h5(1).
        # Expected: sort by quality desc, ties by generation order, capped at 4:
        #   h3(5, idx2), h4(5, idx3), h7(4, idx6), h1(3, idx0)  -- h6(2) dropped.
        reflections = [
            {"hypothesis_id": "h1", "novelty": "novel", "critique": "ok", "quality": 3},
            {"hypothesis_id": "h2", "novelty": "known", "critique": "seen", "quality": 5},
            {"hypothesis_id": "h3", "novelty": "novel", "critique": "strong", "quality": 5},
            {"hypothesis_id": "h4", "novelty": "novel", "critique": "strong", "quality": 5},
            {"hypothesis_id": "h5", "novelty": "known", "critique": "seen", "quality": 1},
            {"hypothesis_id": "h6", "novelty": "novel", "critique": "weak", "quality": 2},
            {"hypothesis_id": "h7", "novelty": "novel", "critique": "good", "quality": 4},
        ]
        survivors = filter_survivors(reflections)
        self.assertLessEqual(len(survivors), 4)
        survivor_ids = [s["hypothesis_id"] for s in survivors]
        self.assertEqual(survivor_ids, ["h3", "h4", "h7", "h1"])


if __name__ == "__main__":
    unittest.main()
