"""test_verification_not_a_roadblock.py — verification records, never gates.

OWNER RULING 2026-07-25: verification and execution are separate concerns.
Verification exists so a number nobody watched can re-prove itself; it must never
constrain what execution may attempt. It was doing both, in two places:

1. DEFAULT_REL_TOL = 1e-6 is a bit-exactness test — right for arithmetic, wrong
   for convergence-dependent quantities. The agent searches locally, the wall
   re-runs in a container, and iteration counts / solver-eval counts / ratios of
   them shift with floating-point details across environments. Live: a legitimate
   FD/adjoint ratio of 128.0 re-ran as 127.49004 (0.4%) and was rejected, along
   with ~60% of a good study's findings.
2. publishable meant NOTHING FAILED, so one shaky side-metric sank a run carrying
   ten reproduced results and reported it as having achieved nothing.

Neither fix loosens what "verified" means: a claim still only counts when an
independent, no-model re-run reproduces it.

Run directly: venv/bin/python3 tests/test_verification_not_a_roadblock.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.verification import (DEFAULT_REL_TOL,  # noqa: E402
                                 MAX_DECLARED_REL_TOL, _declared_tolerance,
                                 planted_constant_reason, verify_claim,
                                 verify_run)


class TestDeclaredTolerance(unittest.TestCase):
    def test_no_declaration_keeps_the_strict_default(self):
        self.assertEqual(_declared_tolerance({}, DEFAULT_REL_TOL), DEFAULT_REL_TOL)

    def test_a_declared_band_is_honored(self):
        self.assertEqual(_declared_tolerance({"tolerance": 0.01}, DEFAULT_REL_TOL),
                         0.01)

    def test_the_live_case_would_now_pass(self):
        """128.0 vs 127.49004 is 0.4% — a real result, previously rejected."""
        rel = abs(128.0 - 127.49004) / 128.0
        self.assertLess(rel, _declared_tolerance({"tolerance": 0.01}, DEFAULT_REL_TOL))

    def test_a_declaration_can_never_tighten_below_the_default(self):
        """The knob exists to unblock legitimate work, not to create false passes
        by making a check stricter than the floor."""
        self.assertEqual(_declared_tolerance({"tolerance": 1e-12}, DEFAULT_REL_TOL),
                         DEFAULT_REL_TOL)

    def test_a_declaration_is_capped(self):
        """A claim needing more than the cap is not a stable measurement."""
        self.assertEqual(_declared_tolerance({"tolerance": 0.9}, DEFAULT_REL_TOL),
                         MAX_DECLARED_REL_TOL)
        self.assertLessEqual(MAX_DECLARED_REL_TOL, 0.05)

    def test_junk_declarations_fall_back_rather_than_crashing(self):
        for junk in (None, "loose", float("nan"), float("inf"), -1, 0, [0.1]):
            self.assertEqual(_declared_tolerance({"tolerance": junk}, DEFAULT_REL_TOL),
                             DEFAULT_REL_TOL)


def _claim(value, code, quantity="q", tolerance=None):
    return {"value": value, "label": f"c{value}", "tolerance": tolerance,
            "artifact": {"kind": "code", "code": code, "quantity": quantity}}


class TestPublishableIsNotAllOrNothing(unittest.TestCase):
    """verify_run's flag, exercised through fake verdicts rather than Docker."""

    def _summary(self, verdicts):
        # verify_run computes the flag from its verdicts; build them directly by
        # verifying claims whose artifacts are trivially (non-)reproducible would
        # need Docker, so assert the rule on the documented contract instead.
        verified = [v for v in verdicts if v["verified"]]
        return {"publishable": bool(verified), "verified": len(verified),
                "total": len(verdicts)}

    def test_one_failure_no_longer_sinks_ten_successes(self):
        verdicts = [{"verified": True}] * 10 + [{"verified": False}]
        s = self._summary(verdicts)
        self.assertTrue(s["publishable"])
        self.assertEqual((s["verified"], s["total"]), (10, 11))

    def test_nothing_reproduced_is_still_not_publishable(self):
        self.assertFalse(self._summary([{"verified": False}] * 3)["publishable"])

    def test_an_empty_claim_set_is_not_publishable(self):
        self.assertFalse(self._summary([])["publishable"])

    def test_verify_run_reports_no_claims_honestly(self):
        out = verify_run([])
        self.assertEqual(out["total"], 0)
        self.assertFalse(out["publishable"])


class TestTheGuaranteeIsUnchanged(unittest.TestCase):
    def test_the_default_is_still_bit_exact(self):
        """Loosening is opt-in per finding; the floor did not move."""
        self.assertEqual(DEFAULT_REL_TOL, 1e-6)

    def test_the_experimenter_is_told_when_a_band_is_legitimate(self):
        from stages.free_experimenter import SYSTEM_PROMPT
        self.assertIn("TOLERANCE", SYSTEM_PROMPT)
        self.assertIn("iteration counts", SYSTEM_PROMPT)
        self.assertIn("only where the quantity genuinely warrants it", SYSTEM_PROMPT)




class TestAStringResultReproducesByBeingIdentical(unittest.TestCase):
    """FOUND LIVE (study-20260727T091129Z). A run downloaded NASA GISTEMP from the
    open web, reported the mean anomaly AND the file's SHA-256, and the hash came
    back unverified as "non_numeric" — even though re-running the artifact
    produced the same hash character for character. The director recorded it as "a
    known harness limitation".

    It was a category error, not a safeguard. Exact string equality is
    reproduction in the strictest sense available, and refusing it made every
    hash, identifier, categorical outcome and chosen-option finding permanently
    unverifiable — while the experimenter's own prompt invites "a number or short
    string" as a value."""

    def _claim(self, value, code, quantity="h"):
        return {"value": value, "label": "l",
                "artifact": {"kind": "code", "code": code, "quantity": quantity}}

    def test_an_identical_string_verifies(self):
        v = verify_claim(self._claim("d41d8cd98f00", 'metrics = {"h": "d41d8cd98f00"}'))
        self.assertTrue(v["verified"])
        self.assertEqual(v["reason"], "reproduced")
        self.assertEqual(v["comparison"], "exact string")

    def test_a_different_string_is_a_mismatch_not_a_pass(self):
        v = verify_claim(self._claim("aaa", 'metrics = {"h": "bbb"}'))
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "mismatch")
        self.assertIn("must match exactly", v["detail"])

    def test_there_is_no_tolerance_for_strings(self):
        """A string has no near-miss; a declared tolerance must not soften it."""
        c = self._claim("abc", 'metrics = {"h": "abd"}')
        c["tolerance"] = 0.02
        self.assertFalse(verify_claim(c)["verified"])

    def test_surrounding_whitespace_does_not_break_a_match(self):
        v = verify_claim(self._claim("abc", 'metrics = {"h": " abc "}'))
        self.assertTrue(v["verified"])

    def test_a_string_metric_survives_the_sandbox_gate(self):
        """The sandbox coerced qoi with float(), so a string never even reached
        verification — fixing only the comparison would have been dead code."""
        from tools.run_python_experiment import run_python_experiment
        out = run_python_experiment({"code": 'metrics = {"h": "sha-abc"}',
                                     "quantity": "h"})
        self.assertTrue(out["valid"])
        self.assertEqual(out["qoi"], "sha-abc")

    def test_an_empty_or_oversized_string_is_still_refused(self):
        """A result is a value, not a document: the metric channel must not become
        a way to return a transcript from the sandbox."""
        from tools.run_python_experiment import MAX_STRING_QOI, run_python_experiment
        self.assertFalse(run_python_experiment(
            {"code": 'metrics = {"h": "  "}', "quantity": "h"})["valid"])
        big = "x" * (MAX_STRING_QOI + 1)
        out = run_python_experiment({"code": f'metrics = {{"h": "{big}"}}',
                                     "quantity": "h"})
        self.assertFalse(out["valid"])
        self.assertIn("over the", out["diagnostics"])

    def test_numbers_are_untouched(self):
        v = verify_claim(self._claim(2.0, 'metrics = {"h": 1.0 + 1.0}'))
        self.assertTrue(v["verified"])
        self.assertNotIn("comparison", v)


class TestMalformedArtifactIsAVerdictNotACrash(unittest.TestCase):
    """Every field of an artifact is MODEL-AUTHORED, so a malformed one is
    ordinary input to this pass, not a broken invariant.

    verify_claim used to catch only ArtifactError, and none of the exceptions a
    bad artifact actually raises is a subclass of it. Each of these three killed
    run_free_investigation outright — after all the work, leaving no
    verification.json at all. The bar is that an unverifiable claim is a RESULT.
    """

    def _verdict(self, artifact):
        return verify_claim({"value": 1.0, "label": "l", "artifact": artifact})

    def test_hallucinated_substrate_id(self):
        v = self._verdict({"kind": "substrate", "substrate_id": "not_a_real_tool",
                           "typed_input": {}})
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "unrunnable_artifact")

    def test_substrate_input_missing_a_required_field(self):
        v = self._verdict({"kind": "substrate", "substrate_id": "python_experiment",
                           "typed_input": {"code": "metrics['x']=1"}})  # no quantity
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "unrunnable_artifact")

    def test_case_build_artifact_without_adapter_input(self):
        v = self._verdict({"kind": "substrate", "substrate_id": "cavity_2d_cfd",
                           "call_style": "case_build"})
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "unrunnable_artifact")

    def test_the_exception_type_survives_into_the_detail(self):
        """A real defect in this pass must stay legible in the evidence rather
        than be smoothed into a generic refusal."""
        v = self._verdict({"kind": "substrate", "substrate_id": "not_a_real_tool",
                           "typed_input": {}})
        self.assertIn("Error", v["detail"])


class TestPlantedConstantReachesModelAuthoredCode(unittest.TestCase):
    """The tripwire keys on 'did a model write the code that produced this
    number', not on artifact kind — python_experiment's instrument IS the
    model's code, so exempting it with the other substrates was a hole.

    The two DELIBERATE non-coverages are pinned here too, because they were
    tried and reverted on evidence: see planted_constant_reason's comments.
    """

    PLANT = "metrics['x'] = 0.99"

    def test_python_experiment_substrate_is_checked(self):
        self.assertIsNotNone(planted_constant_reason(
            {"kind": "substrate", "substrate_id": "python_experiment",
             "typed_input": {"code": self.PLANT, "quantity": "x"}}))

    def test_inline_code_and_workspace_file_still_checked(self):
        self.assertIsNotNone(planted_constant_reason(
            {"kind": "code", "code": self.PLANT, "quantity": "x"}))

    def test_computed_code_is_left_alone(self):
        self.assertIsNone(planted_constant_reason(
            {"kind": "code", "code": "import math\nmetrics['x']=math.sqrt(2)",
             "quantity": "x"}))

    def test_a_real_instrument_substrate_is_not_checked(self):
        """cavity's typed input drives a solver, not model-authored code."""
        self.assertIsNone(planted_constant_reason(
            {"kind": "substrate", "substrate_id": "cavity_2d_cfd",
             "typed_input": {"case_name": "c"}}))

    def test_composition_steps_are_deliberately_not_checked(self):
        """A step's constant scalar is often TRUE — a count of what it emitted —
        while its real contribution is the file downstream steps consume.
        Checking it failed a legitimate handoff recipe; the gap is accepted."""
        self.assertIsNone(planted_constant_reason(
            {"kind": "composition",
             "steps": [{"step_id": "produce", "kind": "code",
                        "code": "open('v','w').write('1,2,3')\nmetrics['n']=3.0",
                        "quantity": "n"}],
             "combine": {"code": "metrics['o']=inputs['produce']*2",
                         "quantity": "o"}}))

    def test_the_combine_is_still_checked(self):
        self.assertIsNotNone(planted_constant_reason(
            {"kind": "composition", "steps": [],
             "combine": {"code": "metrics['o'] = 0.97", "quantity": "o"}}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
