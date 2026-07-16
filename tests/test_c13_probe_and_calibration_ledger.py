"""test_c13_probe_and_calibration_ledger.py — step21. Call-free: NO model
calls, NO network, NO docker, NO mutation of the real ledger files (tmp paths).

Covers:
  * harness/c13_steerability_probe.py — constructive single-variable isolation,
    the reproduction guarantee (base == slate C13), identity-span invariance,
    the guard-coverage proof (RULE-1 tripwire fires on a planted key), reuse of
    the FROZEN run_gate_case path, and prediction mapping.
  * harness/calibration_ledger.py — append/count/read roundtrip, idempotent
    seeding, source validation, and the R-CAL-3 SEPARATION invariant (the
    calibration ledger is never the production fidelity/override ledger).

Run directly: venv/bin/python3 -m pytest tests/test_c13_probe_and_calibration_ledger.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import c13_steerability_probe as probe
from harness import calibration_battery as cb
from harness import calibration_ledger as cl
from memory import ledgers
from stages.stage3_fidelity_gate import VALID_LABELS


class TestProbeIsolation(unittest.TestCase):
    def setUp(self):
        self.probe = probe.load_probe()
        self.cells = {c["id"]: c for c in self.probe["cells"]}
        self.base = self.probe["meta"]["base_experiment"]

    def test_base_is_slate_c13_verbatim(self):
        # Reproduction guarantee: base_experiment == the ruled slate's C13.
        slate = json.loads((ROOT / "harness" / "calibration_cases_code.json").read_text())
        c13 = {g["id"]: g for g in slate["gate_cases"]}["C13"]
        self.assertEqual(self.base, c13["experiment"])
        self.assertEqual(self.cells["P-0"]["experiment"], c13["experiment"])

    def test_contract_read_verbatim_from_slate(self):
        # substrate/envelope are byte-identical to the code slate — the gate's
        # contract is unchanged; only the experiment varies.
        slate = json.loads((ROOT / "harness" / "calibration_cases_code.json").read_text())
        self.assertEqual(self.probe["substrate_text"], slate["substrate_text"])
        self.assertEqual(self.probe["envelope_text"], slate["envelope_text"])

    def test_four_cells_present(self):
        self.assertEqual(set(self.cells), {"P-0", "P-A", "P-B", "P-C"})

    def test_identity_spans_intact_every_cell(self):
        # data/model/split identity never moves — only the judged framing does.
        for cid, c in self.cells.items():
            for span in probe._IDENTITY_SPANS:
                self.assertIn(span, c["experiment"], f"{cid} lost identity span {span!r}")

    def test_p_a_isolates_criterion_only(self):
        # Register neutralized; leak disclosure (y_copy + ~1.0) RETAINED; scope narrow.
        exp = self.cells["P-A"]["experiment"]
        self.assertIn("its columns also include y_copy", exp)        # disclosure kept
        self.assertIn("Expect a suspiciously perfect metric", exp)   # kept
        self.assertNotIn("trust the reported accuracy", exp)         # register changed
        self.assertIn("report the held-out accuracy for this triple", exp)
        self.assertNotIn("generalizes", exp)                         # scope still narrow

    def test_p_b_isolates_disclosure_only(self):
        # Disclosure removed; criterion RETAINED byte-for-byte.
        exp = self.cells["P-B"]["experiment"]
        self.assertNotIn("y_copy", exp)
        self.assertNotIn("Expect a suspiciously perfect metric", exp)
        self.assertIn("trust the reported accuracy as a benchmark", exp)  # criterion kept

    def test_p_c_isolates_scope_only(self):
        # Scope broadened; register ('trust the reported accuracy') + disclosure RETAINED.
        exp = self.cells["P-C"]["experiment"]
        self.assertIn("trust the reported accuracy", exp)            # register kept
        self.assertIn("its columns also include y_copy", exp)       # disclosure kept
        self.assertIn("generalizes to new data", exp)               # scope broadened
        self.assertNotIn("as a benchmark", exp)

    def test_every_non_base_differs_from_base_in_exactly_its_edit(self):
        # Constructive proof: applying the cell's own edit to base reproduces the
        # cell's experiment, and no OTHER edit reproduces it — single variable.
        for cid in ("P-A", "P-B", "P-C"):
            c = self.cells[cid]
            self.assertEqual(probe._apply_edit(self.base, c["edit"]), c["experiment"])
            self.assertNotEqual(c["experiment"], self.base)

    def test_apply_edit_rejects_ambiguous_anchor(self):
        # An anchor that is absent (or appears more than once) must raise — the
        # isolation cannot rest on an ambiguous edit.
        with self.assertRaises(ValueError):
            probe._apply_edit("no anchor here", {"kind": "replace", "find": "zzz", "repl": "q"})

    def test_acceptable_labels_are_vocabulary(self):
        for c in self.cells.values():
            self.assertTrue(c["acceptable_labels"])
            for lbl in c["acceptable_labels"]:
                self.assertIn(lbl, VALID_LABELS)


class TestProbeReusesFrozenPath(unittest.TestCase):
    def test_probe_uses_the_real_run_gate_case(self):
        # The probe must go through the frozen battery path, not a copy.
        self.assertIs(probe.cb.run_gate_case, cb.run_gate_case)

    def test_probe_never_enters_a_ruled_slate(self):
        # The probe substrate id is NOT a battery --substrate choice, and the
        # ruled slates keep their locked composition (15 FEA / 14 code).
        self.assertNotIn("code_sklearn_eval_probe_c13", cb._CASE_FILES)
        fea = cb.load_cases("calculix_cantilever_fea")
        code = cb.load_cases("code_sklearn_eval")
        self.assertEqual(len(fea["gate_cases"]) + len(fea["wrapper_cases"]), 15)
        self.assertEqual(len(code["gate_cases"]) + len(code["wrapper_cases"]), 14)


class TestProbeGuardCoverage(unittest.TestCase):
    """RULE-1 answer-key tripwire covers the probe cells — proven by FAILING the
    escape, not by re-reading the safe path."""

    def setUp(self):
        self.probe = probe.load_probe()

    def test_clean_probe_inputs_pass(self):
        for c in self.probe["cells"]:
            stage_input = {
                "case_id": c["id"], "substrate": self.probe["substrate_text"],
                "envelope": self.probe["envelope_text"], "experiment": c["experiment"],
            }
            cb._assert_no_answer_key_leak(stage_input, c["id"])  # no raise == pass

    def test_planted_key_fires_the_guard(self):
        for k in cb._ANSWER_KEY_KEYS:
            leaking = {
                "case_id": "P-0", "substrate": self.probe["substrate_text"],
                "envelope": self.probe["envelope_text"],
                "experiment": self.probe["cells"][0]["experiment"], k: "planted",
            }
            with self.assertRaises(AssertionError, msg=k):
                cb._assert_no_answer_key_leak(leaking, "P-0")


class TestPredictionMapping(unittest.TestCase):
    def test_p8_and_alarming_flags(self):
        cells = {
            "P-0": {"distribution": {"trust": 2, "defer": 1}},
            "P-A": {"distribution": {"trust": 3}},
            "P-B": {"distribution": {"trust": 3}},
            "P-C": {"distribution": {"defer": 3}},
        }
        p = probe.evaluate_predictions(cells)
        self.assertTrue(p["P8_c13_reproduces"]["holds"])       # 2/3 trust
        self.assertTrue(p["P9_scope_literalism_H3"]["holds"])  # P-C 3 defer, A/B trust
        self.assertTrue(p["P10_H2_false"]["holds"])            # P-B trusts
        self.assertTrue(p["P11_H1_false"]["holds"])            # P-A trusts

    def test_p8_false_marks_probe_void_note(self):
        cells = {"P-0": {"distribution": {"defer": 2, "trust": 1}}}
        p = probe.evaluate_predictions(cells)
        self.assertFalse(p["P8_c13_reproduces"]["holds"])
        self.assertIn("n=1 noise", p["P8_c13_reproduces"]["note"])


class TestCalibrationLedgerSeparation(unittest.TestCase):
    """R-CAL-3: the calibration ledger is NEVER the production fidelity/override
    ledger. Different file, different directory — pooling is impossible."""

    def test_paths_are_distinct(self):
        self.assertNotEqual(cl.CALIBRATION_LEDGER_PATH, ledgers.FIDELITY_LEDGER_PATH)
        self.assertNotEqual(cl.CALIBRATION_LEDGER_PATH, ledgers.OVERRIDE_LEDGER_PATH)
        self.assertEqual(cl.CALIBRATION_LEDGER_PATH.parent.name, "harness")
        self.assertEqual(ledgers.FIDELITY_LEDGER_PATH.parent.name, "memory")


class TestCalibrationLedgerIO(unittest.TestCase):
    def _tmp(self):
        import tempfile
        d = Path(tempfile.mkdtemp())
        return d / "calibration_ledger.jsonl"

    def test_append_count_read_roundtrip(self):
        p = self._tmp()
        cl.append_entry(source="probe", batch_id="B1", substrate_id="s", case_id="P-0",
                        expected_class="leakage-suspect", acceptable_labels=["defer"],
                        raw_verdict="trust", routed_outcome="defer", hook_fired=True,
                        passed=False, rationale="r", cell="P-0", repeat=0, path=p)
        self.assertEqual(cl.count_entries(p), 1)
        got = cl.read_all(p)[0]
        self.assertEqual(got["source"], "probe")
        self.assertEqual(got["raw_verdict"], "trust")
        self.assertEqual(got["repeat"], 0)

    def test_bad_source_rejected(self):
        p = self._tmp()
        with self.assertRaises(ValueError):
            cl.append_entry(source="fidelity", batch_id="B", substrate_id="s",
                            case_id="C", expected_class="in", acceptable_labels=["trust"],
                            raw_verdict="trust", routed_outcome="defer", hook_fired=True,
                            passed=True, path=p)

    def test_seed_is_idempotent(self):
        p = self._tmp()
        report = ROOT / "harness" / "calibration_code_sklearn_eval_20260716T013014Z.json"
        n1 = cl.seed_from_battery_report(report, path=p)
        n2 = cl.seed_from_battery_report(report, path=p)
        self.assertEqual(n1, 11)          # 11 gate cases in the code report
        self.assertEqual(n2, 0)           # re-seed adds nothing
        self.assertEqual(cl.count_entries(p), 11)

    def test_seed_records_c13_failure_verbatim(self):
        p = self._tmp()
        report = ROOT / "harness" / "calibration_code_sklearn_eval_20260716T013014Z.json"
        cl.seed_from_battery_report(report, path=p)
        c13 = [e for e in cl.read_all(p) if e["case_id"] == "C13"][0]
        self.assertEqual(c13["raw_verdict"], "trust")
        self.assertEqual(c13["expected_class"], "leakage-suspect")
        self.assertFalse(c13["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
