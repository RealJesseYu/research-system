"""
test_run_rdkit.py — the RDKit descriptor wrapper (BIO Wave D.2, T1).

Two layers:
  * PURE tests (no container): input validation + jail classification — the
    allowlist gate, missing/extra fields, the descriptor-off-allowlist reject.
    These run everywhere.
  * LIVE tests (rdkit-prod required): real descriptor values + the SMILES-parse
    jail + determinism, proven by TRIGGERING the failure, not reading config.
    Skipped (never failed) when the container is down, mirroring the
    container-gated FEA/ngspice live tests.

Run directly: venv/bin/python3 tests/test_run_rdkit.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_rdkit
from tools.run_rdkit import QOI_FIELDS, RdkitInputError, _validate_input, run_rdkit as run

_LIVE = run_rdkit.preflight() is None  # rdkit-prod up?


class PureValidation(unittest.TestCase):
    def test_clean_input_passes(self):
        self.assertEqual(
            _validate_input({"smiles": "CCO", "quantity": "MolWt"}),
            {"smiles": "CCO", "quantity": "MolWt"},
        )

    def test_missing_field_rejected_by_name(self):
        with self.assertRaises(RdkitInputError) as e:
            _validate_input({"smiles": "CCO"})
        self.assertIn("quantity", str(e.exception))

    def test_extra_field_rejected_by_name(self):
        with self.assertRaises(RdkitInputError) as e:
            _validate_input({"smiles": "CCO", "quantity": "MolWt", "sneaky": 1})
        self.assertIn("sneaky", str(e.exception))

    def test_empty_smiles_rejected(self):
        with self.assertRaises(RdkitInputError):
            _validate_input({"smiles": "   ", "quantity": "MolWt"})

    def test_descriptor_off_allowlist_rejected(self):
        # JAIL 2, pure: a descriptor not on the fixed allowlist never runs.
        with self.assertRaises(RdkitInputError) as e:
            _validate_input({"smiles": "CCO", "quantity": "NotADescriptor"})
        self.assertIn("allowlist", str(e.exception))

    def test_off_allowlist_quantity_fails_loud_through_run(self):
        # same jail, through the public entry: no container needed (pre-run).
        r = run({"smiles": "CCO", "quantity": "NotADescriptor"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("input rejected", r["diagnostics"])

    def test_allowlist_is_nonempty_and_stringy(self):
        self.assertTrue(QOI_FIELDS)
        self.assertTrue(all(isinstance(n, str) for n in QOI_FIELDS))
        self.assertIn("MolWt", QOI_FIELDS)
        self.assertIn("MolLogP", QOI_FIELDS)  # the computed-proxy descriptor (C1-hole)


@unittest.skipUnless(_LIVE, "rdkit-prod not running — live descriptor checks skipped")
class LiveDescriptors(unittest.TestCase):
    def test_ethanol_molwt(self):
        r = run({"smiles": "CCO", "quantity": "MolWt"})
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["qoi"], 46.069, places=2)

    def test_bad_smiles_is_jailed(self):
        # JAIL 1, triggered: an unparseable SMILES returns no number.
        r = run({"smiles": "this_is_not_smiles", "quantity": "MolWt"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("parse", r["diagnostics"].lower())

    def test_unsanitizable_valence_is_jailed(self):
        # JAIL 1, triggered: pentavalent carbon fails RDKit sanitization -> None.
        r = run({"smiles": "C(C)(C)(C)(C)C", "quantity": "MolWt"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])

    def test_determinism_identical_repeat(self):
        a = run({"smiles": "c1ccccc1", "quantity": "MolLogP"})
        b = run({"smiles": "c1ccccc1", "quantity": "MolLogP"})
        self.assertTrue(a["valid"] and b["valid"])
        self.assertEqual(a["qoi"], b["qoi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
