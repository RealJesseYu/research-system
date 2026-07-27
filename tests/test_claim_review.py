"""test_claim_review.py — the advisory mechanism check beside the wall.

Call-free (the reviewer call is injected). Proves:
  - only code-carrying claims are sent, bounded, with true indices kept;
  - a flag attaches as a `mechanism_review` caveat on the RIGHT finding and
    never touches `verified`;
  - a flag without a quoted note does not travel; a passing review adds nothing;
  - invented claim indices from the model are ignored;
  - CLAIM_REVIEW=0 disables; a crashing call returns {} (advisory: silence
    over crash) — never raises.

Run directly: venv/bin/python3 tests/test_claim_review.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.claim_review import (_payload_from_claims,  # noqa: E402
                                 attach_mechanism_reviews,
                                 review_claim_mechanisms)


def _claims():
    return [
        {"value": 1.0, "label": "sweep e adaptively",
         "artifact": {"kind": "code", "code": "e = 2\nprint(1.0)",
                      "quantity": "x"}},
        {"value": 2.0, "label": "substrate run",
         "artifact": {"kind": "substrate", "substrate_id": "rdkit",
                      "typed_input": {}, "quantity": "y"}},
        {"value": 3.0, "label": "no artifact", "artifact": None},
        {"value": 4.0, "label": "baseline k-fold k=10",
         "artifact": {"kind": "code", "code": "run_efold(e=50)",
                      "quantity": "z"}},
    ]


class PayloadTests(unittest.TestCase):
    def test_only_code_claims_travel_with_true_indices(self):
        payload = _payload_from_claims(_claims())
        self.assertEqual([p["claim_index"] for p in payload], [0, 3])

    def test_empty_code_skipped(self):
        payload = _payload_from_claims(
            [{"label": "x", "artifact": {"kind": "code", "code": "   "}}])
        self.assertEqual(payload, [])


class ReviewTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("CLAIM_REVIEW", None)

    def test_flag_maps_by_true_claim_index(self):
        def fake_call(stage, prompt, stage_input, schema, **kw):
            sent = {c["claim_index"] for c in stage_input["claims"]}
            self.assertEqual(sent, {0, 3})
            return ({"reviews": [
                {"claim_index": 3, "mechanism_ok": False,
                 "note": "label says k-fold but code is `run_efold(e=50)`"},
                {"claim_index": 0, "mechanism_ok": True, "note": ""},
                {"claim_index": 9, "mechanism_ok": False, "note": "invented"},
            ]}, {})
        reviews = review_claim_mechanisms(_claims(), call=fake_call)
        self.assertIn(3, reviews)
        self.assertFalse(reviews[3]["mechanism_ok"])
        self.assertNotIn(9, reviews)  # invented index ignored

    def test_kill_switch(self):
        os.environ["CLAIM_REVIEW"] = "0"
        try:
            called = []
            reviews = review_claim_mechanisms(
                _claims(), call=lambda *a, **k: called.append(1))
            self.assertEqual(reviews, {})
            self.assertEqual(called, [])
        finally:
            os.environ.pop("CLAIM_REVIEW", None)

    def test_crashing_call_is_silence_not_raise(self):
        def boom(*a, **k):
            raise RuntimeError("transport died")
        self.assertEqual(review_claim_mechanisms(_claims(), call=boom), {})

    def test_no_reviewable_claims_makes_no_call(self):
        called = []
        out = review_claim_mechanisms(
            [{"label": "x", "artifact": None}],
            call=lambda *a, **k: called.append(1))
        self.assertEqual(out, {})
        self.assertEqual(called, [])


class AttachTests(unittest.TestCase):
    def test_flag_lands_on_right_finding_and_wall_untouched(self):
        findings = [{"label": "a", "verified": True},
                    {"label": "b", "verified": True},
                    {"label": "c", "verified": False}]
        claimed = [(0, findings[0]), (1, findings[1])]  # wall's pairing
        reviews = {1: {"mechanism_ok": False, "note": "code says e=50"}}
        n = attach_mechanism_reviews(findings, claimed, reviews)
        self.assertEqual(n, 1)
        self.assertNotIn("mechanism_review", findings[0])
        self.assertEqual(findings[1]["mechanism_review"]["note"],
                         "code says e=50")
        self.assertTrue(findings[1]["verified"])  # caveat, never a veto
        self.assertNotIn("mechanism_review", findings[2])

    def test_pass_and_noteless_flag_add_nothing(self):
        findings = [{"label": "a", "verified": True},
                    {"label": "b", "verified": True}]
        claimed = [(0, findings[0]), (1, findings[1])]
        reviews = {0: {"mechanism_ok": True, "note": ""},
                   1: {"mechanism_ok": False, "note": "  "}}  # no evidence
        n = attach_mechanism_reviews(findings, claimed, reviews)
        self.assertEqual(n, 0)
        self.assertNotIn("mechanism_review", findings[0])
        self.assertNotIn("mechanism_review", findings[1])


if __name__ == "__main__":
    unittest.main()
