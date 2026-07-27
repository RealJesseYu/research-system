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


#: Generation order 0..6. Novel: h1(3), h3(5), h4(5), h6(2), h7(4).
#: Known:              h2(5), h5(1).
_MIXED = [
    {"hypothesis_id": "h1", "novelty": "novel", "critique": "ok", "quality": 3},
    {"hypothesis_id": "h2", "novelty": "known", "critique": "seen", "quality": 5},
    {"hypothesis_id": "h3", "novelty": "novel", "critique": "strong", "quality": 5},
    {"hypothesis_id": "h4", "novelty": "novel", "critique": "strong", "quality": 5},
    {"hypothesis_id": "h5", "novelty": "known", "critique": "seen", "quality": 1},
    {"hypothesis_id": "h6", "novelty": "novel", "critique": "weak", "quality": 2},
    {"hypothesis_id": "h7", "novelty": "novel", "critique": "good", "quality": 4},
]


class TestFilterHappyPath(unittest.TestCase):
    """The old version of this test asserted ["h3","h4","h7","h1"] and its comment
    read "Known (excluded): h2(5), h5(1)" — the pre-2026-07-25 novelty VETO, still
    encoded here long after filter_survivors stopped killing on novelty. It made a
    quality-5 known-method hypothesis vanish and called that correct."""

    def _ids(self, priority=None):
        kw = {} if priority is None else {"novelty_priority": priority}
        return [s["hypothesis_id"] for s in filter_survivors(_MIXED, **kw)]

    def test_default_is_balanced_quality_leads_novelty_breaks_ties(self):
        """h2 (known, 5) COMPETES: it ties h3/h4 on quality and loses the tie to
        them for being known — it is not deleted for it."""
        self.assertEqual(self._ids(), ["h3", "h4", "h2", "h7"])
        self.assertEqual(self._ids("balanced"), self._ids())

    def test_required_puts_every_novel_hypothesis_first(self):
        """The SCIENCE setting: an established answer by an established method is
        not a result, so novelty leads and h2 falls outside the cap."""
        self.assertEqual(self._ids("required"), ["h3", "h4", "h7", "h1"])

    def test_irrelevant_ranks_on_quality_alone(self):
        """The ENGINEERING setting: a well-established method is a virtue, so h2
        places on merit and generation order breaks the h3/h4/h2 tie."""
        self.assertEqual(self._ids("irrelevant"), ["h2", "h3", "h4", "h7"])

    def test_the_cap_is_respected_under_every_priority(self):
        for p in ("required", "balanced", "irrelevant"):
            self.assertLessEqual(len(self._ids(p)), 4, p)

    def test_an_unknown_priority_is_refused_rather_than_defaulted(self):
        """Silently falling back would make a typo in a director's action change
        which hypotheses survive, with nothing in the record saying so."""
        with self.assertRaises(ValueError):
            filter_survivors(_MIXED, novelty_priority="high")


if __name__ == "__main__":
    unittest.main()
