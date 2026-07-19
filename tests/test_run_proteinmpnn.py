"""test_run_proteinmpnn.py — ProteinMPNN wrapper (D.2, DEFERRED — no GPU).
Proven now: input gate + honest DEFERRED state, never a fabricated score."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_proteinmpnn import (BACKBONE_ALLOWLIST, QOI_FIELDS,
    ProteinMPNNInputError, _validate_input, gpu_and_weights_available,
    run_proteinmpnn as run)


class InputGate(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(_validate_input({"backbone": "demo_backbone", "quantity": "seq_recovery"})["quantity"], "seq_recovery")
    def test_bad_backbone_rejected(self):
        with self.assertRaises(ProteinMPNNInputError):
            _validate_input({"backbone": "1abc", "quantity": "seq_recovery"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(ProteinMPNNInputError):
            _validate_input({"backbone": "demo_backbone", "quantity": "perplexity"})
    def test_missing_and_extra_rejected(self):
        with self.assertRaises(ProteinMPNNInputError):
            _validate_input({"backbone": "demo_backbone"})
        with self.assertRaises(ProteinMPNNInputError):
            _validate_input({"backbone": "demo_backbone", "quantity": "seq_recovery", "x": 1})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("seq_recovery",))
        self.assertEqual(BACKBONE_ALLOWLIST, ("demo_backbone",))


class DeferredState(unittest.TestCase):
    def test_no_gpu_here(self):
        self.assertIsNotNone(gpu_and_weights_available())
    def test_valid_input_returns_deferred(self):
        r = run({"backbone": "demo_backbone", "quantity": "seq_recovery"})
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"]); self.assertIn("DEFERRED", r["diagnostics"])
    def test_bad_input_refused_first(self):
        self.assertIn("input rejected", run({"backbone": "1abc", "quantity": "seq_recovery"})["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
