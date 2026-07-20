"""
test_barren_redesign — the BARREN-RUN REDESIGN gate (2026-07-20).

A run that executes and measures NOTHING must never become a paper about its
own failure: it loops back to stage 2 carrying the substrate's verbatim
rejection messages, bounded, and ends honestly when the budget is spent.

The shapes here are taken from run 20260720T080610Z, the run that motivated
the gate: three cobrapy solves rejected on a missing typed field before the
solver started, status "executed", verdict "trust" — invisible to the existing
total-defer retry, which requires a defer verdict.
"""

import unittest

from baton import Baton
from stages.stage2_experiment_design import build_execution_failure_block
from supervisor import barren_diagnosis, is_barren

REJECTION = "input rejected: missing required field(s): model"


def _baton(execution_results, verdict_label="trust"):
    b = Baton(run_id="testrun", created_at="2026-07-20T00:00:00Z", mode="auto")
    b.payload = {
        "domain": "test-domain",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "substrate_id": "cobrapy",
        "fidelity_verdict": {"label": verdict_label, "rationale": "x",
                             "right_instrument": "y"},
        "execution_results": execution_results,
    }
    return b


class TestIsBarren(unittest.TestCase):

    def test_the_motivating_run_is_barren(self):
        """Run 20260720T080610Z's exact shape: executed, trust, 3 rejections."""
        b = _baton({
            "status": "executed",
            "runs": [
                {"converged": False, "wall_clock_s": 0.0, "qoi_error": REJECTION}
                for _ in range(3)
            ],
        })
        self.assertTrue(is_barren(b))

    def test_halted_synthesis_is_barren(self):
        b = _baton({"status": "halted_synthesis",
                    "reason": "unsupported parameters: a, b, c"})
        self.assertTrue(is_barren(b))

    def test_one_real_value_is_not_barren(self):
        """The cobrapy success shape: two values plus a legitimate infeasible.

        The absent third value IS the finding (the infeasibility onset), so a
        run carrying it must reach the paper, not the redesign loop.
        """
        b = _baton({
            "status": "executed",
            "runs": [
                {"converged": True, "wall_clock_s": 1.0, "qoi_value": 0.8739215},
                {"converged": True, "wall_clock_s": 1.0, "qoi_value": 0.8739215},
                {"converged": False, "wall_clock_s": 1.0,
                 "qoi_error": "FBA did not yield a trustworthy growth (infeasible)"},
            ],
        })
        self.assertFalse(is_barren(b))

    def test_skipped_defer_is_not_barren(self):
        """A defer verdict is the fidelity gate working; it belongs to
        is_total_defer, which has its own ruled retry. Claiming it here would
        double-govern the same run."""
        b = _baton({"status": "skipped_defer"}, verdict_label="defer")
        self.assertFalse(is_barren(b))

    def test_missing_execution_results_is_not_barren(self):
        b = _baton({})
        b.payload.pop("execution_results")
        self.assertFalse(is_barren(b))


class TestBarrenDiagnosis(unittest.TestCase):

    def test_identical_errors_deduplicated(self):
        b = _baton({
            "status": "executed",
            "runs": [{"qoi_error": REJECTION} for _ in range(3)],
        })
        d = barren_diagnosis(b)
        self.assertEqual(d["distinct_errors"], [REJECTION])
        self.assertEqual(d["runs_attempted"], 3)
        self.assertEqual(d["runs_with_data"], 0)

    def test_distinct_errors_all_kept_in_order(self):
        b = _baton({
            "status": "executed",
            "runs": [{"qoi_error": "first"}, {"qoi_error": "second"},
                     {"qoi_error": "first"}],
        })
        self.assertEqual(barren_diagnosis(b)["distinct_errors"], ["first", "second"])

    def test_halt_reason_carried(self):
        b = _baton({"status": "halted_synthesis", "reason": "unsupported: x"})
        self.assertEqual(barren_diagnosis(b)["reason"], "unsupported: x")


class TestExecutionFailureBlock(unittest.TestCase):

    def test_verbatim_rejection_reaches_the_block(self):
        """The actionable content lives in the exact wording — the block must
        carry it uninterpreted."""
        block = build_execution_failure_block({
            "status": "executed", "runs_attempted": 3,
            "distinct_errors": [REJECTION], "runs_with_data": 0,
        })
        self.assertIn(REJECTION, block)
        self.assertIn("0 returned a value", block)

    def test_none_on_no_diagnosis(self):
        """Every ordinary first pass: composition must be byte-identical."""
        self.assertIsNone(build_execution_failure_block(None))
        self.assertIsNone(build_execution_failure_block({}))

    def test_not_framed_as_unverified_leads(self):
        """A wrapper rejection is deterministic machine output. Hedging it the
        way the lessons block hedges model text would invite the redesign to
        discount its only ground truth."""
        block = build_execution_failure_block({
            "status": "executed", "runs_attempted": 1,
            "distinct_errors": [REJECTION],
        })
        self.assertNotIn("unverified model text", block)
        self.assertNotIn("leads, not established facts", block)

    def test_halt_reason_rendered(self):
        block = build_execution_failure_block({
            "status": "halted_synthesis", "runs_attempted": 0,
            "reason": "unsupported parameters: a, b", "distinct_errors": [],
        })
        self.assertIn("unsupported parameters: a, b", block)


if __name__ == "__main__":
    unittest.main()
