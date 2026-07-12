"""
test_strip_fence.py — standalone test of model_call's fence detector.
Zero model calls: strip_fence is a pure function with no I/O, so this
exercises it directly. The load-bearing property (Step-11 fence-fix ruling)
is that detection is independent of whether the stripped text parses as
JSON — a fenced-but-garbage reply must still report was_fenced=True.

Also covers the 17-CLOSE single-fence prose tolerance
(extract_single_fenced_block plus its call_stage_model wiring, driven by a
fake transport): the frozen fixture is the EXACT attempt-1 failure reply
from the Step-22 smoke crash (RE-ASK line, stage6_paper_hypothesis_reflect,
runs/smoke6-20260711T083510Z in the build-22 worktree) — prose around
exactly one ```json fence, which burned the whole re-ask budget live.

Run directly: venv/bin/python3 tests/test_strip_fence.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
from model_call import call_stage_model, extract_single_fenced_block, strip_fence

FIXTURE_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "smoke6_prose_wrapped_reply.txt"
)


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


class TestSingleFenceProseTolerance(unittest.TestCase):
    def test_smoke_crash_fixture_fails_the_existing_path(self):
        # The frozen reply reproduces the live failure: it does not START
        # with a fence (strip_fence sees no fence), and the raw text is not
        # JSON — exactly the shape that re-asked three times and crashed.
        reply = FIXTURE_PATH.read_text()
        text, was_fenced = strip_fence(reply)
        self.assertFalse(was_fenced)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)

    def test_smoke_crash_fixture_is_rescued_by_extraction(self):
        reply = FIXTURE_PATH.read_text()
        block = extract_single_fenced_block(reply)
        self.assertIsNotNone(block)
        data = json.loads(block)
        self.assertEqual(data["ack_run_id"], "smoke6-20260711T083510Z")
        self.assertIn("section_markdown", data)

    def test_no_fence_and_multiple_fences_return_none(self):
        # No fence: existing behavior kept.
        self.assertIsNone(extract_single_fenced_block("just prose, no json"))
        # Multiple fences: ambiguous, existing behavior kept.
        self.assertIsNone(
            extract_single_fenced_block(
                'a ```json\n{"a": 1}\n``` b ```json\n{"b": 2}\n``` c'
            )
        )
        # Unclosed fence (odd backtick runs): not exactly one block.
        self.assertIsNone(extract_single_fenced_block('```json\n{"a": 1}'))

    def test_language_tag_dropped_and_plain_fence_kept(self):
        self.assertEqual(
            extract_single_fenced_block('prose ```json\n{"a": 1}\n``` more prose'),
            '{"a": 1}',
        )
        self.assertEqual(
            extract_single_fenced_block('prose ```\n{"a": 1}\n```'), '{"a": 1}'
        )

    def test_call_stage_model_rescues_the_fixture_on_attempt_1(self):
        # The wiring proof: a fake transport returns the exact crash reply;
        # call_stage_model must now succeed on attempt 1 with no re-ask.
        reply = FIXTURE_PATH.read_text()
        with patch.object(model_call, "_invoke_transport", return_value=reply):
            data, timing = call_stage_model(
                "tolerance_test_stage",
                "system prompt",
                {"input": "x"},  # no run_id: nothing durably logged
                {"required": ["ack_run_id", "section_markdown"]},
            )
        self.assertEqual(timing["attempts"], 1)
        self.assertEqual(data["ack_run_id"], "smoke6-20260711T083510Z")

    def test_unrescuable_reply_keeps_existing_failure_path(self):
        # A prose-only reply (no fence) must still burn all attempts and
        # raise, exactly as before the tolerance.
        with patch.object(
            model_call, "_invoke_transport", return_value="no json here at all"
        ):
            with self.assertRaises(RuntimeError):
                call_stage_model(
                    "tolerance_test_stage",
                    "system prompt",
                    {"input": "x"},
                    {"required": ["ack_run_id"]},
                )


if __name__ == "__main__":
    unittest.main()
