"""
test_triage_rescue — the held-back candidates are a RESERVE, not a bin.

The promise triage (2026-07-27) deep-reviews only the top MAX_DEEP_REVIEW
candidates and logs the rest as "held back as lower promise (recorded, not
discarded)". But if every reviewed candidate then died on a fundamental flaw,
reflect_on_pool raised "all N candidates were discarded" and — in round 1 —
crashed the whole run, while PASSING, NEVER-REVIEWED candidates sat untouched.

Two things were wrong with that. The message was false: they were not discarded,
they were never looked at. And the behaviour threw away usable research — deep
verification killed 7 of 8 in a witnessed run, so "the whole batch dies" is a
live shape, not a corner case.

A chat handed eight bad ideas and eight unexamined ones does not stop; it looks
at the unexamined ones. Same rule as filter_survivors' 2026-07-25 change: a
screening stage REPORTS, it does not veto.

Offline: every model call is replaced by a fake, so this exercises the control
flow and nothing else.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import stages.reflection_reviews as R  # noqa: E402


class TriageRescueTestCase(unittest.TestCase):
    POOL = [{"id": f"h{i}", "statement": f"s{i}", "rationale": "r"}
            for i in range(1, 6)]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)
        self.evidence_dir = Path("evidence")
        self.evidence_dir.mkdir()
        self._saved = {name: getattr(R, name) for name in (
            "initial_review", "gather_review_refs", "full_review",
            "scrutiny_review", "recurrent_tournament_review")}
        os.environ["RESEARCH_DEEP_REVIEW_MAX"] = "2"

    def tearDown(self):
        for name, fn in self._saved.items():
            setattr(R, name, fn)
        os.environ.pop("RESEARCH_DEEP_REVIEW_MAX", None)
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def _wire(self, doomed):
        """Fakes where `doomed` ids are the highest-promise AND die on flaws."""
        R.initial_review = lambda *a, **k: [
            {"id": h["id"], "verdict": "pass", "reason": "",
             "promise": 5 if h["id"] in doomed else 1} for h in self.POOL]
        R.gather_review_refs = lambda run_id, h: ([{"ref": "R1"}], {})
        R.full_review = lambda run_id, d, h, refs, fb=None: {
            "novelty": "novel", "answer_established": False, "critique": "c",
            "quality": 3, "novelty_rationale": "x", "novelty_grounded_in": ["R1"]}
        R.scrutiny_review = lambda run_id, d, h, mb, fb=None: {
            "deep_verification": {
                "fundamental_flaw": h["id"] in doomed,
                "summary": "fatal" if h["id"] in doomed else "",
                "addressable_notes": []},
            "observation": {"accounts_for": "yes"},
            "simulation": {"failure_scenarios": []}}
        R.recurrent_tournament_review = lambda *a, **k: None

    def _run(self):
        reflections, _ = R.reflect_on_pool(
            "t", "dom", self.POOL, None, self.evidence_dir)
        evidence = json.loads(
            (self.evidence_dir / "reflection_reviews.json").read_text())
        return reflections, evidence


class TestTheReserveIsReviewedRatherThanHalting(TriageRescueTestCase):
    def test_the_run_continues_when_every_reviewed_candidate_dies(self):
        self._wire(doomed={"h1", "h2"})       # the two highest-promise
        reflections, _ = self._run()
        self.assertTrue(reflections)          # was: RuntimeError, run over

    def test_the_survivors_are_the_held_back_candidates(self):
        self._wire(doomed={"h1", "h2"})
        reflections, _ = self._run()
        self.assertEqual([r["hypothesis_id"] for r in reflections],
                         ["h3", "h4", "h5"])

    def test_the_rescue_is_recorded_in_the_evidence(self):
        """A reader has to be able to tell a rescued survivor from a
        first-choice one."""
        self._wire(doomed={"h1", "h2"})
        _, evidence = self._run()
        self.assertEqual(evidence["rescued_from_triage"], ["h3", "h4", "h5"])

    def test_the_deaths_are_still_recorded_honestly(self):
        self._wire(doomed={"h1", "h2"})
        _, evidence = self._run()
        self.assertEqual(
            sorted(x["id"] for x in evidence["discarded_by_deep_verification"]),
            ["h1", "h2"])


class TestTheNormalPathIsUnchanged(TriageRescueTestCase):
    def test_no_rescue_when_the_first_batch_survives(self):
        """The reserve costs nothing on the normal path — it is reviewed ONLY
        when the first batch left nothing."""
        self._wire(doomed=set())
        reflections, evidence = self._run()
        self.assertEqual([r["hypothesis_id"] for r in reflections], ["h1", "h2"])
        self.assertEqual(evidence["rescued_from_triage"], [])

    def test_a_partial_survival_does_not_trigger_the_rescue(self):
        """One survivor is enough; the reserve is for ZERO."""
        self._wire(doomed={"h1"})
        reflections, evidence = self._run()
        self.assertEqual([r["hypothesis_id"] for r in reflections], ["h2"])
        self.assertEqual(evidence["rescued_from_triage"], [])


class TestAGenuinelyEmptyPoolStillHalts(TriageRescueTestCase):
    def test_everything_dying_including_the_reserve_still_raises(self):
        """The honest halt is preserved — it just now means what it says,
        because the reserve was examined too."""
        self._wire(doomed={h["id"] for h in self.POOL})
        with self.assertRaises(RuntimeError) as cm:
            self._run()
        self.assertIn("held back by the promise triage", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
