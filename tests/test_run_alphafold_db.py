"""test_run_alphafold_db.py — AFDB lookup wrapper (D.2, DEFERRED — network).
Proven now: input gate + honest DEFERRED, never a fabricated pLDDT."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_alphafold_db import (QOI_FIELDS, AlphaFoldDBInputError,
    _validate_input, afdb_endpoint_available, run_alphafold_db as run)


class InputGate(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(_validate_input({"protein_sequence": "MKTAY", "quantity": "mean_pLDDT"})["quantity"], "mean_pLDDT")
    def test_non_protein_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"protein_sequence": "12345", "quantity": "mean_pLDDT"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"protein_sequence": "MKTAY", "quantity": "plddt"})
    def test_missing_and_extra_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"protein_sequence": "MKTAY"})
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"protein_sequence": "MKTAY", "quantity": "mean_pLDDT", "x": 1})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("mean_pLDDT",))


class DeferredState(unittest.TestCase):
    def test_endpoint_absent_here_and_never_trust_alone_noted(self):
        r = afdb_endpoint_available()
        self.assertIsNotNone(r)
        self.assertIn("NEVER-TRUSTED-ALONE", r)  # permanent claim surfaced
    def test_valid_input_returns_deferred(self):
        r = run({"protein_sequence": "MKTAYIAKQR", "quantity": "mean_pLDDT"})
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"]); self.assertIn("DEFERRED", r["diagnostics"])
    def test_bad_input_refused_first(self):
        self.assertIn("input rejected", run({"protein_sequence": "12345", "quantity": "mean_pLDDT"})["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
