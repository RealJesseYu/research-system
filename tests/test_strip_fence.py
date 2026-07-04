"""
test_strip_fence.py — standalone test of model_call's fence detector.
Zero model calls: strip_fence is a pure function with no I/O, so this
exercises it directly. The load-bearing property (Step-11 fence-fix ruling)
is that detection is independent of whether the stripped text parses as
JSON — a fenced-but-garbage reply must still report was_fenced=True.

Run directly: venv/bin/python3 tests/test_strip_fence.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model_call import strip_fence


class TestStripFence(unittest.TestCase):
    def test_detection_is_independent_of_parseability(self):
        # Plain JSON: untouched, not fenced.
        self.assertEqual(strip_fence('{"a": 1}'), ('{"a": 1}', False))
        # Fenced JSON with language tag: stripped and flagged.
        self.assertEqual(
            strip_fence('```json\n{"a": 1}\n```'), ('{"a": 1}', True)
        )
        # Fenced JSON without language tag: stripped and flagged.
        self.assertEqual(strip_fence('```\n{"a": 1}\n```'), ('{"a": 1}', True))
        # THE undercount case: fenced text that is NOT valid JSON must still
        # be flagged — the flag reports the fence, not the parse.
        text, was_fenced = strip_fence("```\nnot json at all\n```")
        self.assertTrue(was_fenced)
        self.assertEqual(text, "not json at all")
        # Surrounding whitespace tolerated, as before.
        self.assertEqual(strip_fence('  ```json\n{"a": 1}\n```  '), ('{"a": 1}', True))
        # Unfenced non-JSON passes through unflagged (whitespace-trimmed only).
        self.assertEqual(strip_fence("  hello  "), ("hello", False))


if __name__ == "__main__":
    unittest.main()
