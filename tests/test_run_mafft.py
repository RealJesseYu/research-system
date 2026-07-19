"""
test_run_mafft.py — the MAFFT MSA wrapper (BIO Wave D.2, T2).

MAFFT is near-total (garbage in -> well-formed alignment of garbage out), so the
did-it-work signal is the STRICT INPUT GATE, checked BEFORE running:
  * PURE tests (no container): the input gate refuses un-alignable input up front
    (single sequence, empty, invalid residues, mixed alphabet) — proven by
    triggering; plus the pure alignment_identity metric.
  * LIVE tests (mafft-prod): a real alignment's identity + determinism.

Run directly: venv/bin/python3 tests/test_run_mafft.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_mafft
from tools.run_mafft import (
    QOI_FIELDS, MafftInputError, _validate_input, alignment_identity,
    run_mafft as run,
)

_LIVE = run_mafft.preflight() is None


class StrictInputGate(unittest.TestCase):
    def test_two_valid_sequences_pass(self):
        out = _validate_input({"sequences": ["MKTAY", "MKTAI"],
                               "quantity": "alignment_identity"})
        self.assertEqual(out["alphabet"], "aa")
        self.assertEqual(len(out["sequences"]), 2)

    def test_single_sequence_refused(self):
        with self.assertRaises(MafftInputError) as e:
            _validate_input({"sequences": ["MKTAY"], "quantity": "alignment_identity"})
        self.assertIn(">= 2", str(e.exception))

    def test_empty_sequence_refused(self):
        with self.assertRaises(MafftInputError):
            _validate_input({"sequences": ["MKTAY", "   "],
                             "quantity": "alignment_identity"})

    def test_invalid_residue_junk_refused(self):
        # the plausible-wrong-answer prevention: junk is refused, not aligned.
        with self.assertRaises(MafftInputError):
            _validate_input({"sequences": ["MKTAY", "12345!@#"],
                             "quantity": "alignment_identity"})

    def test_mixed_alphabet_refused(self):
        with self.assertRaises(MafftInputError) as e:
            _validate_input({"sequences": ["MKTAYIAKQR", "ACGTACGTAC"],
                             "quantity": "alignment_identity"})
        self.assertIn("alphabet", str(e.exception).lower())

    def test_non_list_refused(self):
        with self.assertRaises(MafftInputError):
            _validate_input({"sequences": "MKTAY", "quantity": "alignment_identity"})

    def test_bad_quantity_refused(self):
        with self.assertRaises(MafftInputError):
            _validate_input({"sequences": ["MKTAY", "MKTAI"], "quantity": "sp_score"})

    def test_gate_fires_through_run_before_container(self):
        # a single sequence is refused with no container needed.
        r = run({"sequences": ["MKTAY"], "quantity": "alignment_identity"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("input rejected", r["diagnostics"])


class AlignmentIdentityMetric(unittest.TestCase):
    def test_identical_alignment_is_100(self):
        self.assertEqual(alignment_identity(["ABC", "ABC"]), 100.0)

    def test_one_mismatch_in_three(self):
        self.assertAlmostEqual(alignment_identity(["ABC", "ABD"]), 200.0 / 3)

    def test_gaps_ignored_in_comparison(self):
        # only non-gap columns are compared
        self.assertEqual(alignment_identity(["A-C", "A-C"]), 100.0)

    def test_unequal_rows_raise(self):
        with self.assertRaises(ValueError):
            alignment_identity(["ABC", "AB"])

    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("alignment_identity",))


@unittest.skipUnless(_LIVE, "mafft-prod not running — live MSA checks skipped")
class LiveMafft(unittest.TestCase):
    def test_real_alignment_identity(self):
        r = run({"sequences": ["MKTAYIAKQRQISFVKSHFSRQLE",
                               "MKTAYIAKQRAISFVKSHFSRQLE",
                               "MKTAYIAKQRQISFVKSHYSRQLE"],
                 "quantity": "alignment_identity"})
        self.assertTrue(r["valid"])
        self.assertGreater(r["qoi"], 90.0)
        self.assertLessEqual(r["qoi"], 100.0)

    def test_determinism_identical_repeat(self):
        seqs = ["MKTAYIAKQRQISFV", "MKTAYIAKQRAISFV"]
        a = run({"sequences": seqs, "quantity": "alignment_identity"})
        b = run({"sequences": seqs, "quantity": "alignment_identity"})
        self.assertEqual(a["qoi"], b["qoi"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
