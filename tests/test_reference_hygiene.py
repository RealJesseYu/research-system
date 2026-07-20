"""
test_reference_hygiene — the two reference bugs behind run 20260720T080610Z.

That run shipped an E. coli metabolic-modelling paper whose entire reference
list was three particle-physics collaborations: a CMS/LHCb dimuon decay, ATLAS
detector performance, and an IceCube/LIGO neutrino search. Two independent
causes, fixed independently and tested here:

  1. arXiv's all: field ORs an unquoted multi-word query, so a full-sentence
     hypothesis scored huge, heavily-indexed collaboration papers above
     anything on the subject (build_arxiv_query).
  2. The References section listed every reference PROVIDED rather than every
     reference USED, so retrieval noise became a bibliography
     (prune_uncited_references).

The pruning tests are the load-bearing ones: they hold even if retrieval
regresses, which is why the fix lives in code and not only in the prompt.
"""

import unittest

from retrieval.scholar_search import build_arxiv_query
from stages.stage6_paper import cited_ref_ids, prune_uncited_references

FBA_SENTENCE = (
    "The maximum growth rate predicted by flux balance analysis is invariant "
    "under a redundant biomass lower bound constraint"
)

NOISE_REFS = [
    {"ref": "R1", "year": 2014, "source": "arxiv:1411.4413",
     "title": "Observation of the rare B0s decay from CMS and LHCb data"},
    {"ref": "R2", "year": 2008, "source": "arxiv:0901.0512",
     "title": "Expected Performance of the ATLAS Experiment"},
    {"ref": "R3", "year": 2026, "source": "arxiv:2601.07595",
     "title": "Deep Search for Joint Sources of Gravitational Waves"},
]


class TestArxivQueryConstruction(unittest.TestCase):

    def test_stopwords_dropped_and_terms_anded(self):
        q = build_arxiv_query(FBA_SENTENCE, max_terms=5)
        self.assertNotIn("all:the", q)
        self.assertNotIn("all:by", q)
        self.assertNotIn("all:is", q)
        self.assertIn(" AND ", q)
        self.assertEqual(q.count("all:"), 5)

    def test_term_order_preserved_and_deduplicated(self):
        q = build_arxiv_query("growth growth rate of growth", max_terms=4)
        self.assertEqual(q, "all:growth AND all:rate")

    def test_max_terms_respected(self):
        for n in (2, 4, 6):
            self.assertEqual(
                build_arxiv_query(FBA_SENTENCE, max_terms=n).count("all:"), n
            )

    def test_already_field_qualified_passes_through(self):
        self.assertEqual(build_arxiv_query("ti:cavity flow"), "ti:cavity flow")

    def test_all_stopwords_falls_back_rather_than_emitting_empty(self):
        self.assertEqual(build_arxiv_query("the and of"), "all:the and of")

    def test_empty_query_is_empty(self):
        self.assertEqual(build_arxiv_query("   "), "")


class TestCitedRefIds(unittest.TestCase):

    def test_finds_bracketed_citations_in_body(self):
        sections = {"Background": "As shown in [R1] and later [R3].",
                    "References": "1. R1  2. R2  3. R3"}
        self.assertEqual(cited_ref_ids(sections), {"R1", "R3"})

    def test_references_section_itself_is_not_a_citation(self):
        """Otherwise every provided reference would look cited and the prune
        would never fire — the bug this whole module exists to prevent."""
        sections = {"Background": "No citations here.",
                    "References": "1. R1  2. R2  3. R3"}
        self.assertEqual(cited_ref_ids(sections), set())


class TestPruneUncitedReferences(unittest.TestCase):

    def test_the_motivating_paper_loses_every_fake_reference(self):
        sections = {
            "Background": "FBA is a linear program over a metabolic network.",
            "Results": "All three runs were rejected before execution.",
            "References": "1. R1 ...\n2. R2 ...\n3. R3 ...",
        }
        pruned, dropped = prune_uncited_references(sections, NOISE_REFS)
        self.assertEqual([d["ref"] for d in dropped], ["R1", "R2", "R3"])
        for token in ("ATLAS", "IceCube", "B0s"):
            self.assertNotIn(token, pruned["References"])

    def test_no_citations_yields_an_honest_line_not_a_fabricated_list(self):
        sections = {"Background": "No citations.", "References": "1. R1 ..."}
        pruned, _ = prune_uncited_references(sections, NOISE_REFS)
        self.assertIn("No references are cited", pruned["References"])

    def test_cited_references_are_kept(self):
        sections = {"Background": "As shown in [R2].", "References": "stale"}
        pruned, dropped = prune_uncited_references(sections, NOISE_REFS)
        self.assertIn("ATLAS", pruned["References"])
        self.assertEqual([d["ref"] for d in dropped], ["R1", "R3"])

    def test_all_cited_is_a_no_op(self):
        """Nothing dropped must mean nothing rewritten — a paper whose
        references are all used keeps the model's own section text."""
        sections = {"Background": "[R1][R2][R3]", "References": "ORIGINAL TEXT"}
        pruned, dropped = prune_uncited_references(sections, NOISE_REFS)
        self.assertEqual(dropped, [])
        self.assertEqual(pruned["References"], "ORIGINAL TEXT")

    def test_empty_refs_list_is_a_no_op(self):
        sections = {"Background": "x", "References": "ORIGINAL"}
        pruned, dropped = prune_uncited_references(sections, [])
        self.assertEqual(dropped, [])
        self.assertEqual(pruned["References"], "ORIGINAL")


if __name__ == "__main__":
    unittest.main()
