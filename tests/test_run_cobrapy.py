"""
test_run_cobrapy.py — the COBRApy FBA wrapper (BIO Wave D.2, T1).

Two layers (mirrors test_run_rdkit):
  * PURE tests (no container): input validation + jail classification.
  * LIVE tests (cobrapy-prod required): real FBA on e_coli_core AND the
    genome-scale iML1515, plus THE STATUS-GATE JAIL proven by triggering it on
    BOTH models — an infeasible solve returns None, never the stale objective.
    That infeasible test is the proof the gate can fail (owner ruling 2).

Run directly: venv/bin/python3 tests/test_run_cobrapy.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_cobrapy
from tools.run_cobrapy import (
    MODEL_ALLOWLIST, QOI_FIELDS, CobrapyInputError, _validate_input,
    run_cobrapy as run,
)

_LIVE = run_cobrapy.preflight() is None  # cobrapy-prod up?


class PureValidation(unittest.TestCase):
    def test_clean_input_passes(self):
        self.assertEqual(
            _validate_input({"model": "e_coli_core", "quantity": "growth_rate"}),
            {"model": "e_coli_core", "quantity": "growth_rate", "min_growth": None},
        )

    def test_model_off_allowlist_rejected(self):
        with self.assertRaises(CobrapyInputError) as e:
            _validate_input({"model": "not_a_model", "quantity": "growth_rate"})
        self.assertIn("allowlist", str(e.exception))

    def test_quantity_off_allowlist_rejected(self):
        with self.assertRaises(CobrapyInputError):
            _validate_input({"model": "e_coli_core", "quantity": "flux"})

    def test_missing_and_extra_fields_rejected(self):
        with self.assertRaises(CobrapyInputError):
            _validate_input({"model": "e_coli_core"})
        with self.assertRaises(CobrapyInputError) as e:
            _validate_input({"model": "e_coli_core", "quantity": "growth_rate", "x": 1})
        self.assertIn("x", str(e.exception))

    def test_negative_min_growth_rejected(self):
        with self.assertRaises(CobrapyInputError):
            _validate_input({"model": "e_coli_core", "quantity": "growth_rate",
                             "min_growth": -1})

    def test_bad_model_fails_loud_through_run(self):
        r = run({"model": "not_a_model", "quantity": "growth_rate"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("input rejected", r["diagnostics"])

    def test_vocabularies_are_the_baked_set(self):
        self.assertEqual(MODEL_ALLOWLIST, ("e_coli_core", "iML1515"))
        self.assertEqual(QOI_FIELDS, ("growth_rate",))


@unittest.skipUnless(_LIVE, "cobrapy-prod not running — live FBA checks skipped")
class LiveFBA(unittest.TestCase):
    def test_e_coli_core_optimal_growth(self):
        r = run({"model": "e_coli_core", "quantity": "growth_rate"})
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["qoi"], 0.8739, places=3)
        self.assertIn("status=optimal", r["diagnostics"])

    def test_iml1515_genome_scale_optimal_growth(self):
        r = run({"model": "iML1515", "quantity": "growth_rate"})
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["qoi"], 0.8770, places=3)

    def test_infeasible_returns_none_not_stale_objective__e_coli_core(self):
        # THE STATUS-GATE JAIL, triggered: an unachievable biomass lower bound
        # makes the solve infeasible. cobra still exposes a stale objective
        # (~0.8739); the wrapper MUST return None, never that number.
        r = run({"model": "e_coli_core", "quantity": "growth_rate", "min_growth": 1000})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertNotEqual(r["qoi"], 0.8739215069684305)
        self.assertIn("infeasible", r["diagnostics"].lower())

    def test_infeasible_returns_none_on_the_real_model__iml1515(self):
        # the same gate, proven on the genome-scale model (owner ruling: exercise
        # the infeasible jail on the real model too).
        r = run({"model": "iML1515", "quantity": "growth_rate", "min_growth": 1000})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("infeasible", r["diagnostics"].lower())

    def test_feasible_min_growth_still_optimal(self):
        r = run({"model": "e_coli_core", "quantity": "growth_rate", "min_growth": 0.5})
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["qoi"], 0.8739, places=3)

    def test_determinism_identical_repeat(self):
        a = run({"model": "iML1515", "quantity": "growth_rate"})
        b = run({"model": "iML1515", "quantity": "growth_rate"})
        self.assertEqual(a["qoi"], b["qoi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
