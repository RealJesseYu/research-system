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
    def test_five_keys_and_exact_serialized_input(self):
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
                    },
                )
                self.assertEqual(data["stage_input_serialized"], serialized)
                self.assertEqual(data["stage_name"], "stage_x_test")
                self.assertEqual(data["model"], "model-y")
                self.assertEqual(data["system_prompt"], "SYSTEM PROMPT TEXT")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
