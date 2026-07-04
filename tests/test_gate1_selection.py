"""
test_gate1_selection.py — standalone test of the supervisor's gate-1 answer
parser. Zero model calls: parse_gate1_selection is a pure function with no
I/O, so this exercises it directly against every category of raw answer.

Run directly: python3 tests/test_gate1_selection.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supervisor import parse_gate1_selection


class TestValidPicks(unittest.TestCase):
    def test_pick_1(self):
        self.assertEqual(parse_gate1_selection("1", 4), ("select", 1))

    def test_pick_k_itself(self):
        self.assertEqual(parse_gate1_selection("4", 4), ("select", 4))

    def test_pick_middle(self):
        self.assertEqual(parse_gate1_selection("3", 4), ("select", 3))


class TestHalt(unittest.TestCase):
    def test_lowercase_n_halts(self):
        self.assertEqual(parse_gate1_selection("n", 4), ("halt",))

    def test_uppercase_n_halts(self):
        self.assertEqual(parse_gate1_selection("N", 4), ("halt",))


class TestInvalid(unittest.TestCase):
    def test_zero_is_invalid(self):
        self.assertEqual(parse_gate1_selection("0", 4), ("invalid",))

    def test_k_plus_one_is_invalid(self):
        self.assertEqual(parse_gate1_selection("5", 4), ("invalid",))

    def test_text_is_invalid(self):
        self.assertEqual(parse_gate1_selection("abc", 4), ("invalid",))

    def test_empty_is_invalid(self):
        self.assertEqual(parse_gate1_selection("", 4), ("invalid",))


class TestWhitespaceTolerance(unittest.TestCase):
    def test_padded_number_selects(self):
        self.assertEqual(parse_gate1_selection("  2  ", 4), ("select", 2))

    def test_padded_n_halts(self):
        self.assertEqual(parse_gate1_selection(" N \n", 4), ("halt",))


class TestKEqualsOne(unittest.TestCase):
    def test_pick_1_when_k_is_1(self):
        self.assertEqual(parse_gate1_selection("1", 1), ("select", 1))

    def test_pick_2_when_k_is_1_is_invalid(self):
        self.assertEqual(parse_gate1_selection("2", 1), ("invalid",))

    def test_n_still_halts_when_k_is_1(self):
        self.assertEqual(parse_gate1_selection("n", 1), ("halt",))


if __name__ == "__main__":
    unittest.main()
