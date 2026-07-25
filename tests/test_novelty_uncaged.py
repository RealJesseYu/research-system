"""test_novelty_uncaged.py — the reviewer establishes prior art ITSELF.

THE DEFECT (live, study-20260725T073215Z). The novelty review held FULL
capabilities — WebSearch, WebFetch — but its prompt said "Judge NOVELTY strictly
against those snippets", and its validator rejected any citation outside the
pre-fetched refs. Retrieval that run returned 6 refs, none relevant (S2 429'd,
the web_search sub-agent returned prose, OpenAlex 0, arXiv 3 off-topic). So for a
hypothesis whose prior art dates to Pironneau 1974 / Jameson 1988, "novel" was
the ONLY verdict the validator would accept. The gate could not fail closed.

The anti-hallucination discipline is re-sited, not dropped: a citation must be
CHECKABLE (a provided ref id, or a locator a human can follow) rather than
DRAWN FROM A FIXED LIST. Blind honesty is worse than the disease.

Run directly: venv/bin/python3 tests/test_novelty_uncaged.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.reflection_reviews import (FULL_REVIEW_SYSTEM_PROMPT,  # noqa: E402
                                       _is_checkable_citation)

REFS = {"R1", "R2"}


class TestCheckableCitation(unittest.TestCase):
    def test_a_provided_ref_id_is_accepted(self):
        self.assertTrue(_is_checkable_citation("R1", REFS))

    def test_a_located_url_is_accepted(self):
        """THE FIX. Before, this was rejected as an 'unknown ref' — which is what
        forced 'novel' whenever the keyword APIs missed."""
        self.assertTrue(_is_checkable_citation(
            "https://doi.org/10.1006/jcph.1988.1000 (Jameson 1988)", REFS))

    def test_a_doi_is_accepted(self):
        self.assertTrue(_is_checkable_citation("doi:10.1007/BF01061285", REFS))

    def test_an_arxiv_id_is_accepted(self):
        self.assertTrue(_is_checkable_citation("arXiv:1607.05126", REFS))

    def test_a_bare_unfindable_assertion_is_rejected(self):
        """Anti-hallucination: 'it is well known' is not a citation."""
        self.assertFalse(_is_checkable_citation("everyone knows this", REFS))
        self.assertFalse(_is_checkable_citation("", REFS))
        self.assertFalse(_is_checkable_citation(None, REFS))


class TestPromptTeachesSearch(unittest.TestCase):
    def test_the_reviewer_is_told_to_search(self):
        p = FULL_REVIEW_SYSTEM_PROMPT
        self.assertIn("ESTABLISH THE PRIOR ART YOURSELF", p)
        self.assertIn("web search", p.lower())

    def test_snippets_are_framed_as_a_starting_point_not_a_boundary(self):
        p = FULL_REVIEW_SYSTEM_PROMPT
        self.assertIn("STARTING POINT, not", p)
        # the precise failure mode is named so the model cannot repeat it
        self.assertIn("statement about the search, not about the literature", p)

    def test_textbook_prior_art_must_be_found_and_said(self):
        self.assertIn("textbook or decades old", FULL_REVIEW_SYSTEM_PROMPT)

    def test_citations_must_be_seen_not_invented(self):
        self.assertIn("never cite a paper you have not actually seen",
                      FULL_REVIEW_SYSTEM_PROMPT.lower())


class TestPoolVolumeIsAKnob(unittest.TestCase):
    def test_defaults_are_scaled_for_volume(self):
        """A chat gives ~6 ideas; volume is the thing it will not do."""
        import stages.generation_strategies as g
        total = (g.LITERATURE_HYPOTHESIS_COUNT + g.ASSUMPTION_HYPOTHESIS_COUNT
                 + g.EXPANSION_HYPOTHESIS_COUNT + 1)  # +1 converged debate result
        self.assertGreaterEqual(total, 50)

    def test_a_knob_overrides_and_junk_falls_back(self):
        import os
        from unittest.mock import patch
        import stages.generation_strategies as g
        with patch.dict(os.environ, {"RESEARCH_IDEATION_LITERATURE": "40"}):
            self.assertEqual(g._count("RESEARCH_IDEATION_LITERATURE", 30), 40)
        for junk in ("0", "-5", "lots", ""):
            with patch.dict(os.environ, {"RESEARCH_IDEATION_LITERATURE": junk}):
                self.assertEqual(g._count("RESEARCH_IDEATION_LITERATURE", 30), 30)


# --------------------------------------------------------------------------
# Generation, uncaged the same way (2026-07-25).
# --------------------------------------------------------------------------

class TestGenerationUncaged(unittest.TestCase):
    def test_generator_is_told_to_read_the_literature_itself(self):
        import stages.generation_strategies as g
        p = g.LITERATURE_SYSTEM_PROMPT
        self.assertIn("READ THE LITERATURE YOURSELF", p)
        self.assertIn("STARTING POINT, not the", p)

    def test_generator_is_pushed_toward_range_not_safety(self):
        """The filters only reject defects, so nothing downstream rewards a bold
        idea; the generator is the only place range can be asked for."""
        import stages.generation_strategies as g
        p = g.LITERATURE_SYSTEM_PROMPT
        self.assertIn("AIM FOR RANGE, NOT SAFETY", p)
        self.assertIn("restatements of the same safe idea", p)

    def test_generation_citations_may_be_located_sources(self):
        """Same rule as the review: checkable, not drawn from a fixed list."""
        from stages.reflection_reviews import _is_checkable_citation
        self.assertTrue(_is_checkable_citation("https://doi.org/10.1234/x", {"R1"}))
        self.assertTrue(_is_checkable_citation("R1", {"R1"}))
        self.assertFalse(_is_checkable_citation("trust me", {"R1"}))

    def test_the_web_search_subagent_is_gone_from_both_paths(self):
        """It was scaffolding for stages that held no tools; both paths now search
        natively, and the wrapper could only lose information."""
        import inspect
        import stages.generation_strategies as g
        import stages.reflection_reviews as r
        for mod in (g, r):
            src = inspect.getsource(mod)
            self.assertNotIn("= web_search(", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
