"""
test_stage2_code_iteration.py — stage 2's authoring-time code-execution check
(stages/stage2_experiment_design.py, 2026-07-21).

WHAT THIS PROVES, with an INJECTED runner (no container, no model):
  - for python_experiment, a spec whose code RUNS (runner -> valid) produces no
    error, so authoring accepts it on that attempt;
  - a spec whose code FAILS (runner -> valid=False) surfaces the wrapper's
    verbatim diagnostic as a re-ask error, so call_stage_model will feed it back
    and the model re-authors the code — the tight loop, at authoring time;
  - the container is NEVER run for any non-python substrate (gated), so cavity /
    ngspice / bio authoring is byte-identical;
  - the container is NEVER run when the cheap checks (envelope / validate_spec /
    serve-ability) already failed — no execution for a shape-invalid spec.

Run directly: venv/bin/python3 tests/test_stage2_code_iteration.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.stage2_experiment_design import (  # noqa: E402
    _code_execution_errors,
    _make_extra_validator,
)
from stages.stage2_spec import validate_spec  # noqa: E402
from tools.qoi_vocab import vocab_for  # noqa: E402

SID = "python_experiment"
_CODE = "metrics = {'r2': 0.9}\n"


def _code_spec(quantity="r2"):
    return {
        "hypothesis_id": "h1",
        "title": "Ridge CV baseline",
        "objective": "Measure the cross-validated R2.",
        "parameters": [],
        "regime": {"code": _CODE, "notes": "single deterministic seeded run"},
        "qoi": {
            "name": "cross-validated R2", "units": "dimensionless",
            "definition": "mean 5-fold CV R2", "how_extracted": "read metric r2",
            "quantity": quantity,
        },
        "success_criterion": {"statement": "explains most variance",
                              "threshold": 0.5, "direction": "above"},
        "mini_experiment": {"runs": [{}], "expected_observation": "R2 near 0.9"},
        "full_experiment": {"design": "sweep alpha", "estimated_run_count": 5},
    }


class SpyRunner:
    """Records the specs it was handed and returns a scripted summary."""

    def __init__(self, summary):
        self._summary = summary
        self.specs_seen = []

    def __call__(self, spec):
        self.specs_seen.append(spec)
        return self._summary


_VALID = {"valid": True, "qoi": 0.9, "metrics": {"r2": 0.9},
          "diagnostics": "ok", "runtime_s": 0.2}
_INVALID = {"valid": False, "qoi": None, "metrics": {},
            "diagnostics": "the experiment exited 1 — NameError: np is not defined",
            "runtime_s": 0.1}


class CodeExecutionErrors(unittest.TestCase):
    """The new helper, in isolation."""

    def test_gated_off_for_non_python_substrate(self):
        runner = SpyRunner(_INVALID)
        errs = _code_execution_errors(_code_spec(), "cavity_2d_cfd", runner)
        self.assertEqual(errs, [])
        self.assertEqual(runner.specs_seen, [])  # container never touched

    def test_clean_code_yields_no_error(self):
        runner = SpyRunner(_VALID)
        errs = _code_execution_errors(_code_spec(), SID, runner)
        self.assertEqual(errs, [])
        # it ran exactly what stage 4 would: {code, quantity}
        self.assertEqual(len(runner.specs_seen), 1)
        self.assertEqual(runner.specs_seen[0]["code"], _CODE)
        self.assertEqual(runner.specs_seen[0]["quantity"], "r2")

    def test_failing_code_surfaces_the_verbatim_diagnostic(self):
        runner = SpyRunner(_INVALID)
        errs = _code_execution_errors(_code_spec(), SID, runner)
        self.assertEqual(len(errs), 1)
        self.assertIn("NameError: np is not defined", errs[0])
        self.assertIn("'r2'", errs[0])

    def test_missing_code_defers_to_cheap_checks_not_a_run(self):
        spec = _code_spec()
        del spec["regime"]["code"]
        runner = SpyRunner(_INVALID)
        errs = _code_execution_errors(spec, SID, runner)
        self.assertEqual(errs, [])
        self.assertEqual(runner.specs_seen, [])  # never executed a codeless spec


class ValidatorWiring(unittest.TestCase):
    """The whole extra_validator: cheap checks first, code check only after."""

    def _validator(self, runner):
        return _make_extra_validator("h1", vocab_for(SID), SID, runner=runner)

    def test_clean_python_spec_passes(self):
        runner = SpyRunner(_VALID)
        check = self._validator(runner)
        errs = check({"ack_run_id": "r1", "spec": _code_spec()})
        self.assertEqual(errs, [])
        self.assertEqual(len(runner.specs_seen), 1)  # code was executed

    def test_failing_python_spec_returns_the_diagnostic(self):
        runner = SpyRunner(_INVALID)
        check = self._validator(runner)
        errs = check({"ack_run_id": "r1", "spec": _code_spec()})
        self.assertTrue(any("NameError" in e for e in errs))

    def test_shape_broken_spec_never_runs_the_container(self):
        # an extra envelope field is a cheap error; the code check must be
        # skipped entirely (no container for an already-invalid reply).
        runner = SpyRunner(_INVALID)
        check = self._validator(runner)
        errs = check({"ack_run_id": "r1", "spec": _code_spec(), "extra": 1})
        self.assertTrue(any("not allowed" in e for e in errs))
        self.assertEqual(runner.specs_seen, [])

    def test_sanity_baseline_spec_is_actually_valid(self):
        # guards the fixture: the spec passes validate_spec, so the only thing
        # the wiring tests can be exercising is the code check.
        self.assertEqual(validate_spec(_code_spec(), "h1", vocab_for(SID)), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
