"""test_composition.py — one experiment that CALLS several tools, verified.

Phase 1, T1.2/T1.3 (docs/memo_phase1_composition.md, R-COMP-1..5). Proves the
first genuine two-tool composition: two mature substrates on two different
production containers, their scalars combined by a sealed code step, run once
and then INDEPENDENTLY reproduced end-to-end by the same verification pass that
already guards single artifacts.

The load-bearing property is R-COMP-4: running a composition and re-running it
are the same deterministic code path, so the number a composition produces is
the number verification regenerates — a composed result that cannot be
reproduced is caught, never shipped. The reproduction assertions here are
genuine re-executions of real wrappers (rdkit-prod, cobrapy-prod), not fakes
agreeing with themselves.

Run directly: venv/bin/python3 tests/test_composition.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.verification import (  # noqa: E402
    ArtifactError,
    rerun_artifact,
    run_composition,
    verify_claim,
)
from tools import substrate_dispatch as dispatch  # noqa: E402
from tools.run_cobrapy import run_cobrapy  # noqa: E402
from tools.run_rdkit import run_rdkit  # noqa: E402

TD = dispatch.CALL_TYPED_DICT


def _rdkit_step(step_id="mass", smiles="CCO", quantity="MolWt"):
    return {"step_id": step_id, "kind": "substrate", "substrate_id": "rdkit",
            "call_style": TD,
            "typed_input": {"smiles": smiles, "quantity": quantity},
            "quantity": quantity, "qoi_request": {"quantity": quantity}}


def _cobrapy_step(step_id="growth", model="e_coli_core", quantity="growth_rate"):
    return {"step_id": step_id, "kind": "substrate", "substrate_id": "cobrapy",
            "call_style": TD,
            "typed_input": {"model": model, "quantity": quantity},
            "quantity": quantity, "qoi_request": {"quantity": quantity}}


def _code_step(step_id, code, quantity):
    return {"step_id": step_id, "kind": "code", "code": code, "quantity": quantity}


class TestRecipeValidation(unittest.TestCase):
    """A malformed recipe is a broken artifact — it raises, fast, before any
    container is touched (these tests make no wrapper call)."""

    def _bad(self, recipe, needle):
        with self.assertRaises(ArtifactError) as ctx:
            rerun_artifact(recipe)
        self.assertIn(needle, str(ctx.exception))

    def test_no_steps(self):
        self._bad({"kind": "composition", "steps": [],
                   "combine": {"kind": "code", "code": "x", "quantity": "q",
                               "inputs": []}}, "non-empty 'steps'")

    def test_duplicate_step_id(self):
        self._bad({"kind": "composition",
                   "steps": [_code_step("a", "metrics['a']=1.0", "a"),
                             _code_step("a", "metrics['a']=2.0", "a")],
                   "combine": {"kind": "code", "code": "metrics['q']=inputs['a']",
                               "quantity": "q", "inputs": ["a"]}},
                  "not unique")

    def test_combine_references_unknown_step(self):
        self._bad({"kind": "composition",
                   "steps": [_code_step("a", "metrics['a']=1.0", "a")],
                   "combine": {"kind": "code",
                               "code": "metrics['q']=inputs['b']",
                               "quantity": "q", "inputs": ["b"]}},
                  "unknown step")

    def test_combine_must_be_code(self):
        self._bad({"kind": "composition",
                   "steps": [_code_step("a", "metrics['a']=1.0", "a")],
                   "combine": {"kind": "substrate", "quantity": "q",
                               "inputs": ["a"]}},
                  "must be a 'code' step")

    def test_step_must_be_code_or_substrate(self):
        self._bad({"kind": "composition",
                   "steps": [{"step_id": "a", "kind": "composition"}],
                   "combine": {"kind": "code", "code": "metrics['q']=1.0",
                               "quantity": "q", "inputs": []}},
                  "'code' or 'substrate'")


class TestCodeOnlyComposition(unittest.TestCase):
    """Two sealed code steps + a code combine — the whole recipe machinery
    without external science. Injected inputs reach the combine and are
    genuinely computed against."""

    def test_two_code_steps_combine(self):
        recipe = {"kind": "composition",
                  "steps": [_code_step("a", "metrics['a']=1.0", "a"),
                            _code_step("b", "metrics['b']=2.0", "b")],
                  "combine": {"kind": "code",
                              "code": "metrics['sum'] = inputs['a'] + inputs['b']",
                              "quantity": "sum", "inputs": ["a", "b"]}}
        out = run_composition(recipe)
        self.assertIsNone(out["error"])
        self.assertEqual(out["value"], 3.0)
        self.assertEqual(out["steps"], {"a": 1.0, "b": 2.0})
        # and it reproduces through the same pass a single artifact uses
        verdict = verify_claim({"value": out["value"], "artifact": out["artifact"]})
        self.assertTrue(verdict["verified"], verdict)
        self.assertEqual(verdict["reason"], "reproduced")

    def test_a_failing_step_fails_the_whole_composition(self):
        recipe = {"kind": "composition",
                  "steps": [_code_step("a", "metrics['a']=1.0", "a"),
                            _code_step("b", "raise ValueError('boom')", "b")],
                  "combine": {"kind": "code",
                              "code": "metrics['sum'] = inputs['a'] + inputs['b']",
                              "quantity": "sum", "inputs": ["a", "b"]}}
        out = run_composition(recipe)
        self.assertIsNone(out["value"])
        self.assertIn("step 'b'", out["error"])
        # a composition that could not run is not publishable
        verdict = verify_claim({"value": 3.0, "artifact": recipe})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "rerun_failed")

    def test_a_hardcoded_combine_is_caught(self):
        """The combine reproduces perfectly — because the number is written into
        the source, measuring nothing about the steps. The tripwire catches it."""
        recipe = {"kind": "composition",
                  "steps": [_code_step("a", "metrics['a']=1.0", "a"),
                            _code_step("b", "metrics['b']=2.0", "b")],
                  "combine": {"kind": "code", "code": "metrics['sum'] = 3.0",
                              "quantity": "sum", "inputs": ["a", "b"]}}
        verdict = verify_claim({"value": 3.0, "artifact": recipe})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "hardcoded_constant")


class TestTwoToolComposition(unittest.TestCase):
    """The real thing: rdkit (rdkit-prod) x cobrapy (cobrapy-prod), one
    composed scalar, independently reproduced. Two different substrates, two
    different containers, one experiment."""

    @classmethod
    def setUpClass(cls):
        # Ground truth from direct wrapper calls, so the composition's
        # intermediates are checked against the instruments themselves.
        cls.mass = run_rdkit({"smiles": "CCO", "quantity": "MolWt"})
        cls.growth = run_cobrapy({"model": "e_coli_core", "quantity": "growth_rate"})
        if not (cls.mass["valid"] and cls.growth["valid"]):
            raise unittest.SkipTest(
                "rdkit-prod / cobrapy-prod not producing values "
                f"(mass={cls.mass['diagnostics']}; growth={cls.growth['diagnostics']})")

    def _recipe(self):
        return {"kind": "composition",
                "steps": [_cobrapy_step("growth"), _rdkit_step("mass")],
                "combine": {"kind": "code",
                            "code": ("metrics['growth_per_mass'] = "
                                     "inputs['growth'] / inputs['mass']"),
                            "quantity": "growth_per_mass",
                            "inputs": ["growth", "mass"]}}

    def test_composition_runs_and_intermediates_match_the_instruments(self):
        out = run_composition(self._recipe())
        self.assertIsNone(out["error"], out["error"])
        self.assertEqual(out["steps"]["mass"], self.mass["qoi"])
        self.assertEqual(out["steps"]["growth"], self.growth["qoi"])
        expected = self.growth["qoi"] / self.mass["qoi"]
        self.assertAlmostEqual(out["value"], expected, places=12)

    def test_the_composed_number_independently_reproduces(self):
        out = run_composition(self._recipe())
        verdict = verify_claim({"value": out["value"], "artifact": out["artifact"],
                                "label": "growth_per_mass"})
        self.assertTrue(verdict["verified"], verdict)
        self.assertEqual(verdict["reason"], "reproduced")
        self.assertLessEqual(verdict["rel_error"], 1e-6)

    def test_a_perturbed_composed_value_is_caught(self):
        out = run_composition(self._recipe())
        verdict = verify_claim({"value": out["value"] * 1.1,
                                "artifact": out["artifact"]})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "mismatch")
        self.assertAlmostEqual(verdict["reproduced"], out["value"], places=12)


if __name__ == "__main__":
    unittest.main()
