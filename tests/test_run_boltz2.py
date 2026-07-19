"""test_run_boltz2.py — Boltz-2 wrapper (D.2, DEFERRED — no GPU here).
Proven now (pure-Python): the input gate + that a valid input returns the honest
DEFERRED state, never a fabricated prediction."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_boltz2 import (QOI_FIELDS, Boltz2InputError, _validate_input,
                              gpu_and_weights_available, run_boltz2 as run)


class InputGate(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(_validate_input({"protein_sequence": "MKTAY", "quantity": "affinity"})["quantity"], "affinity")
    def test_clean_with_ligand(self):
        self.assertEqual(_validate_input({"protein_sequence": "MKTAY", "quantity": "rmsd", "ligand": "CCO"})["ligand"], "CCO")
    def test_non_protein_rejected(self):
        with self.assertRaises(Boltz2InputError):
            _validate_input({"protein_sequence": "12345", "quantity": "affinity"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(Boltz2InputError):
            _validate_input({"protein_sequence": "MKTAY", "quantity": "kd"})
    def test_missing_field_rejected(self):
        with self.assertRaises(Boltz2InputError):
            _validate_input({"protein_sequence": "MKTAY"})
    def test_empty_ligand_rejected(self):
        with self.assertRaises(Boltz2InputError):
            _validate_input({"protein_sequence": "MKTAY", "quantity": "affinity", "ligand": " "})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("affinity", "rmsd"))


class DeferredState(unittest.TestCase):
    def test_no_gpu_here(self):
        self.assertIsNotNone(gpu_and_weights_available())
    def test_valid_input_returns_deferred_not_a_prediction(self):
        r = run({"protein_sequence": "MKTAYIAKQR", "quantity": "affinity"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("DEFERRED", r["diagnostics"])
    def test_bad_input_refused_before_deferral(self):
        r = run({"protein_sequence": "12345", "quantity": "affinity"})
        self.assertIn("input rejected", r["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
