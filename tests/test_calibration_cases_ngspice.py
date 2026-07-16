"""The ngspice calibration slate's teeth.

harness/calibration_cases_ngspice_linear_passive.json is GENERATED. Without a
test that re-derives it, the generator is just a third hand-authored copy with
extra steps — so the load-bearing test here is BYTE-IDENTITY: re-run the
generator in-process and compare its bytes to what is committed. A hand edit to
the JSON fails. A generator change that was never regenerated fails.

The rest of the file asserts the things the battery driver will rely on but
cannot check for a substrate it has not been wired to yet (ngspice is
deliberately absent from calibration_battery._CASE_FILES until merge — see
onboarding/ngspice_linear_passive/MERGE_NOTES.md), plus the owner-ruled
per-layer wrapper coverage.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import calibration_battery as cb  # noqa: E402
from stages.stage3_fidelity_gate import VALID_LABELS  # noqa: E402
from tools.run_ngspice import NgspiceInputError, _validate_input  # noqa: E402

GEN_PATH = ROOT / "onboarding" / "ngspice_linear_passive" / "generate_calibration_cases.py"
CASE_FILE = ROOT / "harness" / "calibration_cases_ngspice_linear_passive.json"


def _load_generator():
    spec = importlib.util.spec_from_file_location("_ngspice_case_gen", GEN_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


GEN = _load_generator()


class TestGeneratorIsTheSourceOfTruth(unittest.TestCase):
    """The teeth. These fail on a hand-edited JSON or a stale regeneration."""

    def test_committed_json_is_byte_identical_to_a_fresh_generation(self):
        fresh = GEN.render(GEN.build())
        committed = CASE_FILE.read_text()
        self.assertEqual(
            fresh, committed,
            "harness/calibration_cases_ngspice_linear_passive.json is NOT what the "
            "generator emits. It is a GENERATED file: re-run "
            "onboarding/ngspice_linear_passive/generate_calibration_cases.py "
            "rather than editing the JSON by hand.")

    def test_generation_is_deterministic(self):
        # Two consecutive generations must agree — no clock, no randomness, no
        # environment read may leak into the payload.
        self.assertEqual(GEN.render(GEN.build()), GEN.render(GEN.build()))

    def test_committed_json_parses_and_round_trips(self):
        # Byte-identity above is the real check; this proves the bytes are also
        # valid JSON carrying the structure the driver indexes into.
        doc = json.loads(CASE_FILE.read_text())
        self.assertEqual(doc, GEN.build())


class TestSchemaMatchesTheDriver(unittest.TestCase):
    """The driver is the authority. These mirror what calibration_battery
    actually reads, field for field."""

    def setUp(self):
        self.doc = json.loads(CASE_FILE.read_text())

    def test_top_level_shape(self):
        # Every key load_cases / run_gate_case indexes, present.
        for k in ("substrate_id", "card", "cases_doc", "substrate_text",
                  "envelope_text", "gate_cases", "wrapper_cases"):
            self.assertIn(k, self.doc, k)
        self.assertEqual(self.doc["substrate_id"], "ngspice_linear_passive")

    def test_gate_case_fields_match_the_fea_sibling_exactly(self):
        # Field-for-field against the driver's own reference file. A gate case
        # gaining or losing a field relative to FEA is drift.
        fea = json.loads((ROOT / "harness" / "calibration_cases_fea.json").read_text())
        expected = set(fea["gate_cases"][0])
        for g in self.doc["gate_cases"]:
            self.assertEqual(set(g), expected, g["id"])

    def test_wrapper_case_fields_match_the_fea_sibling_exactly(self):
        fea = json.loads((ROOT / "harness" / "calibration_cases_fea.json").read_text())
        expected = set(fea["wrapper_cases"][0])
        for w in self.doc["wrapper_cases"]:
            self.assertEqual(set(w), expected, w["id"])

    def test_slate_composition_is_the_ruled_15(self):
        # Owner-ruled 2026-07-16: 15 = 10 gate + 5 wrapper.
        self.assertEqual(len(self.doc["gate_cases"]), 10)
        self.assertEqual(len(self.doc["wrapper_cases"]), 5)

    def test_acceptable_labels_are_vocabulary_and_non_empty(self):
        # load_cases raises on both of these; assert them before it ever runs.
        for g in self.doc["gate_cases"]:
            self.assertTrue(g["acceptable_labels"], g["id"])
            for lbl in g["acceptable_labels"]:
                self.assertIn(lbl, VALID_LABELS, g["id"])

    def test_ruled_label_split(self):
        by_id = {g["id"]: g for g in self.doc["gate_cases"]}
        for cid in ("G01", "G02", "G03", "G04", "G05"):
            self.assertEqual(by_id[cid]["acceptable_labels"], ["trust"], cid)
        for cid in ("G06", "G07", "G08", "G09"):
            self.assertEqual(by_id[cid]["acceptable_labels"], ["defer"], cid)
        self.assertEqual(by_id["G10"]["acceptable_labels"], ["refine"])

    def test_every_wrapper_case_is_a_setup_error_expecting_rejection(self):
        for w in self.doc["wrapper_cases"]:
            self.assertEqual(w["expected_class"], "setup_error", w["id"])
            self.assertFalse(w["expect_valid"], w["id"])


class TestAnswerKeyContainment(unittest.TestCase):
    """RULE-1: only `id` and `experiment` may reach the model, and no
    answer-key key name may appear in the built input."""

    def setUp(self):
        self.doc = json.loads(CASE_FILE.read_text())

    def test_no_answer_key_leak_in_the_input_the_battery_would_build(self):
        # The exact stage_input run_gate_case constructs, run through the exact
        # tripwire it asserts.
        for g in self.doc["gate_cases"]:
            stage_input = {
                "case_id": g["id"],
                "substrate": self.doc["substrate_text"],
                "envelope": self.doc["envelope_text"],
                "experiment": g["experiment"],
            }
            cb._assert_no_answer_key_leak(stage_input, g["id"])  # raises on leak

    def test_blocklist_covers_every_hidden_gate_field(self):
        # The drift guard test_calibration_battery.py runs over (FEA, CODE).
        # ngspice is not in _CASE_FILES yet, so that loop cannot see this slate:
        # run the identical derivation here so the slate cannot merge with a
        # hidden field the blocklist does not know.
        for g in self.doc["gate_cases"]:
            hidden = set(g) - set(cb._MODEL_VISIBLE_GATE_FIELDS)
            missing = hidden - set(cb._ANSWER_KEY_KEYS)
            self.assertEqual(
                missing, set(),
                f"{g['id']}: answer-key field(s) not in the battery blocklist: "
                f"{missing}")

    def test_provenance_is_top_level_not_a_per_case_field(self):
        # Per-case provenance would be a hidden gate field outside the blocklist
        # (see the test above). It lives once, at top level, where it never
        # reaches a model input.
        self.assertIn("label_provenance", self.doc)
        for g in self.doc["gate_cases"]:
            self.assertNotIn("label_provenance", g, g["id"])
            self.assertNotIn("label_rationale", g, g["id"])


class TestWrapperCasesRejectAtTheirRegisteredLayer(unittest.TestCase):
    """Owner condition 2026-07-16: assert the LAYER per case, not the prose.

    This is the same call run_wrapper_case makes (validator only — no model, no
    container), so a case that could not pass in the battery cannot pass here."""

    LAYERS = {
        "W01": "dot-line",
        "W02": "value",
        "W03": "arity",
        "W04": "typed-field",
        "W05": "letter",
    }

    def setUp(self):
        self.doc = json.loads(CASE_FILE.read_text())
        self.by_id = {w["id"]: w for w in self.doc["wrapper_cases"]}

    def test_five_distinct_layers_zero_overlap(self):
        self.assertEqual(set(self.by_id), set(self.LAYERS))
        substrings = [w["reason_substring"] for w in self.doc["wrapper_cases"]]
        self.assertEqual(len(set(substrings)), 5, "layer substrings must be distinct")

    def test_each_case_is_rejected_by_its_own_layer(self):
        for cid, layer in self.LAYERS.items():
            case = self.by_id[cid]
            with self.subTest(case=cid, layer=layer):
                with self.assertRaises(NgspiceInputError) as ctx:
                    _validate_input(case["spec"])
                self.assertIn(case["reason_substring"], str(ctx.exception))

    def test_a_layer_substring_does_not_match_another_layers_rejection(self):
        # Zero overlap, proven by failing the escape: each case's registered
        # substring must NOT appear in any OTHER case's rejection reason. A
        # substring generic enough to match everything would make the whole
        # wrapper track pass vacuously.
        reasons = {}
        for cid, case in self.by_id.items():
            try:
                _validate_input(case["spec"])
            except NgspiceInputError as e:
                reasons[cid] = str(e)
        self.assertEqual(len(reasons), 5)
        for cid, case in self.by_id.items():
            for other, reason in reasons.items():
                if other == cid:
                    continue
                self.assertNotIn(
                    case["reason_substring"], reason,
                    f"{cid}'s layer substring also matches {other}'s rejection — "
                    f"the layers are not separated")

    def test_the_marker_scan_layer_is_deliberately_absent(self):
        # W01 was amended off the floating-node case because run_wrapper_case
        # calls the validator only. Prove the premise of that ruling: the
        # validator ACCEPTS a floating-node netlist, so such a case could never
        # pass this track. Its real proof lives in test_run_ngspice.py.
        floating = {
            "netlist_body": "V1 in 0 1.0\nC1 in mid 1u\nC2 mid out 1u\n",
            "analysis": {"type": "op"},
            "qoi": {"kind": "node_voltage", "target": "mid",
                    "reduction": "op_value"},
        }
        _validate_input(floating)  # must NOT raise — that is the whole point


if __name__ == "__main__":
    unittest.main(verbosity=2)
