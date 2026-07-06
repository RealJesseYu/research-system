"""
test_transport_retry.py — standalone tests of model_call's bounded transport
retry (Step 16, JC1a). Zero real model calls: the factored seam
model_call._invoke_transport is patched with fakes, and time.sleep is
patched out so the backoff costs nothing.

The retry corrects DELIVERY only: a fake transport that fails then succeeds
must leave the validation attempts counter at 1, and our own validation
errors (SchemaValidationError / JSONDecodeError) are raised after the
transport returned — they never enter the retry path.

Run directly: venv/bin/python3 tests/test_transport_retry.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call
from model_call import call_stage_model


class FakeSDKError(Exception):
    """Stands in for an SDK/transport exception (e.g. the Step-15 crash's
    'Reached maximum number of turns (1)')."""


class TestTransportRetry(unittest.TestCase):
    def setUp(self):
        # A run dir so TRANSPORT-RETRY lines have a durable home, exercised
        # through the same runs/<run_id>/log.txt derivation as RE-ASK.
        self._tmp = tempfile.TemporaryDirectory()
        self.run_id = "transport-retry-test"
        self.run_dir = Path(self._tmp.name) / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "log.txt").write_text("")
        self._cwd = Path.cwd()
        import os

        os.chdir(self._tmp.name)

    def tearDown(self):
        import os

        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _log_text(self) -> str:
        return (self.run_dir / "log.txt").read_text()

    def test_fail_once_then_succeed(self):
        calls = {"n": 0}

        def flaky_transport(system_prompt, user_turn, model):
            calls["n"] += 1
            if calls["n"] == 1:
                raise FakeSDKError("Reached maximum number of turns (1)")
            return '{"ack": "pong"}'

        with patch.object(model_call, "_invoke_transport", flaky_transport), patch(
            "model_call.time.sleep"
        ) as slept:
            data, timing = call_stage_model(
                "fake_stage",
                "irrelevant",
                {"run_id": self.run_id},
                {"required": ["ack"]},
            )
        self.assertEqual(data, {"ack": "pong"})
        self.assertEqual(calls["n"], 2)
        # Validation attempts unaffected: delivery was retried, content was
        # right the first time it arrived.
        self.assertEqual(timing["attempts"], 1)
        slept.assert_called_once_with(model_call.TRANSPORT_RETRY_BACKOFFS[0])
        log = self._log_text()
        self.assertEqual(log.count("TRANSPORT-RETRY"), 1)
        self.assertIn(
            "TRANSPORT-RETRY stage=fake_stage retry=1 "
            "exception=FakeSDKError: Reached maximum number of turns (1)",
            log,
        )
        self.assertNotIn("RE-ASK", log)

    def test_fail_three_times_reraises_after_two_retries(self):
        calls = {"n": 0}

        def dead_transport(system_prompt, user_turn, model):
            calls["n"] += 1
            raise FakeSDKError(f"transport down (call {calls['n']})")

        with patch.object(model_call, "_invoke_transport", dead_transport), patch(
            "model_call.time.sleep"
        ) as slept:
            with self.assertRaises(FakeSDKError) as ctx:
                call_stage_model(
                    "fake_stage",
                    "irrelevant",
                    {"run_id": self.run_id},
                    {"required": ["ack"]},
                )
        # The original exception, unwrapped, from the third (final) attempt.
        self.assertIn("transport down (call 3)", str(ctx.exception))
        self.assertEqual(calls["n"], 3)
        self.assertEqual(slept.call_count, 2)
        log = self._log_text()
        self.assertEqual(log.count("TRANSPORT-RETRY"), 2)
        self.assertIn("retry=1", log)
        self.assertIn("retry=2", log)

    def test_validation_error_does_not_enter_transport_retry(self):
        # Transport always delivers, but the content fails the schema: the
        # validation re-ask loop must own it — zero TRANSPORT-RETRY lines,
        # attempts=2.
        replies = iter(['{"wrong": 1}', '{"ack": "pong"}'])

        def healthy_transport(system_prompt, user_turn, model):
            return next(replies)

        with patch.object(model_call, "_invoke_transport", healthy_transport), patch(
            "model_call.time.sleep"
        ) as slept:
            data, timing = call_stage_model(
                "fake_stage",
                "irrelevant",
                {"run_id": self.run_id},
                {"required": ["ack"]},
            )
        self.assertEqual(data, {"ack": "pong"})
        self.assertEqual(timing["attempts"], 2)
        slept.assert_not_called()
        log = self._log_text()
        self.assertNotIn("TRANSPORT-RETRY", log)
        self.assertEqual(log.count("RE-ASK"), 1)


if __name__ == "__main__":
    unittest.main()
