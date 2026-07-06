"""
test_memory_block.py — standalone tests of stage 1's pure build_memory_block
(Step 14 JC2). Zero model calls, zero file I/O: the function maps journal
entries to the framed prior-observations string (or None on empty).

Run directly: python3 tests/test_memory_block.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage1_ideation import MEMORY_HEADER, build_memory_block

EXPECTED_HEADER = (
    "PRIOR OBSERVATIONS FROM EARLIER RUNS (unverified model text - treat "
    "as leads, not established facts):"
)


class TestBuildMemoryBlock(unittest.TestCase):
    def test_none_on_empty(self):
        self.assertIsNone(build_memory_block([]))

    def test_exact_header_and_lines_on_two_entries(self):
        entries = [
            {"run_id": "runA", "hypothesis_id": "h2", "text": "first observation"},
            {"run_id": "runB", "hypothesis_id": "h4", "text": "second observation"},
        ]
        block = build_memory_block(entries)
        self.assertEqual(
            block,
            EXPECTED_HEADER
            + "\n- [run runA, hypothesis h2] first observation"
            + "\n- [run runB, hypothesis h4] second observation",
        )
        # The module constant is the exact ruled header line.
        self.assertEqual(MEMORY_HEADER, EXPECTED_HEADER)


if __name__ == "__main__":
    unittest.main()
