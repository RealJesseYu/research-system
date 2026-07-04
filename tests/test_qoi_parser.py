"""
test_qoi_parser.py — standalone test of the production wrapper's
volFieldValue.dat parser. Zero model calls, zero docker: parse_volfieldvalue_dat
is a pure function, exercised against tests/fixtures/volFieldValue.dat — a
REAL captured output file, frozen verbatim from the Step-11 live proof run
(cavity_baseline, postProcess volAverage(mag(U)) at latest time 20).

Run directly: venv/bin/python3 tests/test_qoi_parser.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from run_cfd import parse_volfieldvalue_dat

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "volFieldValue.dat"


class TestParseVolFieldValueDat(unittest.TestCase):
    def test_frozen_real_output_parses_to_the_live_proof_value(self):
        row_time, value = parse_volfieldvalue_dat(FIXTURE.read_text())
        self.assertEqual(row_time, 20.0)
        self.assertEqual(value, 0.4168179)
        self.assertIsInstance(value, float)


if __name__ == "__main__":
    unittest.main()
