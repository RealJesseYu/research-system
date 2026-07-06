"""
test_stage_crash.py — standalone tests of the supervisor's run_single_stage
crash catch (Step 16, JC1b). Zero model calls.

record_run_outcome is patched out so no test appends to the real journal;
the live behavior including the real journal append is proven on disk at
runs/crash-proof-20260706T074756Z (chunk-1 evidence).

Run directly: venv/bin/python3 tests/test_stage_crash.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from supervisor import Logger, run_single_stage


def _make_baton() -> Baton:
    return Baton(
        run_id="test-crash",
        created_at="2026-07-06T00:00:00+00:00",
        mode="auto",
        payload={"domain": "canned"},
    )


class TestRunSingleStage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "log.txt"
        self.logger = Logger(self.log_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_stage_passes_through_unchanged(self):
        baton = _make_baton()

        def healthy_stage(b):
            b.add_history("healthy_stage", "did the thing")
            return b

        with patch("supervisor.record_run_outcome") as recorded:
            out = run_single_stage(self.logger, baton, "healthy_stage", healthy_stage)
            recorded.assert_not_called()
        self.assertIs(out, baton)
        self.assertEqual(out.history[-1]["note"], "did the thing")
        # Catch is silent on success: nothing was ever written to the log.
        self.assertFalse(self.log_path.exists())

    def test_raising_stage_recorded_and_exits(self):
        baton = _make_baton()

        def exploding_stage(b):
            raise RuntimeError("boom: first line\nsecond line never logged")

        with patch("supervisor.record_run_outcome") as recorded:
            with self.assertRaises(SystemExit) as ctx:
                run_single_stage(
                    self.logger, baton, "exploding_stage", exploding_stage
                )
            self.assertEqual(ctx.exception.code, 1)
            recorded.assert_called_once()
            how_far = recorded.call_args.args[1]
            self.assertEqual(
                how_far, "crashed at exploding_stage: RuntimeError: boom: first line"
            )
        log = self.log_path.read_text()
        self.assertIn(
            "STAGE-CRASH stage=exploding_stage exception=RuntimeError: boom: first line",
            log,
        )
        self.assertIn("STAGE-CRASH | ", log)  # traceback tail present
        self.assertIn("CRASHED at stage exploding_stage", log)
        self.assertNotIn("second line never logged", log.split("STAGE-CRASH | ")[0])


if __name__ == "__main__":
    unittest.main()
