"""
test_gate_bets.py — Phase-1 Lane-1: Brier machinery + calibration table.
Deterministic, ZERO model calls. Brier values are hand-computed in the
assertions; the live-ledger read is an offline file read that locks the
current all-unresolved blocker.

Run directly: venv/bin/python3 tests/test_gate_bets.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from harness import gate_bets


class BrierMath(unittest.TestCase):
    def test_single_event_brier(self):
        self.assertAlmostEqual(gate_bets.brier(0.9, 1), 0.01)
        self.assertAlmostEqual(gate_bets.brier(0.9, 0), 0.81)
        self.assertAlmostEqual(gate_bets.brier(0.1, 0), 0.01)
        self.assertAlmostEqual(gate_bets.brier(0.5, 1), 0.25)
        self.assertAlmostEqual(gate_bets.brier(0.5, 0), 0.25)
        self.assertAlmostEqual(gate_bets.brier(0.3, 1), 0.49)


class Probability(unittest.TestCase):
    def test_prior_by_verdict(self):
        self.assertEqual(gate_bets.entry_probability({"verdict": "trust"}), 0.90)
        self.assertEqual(gate_bets.entry_probability({"verdict": "refine"}), 0.50)
        self.assertEqual(gate_bets.entry_probability({"verdict": "defer"}), 0.10)

    def test_explicit_probability_seam_wins_and_clamps(self):
        self.assertEqual(gate_bets.entry_probability({"verdict": "trust", "probability": 0.3}), 0.3)
        self.assertEqual(gate_bets.entry_probability({"verdict": "defer", "probability": 1.4}), 1.0)
        self.assertEqual(gate_bets.entry_probability({"verdict": "defer", "probability": -0.2}), 0.0)
        # a null explicit probability falls back to the prior
        self.assertEqual(gate_bets.entry_probability({"verdict": "trust", "probability": None}), 0.90)

    def test_unknown_verdict_is_unpredictable(self):
        self.assertIsNone(gate_bets.entry_probability({"verdict": "banana"}))
        self.assertIsNone(gate_bets.entry_probability({}))


class OutcomeResolution(unittest.TestCase):
    def test_resolves_true_false_and_unresolved(self):
        self.assertEqual(gate_bets.resolve_outcome({"outcome": True}), 1)
        self.assertEqual(gate_bets.resolve_outcome({"outcome": "faithful"}), 1)
        self.assertEqual(gate_bets.resolve_outcome({"outcome": "USABLE"}), 1)
        self.assertEqual(gate_bets.resolve_outcome({"outcome": False}), 0)
        self.assertEqual(gate_bets.resolve_outcome({"outcome": "failure"}), 0)
        self.assertIsNone(gate_bets.resolve_outcome({"outcome": None}))
        self.assertIsNone(gate_bets.resolve_outcome({}))
        self.assertIsNone(gate_bets.resolve_outcome({"outcome": "maybe"}))


class ScoreLedger(unittest.TestCase):
    def setUp(self):
        # 4 resolvable + 1 unresolved + 1 unpredictable
        self.entries = [
            {"run_id": "r1", "verdict": "trust", "outcome": True},    # p .9 y1 brier .01
            {"run_id": "r2", "verdict": "trust", "outcome": False},   # p .9 y0 brier .81
            {"run_id": "r3", "verdict": "defer", "outcome": "failure"},  # p .1 y0 brier .01
            {"run_id": "r4", "verdict": "refine", "outcome": "usable"},  # p .5 y1 brier .25
            {"run_id": "r5", "verdict": "trust", "outcome": None},    # excluded: unresolved
            {"run_id": "r6", "verdict": "banana", "outcome": True},   # excluded: unpredictable
        ]
        self.report = gate_bets.score_ledger(self.entries)

    def test_counts(self):
        self.assertEqual(self.report["n_total"], 6)
        self.assertEqual(self.report["n_resolved"], 4)
        self.assertEqual(self.report["n_excluded"], 2)
        self.assertEqual(self.report["n_unpredictable"], 1)

    def test_cumulative_brier_hand_computed(self):
        # (0.01 + 0.81 + 0.01 + 0.25) / 4 = 1.08 / 4 = 0.27
        self.assertAlmostEqual(self.report["cumulative_brier"], 0.27)

    def test_per_entry_brier(self):
        by_run = {pe["run_id"]: pe for pe in self.report["per_entry"]}
        self.assertAlmostEqual(by_run["r1"]["brier"], 0.01)
        self.assertAlmostEqual(by_run["r2"]["brier"], 0.81)
        self.assertAlmostEqual(by_run["r3"]["brier"], 0.01)
        self.assertAlmostEqual(by_run["r4"]["brier"], 0.25)
        self.assertNotIn("r5", by_run)
        self.assertNotIn("r6", by_run)

    def test_calibration_table(self):
        cal = {(row["verdict"], row["predicted_p"]): row for row in self.report["calibration"]}
        # trust bucket: predicted 0.9, ys=[1,0] -> observed 0.5, n=2
        self.assertAlmostEqual(cal[("trust", 0.9)]["observed_frequency"], 0.5)
        self.assertEqual(cal[("trust", 0.9)]["n"], 2)
        # defer bucket: predicted 0.1, ys=[0] -> observed 0.0, n=1
        self.assertAlmostEqual(cal[("defer", 0.1)]["observed_frequency"], 0.0)
        self.assertEqual(cal[("defer", 0.1)]["n"], 1)
        # refine bucket: predicted 0.5, ys=[1] -> observed 1.0, n=1
        self.assertAlmostEqual(cal[("refine", 0.5)]["observed_frequency"], 1.0)
        self.assertEqual(cal[("refine", 0.5)]["n"], 1)

    def test_explicit_probability_makes_its_own_bucket(self):
        entries = [
            {"run_id": "a", "verdict": "trust", "probability": 0.3, "outcome": True},  # brier .49
            {"run_id": "b", "verdict": "trust", "outcome": True},                       # p .9 brier .01
        ]
        rep = gate_bets.score_ledger(entries)
        cal = {(row["verdict"], row["predicted_p"]): row for row in rep["calibration"]}
        self.assertIn(("trust", 0.3), cal)
        self.assertIn(("trust", 0.9), cal)
        self.assertEqual(cal[("trust", 0.3)]["n"], 1)


class EmptyAndLiveLedger(unittest.TestCase):
    def test_empty_ledger_undefined_cumulative(self):
        rep = gate_bets.score_ledger([])
        self.assertEqual(rep["n_resolved"], 0)
        self.assertIsNone(rep["cumulative_brier"])
        self.assertEqual(rep["calibration"], [])

    def test_live_ledger_is_all_unresolved(self):
        """Offline read of the real ledger: locks the current blocker —
        every entry's outcome is null, so 0 resolved and Brier undefined."""
        entries = gate_bets.load_ledger()
        rep = gate_bets.score_ledger(entries)
        self.assertEqual(rep["n_total"], len(entries))
        self.assertEqual(rep["n_resolved"], 0)
        self.assertEqual(rep["n_excluded"], len(entries))
        self.assertIsNone(rep["cumulative_brier"])


if __name__ == "__main__":
    unittest.main()
