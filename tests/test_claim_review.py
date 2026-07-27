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
import tempfile
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


class TestItReachesTheShapesProductionActuallyEmits(unittest.TestCase):
    """This pass was INERT in production for its whole life.

    It filtered for artifact kind "code", which the only production claim builder
    (free_experimenter._finding_artifact) never emits: a saved code file becomes
    "workspace_file" and everything else becomes "substrate". So
    review_claim_mechanisms returned {} on every real run and the documented
    88%-catch safeguard could not attach a caveat to anything — while the tests
    stayed green because they only ever built kind "code".

    These pin the shapes that must be reviewable and, just as importantly, the
    ones that must NOT be: a claim whose number came from a real instrument is
    already a contract, and reviewing it would be words about code no model
    wrote.
    """

    def setUp(self):
        self.ws = Path(tempfile.mkdtemp())
        self.f = self.ws / "solve.py"
        self.f.write_text("import math\nmetrics['x'] = math.sqrt(2)\n")

    def _claim(self, artifact, label="l", value=1.0):
        return {"label": label, "value": value, "artifact": artifact}

    def test_workspace_file_is_reviewed_with_code_read_off_disk(self):
        """The common production shape: the code lives in the file, not the dict."""
        p = _payload_from_claims([self._claim(
            {"kind": "workspace_file", "path": str(self.f), "quantity": "x"})])
        self.assertEqual(len(p), 1)
        self.assertIn("math.sqrt", p[0]["code"])

    def test_python_experiment_substrate_is_reviewed(self):
        """Its typed_input.code IS model-authored — the instrument is the model."""
        p = _payload_from_claims([self._claim(
            {"kind": "substrate", "substrate_id": "python_experiment",
             "typed_input": {"code": "metrics['y']=0.5", "quantity": "y"}})])
        self.assertEqual(len(p), 1)
        self.assertIn("metrics['y']", p[0]["code"])

    def test_a_real_instrument_substrate_is_not_reviewed(self):
        """Same boundary the planted-constant tripwire draws: a solver's typed
        input is a contract, not code a model wrote."""
        p = _payload_from_claims([self._claim(
            {"kind": "substrate", "substrate_id": "cavity_2d_cfd",
             "typed_input": {"case_name": "c"}})])
        self.assertEqual(p, [])

    def test_an_unreadable_workspace_file_is_skipped_not_raised(self):
        """The wall already reports an artifact it cannot re-run; an advisory
        pass must not crash on a vanished file."""
        p = _payload_from_claims([self._claim(
            {"kind": "workspace_file", "path": str(self.ws / "gone.py")})])
        self.assertEqual(p, [])

    def test_a_claim_with_no_artifact_is_skipped(self):
        self.assertEqual(_payload_from_claims([self._claim(None)]), [])

    def test_claim_indices_survive_the_filtering(self):
        """The reviewer's verdicts are keyed by index into the ORIGINAL list, so
        a shifted index would attach a caveat to the wrong claim."""
        claims = [
            self._claim(None, "skipped"),
            self._claim({"kind": "substrate", "substrate_id": "cavity_2d_cfd",
                         "typed_input": {}}, "also skipped"),
            self._claim({"kind": "workspace_file", "path": str(self.f)}, "reviewed"),
        ]
        p = _payload_from_claims(claims)
        self.assertEqual([q["claim_index"] for q in p], [2])
        self.assertEqual(p[0]["label"], "reviewed")

    def test_the_pass_end_to_end_reaches_the_model_on_production_shapes(self):
        seen = {}

        def fake_call(stage, sysp, inp, schema, **kw):
            seen["n"] = len(inp["claims"])
            return {"reviews": [{"claim_index": q["claim_index"],
                                 "mechanism_ok": True, "note": "ok"}
                                for q in inp["claims"]]}, {}

        out = review_claim_mechanisms(
            [self._claim({"kind": "workspace_file", "path": str(self.f)})],
            call=fake_call)
        self.assertEqual(seen.get("n"), 1)
        self.assertIn(0, out)


if __name__ == "__main__":
    unittest.main()
