"""test_ideation_depth_wiring.py — Step ④.1 (docs/plan_step4_free_the_entrance.md).

The supervisor chooses the ideation depth, default 'quick'. Proves:
  * _stages_with_ideation_depth binds depth into the stage-1 callable only,
    leaving every other stage object untouched;
  * run_relay's default ideation_depth is 'quick' (the new runtime default);
  * stage1_ideation.run's OWN default stays 'full' (protecting the kill-rate
    battery and direct callers) so a future edit cannot silently flip it.

Call-free: zero model calls, zero docker.

Run directly: venv/bin/python3 tests/test_ideation_depth_wiring.py
"""

from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import supervisor  # noqa: E402
from stages import stage1_ideation  # noqa: E402


class TestDepthBinding(unittest.TestCase):
    def _fake_stages(self):
        calls: dict[str, object] = {}

        def stage1(baton, depth="full"):
            calls["stage1_depth"] = depth
            return baton

        def stage2(baton):
            calls["stage2_ran"] = True
            return baton

        return [("stage1_ideation", stage1), ("stage2_x", stage2)], calls

    def test_binds_depth_into_stage1_only(self):
        stages, calls = self._fake_stages()
        original_stage2 = stages[1][1]
        bound = supervisor._stages_with_ideation_depth(stages, "quick")

        # stage 2 is passed through as the SAME object (not wrapped)
        self.assertIs(bound[1][1], original_stage2)
        # invoking the bound stage 1 calls the underlying fn with the chosen depth
        bound[0][1]("baton-sentinel")
        self.assertEqual(calls["stage1_depth"], "quick")

    def test_full_is_threaded_when_requested(self):
        stages, calls = self._fake_stages()
        bound = supervisor._stages_with_ideation_depth(stages, "full")
        bound[0][1]("baton-sentinel")
        self.assertEqual(calls["stage1_depth"], "full")


class TestRuntimeDefault(unittest.TestCase):
    def test_run_relay_defaults_to_quick(self):
        sig = inspect.signature(supervisor.run_relay)
        self.assertEqual(sig.parameters["ideation_depth"].default, "quick")

    def test_stage1_run_own_default_stays_full(self):
        # The direct-caller default (kill-rate battery, tests) MUST stay 'full';
        # the 'quick' default lives at the supervisor layer only.
        sig = inspect.signature(stage1_ideation.run)
        self.assertEqual(sig.parameters["depth"].default, "full")


if __name__ == "__main__":
    unittest.main()
