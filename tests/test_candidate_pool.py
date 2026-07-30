"""test_candidate_pool.py — the ideation POOL channel (2026-07-30).

Proves the fix for the arm-C funnel: ideation generated 33 candidates, 24 of them
`verdict: "pass"` were held back by the promise triage and never deep-reviewed, and
the director was handed two bare statements. Nothing here changes what gets
reviewed or ranked — it proves the whole pool, with the review reasoning that
decided each row, now travels ALONGSIDE the unchanged ranked digest.

Run directly: venv/bin/python3 tests/test_candidate_pool.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.capabilities as C  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.study import create_study  # noqa: E402
from stages.stage1_ideation import build_candidate_pool  # noqa: E402


def _hyp(hid, n=None):
    return {"id": hid, "statement": f"statement {hid}", "rationale": f"why {hid}"}


# The shape reflect_on_pool actually writes, reduced to the five fates.
EVIDENCE = {
    "pool_size": 5,
    "initial_review": [
        {"id": "h1", "verdict": "pass", "promise": 4, "reason": "top pick"},
        {"id": "h2", "verdict": "pass", "promise": 3, "reason": "reviewed, dropped"},
        {"id": "h3", "verdict": "pass", "promise": 4,
         "reason": "Modified B31G/RSTRENG already codified the effective-area "
                   "correction the candidate proposes to rediscover."},
        {"id": "h4", "verdict": "pass", "promise": 3, "reason": "flawed on scrutiny"},
        {"id": "h5", "verdict": "discard", "promise": 1, "reason": "incoherent"},
    ],
    "triaged_lower_promise": [
        {"id": "h3", "verdict": "pass", "promise": 4,
         "reason": "Modified B31G/RSTRENG already codified the effective-area "
                   "correction the candidate proposes to rediscover."},
    ],
    "discarded_by_deep_verification": [{"id": "h4", "reason": "circular"}],
    "discarded_by_initial_review": [{"id": "h5", "verdict": "discard"}],
    "rescued_from_triage": [],
    "final_reflections": [
        {"hypothesis_id": "h1", "novelty": "novel", "answer_established": False,
         "quality": 5, "critique": "good", "addressable_notes": ["check units"]},
        {"hypothesis_id": "h2", "novelty": "known", "answer_established": True,
         "quality": 2, "critique": "already measured", "addressable_notes": []},
    ],
}
HYPS = [_hyp(f"h{n}") for n in range(1, 6)]
SURVIVORS = [{"id": "h1", "statement": "statement h1", "rationale": "why h1",
              "novelty": "novel", "critique": "good", "quality": 5,
              "addressable_notes": ["check units"]}]


class TestBuildCandidatePool(unittest.TestCase):
    def test_every_candidate_appears_with_its_fate(self):
        pool = build_candidate_pool(HYPS, EVIDENCE, SURVIVORS,
                                    [SURVIVORS[0]])
        self.assertEqual(len(pool), 5)
        by_id = {e["id"]: e for e in pool}
        self.assertEqual(by_id["h1"]["status"], "survivor")
        self.assertEqual(by_id["h2"]["status"], "reviewed")
        self.assertEqual(by_id["h3"]["status"], "not_reviewed")
        self.assertEqual(by_id["h4"]["status"], "discarded_deep")
        self.assertEqual(by_id["h5"]["status"], "discarded_initial")

    def test_the_sentence_that_was_lost_now_travels(self):
        """The arm-C failure in one assertion: a pass-verdict candidate that was
        never deep-reviewed still carries the triage reason naming the state of
        the art. That sentence never left reflection_reviews.json before."""
        pool = build_candidate_pool(HYPS, EVIDENCE, SURVIVORS, [SURVIVORS[0]])
        h3 = next(e for e in pool if e["id"] == "h3")
        self.assertEqual(h3["status"], "not_reviewed")
        self.assertEqual(h3["screen_verdict"], "pass")
        self.assertEqual(h3["promise"], 4)
        self.assertIn("already codified", h3["screen_reason"])

    def test_survivors_lead_and_carry_review_reasoning_and_rank(self):
        pool = build_candidate_pool(HYPS, EVIDENCE, SURVIVORS, [SURVIVORS[0]])
        self.assertEqual(pool[0]["id"], "h1")
        self.assertEqual(pool[0]["rank"], 1)
        self.assertEqual(pool[0]["quality"], 5)
        self.assertEqual(pool[0]["novelty"], "novel")
        self.assertEqual(pool[0]["critique"], "good")
        self.assertEqual(pool[0]["addressable_notes"], ["check units"])

    def test_deep_discard_reason_travels(self):
        pool = build_candidate_pool(HYPS, EVIDENCE, SURVIVORS, [SURVIVORS[0]])
        h4 = next(e for e in pool if e["id"] == "h4")
        self.assertEqual(h4["discard_reason"], "circular")

    def test_evolution_variant_is_appended_not_dropped(self):
        """ev2 ranked FIRST in study-20260730T034915Z and has no generation-pool
        row, so a pool built only from `hypotheses` would omit the winner."""
        variant = {"id": "ev2", "statement": "evolved", "rationale": "r",
                   "novelty": "novel", "quality": 4, "critique": "c"}
        pool = build_candidate_pool(HYPS, EVIDENCE, SURVIVORS,
                                    [variant, SURVIVORS[0]])
        self.assertEqual(pool[0]["id"], "ev2")
        self.assertEqual(pool[0]["status"], "survivor_variant")
        self.assertEqual(pool[0]["rank"], 1)
        self.assertEqual(pool[1]["id"], "h1")

    def test_pure_and_never_raises_on_junk(self):
        self.assertEqual(build_candidate_pool([], {}, [], []), [])
        self.assertEqual(build_candidate_pool(None, None, None, None), [])
        # a malformed row is skipped, not fatal
        self.assertEqual(len(build_candidate_pool(
            [{"no_id": 1}, _hyp("h9")], {}, [], [])), 1)


class TestCapabilityDelivery(unittest.TestCase):
    """The second chokepoint: the arc digest was {id, statement} x 8 and threw
    the reasoning away."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = create_study("goal", study_id="s", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_pool(self, runs_root, pool):
        d = runs_root / C._capability_run_id(self.study, 1) / "stage1"
        d.mkdir(parents=True)
        (d / "candidate_pool.json").write_text(json.dumps(pool))

    def test_pool_reaches_the_result_beside_the_unchanged_digest(self):
        pool = [{"id": "h1", "statement": "A", "status": "survivor", "rank": 1},
                {"id": "h3", "statement": "C", "status": "not_reviewed",
                 "promise": 4, "screen_reason": "already codified"}]
        self._write_pool(self.root, pool)
        real_read = C.read_candidate_pool
        C.read_candidate_pool = lambda rid: real_read(rid, runs_root=self.root)
        try:
            r = C.run_ideation({"action": "call_ideation", "domain": "q"},
                               self.study, Budget(5), 1,
                               run=lambda d, s, q: [{"id": "h1", "statement": "A"}])
        finally:
            C.read_candidate_pool = real_read
        # the digest is exactly what it always was
        self.assertEqual(r["hypotheses"], [{"id": "h1", "statement": "A"}])
        # and the pool now rides beside it
        self.assertEqual([e["id"] for e in r["candidate_pool"]], ["h1", "h3"])
        self.assertIn("already codified", r["candidate_pool"][1]["screen_reason"])
        self.assertIn("never deep-reviewed", r["candidate_pool_note"])

    def test_no_pool_on_disk_means_no_pool_keys(self):
        """Every offline/injected path keeps its pre-existing result exactly."""
        r = C.run_ideation({"action": "call_ideation", "domain": "q"},
                           self.study, Budget(5), 1,
                           run=lambda d, s, q: [{"id": "h1", "statement": "A"}])
        self.assertNotIn("candidate_pool", r)
        self.assertNotIn("candidate_pool_note", r)
        self.assertEqual(r["detail"],
                         "1 candidate direction(s) at depth=quick for: q")

    def test_reader_never_raises(self):
        self.assertEqual(C.read_candidate_pool("nope", runs_root=self.root), [])
        d = self.root / "bad" / "stage1"
        d.mkdir(parents=True)
        (d / "candidate_pool.json").write_text("{not json")
        self.assertEqual(C.read_candidate_pool("bad", runs_root=self.root), [])

    def test_pool_is_bounded(self):
        self._write_pool(self.root, [{"id": f"h{n}", "status": "not_reviewed"}
                                     for n in range(200)])
        real_read = C.read_candidate_pool
        C.read_candidate_pool = lambda rid: real_read(rid, runs_root=self.root)
        try:
            r = C.run_ideation({"action": "call_ideation", "domain": "q"},
                               self.study, Budget(5), 1,
                               run=lambda d, s, q: [{"id": "h1", "statement": "A"}])
        finally:
            C.read_candidate_pool = real_read
        self.assertEqual(len(r["candidate_pool"]), C._MAX_POOL_ITEMS)


if __name__ == "__main__":
    unittest.main()
