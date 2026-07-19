"""test_run_retrosynthesis.py — retrosynthesis wrapper (D.2, DEFERRED).
Proven now: input gate + honest DEFERRED, never a fabricated route."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_retrosynthesis import (BACKEND_ALLOWLIST, QOI_FIELDS,
    RetrosynthesisInputError, _validate_input, models_and_backend_available,
    run_retrosynthesis as run)


class InputGate(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(_validate_input({"target_smiles": "CCO", "backend": "aizynth", "quantity": "synthesizability"})["backend"], "aizynth")
    def test_empty_smiles_rejected(self):
        with self.assertRaises(RetrosynthesisInputError):
            _validate_input({"target_smiles": "  ", "backend": "aizynth", "quantity": "synthesizability"})
    def test_bad_smiles_chars_rejected(self):
        with self.assertRaises(RetrosynthesisInputError):
            _validate_input({"target_smiles": "hello world!", "backend": "aizynth", "quantity": "synthesizability"})
    def test_bad_backend_rejected(self):
        with self.assertRaises(RetrosynthesisInputError):
            _validate_input({"target_smiles": "CCO", "backend": "rxn4chem", "quantity": "synthesizability"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(RetrosynthesisInputError):
            _validate_input({"target_smiles": "CCO", "backend": "aizynth", "quantity": "route"})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("synthesizability",))
        self.assertEqual(BACKEND_ALLOWLIST, ("aizynth", "askcos"))


class DeferredState(unittest.TestCase):
    def test_backend_absent_here(self):
        self.assertIsNotNone(models_and_backend_available())
    def test_valid_input_returns_deferred(self):
        r = run({"target_smiles": "CCO", "backend": "aizynth", "quantity": "synthesizability"})
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"]); self.assertIn("DEFERRED", r["diagnostics"])
    def test_bad_input_refused_first(self):
        self.assertIn("input rejected", run({"target_smiles": "CCO", "backend": "nope", "quantity": "synthesizability"})["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
