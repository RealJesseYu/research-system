"""
test_gate5_decision.py — standalone tests of parse_gate5_decision (Step 16),
the gate-5 accept/override/stop parser. Pure function, no I/O, no model
calls; every branch plus whitespace and case tolerance.

Run directly: venv/bin/python3 tests/test_gate5_decision.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supervisor import parse_gate5_decision


class TestParseGate5Decision(unittest.TestCase):
    def test_accept(self):
        self.assertEqual(parse_gate5_decision("a"), ("accept",))

    def test_halt(self):
        self.assertEqual(parse_gate5_decision("n"), ("halt",))

    def test_override_back_to_design(self):
        self.assertEqual(parse_gate5_decision("b"), ("override", "back_to_design"))

    def test_override_back_to_ideation(self):
        self.assertEqual(parse_gate5_decision("i"), ("override", "back_to_ideation"))

    def test_override_more_data(self):
        self.assertEqual(parse_gate5_decision("m"), ("override", "more_data"))

    def test_override_exit(self):
        self.assertEqual(parse_gate5_decision("e"), ("override", "exit"))

    def test_whitespace_tolerated(self):
        self.assertEqual(parse_gate5_decision("  a  "), ("accept",))
        self.assertEqual(parse_gate5_decision("\tb\n"), ("override", "back_to_design"))

    def test_case_insensitive(self):
        self.assertEqual(parse_gate5_decision("A"), ("accept",))
        self.assertEqual(parse_gate5_decision("N"), ("halt",))
        self.assertEqual(parse_gate5_decision("I"), ("override", "back_to_ideation"))
        self.assertEqual(parse_gate5_decision("E"), ("override", "exit"))

    def test_invalid_answers(self):
        for raw in ("", "yes", "y", "x", "back_to_design", "ab", "1", "  "):
            self.assertEqual(parse_gate5_decision(raw), ("invalid",), raw)


if __name__ == "__main__":
    unittest.main()
