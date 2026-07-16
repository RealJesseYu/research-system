"""
test_run_fenicsx.py — call-free tests for the FEniCSx/DOLFINx wrapper.

ZERO model calls, ZERO docker: the solver is either bypassed (pure functions:
validation, mesh sizing, output parsing, the analytic formula) or replaced by a
stub that simulates the container by replaying a frozen REAL fixture. The three
fixtures were captured from REAL dolfinx-prod runs on 2026-07-16:
  * fenicsx_cantilever_converged.out  — the 8x1x1 degree-2 reference solve;
  * fenicsx_realmode_pin_failure.out  — the ACTUAL output of the real-mode pin
    firing under `source /usr/local/bin/dolfinx-complex-mode` (the escape test);
  * fenicsx_solver_failure.out        — an ACTUAL in-container solver crash.

Mirrors tests/test_run_fea.py in shape.

Run directly:  venv/bin/python3 -m pytest tests/test_run_fenicsx.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import run_fenicsx  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONVERGED = (FIXTURES / "fenicsx_cantilever_converged.out").read_text()
REALMODE_PIN_FAILURE = (FIXTURES / "fenicsx_realmode_pin_failure.out").read_text()
SOLVER_FAILURE = (FIXTURES / "fenicsx_solver_failure.out").read_text()

BASE_SPEC = {"length": 1.0, "width": 0.05, "height": 0.05,
             "E": 210e9, "nu": 0.3, "tip_load": 1000.0,
             "mesh_density": 8, "element_degree": 2}


class TestInputValidation(unittest.TestCase):
    def test_the_five_registered_rejections(self):
        """The EXACT reason substrings the calibration slate (X11-X15) asserts on.
        These strings are a contract with harness/calibration_cases_fenicsx_*.json;
        changing one breaks the battery, so they are pinned here by exact text."""
        cases = [
            ({**BASE_SPEC, "E": -210e9}, "field 'E' must be positive"),
            ({**BASE_SPEC, "height": 0.0}, "field 'height' must be positive"),
            ({**BASE_SPEC, "nu": 0.6}, "nu must be in (-1, 0.5)"),
            ({**BASE_SPEC, "element_degree": 0}, "element_degree must be >= 1"),
            ({**BASE_SPEC, "material": "steel"},
             "unsupported field(s) for fenicsx cantilever v1: material"),
        ]
        for spec, expected in cases:
            with self.subTest(expected=expected):
                with self.assertRaises(run_fenicsx.FenicsxInputError) as ctx:
                    run_fenicsx._validate_input(spec)
                self.assertIn(expected, str(ctx.exception))

    def test_missing_field_is_named(self):
        spec = {k: v for k, v in BASE_SPEC.items() if k != "element_degree"}
        with self.assertRaises(run_fenicsx.FenicsxInputError) as ctx:
            run_fenicsx._validate_input(spec)
        self.assertIn("missing required field(s): element_degree", str(ctx.exception))

    def test_degree_1_is_accepted_not_rejected(self):
        """THE LOAD-BEARING ASYMMETRY (card ruling G5). Degree 1 LOCKS and is not
        validated — but that is a REGIME judgment for the fidelity gate, not a
        wrapper rejection. The wrapper must accept it and return its (wrong)
        number honestly. Degree 0 is a different thing entirely: not a
        displacement element, so it IS a typed rejection."""
        clean = run_fenicsx._validate_input({**BASE_SPEC, "element_degree": 1})
        self.assertEqual(clean["element_degree"], 1)
        with self.assertRaises(run_fenicsx.FenicsxInputError):
            run_fenicsx._validate_input({**BASE_SPEC, "element_degree": 0})

    def test_nu_boundary_is_exclusive_at_half(self):
        # 0.4999 is VALID input (case X10 reaches the gate); 0.5 is not.
        self.assertEqual(
            run_fenicsx._validate_input({**BASE_SPEC, "nu": 0.4999})["nu"], 0.4999)
        with self.assertRaises(run_fenicsx.FenicsxInputError):
            run_fenicsx._validate_input({**BASE_SPEC, "nu": 0.5})

    def test_non_numeric_is_rejected_by_name(self):
        with self.assertRaises(run_fenicsx.FenicsxInputError) as ctx:
            run_fenicsx._validate_input({**BASE_SPEC, "E": "steel"})
        self.assertIn("'E' must be a number", str(ctx.exception))


class TestAnalyticAndMesh(unittest.TestCase):
    def test_analytic_tip_deflection_against_hand_computed_value(self):
        """delta = P L^3 / (3 E I), I = w h^3 / 12, computed BY HAND here:
          I    = 0.05 * 0.05^3 / 12 = 5.208333...e-7 m^4
          3EI  = 3 * 210e9 * 5.208333...e-7 = 328125.0
          delta= 1000 * 1.0^3 / 328125.0 = 3.047619047...e-3 m
        Pinned as a literal so a formula edit cannot silently redefine the
        reference the whole card is validated against."""
        self.assertAlmostEqual(
            run_fenicsx.analytic_tip_deflection(BASE_SPEC), 0.0030476190476190473,
            places=15)

    def test_analytic_scales_as_cube_of_length(self):
        # An independent structural check of the formula: 2x length -> 8x deflection.
        base = run_fenicsx.analytic_tip_deflection(BASE_SPEC)
        twice = run_fenicsx.analytic_tip_deflection({**BASE_SPEC, "length": 2.0})
        self.assertAlmostEqual(twice / base, 8.0, places=9)

    def test_analytic_is_independent_of_mesh_and_degree(self):
        # The closed form is a property of the BEAM, never of the discretization.
        for md, deg in ((8, 1), (32, 2), (64, 3)):
            self.assertAlmostEqual(
                run_fenicsx.analytic_tip_deflection(
                    {**BASE_SPEC, "mesh_density": md, "element_degree": deg}),
                0.0030476190476190473, places=15)

    def test_mesh_counts_mirror_the_fea_ladder(self):
        # The reference beam's ladder, matching run_fea.py's rule rung for rung.
        for md, expected in ((8, (8, 1, 1)), (16, (16, 1, 1)), (32, (32, 2, 2))):
            spec = run_fenicsx._validate_input({**BASE_SPEC, "mesh_density": md})
            self.assertEqual(run_fenicsx._mesh_counts(spec), expected)

    def test_slenderness(self):
        self.assertAlmostEqual(run_fenicsx.slenderness(BASE_SPEC), 20.0, places=9)


class TestOutputParsing(unittest.TestCase):
    def test_converged_fixture_parses(self):
        payload = run_fenicsx.parse_solver_output(CONVERGED)
        self.assertAlmostEqual(payload["tip_displacement"], 0.0030078565819576172,
                               places=15)
        self.assertGreater(payload["max_von_mises"], 0.0)
        self.assertEqual(payload["dolfinx_version"], "0.11.0.post0")
        self.assertEqual(payload["scalar_type"], "float64")

    def test_real_mode_pin_failure_raises_not_fabricates(self):
        """THE REAL-MODE PIN, asserted on its ACTUAL captured output. The fixture
        is what the container really printed under dolfinx-complex-mode — the
        escape test. The wrapper must turn it into a raised failure, never a
        number."""
        with self.assertRaises(ValueError) as ctx:
            run_fenicsx.parse_solver_output(REALMODE_PIN_FAILURE)
        self.assertIn("real-mode pin FAILED", str(ctx.exception))
        self.assertIn("complex128", str(ctx.exception))

    def test_solver_failure_fixture_raises_not_fabricates(self):
        with self.assertRaises(ValueError) as ctx:
            run_fenicsx.parse_solver_output(SOLVER_FAILURE)
        self.assertIn("solver reported failure", str(ctx.exception))

    def test_missing_sentinel_raises(self):
        with self.assertRaises(ValueError) as ctx:
            run_fenicsx.parse_solver_output("Solving linear system...\ndone.\n")
        self.assertIn("no result line", str(ctx.exception))

    def test_duplicate_sentinel_raises(self):
        # Two result lines means we cannot know which is THE result: fail loud
        # rather than silently take one.
        with self.assertRaises(ValueError):
            run_fenicsx.parse_solver_output(CONVERGED + CONVERGED)

    def test_sentinel_survives_surrounding_solver_noise(self):
        noisy = "PETSc INFO: ksp converged\n" + CONVERGED + "MPI finalize\n"
        self.assertAlmostEqual(
            run_fenicsx.parse_solver_output(noisy)["tip_displacement"],
            0.0030078565819576172, places=15)

    def test_non_numeric_qoi_is_rejected(self):
        line = run_fenicsx.RESULT_SENTINEL + json.dumps(
            {"ok": True, "tip_displacement": "0.003", "max_von_mises": 1.0})
        with self.assertRaises(ValueError) as ctx:
            run_fenicsx.parse_solver_output(line)
        self.assertIn("not a number", str(ctx.exception))


class _StubSolver:
    """Replaces run_fenicsx._run_solver. Scripted per-attempt outcomes; on
    'ok' it replays the frozen REAL fixture like the container would."""

    def __init__(self, outcomes):
        self.outcomes = outcomes      # "ok" | "transient" | "timeout" | "crash"
        self.calls = 0

    def __call__(self, job: str):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="docker exec",
                                            timeout=run_fenicsx.TIMEOUT_SECONDS)
        if outcome == "ok":
            return (0, CONVERGED, "")
        if outcome == "crash":
            return (1, SOLVER_FAILURE, "")
        return (1, "", "Error response from daemon: container is restarting")


class TestExecutionPaths(unittest.TestCase):
    def setUp(self):
        self._orig_host = run_fenicsx.SHARED_HOST
        self._orig_run = run_fenicsx._run_solver
        self._orig_preflight = run_fenicsx.preflight
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        run_fenicsx.SHARED_HOST = Path(self._tmp.name)
        run_fenicsx.preflight = lambda: ""      # substrate assumed up

    def tearDown(self):
        run_fenicsx.SHARED_HOST = self._orig_host
        run_fenicsx._run_solver = self._orig_run
        run_fenicsx.preflight = self._orig_preflight
        self._tmp.cleanup()

    def test_happy_path_returns_both_qois(self):
        run_fenicsx._run_solver = _StubSolver(["ok"])
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertTrue(result["valid"])
        self.assertAlmostEqual(result["qoi"]["tip_displacement"],
                               0.0030078565819576172, places=15)
        self.assertIn("max_von_mises", result["qoi"])

    def test_retry_once_then_succeeds(self):
        stub = _StubSolver(["transient", "ok"])
        run_fenicsx._run_solver = stub
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertTrue(result["valid"])
        self.assertEqual(stub.calls, 2)              # retried exactly once

    def test_timeout_path_returns_invalid(self):
        stub = _StubSolver(["timeout", "timeout"])
        run_fenicsx._run_solver = stub
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])
        self.assertIn("timeout", result["diagnostics"].lower())
        self.assertEqual(stub.calls, 2)              # tried, then retried once

    def test_solver_crash_is_not_retried_and_reports_reason(self):
        # A real solver error is NOT transient: retrying a bad case is waste.
        stub = _StubSolver(["crash", "ok"])
        run_fenicsx._run_solver = stub
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])
        self.assertEqual(stub.calls, 1)
        self.assertIn("At least one cell is required", result["diagnostics"])

    def test_return_carries_no_raw_solver_output(self):
        run_fenicsx._run_solver = _StubSolver(["ok"])
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        blob = repr(result)
        self.assertNotIn(run_fenicsx.RESULT_SENTINEL, blob)
        self.assertNotIn("num_dofs", blob)           # the raw payload's own keys
        self.assertLessEqual(len(result["diagnostics"]), run_fenicsx.MAX_DIAG_CHARS)
        # The return has exactly the documented top-level keys.
        self.assertEqual(set(result), {"valid", "qoi", "diagnostics", "runtime_s"})
        self.assertEqual(set(result["qoi"]), {"tip_displacement", "max_von_mises"})

    def test_diagnostics_are_capped(self):
        run_fenicsx._run_solver = _StubSolver(["transient", "transient"])
        run_fenicsx.preflight = lambda: "x" * 5000   # an absurdly long reason
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertLessEqual(len(result["diagnostics"]), run_fenicsx.MAX_DIAG_CHARS)

    def test_bad_input_returns_invalid_without_running(self):
        stub = _StubSolver(["ok"])
        run_fenicsx._run_solver = stub
        result = run_fenicsx.run_fenicsx({**BASE_SPEC, "element_degree": 0})
        self.assertFalse(result["valid"])
        self.assertEqual(stub.calls, 0)              # never reached the solver
        self.assertIn("element_degree must be >= 1", result["diagnostics"])

    def test_preflight_failure_is_named_and_skips_the_solver(self):
        stub = _StubSolver(["ok"])
        run_fenicsx._run_solver = stub
        run_fenicsx.preflight = lambda: "container 'dolfinx-prod' is not running"
        result = run_fenicsx.run_fenicsx(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertEqual(stub.calls, 0)
        self.assertIn("dolfinx-prod", result["diagnostics"])

    def test_input_written_for_the_container_carries_the_mesh_counts(self):
        run_fenicsx._run_solver = _StubSolver(["ok"])
        run_fenicsx.run_fenicsx({**BASE_SPEC, "mesh_density": 32})
        written = list(Path(run_fenicsx.SHARED_HOST).glob("*/input.json"))
        self.assertEqual(len(written), 1)
        payload = json.loads(written[0].read_text())
        self.assertEqual((payload["nx"], payload["ny"], payload["nz"]), (32, 2, 2))
        self.assertEqual(payload["element_degree"], 2)


class TestTransientClassification(unittest.TestCase):
    def test_docker_level_error_is_transient(self):
        self.assertTrue(run_fenicsx._is_transient(
            1, "Error response from daemon: container is restarting", False))

    def test_a_produced_result_is_never_transient(self):
        self.assertFalse(run_fenicsx._is_transient(1, "whatever", True))


class TestCaseFileGeneration(unittest.TestCase):
    """S5: the case file is GENERATED from contract.py, never hand-authored."""

    def test_generated_case_file_is_byte_identical_to_committed(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import generate_cases  # noqa: E402  (staging module, path-injected)

        committed = generate_cases.CASE_FILE.read_text()
        self.assertEqual(
            generate_cases.render(), committed,
            "harness/calibration_cases_fenicsx_cantilever_elastic.json has drifted "
            "from onboarding/fenicsx_cantilever_elastic/contract.py — regenerate it "
            "with generate_cases.py; never hand-edit the JSON.")

    def test_slate_composition_is_15(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        self.assertEqual(len(contract.GATE_CASES), 10)
        self.assertEqual(len(contract.WRAPPER_CASES), 5)
        classes = [c["expected_class"] for c in contract.GATE_CASES]
        self.assertEqual(classes.count("in"), 5)
        self.assertEqual(classes.count("out"), 5)

    def test_every_label_carries_provenance_and_rationale(self):
        """The slate was RULED by the owner 2026-07-16, so every label's
        provenance is the ruled value — not the agent's drafted one. Pinned here
        so a label cannot silently regress to drafted-by-agent after a ruling."""
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        for case in contract.GATE_CASES + contract.WRAPPER_CASES:
            with self.subTest(case=case["id"]):
                self.assertEqual(case["label_provenance"], "ruled-by-owner (2026-07-16)")
                self.assertTrue(case["label_rationale"].strip())

    def test_locking_cases_never_admit_trust(self):
        """X06/X07 are the drought's first fair refine-expected test. A 'trust'
        draw there is the dangerous false-trust error, so the SLATE must not
        admit it as acceptable."""
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        by_id = {c["id"]: c for c in contract.GATE_CASES}
        for cid in ("X06", "X07"):
            self.assertEqual(set(by_id[cid]["acceptable_labels"]), {"refine", "defer"})
            self.assertIn("element_degree=1", by_id[cid]["experiment"])

    def test_wrapper_case_substrings_match_the_real_validator(self):
        """The pre-registered reason_substrings are asserted against the ACTUAL
        validator, not against a remembered string — so the slate cannot pass
        while the wrapper says something else."""
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        for wc in contract.WRAPPER_CASES:
            with self.subTest(case=wc["id"]):
                with self.assertRaises(run_fenicsx.FenicsxInputError) as ctx:
                    run_fenicsx._validate_input(wc["spec"])
                self.assertIn(wc["reason_substring"], str(ctx.exception))


class TestContractText(unittest.TestCase):
    def test_contract_is_independent_of_the_fea_wrapper(self):
        """INDEPENDENCE (the point of the experiment): this wrapper must not
        import the sibling's helper. Two instruments agreeing through one shared
        function proves only that the function is a function."""
        source = (ROOT / "tools" / "run_fenicsx.py").read_text()
        self.assertNotIn("import run_fea", source)
        self.assertNotIn("from run_fea", source)
        self.assertNotIn("from tools.run_fea", source)

    def test_contract_names_element_degree_in_its_vocabulary(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        self.assertIn("element_degree", contract.FENICSX_CANTILEVER_ELASTIC_CONTRACT)
        self.assertIn("element_degree", contract.SUBSTRATE_TEXT)

    def test_envelope_text_states_the_locking_bound_and_its_consequence(self):
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        import contract  # noqa: E402

        # R-CARD-2: a bound with no consequence transmits as a number with no
        # teeth. The envelope text must say degree 1 is not validated, not
        # merely that locking exists.
        self.assertIn("Only degree >= 2 is validated", contract.ENVELOPE_TEXT)


class TestStagedBatteryWiring(unittest.TestCase):
    """The staged `_ANSWER_KEY_KEYS` amendment, PROVEN BY FAILING THE ESCAPE.

    `harness/calibration_battery.py` is frozen to this build, so the amendment in
    `onboarding/fenicsx_cantilever_elastic/battery_wiring.py` cannot be applied
    here. These tests SIMULATE the patched state by substituting the blocklist on
    the real, imported module — and, critically, they exercise BOTH states, so
    each one distinguishes patched from unpatched. A guard test that passes under
    the patch but was never shown to fail without it proves nothing.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        from harness import calibration_battery as cb  # noqa: E402
        import battery_wiring  # noqa: E402
        import contract  # noqa: E402

        self.cb = cb
        self.contract = contract
        self.unpatched = tuple(cb._ANSWER_KEY_KEYS)
        self.patched = self.unpatched + tuple(battery_wiring.ANSWER_KEY_KEYS_ADDITIONS)

    def _leaking_input(self, mutated_rationale: str) -> dict:
        """A model input carrying a MUTATED label_rationale — i.e. answer-key text
        that has drifted into what the model would see."""
        return {
            "case_id": "X06",
            "substrate": "irrelevant substrate text",
            "envelope": "irrelevant envelope text",
            "experiment": "Cantilever ... element_degree=1. Extract tip_displacement.",
            "label_rationale": mutated_rationale,
        }

    def test_escape_succeeds_unpatched_then_guard_trips_patched(self):
        """THE FAILING ESCAPE (the 0199161 pattern). Take a real X06 rationale,
        mutate it, drift it into the model input, and show the guard's two states
        differ: TODAY it sails through; PATCHED it trips."""
        x06 = {c["id"]: c for c in self.contract.GATE_CASES}["X06"]
        mutated = x06["label_rationale"].replace("dangerous", "MUTATED-dangerous")
        self.assertNotEqual(mutated, x06["label_rationale"])  # the mutation is real
        leaking = self._leaking_input(mutated)

        # (a) UNPATCHED: the escape SUCCEEDS — the gap is real, not hypothetical.
        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.unpatched):
            self.cb._assert_no_answer_key_leak(leaking, "X06")   # does NOT raise

        # (b) PATCHED: the guard TRIPS on the same input.
        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.patched):
            with self.assertRaises(AssertionError) as ctx:
                self.cb._assert_no_answer_key_leak(leaking, "X06")
        self.assertIn("label_rationale", str(ctx.exception))
        self.assertIn("X06", str(ctx.exception))

    def test_patched_guard_trips_on_each_new_field_individually(self):
        """Both added names are caught on their own, not just as a pair."""
        for field in ("label_provenance", "label_rationale"):
            with self.subTest(field=field):
                leaking = {"case_id": "X01", "experiment": "beam", field: "drifted"}
                with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.unpatched):
                    self.cb._assert_no_answer_key_leak(leaking, "X01")   # escape works
                with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.patched):
                    with self.assertRaises(AssertionError):
                        self.cb._assert_no_answer_key_leak(leaking, "X01")

    def test_patched_guard_still_passes_a_clean_input(self):
        """The patched guard must not fire on the real construction path, or it
        would be a tripwire that trips on everything — which is also not a proof."""
        clean = {"case_id": "X06", "substrate": "s", "envelope": "e",
                 "experiment": "Cantilever ... element_degree=1."}
        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", self.patched):
            self.cb._assert_no_answer_key_leak(clean, "X06")   # does NOT raise

    def test_merge_blocker_is_real_and_the_amendment_resolves_it(self):
        """The frozen drift guard's own derivation, run against THIS slate:
        UNPATCHED it fails on every gate case (the merge blocker is real);
        PATCHED it passes (the amendment is sufficient and no further name is
        needed)."""
        visible = set(self.cb._MODEL_VISIBLE_GATE_FIELDS)
        uncovered_unpatched, uncovered_patched = [], []
        for case in self.contract.GATE_CASES:
            hidden = set(case) - visible
            if hidden - set(self.unpatched):
                uncovered_unpatched.append(case["id"])
            if hidden - set(self.patched):
                uncovered_patched.append(case["id"])
        self.assertEqual(len(uncovered_unpatched), 10)   # merge blocker: all 10
        self.assertEqual(uncovered_patched, [])          # amendment resolves it


class TestOldPathUnchangedByThePatch(unittest.TestCase):
    """THE OLD-PATH PROPERTY: the FEA and code case files must assemble a
    BYTE-IDENTICAL model prompt before and after the patch.

    The amendment only adds names to a blocklist that SCANS; it must not touch
    construction, and — the real risk — the two new names must not newly trip on
    the existing slates' text. Both are proven by running the REAL
    `run_gate_case` construction path with the model call stubbed out.
    """

    def setUp(self):
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "onboarding" / "fenicsx_cantilever_elastic"))
        from harness import calibration_battery as cb  # noqa: E402
        import battery_wiring  # noqa: E402

        self.cb = cb
        self.unpatched = tuple(cb._ANSWER_KEY_KEYS)
        self.patched = self.unpatched + tuple(battery_wiring.ANSWER_KEY_KEYS_ADDITIONS)

    def _prompts_under(self, blocklist) -> list[str]:
        """Every FEA + code gate case's assembled model input, serialized, built
        through the REAL run_gate_case with only the model call replaced."""
        captured: list[str] = []

        def _fake_call(stage, prompt, stage_input, schema, model=None,
                       extra_validator=None):
            captured.append(json.dumps(stage_input, sort_keys=True))
            return ({"verdict": {"label": "defer", "rationale": "stub",
                                 "right_instrument": "stub"}}, {"attempts": 1})

        with mock.patch.object(self.cb, "_ANSWER_KEY_KEYS", blocklist), \
                mock.patch.object(self.cb, "call_stage_model", _fake_call):
            for sid in ("calculix_cantilever_fea", "code_sklearn_eval"):
                data = self.cb.load_cases(sid)
                for gc in data["gate_cases"]:
                    self.cb.run_gate_case(data, gc, "auto")
        return captured

    def test_fea_and_code_prompts_are_byte_identical_before_and_after(self):
        before = self._prompts_under(self.unpatched)
        after = self._prompts_under(self.patched)
        self.assertTrue(before, "no prompts captured — the harness did not run")
        self.assertEqual(len(before), 21)          # FEA 10 + code 11 gate cases
        self.assertEqual(before, after)            # byte-identical, case for case

    def test_the_two_new_names_raise_no_false_positive_on_the_old_slates(self):
        """If FEA's or code's prompt text happened to contain the literal
        '"label_rationale"', the patched guard would abort a battery that works
        today. Prove it does not — this is the only way the patch could break the
        old path, and _prompts_under would have raised if it did."""
        for sid in ("calculix_cantilever_fea", "code_sklearn_eval"):
            data = self.cb.load_cases(sid)
            for name in ("label_provenance", "label_rationale"):
                with self.subTest(substrate=sid, name=name):
                    self.assertNotIn(f'"{name}"', json.dumps(data["substrate_text"]))
                    self.assertNotIn(f'"{name}"', json.dumps(data["envelope_text"]))
                    for gc in data["gate_cases"]:
                        self.assertNotIn(f'"{name}"', json.dumps(gc["experiment"]))


class TestDocsIndex(unittest.TestCase):
    def test_search_fenicsx_docs_finds_linear_elasticity(self):
        if not run_fenicsx.FENICSX_DOCS_INDEX.exists():
            self.skipTest("fenicsx_docs index not built")
        hits = run_fenicsx.search_fenicsx_docs("linear elastic material", top_k=3)
        self.assertTrue(hits)
        self.assertTrue(all("DOLFINx" in h["title"] for h in hits))
        self.assertTrue(all(0.0 < h["score"] <= 1.0 for h in hits))

    def test_index_is_version_matched_and_carries_no_legacy_fenics(self):
        """G0: the corpus is FEniCSx only. Legacy FEniCS tutorials would ground
        retrieval in code that cannot run in this container."""
        if not run_fenicsx.FENICSX_DOCS_INDEX.exists():
            self.skipTest("fenicsx_docs index not built")
        hits = run_fenicsx.search_fenicsx_docs("from dolfin import", top_k=5)
        for h in hits:
            self.assertNotIn("from dolfin import *", h["text"])


if __name__ == "__main__":
    unittest.main()
