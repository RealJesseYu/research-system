"""
test_calibration_battery.py — STEP 26. Call-free: NO model calls, NO network,
NO docker. Covers harness/calibration_battery.py — case-file integrity, the
confusion/hook-witness pure functions, the REAL maturity-hook witness (imported
from supervisor, exercised on fabricated verdicts), and the wrapper-behavior
track run against the substrates' own validators (pure Python validation only —
these reject before any solver/container).

Run directly: venv/bin/python3 tests/test_calibration_battery.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import supervisor
from harness import calibration_battery as cb
from stages.stage3_fidelity_gate import VALID_LABELS

FEA = "calculix_cantilever_fea"
CODE = "code_sklearn_eval"


class TestCaseFileIntegrity(unittest.TestCase):
    def test_fea_composition(self):
        data = cb.load_cases(FEA)
        self.assertEqual(len(data["gate_cases"]), 9)
        self.assertEqual(len(data["wrapper_cases"]), 5)
        classes = [g["expected_class"] for g in data["gate_cases"]]
        self.assertEqual(classes.count("in"), 5)
        self.assertEqual(classes.count("out"), 4)
        self.assertTrue(all(w["expected_class"] == "setup_error"
                            for w in data["wrapper_cases"]))

    def test_code_composition(self):
        data = cb.load_cases(CODE)
        self.assertEqual(len(data["gate_cases"]), 11)
        self.assertEqual(len(data["wrapper_cases"]), 3)
        classes = [g["expected_class"] for g in data["gate_cases"]]
        self.assertEqual(classes.count("in"), 4)
        self.assertEqual(classes.count("conflation"), 3)
        self.assertEqual(classes.count("metric-mismatch"), 2)
        self.assertEqual(classes.count("leakage-suspect"), 2)
        self.assertTrue(all(w["expected_class"] == "setup_error"
                            for w in data["wrapper_cases"]))

    def test_acceptable_labels_are_vocabulary(self):
        for sid in (FEA, CODE):
            for g in cb.load_cases(sid)["gate_cases"]:
                self.assertTrue(g["acceptable_labels"])
                for lbl in g["acceptable_labels"]:
                    self.assertIn(lbl, VALID_LABELS)

    def test_no_bare_trust_for_conflation_or_leakage(self):
        # A single-label gate cannot emit a split; the safe proxy for a
        # conflation/leakage case is NEVER a bare trust.
        for g in cb.load_cases(CODE)["gate_cases"]:
            if g["expected_class"] in ("conflation", "leakage-suspect"):
                self.assertNotIn("trust", g["acceptable_labels"], g["id"])

    def test_rule1_no_answer_key_leak_in_built_input(self):
        # The stage_input a gate case would send carries none of the answer-key
        # keys — the same tripwire run_gate_case asserts live.
        for sid in (FEA, CODE):
            data = cb.load_cases(sid)
            for g in data["gate_cases"]:
                stage_input = {
                    "case_id": g["id"],
                    "substrate": data["substrate_text"],
                    "envelope": data["envelope_text"],
                    "experiment": g["experiment"],
                }
                serialized = json.dumps(stage_input)
                for k in cb._ANSWER_KEY_KEYS:
                    self.assertNotIn(f'"{k}"', serialized, f"{sid}/{g['id']}/{k}")


class TestConfusion(unittest.TestCase):
    def test_confusion_counts(self):
        records = [
            {"expected_class": "in", "raw_verdict": "trust"},
            {"expected_class": "in", "raw_verdict": "refine"},
            {"expected_class": "out", "raw_verdict": "defer"},
            {"expected_class": "out", "raw_verdict": "defer"},
        ]
        m = cb.build_confusion(records)
        self.assertEqual(m["in"], {"trust": 1, "refine": 1, "defer": 0})
        self.assertEqual(m["out"], {"trust": 0, "refine": 0, "defer": 2})


class TestRealHookWitness(unittest.TestCase):
    """Exercises the REAL supervisor.apply_substrate_maturity_hook via witness_hook."""

    def test_hook_is_the_real_imported_function(self):
        # The battery must exercise the real hook, never a copy.
        self.assertIs(cb.apply_substrate_maturity_hook,
                      supervisor.apply_substrate_maturity_hook)

    def test_auto_downgrades_trust(self):
        w = cb.witness_hook({"label": "trust", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")
        self.assertTrue(w["signoff_substrates"])

    def test_auto_downgrades_refine(self):
        w = cb.witness_hook({"label": "refine", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")

    def test_defer_is_noop(self):
        w = cb.witness_hook({"label": "defer", "rationale": "r", "right_instrument": "i"}, "auto")
        self.assertFalse(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "defer")

    def test_human_mode_leaves_verdict_but_records_signoff(self):
        w = cb.witness_hook({"label": "trust", "rationale": "r", "right_instrument": "i"}, "human")
        self.assertTrue(w["hook_fired"])
        self.assertEqual(w["routed_outcome"], "trust")  # untouched in human mode
        self.assertTrue(w["signoff_substrates"])

    def test_witness_does_not_mutate_caller_verdict(self):
        raw = {"label": "trust", "rationale": "r", "right_instrument": "i"}
        cb.witness_hook(raw, "auto")
        self.assertEqual(raw["label"], "trust")  # deep-copied inside


class TestHookSummary(unittest.TestCase):
    def _rec(self, cid, raw, routed, fired):
        return {"case_id": cid, "raw_verdict": raw, "routed_outcome": routed,
                "hook_fired": fired}

    def test_all_defer_zero_silent_trusts(self):
        recs = [self._rec("C1", "defer", "defer", False),
                self._rec("C2", "refine", "defer", True)]
        s = cb.hook_summary(recs, "auto")
        self.assertTrue(s["zero_silent_trusts"])
        self.assertTrue(s["hook_fired_matches_raw_trust_refine"])
        self.assertEqual(s["n_hook_fired"], 1)
        self.assertEqual(s["n_raw_trust_or_refine"], 1)

    def test_human_routed_trust_is_not_silent(self):
        recs = [self._rec("C1", "trust", "trust", True)]
        s = cb.hook_summary(recs, "human")
        self.assertEqual(s["routed_trust_case_ids"], ["C1"])
        self.assertTrue(s["zero_silent_trusts"])  # fired -> flagged -> not silent

    def test_a_silent_trust_is_caught(self):
        # Fabricated broken state: routed trust with no hook firing.
        recs = [self._rec("C1", "trust", "trust", False)]
        s = cb.hook_summary(recs, "auto")
        self.assertFalse(s["zero_silent_trusts"])
        self.assertFalse(s["hook_fired_matches_raw_trust_refine"])


class TestWrapperBehaviorTrack(unittest.TestCase):
    """Runs the real wrapper validators (pure Python; NO docker, NO model)."""

    def test_fea_wrapper_cases_reject_as_registered(self):
        data = cb.load_cases(FEA)
        for wc in data["wrapper_cases"]:
            r = cb.run_wrapper_case(FEA, wc)
            self.assertFalse(r["wrapper_valid"], wc["id"])
            self.assertTrue(r["reason_matched"], f"{wc['id']}: {r['wrapper_reason']}")
            self.assertTrue(r["passed"], wc["id"])

    def test_code_wrapper_cases_reject_as_registered(self):
        data = cb.load_cases(CODE)
        for wc in data["wrapper_cases"]:
            r = cb.run_wrapper_case(CODE, wc)
            self.assertFalse(r["wrapper_valid"], wc["id"])
            self.assertTrue(r["reason_matched"], f"{wc['id']}: {r['wrapper_reason']}")
            self.assertTrue(r["passed"], wc["id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
