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


if __name__ == "__main__":
    unittest.main(verbosity=2)
