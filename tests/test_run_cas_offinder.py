"""
test_run_cas_offinder.py — the Cas-OFFinder wrapper (BIO Wave D.2, DEFERRED).

Cas-OFFinder is re-tiered T1 -> DEFERRED: its OpenCL kernel does not compute
correctly on this colima/aarch64 host (pocl exits 0 with 0 matches). So:
  * PURE tests (no container): input-layer jails — these work regardless of the
    kernel and are the wrapper's failure-honesty, NOT deferred.
  * LIVE test (container): the KNOWN-ANSWER GUARD fires — a valid query returns
    valid=False here because the baked known-present probe site is not found,
    proving the wrapper CANNOT return a fabricated 0-off-target count from a
    broken kernel. On a validated-kernel host the guard passes and a count is
    returned (the un-defer condition).

Run directly: venv/bin/python3 tests/test_run_cas_offinder.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_cas_offinder
from tools.run_cas_offinder import (
    GENOME_ALLOWLIST, QOI_FIELDS, CasOffinderInputError, _validate_input,
    run_cas_offinder as run,
)

_LIVE = run_cas_offinder.preflight() is None
_GUIDE = "ACGGTCATGCAAGTCCTGAT"  # a valid 20-nt guide (matches the baked probe)


class PureInputJails(unittest.TestCase):
    def test_clean_input_passes_validation(self):
        self.assertEqual(
            _validate_input({"genome": "probe", "guide": _GUIDE,
                             "mismatches": 3, "quantity": "off_target_count"}),
            {"genome": "probe", "guide": _GUIDE, "mismatches": 3,
             "quantity": "off_target_count"},
        )

    def test_genome_off_allowlist_rejected(self):
        with self.assertRaises(CasOffinderInputError) as e:
            _validate_input({"genome": "hg38", "guide": _GUIDE,
                             "mismatches": 3, "quantity": "off_target_count"})
        self.assertIn("allowlist", str(e.exception))

    def test_guide_wrong_length_rejected(self):
        with self.assertRaises(CasOffinderInputError) as e:
            _validate_input({"genome": "probe", "guide": "ACGT",
                             "mismatches": 3, "quantity": "off_target_count"})
        self.assertIn("20", str(e.exception))

    def test_guide_non_dna_rejected(self):
        with self.assertRaises(CasOffinderInputError):
            _validate_input({"genome": "probe", "guide": "ACGGTCATGCAAGTCCTGAX",
                             "mismatches": 3, "quantity": "off_target_count"})

    def test_mismatches_out_of_range_rejected(self):
        with self.assertRaises(CasOffinderInputError):
            _validate_input({"genome": "probe", "guide": _GUIDE,
                             "mismatches": 99, "quantity": "off_target_count"})
        with self.assertRaises(CasOffinderInputError):
            _validate_input({"genome": "probe", "guide": _GUIDE,
                             "mismatches": True, "quantity": "off_target_count"})

    def test_quantity_off_allowlist_rejected(self):
        with self.assertRaises(CasOffinderInputError):
            _validate_input({"genome": "probe", "guide": _GUIDE,
                             "mismatches": 3, "quantity": "foo"})

    def test_bad_input_fails_loud_through_run(self):
        r = run({"genome": "hg38", "guide": _GUIDE, "mismatches": 3,
                 "quantity": "off_target_count"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("input rejected", r["diagnostics"])

    def test_vocabularies(self):
        self.assertEqual(GENOME_ALLOWLIST, ("probe",))
        self.assertEqual(QOI_FIELDS, ("off_target_count",))


@unittest.skipUnless(_LIVE, "cas-offinder-prod not running — guard check skipped")
class KnownAnswerGuard(unittest.TestCase):
    def test_guard_refuses_on_broken_kernel_no_fabricated_count(self):
        # THE re-validation gate, triggered: this host's pocl kernel is broken,
        # so the known-present probe site is not found and the wrapper REFUSES —
        # it never returns a (fabricated) 0-off-target count. On a validated
        # kernel this returns a real count instead (the un-defer condition).
        r = run({"genome": "probe", "guide": _GUIDE, "mismatches": 3,
                 "quantity": "off_target_count"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("known-answer guard", r["diagnostics"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
