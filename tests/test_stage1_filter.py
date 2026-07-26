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
    def test_a_known_method_with_an_open_answer_survives(self):
        """CHANGED 2026-07-25 on live evidence. This used to halt: every 'known'
        reflection was discarded. That was survivable only while the reviewer was
        blind and returned 'novel' by default — the moment it could actually
        search, 16 of 16 came back 'known' and the run died with zero survivors.
        Novelty of METHOD is not novelty of ANSWER, and a textbook technique
        carried where nobody has measured the effect is a good hypothesis."""
        reflections = [
            {"hypothesis_id": "h1", "novelty": "known", "critique": "well-known method",
             "quality": 4},
            {"hypothesis_id": "h2", "novelty": "known", "critique": "standard tool",
             "quality": 2},
        ]
        survivors = filter_survivors(reflections)
        self.assertEqual([r["hypothesis_id"] for r in survivors], ["h1", "h2"])

    def test_all_answers_established_reports_instead_of_halting(self):
        """FILTER NEVER HALTS THE RUN (2026-07-25). It raised twice live, on two
        successive predicates, and killing a run is the pipeline overriding the
        researcher — the caged behaviour the PRIME DIRECTIVE forbids. A chat
        handed sixteen already-answered ideas says so and decides; it does not
        refuse to continue. The candidates come back carrying the flag so the
        DIRECTOR can re-ideate, reframe, or proceed knowingly."""
        reflections = [
            {"hypothesis_id": "h1", "novelty": "known", "critique": "seen before",
             "quality": 4, "answer_established": True},
            {"hypothesis_id": "h2", "novelty": "novel", "critique": "but answered",
             "quality": 5, "answer_established": True},
        ]
        survivors = filter_survivors(reflections)
        self.assertTrue(survivors)
        self.assertTrue(all(r["answer_established"] for r in survivors))
        # ranked: novel-and-higher-quality first
        self.assertEqual(survivors[0]["hypothesis_id"], "h2")

    def test_novel_outranks_known_at_equal_quality(self):
        """Novelty survives as a ranking signal rather than a veto."""
        reflections = [
            {"hypothesis_id": "hk", "novelty": "known", "critique": "c", "quality": 5},
            {"hypothesis_id": "hn", "novelty": "novel", "critique": "c", "quality": 5},
        ]
        self.assertEqual([r["hypothesis_id"] for r in filter_survivors(reflections)],
                         ["hn", "hk"])

    def test_an_answered_hypothesis_is_dropped_even_if_novel(self):
        reflections = [
            {"hypothesis_id": "h1", "novelty": "novel", "critique": "c", "quality": 5,
             "answer_established": True},
            {"hypothesis_id": "h2", "novelty": "known", "critique": "c", "quality": 1},
        ]
        self.assertEqual([r["hypothesis_id"] for r in filter_survivors(reflections)],
                         ["h2"])


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
