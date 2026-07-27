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


class TestKeywordAPIsAreGone(unittest.TestCase):
    """They cost ~100 s of throttled retries per run and contributed nothing —
    live: arXiv 503/429/429/timeout, S2 429 x4, OpenAlex 0 — while the agent made
    six WebSearch calls and cited a real paper. In the review path they ran PER
    HYPOTHESIS, so a 16-hypothesis pool paid that sixteen times."""

    def test_no_network_prefetch_in_either_path(self):
        import inspect
        import stages.generation_strategies as g
        import stages.reflection_reviews as r
        for mod in (g, r):
            src = inspect.getsource(mod)
            for call in ("= search_arxiv(", "= search_semantic_scholar(",
                         "= search_openalex(", "= web_search("):
                self.assertNotIn(call, src, f"{mod.__name__} still calls {call}")

    def test_the_local_corpus_is_kept(self):
        """Instant, free, offline, project-specific — the one worth keeping."""
        import inspect
        import stages.generation_strategies as g
        self.assertIn("search_index(", inspect.getsource(g))


class TestLocatedCitationDoesNotCrashTheNumberSignal(unittest.TestCase):
    def test_a_located_citation_has_no_snippet_and_must_not_raise(self):
        """LIVE CRASH: the warn-only unsupported-number check did refs_by_id[r],
        which KeyError'd the moment the agent cited a source it had located
        instead of a pre-fetched ref id — i.e. the behaviour we asked for."""
        from stages.generation_strategies import _unsupported_numbers
        refs_by_id = {"R1": {"snippet": "a value of 5 appears here"}}
        grounded = ["R1", "arXiv:2010.08895 (Fourier Neural Operator)"]
        texts = [" ".join(str(v) for v in (refs_by_id.get(r) or {}).values())
                 for r in grounded]
        self.assertEqual(_unsupported_numbers("the value is 5", texts), [])


class TestInstrumentMenuIsNotTheBoundary(unittest.TestCase):
    """The nudge told the generator that a hypothesis outside a named solver's
    parameter list was "worth nothing here, however novel or well-motivated". The
    questions expressible in a solver's OWN knobs are largely the ones its field
    already answered — that is what the knobs are for — so the constraint
    selected for already-answered ideas. Live: 16 of 16 answer_established."""

    def test_the_worth_nothing_veto_is_gone(self):
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertNotIn("worth nothing", n)
        self.assertNotIn("HARD CONSTRAINT", n)

    def test_the_code_sandbox_is_named_as_the_escape_hatch_for_METHOD_claims(self):
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("python_experiment", n)
        self.assertIn("about a METHOD", n)

    def test_it_does_not_pretend_code_can_settle_facts_about_the_world(self):
        """Code simulates a MODEL YOU SPECIFY, not reality. A hand-written
        simulation of whether a molecule binds returns whatever its assumptions
        imply, which is not evidence — an earlier draft of this block implied
        otherwise and would have produced hypotheses that die at execution."""
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("WHAT CODE CANNOT DO", n)
        self.assertIn("did not already encode", n)
        for real_instrument in ("rdkit", "cobrapy", "mafft", "homology_search"):
            self.assertIn(real_instrument, n)

    def test_simulated_results_must_state_their_assumptions(self):
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("say what the simulation assumes", n)

    def test_feasibility_is_taught_as_a_PRINCIPLE_not_a_parameter_list(self):
        """CHANGED 2026-07-26. Sending the parameter lists was the anchor, so they
        are gone from generation entirely (see build_feasibility_nudge). What
        remains is the principle — testable by something available, code settles
        method claims, physical facts need a real instrument — with the details
        checked downstream."""
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("testable by something available", n)
        self.assertIn("a downstream stage checks the details", n)
        self.assertNotIn("'can vary' line", n)

    def test_generation_no_longer_receives_the_contract_menu(self):
        """THE ANCHOR. Removing the veto was not enough: the very next run still
        put all 25 hypotheses on the five instruments whose contracts opened the
        context. Priming survives permission changes."""
        from stages.generation_strategies import build_feasibility_nudge
        block = build_feasibility_nudge("no-such-run")
        for leak in ("can vary", "can measure", "substrate_id", "typed_input"):
            self.assertNotIn(leak, block)

    def test_it_asks_for_domain_spread_across_the_pool(self):
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("Vary the DOMAIN across your hypotheses", n)
        self.assertIn("wasted pool", n)

    def test_it_pushes_toward_domains_with_no_solver(self):
        from stages.generation_strategies import FEASIBILITY_NUDGE_INSTRUCTION as n
        self.assertIn("no dedicated solver exists", n)
        self.assertIn("fixed rulebook", n)


class TestTheLastCagedPrompts(unittest.TestCase):
    """#16. Only the literature generator and the novelty review were freed
    initially; these are the rest. assumptions_identification and
    research_expansion were never snippet-framed (the first reasons
    conditionally, the second reviews the pool), so there was nothing to uncage
    there — the real list was shorter than the task described."""

    def test_the_debate_personas_may_search(self):
        from stages.generation_strategies import DEBATE_SYSTEM_PROMPT as p
        self.assertIn("SEARCH THE WEB YOURSELF", p)
        self.assertIn("not the boundary of the", p)

    def test_the_observation_review_finds_its_own_observations(self):
        """A hypothesis is interesting when it explains something real the
        accepted account handles badly — undecidable from a keyword pre-fetch."""
        from stages.reflection_reviews import OBSERVATION_REVIEW_SYSTEM_PROMPT as p
        self.assertIn("FIND THE OBSERVATIONS YOURSELF", p)
        self.assertIn("Cite each observation so a human can find it", p)

    def test_the_simulation_review_may_actually_compute(self):
        """It was told to simulate 'mentally' while holding Bash. It had already
        started running code on its own initiative in live runs."""
        from stages.reflection_reviews import SIMULATION_REVIEW_SYSTEM_PROMPT as p
        self.assertIn("YOU DO NOT HAVE TO DO THIS IN YOUR HEAD", p)
        self.assertIn("worth more than one you imagined", p)
        self.assertNotIn("Mentally simulate", p)


class TestTheReviewPoolRunsConcurrently(unittest.TestCase):
    """MEASURED WASTE. A live run logged 157 ideation calls at a mean of 127
    SECONDS each, entirely serial. Pool 25 x 4 reviews x 2 rounds is ~200 calls,
    so ideation alone was heading for eight hours before one experiment ran — and
    it consumed 15% of a weekly usage limit producing nothing.

    Each hypothesis's reviews are independent of every other hypothesis's, so the
    pool is embarrassingly parallel and nothing exploited it. That is what made
    'buy a bigger pool' cost wall-clock linearly."""

    def test_the_pool_is_reviewed_concurrently_and_in_order(self):
        import threading
        import stages.reflection_reviews as r
        live, peak, lock = [0], [0], threading.Lock()

        def one(h):
            with lock:
                live[0] += 1
                peak[0] = max(peak[0], live[0])
            import time
            time.sleep(0.05)
            with lock:
                live[0] -= 1
            return {"hypothesis_id": h["id"]}

        pool = [{"id": f"h{i}"} for i in range(8)]
        out = r._review_pool_concurrently("rid", pool, one)
        self.assertGreater(peak[0], 1, "reviews ran one at a time")
        # order must survive concurrency: evidence and logs are read positionally
        self.assertEqual([o["hypothesis_id"] for o in out],
                         [h["id"] for h in pool])

    def test_concurrency_is_bounded(self):
        """Each worker holds a model call that may run its own tool loop; an
        unbounded pool would blow a rate-limit window in seconds."""
        import stages.reflection_reviews as r
        self.assertLessEqual(r._review_concurrency(), 16)
        self.assertGreaterEqual(r._review_concurrency(), 1)

    def test_a_single_survivor_does_not_spin_up_a_pool(self):
        import stages.reflection_reviews as r
        self.assertEqual(
            r._review_pool_concurrently("rid", [{"id": "h1"}], lambda h: {"id": h["id"]}),
            [{"id": "h1"}])

    def test_rounds_defaults_to_one(self):
        """A second round re-runs the whole reflection chain over the whole pool
        — it doubles the most expensive thing in the system and must be chosen."""
        import stages.stage1_ideation as s1
        self.assertEqual(s1._rounds_default(), 1)

    def test_rounds_is_overridable_and_capped(self):
        import os
        from unittest.mock import patch
        import stages.stage1_ideation as s1
        with patch.dict(os.environ, {"RESEARCH_IDEATION_ROUNDS": "2"}):
            self.assertEqual(s1._rounds_default(), 2)
        with patch.dict(os.environ, {"RESEARCH_IDEATION_ROUNDS": "99"}):
            self.assertLessEqual(s1._rounds_default(), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
