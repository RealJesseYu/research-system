"""
test_stage2_spec.py — standalone test of stage2_spec's schema validator.
Zero model calls: validate_spec is pure Python, so each test takes a fully
valid spec, breaks exactly one rule, and proves the matching plain-language
error comes back.

Run directly: python3 tests/test_stage2_spec.py
"""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage2_spec import validate_spec
from tools.qoi_vocab import vocab_for

# R-23.5-5a: validate_spec's vocab argument is required at every call site —
# these cavity-spec tests pass the cavity record explicitly.
CAVITY_VOCAB = vocab_for("cavity_2d_cfd")

CHOSEN_ID = "h3"


def make_valid_spec() -> dict:
    """A fully valid spec; each test deep-copies this and breaks one rule."""
    return {
        "hypothesis_id": CHOSEN_ID,
        "title": "Lid-speed sweep for mixing onset",
        "objective": "Measure how vortex structure changes as lid speed increases.",
        "parameters": [
            {"name": "lid_velocity", "role": "sweep", "units": "m/s", "min": 0.5, "max": 2.0},
            {"name": "viscosity", "role": "fixed", "units": "m^2/s", "value": 0.01},
        ],
        "qoi": {
            "name": "vortex_center_displacement",
            "units": "m",
            "definition": "Distance of the primary vortex center from the cavity center.",
            "how_extracted": "Locate the velocity-magnitude minimum in the final field.",
        },
        "success_criterion": {
            "statement": "Displacement exceeds 0.1 m at the highest lid speed.",
            "threshold": 0.1,
            "direction": "above",
        },
        "regime": {
            "reynolds_min": 50,
            "reynolds_max": 200,
            "notes": "Laminar throughout; Re = U*L/nu with L = 1 m.",
        },
        "mini_experiment": {
            "runs": [
                {"lid_velocity": 0.5, "viscosity": 0.01},
                {"lid_velocity": 2.0, "viscosity": 0.01},
            ],
            "expected_observation": "Vortex center shifts toward the downstream wall.",
        },
        "full_experiment": {
            "design": "Eight evenly spaced lid speeds across the sweep range.",
            "estimated_run_count": 8,
        },
    }


class TestValidSpecPasses(unittest.TestCase):
    def test_valid_spec_returns_no_errors(self):
        self.assertEqual(validate_spec(make_valid_spec(), CHOSEN_ID, CAVITY_VOCAB), [])


class TestOneRulePerViolation(unittest.TestCase):
    def assert_error_mentioning(self, spec: dict, fragment: str):
        errors = validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB)
        self.assertTrue(
            any(fragment in e for e in errors),
            f"expected an error containing {fragment!r}, got: {errors}",
        )

    def test_wrong_hypothesis_id(self):
        spec = make_valid_spec()
        spec["hypothesis_id"] = "h1"
        self.assert_error_mentioning(spec, f"hypothesis_id must be exactly '{CHOSEN_ID}'")

    def test_missing_required_field(self):
        spec = make_valid_spec()
        del spec["qoi"]
        self.assert_error_mentioning(spec, "required field 'qoi' is missing")

    def test_extra_field_rejected(self):
        spec = make_valid_spec()
        spec["confidence"] = 0.9
        self.assert_error_mentioning(spec, "field 'confidence' is not part of the spec schema")

    def test_sweep_min_not_less_than_max(self):
        spec = make_valid_spec()
        spec["parameters"][0]["min"] = 2.0
        spec["parameters"][0]["max"] = 0.5
        self.assert_error_mentioning(spec, "min strictly less than max")

    def test_sweep_min_max_not_numeric(self):
        spec = make_valid_spec()
        spec["parameters"][0]["min"] = "slow"
        self.assert_error_mentioning(spec, "must carry numeric 'min' and 'max'")

    def test_mini_run_sweep_value_out_of_range(self):
        spec = make_valid_spec()
        spec["mini_experiment"]["runs"][1]["lid_velocity"] = 5.0
        self.assert_error_mentioning(spec, "outside its declared range [0.5, 2.0]")

    def test_mini_run_missing_sweep_value(self):
        spec = make_valid_spec()
        del spec["mini_experiment"]["runs"][0]["lid_velocity"]
        self.assert_error_mentioning(spec, "missing a value for sweep parameter 'lid_velocity'")

    def test_mini_run_fixed_value_changed(self):
        spec = make_valid_spec()
        spec["mini_experiment"]["runs"][0]["viscosity"] = 0.02
        self.assert_error_mentioning(spec, "fixed parameters must keep their declared value")

    def test_reynolds_min_not_positive(self):
        spec = make_valid_spec()
        spec["regime"]["reynolds_min"] = 0
        self.assert_error_mentioning(spec, "0 < reynolds_min <= reynolds_max")

    def test_reynolds_min_above_max(self):
        spec = make_valid_spec()
        spec["regime"]["reynolds_min"] = 300
        self.assert_error_mentioning(spec, "0 < reynolds_min <= reynolds_max")

    def test_threshold_not_a_number(self):
        spec = make_valid_spec()
        spec["success_criterion"]["threshold"] = "0.1"
        self.assert_error_mentioning(spec, "threshold must be a number")

    def test_estimated_run_count_not_positive_integer(self):
        spec = make_valid_spec()
        spec["full_experiment"]["estimated_run_count"] = 0
        self.assert_error_mentioning(spec, "estimated_run_count must be a positive integer")

    def test_estimated_run_count_not_integer(self):
        spec = make_valid_spec()
        spec["full_experiment"]["estimated_run_count"] = 2.5
        self.assert_error_mentioning(spec, "estimated_run_count must be a positive integer")

    def test_mini_run_unknown_parameter_name(self):
        spec = make_valid_spec()
        spec["mini_experiment"]["runs"][0]["lid_speed"] = 1.0
        self.assert_error_mentioning(
            spec,
            "sets 'lid_speed', which is not a declared parameter name — the declared "
            "parameter names are: lid_velocity, viscosity",
        )

    def test_qoi_as_list_rejected(self):
        spec = make_valid_spec()
        spec["qoi"] = [copy.deepcopy(make_valid_spec()["qoi"])]
        self.assert_error_mentioning(spec, "qoi must be a single object, never a list")

    def test_qoi_machine_keys_valid_pass(self):
        spec = make_valid_spec()
        spec["qoi"].update({"field": "U", "operation": "volAverage", "component": "mag"})
        self.assertEqual(validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB), [])

    def test_qoi_machine_keys_absent_pass(self):
        spec = make_valid_spec()
        for key in ("field", "operation", "component"):
            self.assertNotIn(key, spec["qoi"])
        self.assertEqual(validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB), [])

    def test_qoi_invalid_operation_rejected(self):
        spec = make_valid_spec()
        spec["qoi"].update({"field": "U", "operation": "timeAverage"})
        self.assert_error_mentioning(spec, "qoi operation must be one of")

    def test_qoi_component_only_rejected(self):
        spec = make_valid_spec()
        spec["qoi"]["component"] = "mag"
        self.assert_error_mentioning(
            spec, "must carry both 'field' and 'operation'"
        )

    def test_qoi_invalid_component_rejected(self):
        spec = make_valid_spec()
        spec["qoi"].update({"field": "U", "operation": "volAverage", "component": "x"})
        self.assert_error_mentioning(spec, "qoi component must be \"mag\" or 0|1|2")


class TestStep15DocketInclusions(unittest.TestCase):
    """The three Step-15 ruled inclusions: candidate 3 (typed fixed values),
    candidate 2 (derived parameters state their rule), candidate 5 (optional
    two-sided expectation). One passing and at least one failing case each."""

    def assert_error_mentioning(self, spec: dict, fragment: str):
        errors = validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB)
        self.assertTrue(
            any(fragment in e for e in errors),
            f"expected an error containing {fragment!r}, got: {errors}",
        )

    # Candidate 3 — typed fixed values.
    def test_numeric_fixed_value_passes(self):
        # make_valid_spec's viscosity 0.01 is the passing case.
        self.assertEqual(validate_spec(make_valid_spec(), CHOSEN_ID, CAVITY_VOCAB), [])

    def test_string_fixed_value_rejected(self):
        spec = make_valid_spec()
        spec["parameters"][1]["value"] = "step: c=1 for y>0.5 m"  # the S12 shape
        # keep the mini runs consistent with the (invalid) declaration:
        for run in spec["mini_experiment"]["runs"]:
            run["viscosity"] = "step: c=1 for y>0.5 m"
        self.assert_error_mentioning(spec, "must carry a numeric 'value'")

    def test_bool_fixed_value_rejected(self):
        spec = make_valid_spec()
        spec["parameters"][1]["value"] = True
        self.assert_error_mentioning(spec, "must carry a numeric 'value'")

    # Candidate 2 — derived parameters state their rule.
    def test_derived_with_rule_passes(self):
        spec = make_valid_spec()
        spec["parameters"].append(
            {
                "name": "reynolds_number",
                "role": "derived",
                "units": "dimensionless",
                "derived_from": "Re = lid_velocity * 1.0 m / viscosity",
            }
        )
        self.assertEqual(validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB), [])

    def test_derived_name_allowed_in_mini_runs(self):
        spec = make_valid_spec()
        spec["parameters"].append(
            {
                "name": "reynolds_number",
                "role": "derived",
                "units": "dimensionless",
                "derived_from": "Re = lid_velocity * 1.0 m / viscosity",
            }
        )
        spec["mini_experiment"]["runs"][0]["reynolds_number"] = 50
        self.assertEqual(validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB), [])

    def test_derived_without_rule_rejected(self):
        spec = make_valid_spec()
        spec["parameters"].append(
            {"name": "reynolds_number", "role": "derived", "units": "dimensionless"}
        )
        self.assert_error_mentioning(spec, "'derived_from'")

    def test_derived_with_empty_rule_rejected(self):
        spec = make_valid_spec()
        spec["parameters"].append(
            {
                "name": "reynolds_number",
                "role": "derived",
                "units": "dimensionless",
                "derived_from": "   ",
            }
        )
        self.assert_error_mentioning(spec, "'derived_from'")

    # Candidate 5 — optional two-sided expectation.
    def test_two_sided_expectation_passes(self):
        spec = make_valid_spec()
        spec["success_criterion"]["expected_value"] = 0.15
        spec["success_criterion"]["tolerance"] = 0.03
        self.assertEqual(validate_spec(spec, CHOSEN_ID, CAVITY_VOCAB), [])

    def test_expected_value_without_tolerance_rejected(self):
        spec = make_valid_spec()
        spec["success_criterion"]["expected_value"] = 0.15
        self.assert_error_mentioning(spec, "both 'expected_value' and 'tolerance'")

    def test_tolerance_without_expected_value_rejected(self):
        spec = make_valid_spec()
        spec["success_criterion"]["tolerance"] = 0.03
        self.assert_error_mentioning(spec, "both 'expected_value' and 'tolerance'")

    def test_non_numeric_expected_value_rejected(self):
        spec = make_valid_spec()
        spec["success_criterion"]["expected_value"] = "about 0.15"
        spec["success_criterion"]["tolerance"] = 0.03
        self.assert_error_mentioning(spec, "expected_value must be a number")

    def test_non_positive_tolerance_rejected(self):
        spec = make_valid_spec()
        spec["success_criterion"]["expected_value"] = 0.15
        spec["success_criterion"]["tolerance"] = 0
        self.assert_error_mentioning(spec, "tolerance must be a number greater than zero")


if __name__ == "__main__":
    unittest.main()
