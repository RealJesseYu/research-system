"""
test_transcript_writer.py — standalone test of model_call._write_transcript
(Step 14 JC1). Zero model calls: the writer is exercised directly in a temp
working directory and the file it leaves is checked for exactly the five
keys and the byte-for-byte serialized input string.

Run directly: python3 tests/test_transcript_writer.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from model_call import _write_transcript


class TestWriteTranscript(unittest.TestCase):
    def test_eight_keys_and_exact_serialized_input(self):
        """Five keys became eight on 2026-07-20 (capabilities, allowed_tools,
        max_turns). The profile is evidence, not decoration: the same input run
        SEALED and run FULL are different experiments, and a reader who cannot
        tell which one produced a record cannot judge the result."""
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                stage_input = {"run_id": "testrun", "domain": "test domain"}
                serialized = json.dumps(stage_input)
                _write_transcript(
                    "stage_x_test", "SYSTEM PROMPT TEXT", stage_input, serialized, "model-y"
                )
                files = sorted((Path("runs") / "testrun" / "transcripts").iterdir())
                self.assertEqual(len(files), 1)
                self.assertIn("stage_x_test", files[0].name)
                data = json.loads(files[0].read_text())
                self.assertEqual(
                    set(data.keys()),
                    {
                        "stage_name",
                        "model",
                        "timestamp_utc",
                        "system_prompt",
                        "stage_input_serialized",
                        "capabilities",
                        "allowed_tools",
                        "max_turns",
                    },
                )
                # Default is unchanged: a call that does not opt in is sealed.
                self.assertEqual(data["capabilities"], "sealed")
                self.assertEqual(data["allowed_tools"], [])
                self.assertEqual(data["max_turns"], 1)
                self.assertEqual(data["stage_input_serialized"], serialized)
                self.assertEqual(data["stage_name"], "stage_x_test")
                self.assertEqual(data["model"], "model-y")
                self.assertEqual(data["system_prompt"], "SYSTEM PROMPT TEXT")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
