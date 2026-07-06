"""
test_stage4_case_builder.py — unit tests for deterministic case synthesis
and stage 4's QoI translation. Zero model calls. Zero docker: the clean-build
test uses the builder's test seams (cases_root=<tmp>, run_mesh=False) to
verify the rewritten values land in the right files by reading them back;
the live blockMesh step is covered by Step 12's witnessed live proofs, not
here (disclosed choice). The clean-build test copies the REAL
cases/cavity_baseline template and is skipped if it is absent (cases/ is
gitignored evidence-class, so the template exists only on the build machine).

Run directly: venv/bin/python3 tests/test_stage4_case_builder.py
"""

from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage4_case_builder import TEMPLATE, CaseSynthesisError, build_case
from stages.stage4_simulation import translate_qoi

# A fully-buildable run: every buildable parameter present, plus a
# reynolds_number that IS consistent with its explicit decomposition
# (1.5 * 2.0 / 0.02 = 150), so the clean build also proves verify-and-proceed.
CLEAN_PARAMS = {
    "kinematic_viscosity": 0.02,
    "lid_velocity": 1.5,
    "cavity_length": 2.0,
    "mesh_resolution": 32,
    "end_time": 10.0,
    "time_step": 0.01,
    "reynolds_number": 150,
}


class TestBuildCase(unittest.TestCase):
    @unittest.skipUnless(TEMPLATE.is_dir(), "local cases/cavity_baseline template absent")
    def test_clean_build_rewrites_land_in_the_right_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            case_dir = build_case(
                CLEAN_PARAMS, "unit_clean", cases_root=root, run_mesh=False
            )
            self.assertEqual(case_dir, root / "unit_clean")

            props = (case_dir / "constant" / "physicalProperties").read_text()
            self.assertRegex(props, r"(?m)^nu\s+0\.02\s*\[m\^2/s\];")

            u_file = (case_dir / "0" / "U").read_text()
            self.assertIn("uniform (1.5 0 0);", u_file)
            self.assertIn("uniform (0 0 0);", u_file)  # internalField untouched

            mesh = (case_dir / "system" / "blockMeshDict").read_text()
            self.assertRegex(mesh, r"\(32 32 1\)")
            # uniform scaling by 2: unit corner (1 1 0) -> (2 2 0), depth 0.01 -> 0.02
            self.assertIn("(2 2 0)", mesh)
            self.assertIn("(0 0 0.02)", mesh)
            self.assertNotIn("(1 1 0)", mesh)

            control = (case_dir / "system" / "controlDict").read_text()
            self.assertRegex(control, r"(?m)^endTime\s+10;")
            self.assertRegex(control, r"(?m)^deltaT\s+0\.01;")
            # 10.0 / 0.01 = 1000 steps -> final time directory guaranteed
            self.assertRegex(control, r"(?m)^writeInterval\s+1000;")
            self.assertRegex(control, r"(?m)^writeControl\s+timeStep;")

            # the template's Step-11 run artifacts must NOT leak into the case
            self.assertFalse((case_dir / "20").exists())
            self.assertFalse((case_dir / "postProcessing").exists())
            self.assertFalse((case_dir / "log.foamRun").exists())
            self.assertFalse((case_dir / "constant" / "polyMesh").exists())

    def test_unsupported_parameters_halt_naming_every_offender(self):
        params = dict(CLEAN_PARAMS)
        params["floor_amplitude_ratio"] = 0.1
        params["scalar_initial_interface"] = 0.5
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(params, "unit_unsupported", cases_root=Path(tmp), run_mesh=False)
        message = str(ctx.exception)
        self.assertIn("floor_amplitude_ratio", message)
        self.assertIn("scalar_initial_interface", message)
        self.assertIn("not in the buildable set", message)

    def test_inconsistent_reynolds_number_halts_with_the_numbers(self):
        params = dict(CLEAN_PARAMS, reynolds_number=500)  # actual U*L/nu = 150
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(params, "unit_re_bad", cases_root=Path(tmp), run_mesh=False)
        message = str(ctx.exception)
        self.assertIn("500", message)
        self.assertIn("150", message)
        self.assertIn("inconsistent", message)

    def test_reynolds_without_full_decomposition_halts(self):
        params = {"reynolds_number": 200, "kinematic_viscosity": 0.01, "end_time": 20.0}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(params, "unit_re_alone", cases_root=Path(tmp), run_mesh=False)
        message = str(ctx.exception)
        self.assertIn("decomposition", message)
        self.assertIn("lid_velocity", message)
        self.assertIn("cavity_length", message)

    def test_end_time_not_a_whole_number_of_time_steps_halts(self):
        params = {"end_time": 1.0, "time_step": 0.3}
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(params, "unit_bad_ratio", cases_root=Path(tmp), run_mesh=False)
        self.assertIn("whole number of", str(ctx.exception))


class TestDerivedRole(unittest.TestCase):
    """Step 16 (JC2): spec-declared derived parameters are excluded from the
    buildable-set check but verified, never waved through. The shape mirrors
    the Step-15 crashed demo's spec: derived 'Re' with the exact
    decomposition rule, present in every mini-run dict."""

    DERIVED_ROLES = {
        "Re": {
            "role": "derived",
            "derived_from": "lid_velocity * cavity_length / kinematic_viscosity",
        },
        "lid_velocity": {"role": "fixed"},
    }

    def _params(self, re_value):
        # U*L/nu = 1.5 * 2.0 / 0.02 = 150 from CLEAN_PARAMS' values.
        params = dict(CLEAN_PARAMS)
        del params["reynolds_number"]  # 'Re' is the derived key under test
        params["Re"] = re_value
        return params

    @unittest.skipUnless(TEMPLATE.is_dir(), "local cases/cavity_baseline template absent")
    def test_consistent_derived_re_passes_exclusion_and_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = build_case(
                self._params(150),
                "unit_derived_ok",
                roles=self.DERIVED_ROLES,
                cases_root=Path(tmp),
                run_mesh=False,
            )
            self.assertTrue(case_dir.is_dir())

    def test_inconsistent_derived_re_halts_naming_declared_vs_computed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(
                    self._params(500),
                    "unit_derived_bad",
                    roles=self.DERIVED_ROLES,
                    cases_root=Path(tmp),
                    run_mesh=False,
                )
        message = str(ctx.exception)
        self.assertIn("derived parameter Re", message)
        self.assertIn("500", message)   # declared
        self.assertIn("150", message)   # computed
        self.assertIn("computes", message)

    def test_unverifiable_derived_rule_halts_by_name(self):
        roles = {
            "peclet_number": {
                "role": "derived",
                "derived_from": "lid_velocity * cavity_length / diffusivity",
            }
        }
        params = dict(CLEAN_PARAMS)
        del params["reynolds_number"]
        params["peclet_number"] = 300
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(
                    params,
                    "unit_derived_unverifiable",
                    roles=roles,
                    cases_root=Path(tmp),
                    run_mesh=False,
                )
        self.assertIn(
            "derived parameter peclet_number: rule not verifiable by this builder",
            str(ctx.exception),
        )

    def test_non_derived_unbuildable_key_still_halts_as_before(self):
        params = dict(CLEAN_PARAMS)
        params["s_amplitude_fraction"] = 0.3  # NOT declared derived
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CaseSynthesisError) as ctx:
                build_case(
                    params,
                    "unit_nonderived_regression",
                    roles=self.DERIVED_ROLES,
                    cases_root=Path(tmp),
                    run_mesh=False,
                )
        message = str(ctx.exception)
        self.assertIn("s_amplitude_fraction", message)
        self.assertIn("not in the buildable set", message)


class TestTranslateQoi(unittest.TestCase):
    def test_machine_readable_qoi_translates_to_a_request(self):
        request, reason = translate_qoi(
            {"name": "mean speed", "units": "m/s", "definition": "…",
             "how_extracted": "…", "field": "U", "operation": "volAverage",
             "component": "mag"}
        )
        self.assertIsNone(reason)
        self.assertEqual(
            request, {"field": "U", "operation": "volAverage", "component": "mag"}
        )

    def test_free_text_only_qoi_is_refused_with_a_reason(self):
        request, reason = translate_qoi(
            {"name": "Danckwerts mixing index", "units": "-",
             "definition": "…", "how_extracted": "read the scalar field…"}
        )
        self.assertIsNone(request)
        self.assertIn("no machine-readable field/operation", reason)

    def test_unknown_operation_is_refused_with_a_reason(self):
        request, reason = translate_qoi(
            {"name": "x", "field": "U", "operation": "timeSeries"}
        )
        self.assertIsNone(request)
        self.assertIn("timeSeries", reason)


if __name__ == "__main__":
    unittest.main()
