"""
test_run_crispr_guide_scoring.py — the CRISPR guide-scoring wrapper (D.2, DEFERRED).

Re-tiered T2 -> DEFERRED: no verified py3 Doench/CFD scorer runs here (Azimuth is
Python-2; no standalone CFD package). The scoring §3A is produced at provisioning
with a verified scorer artifact. Proven NOW (all pure-Python, no scorer):
  * the input gate (valid guide, valid PAM matching the enzyme motif, form);
  * that a valid input returns the honest DEFERRED state — NEVER a fabricated
    score from an unverified model.

Run directly: venv/bin/python3 tests/test_run_crispr_guide_scoring.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.run_crispr_guide_scoring import (
    ENZYME_ALLOWLIST, QOI_FIELDS, CrisprInputError, _pam_matches_motif,
    _validate_input, run_crispr_guide_scoring as run, scorer_available,
)

_G = "GACGCATAAAGATGAGACGC"  # a valid 20-nt guide


def _spec(**over):
    base = {"guide": _G, "pam": "TGG", "enzyme": "SpCas9",
            "quantity": "activity_score"}
    base.update(over)
    return base


class InputGate(unittest.TestCase):
    def test_clean_input_passes(self):
        out = _validate_input(_spec())
        self.assertEqual(out["enzyme"], "SpCas9")
        self.assertEqual(out["guide"], _G)

    def test_guide_wrong_length_rejected(self):
        with self.assertRaises(CrisprInputError) as e:
            _validate_input(_spec(guide="ACGT"))
        self.assertIn("20", str(e.exception))

    def test_guide_non_dna_rejected(self):
        with self.assertRaises(CrisprInputError):
            _validate_input(_spec(guide="GACGCATAAAGATGAGACGX"))

    def test_pam_not_matching_motif_rejected(self):
        with self.assertRaises(CrisprInputError) as e:
            _validate_input(_spec(pam="TAA"))  # not N GG
        self.assertIn("motif", str(e.exception))

    def test_pam_wrong_length_rejected(self):
        with self.assertRaises(CrisprInputError):
            _validate_input(_spec(pam="GG"))

    def test_bad_enzyme_rejected(self):
        with self.assertRaises(CrisprInputError):
            _validate_input(_spec(enzyme="Cas12a"))

    def test_bad_quantity_rejected(self):
        with self.assertRaises(CrisprInputError):
            _validate_input(_spec(quantity="score"))

    def test_pam_motif_helper(self):
        self.assertTrue(_pam_matches_motif("AGG", "NGG"))
        self.assertTrue(_pam_matches_motif("TGG", "NGG"))
        self.assertFalse(_pam_matches_motif("TAA", "NGG"))
        self.assertFalse(_pam_matches_motif("GG", "NGG"))

    def test_vocabularies(self):
        self.assertEqual(QOI_FIELDS, ("activity_score",))
        self.assertEqual(ENZYME_ALLOWLIST, ("SpCas9",))


class DeferredState(unittest.TestCase):
    def test_no_verified_scorer_here(self):
        self.assertIsNotNone(scorer_available())

    def test_valid_input_returns_deferred_not_a_fabricated_score(self):
        r = run(_spec())
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("DEFERRED", r["diagnostics"])

    def test_input_jail_fires_before_deferral(self):
        r = run(_spec(pam="TAA"))
        self.assertFalse(r["valid"])
        self.assertIn("input rejected", r["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
