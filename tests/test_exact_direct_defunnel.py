"""test_exact_direct_defunnel.py — Step ④.3 (docs/design_step4_3_defunnel.md).

De-funnel the entrance: when a run is scoped to an all-exact toolset, skip
ideation + gate 1 entirely and hand the experimenter the domain directly — no
collapse to one hypothesis + one instrument. Proves:
  * run_is_all_exact_constrained() is the trigger (all-exact => True; any
    approximate or unconstrained => False, the fail-safe direction);
  * with EXACT_ROUTE on and an all-exact constraint, run_relay takes the
    EXACT-DIRECT branch — the static stages never run and the experimenter drives.

Call-free: zero model calls, zero docker. The experimenter is a SCRIPTED code
composition; record_run_outcome is patched (captured, never journaled).
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baton import Baton  # noqa: E402
from supervisor import Logger, run_is_all_exact_constrained, run_relay  # noqa: E402
from test_loop_controller import StubRelay  # noqa: E402


def _fake_free_result(goal):
    return {"goal": goal, "summary": "s",
            "findings": [{"label": "a", "value": 1, "verified": True,
                          "reproduce": "f.py"}],
            "publishable": True}


class TestConstraintPredicate(unittest.TestCase):
    def _pred(self, allowed):
        env = {} if allowed is None else {"ALLOWED_SUBSTRATES": allowed}
        with patch.dict("os.environ", env, clear=False):
            if allowed is None:
                os.environ.pop("ALLOWED_SUBSTRATES", None)
            return run_is_all_exact_constrained()

    def test_all_exact_triggers(self):
        self.assertTrue(self._pred("rdkit,python_experiment"))
        self.assertTrue(self._pred("rdkit"))

    def test_any_approximate_does_not_trigger(self):
        self.assertFalse(self._pred("rdkit,cavity_2d_cfd"))  # mixed
        self.assertFalse(self._pred("cavity_2d_cfd"))        # approximate only

    def test_unconstrained_does_not_trigger(self):
        self.assertFalse(self._pred(None))


class TestDefunnelBranch(unittest.TestCase):
    def test_all_exact_constraint_skips_ideation_and_gate1(self):
        stubs = StubRelay(["exit"])
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="defunnel-test",
                      created_at="2026-07-22T00:00:00+00:00", mode="auto",
                      payload={"domain": "characterize descriptor space"})
        seen = {}

        def fake_free(goal, run_id=None):
            seen["goal"] = goal
            return _fake_free_result(goal)

        outcomes: list[str] = []
        with patch.dict("os.environ",
                        {"EXACT_ROUTE": "1",
                         "ALLOWED_SUBSTRATES": "rdkit,python_experiment"},
                        clear=False), patch(
            "supervisor.record_run_outcome",
            side_effect=lambda b, how_far, retry=0: outcomes.append(how_far),
        ):
            run_relay(logger, baton, run_dir, "auto",
                      stages=stubs.stages(), free_investigate=fake_free)

        log = (run_dir / "log.txt").read_text()
        self.assertIn("EXACT-DIRECT", log)
        # the free experimenter got the domain as its goal (no gate-1 hypothesis)
        self.assertEqual(seen["goal"], "characterize descriptor space")
        self.assertIn("FREE EXPERIMENTER", log)
        # ideation + gate 1 + the static stages were all SKIPPED
        self.assertEqual(stubs.stage2_inputs, [])
        self.assertEqual(stubs.stage6_calls, 0)
        self.assertEqual(baton.history, [])  # no stage ran at all
        # the run ended with a free-investigation outcome
        self.assertEqual(len(outcomes), 1)
        self.assertIn("free investigation", outcomes[0])


if __name__ == "__main__":
    unittest.main()
