"""test_free_experimenter_wiring.py — brick 2: the exact/experiment path routes to
the FREE experimenter under FREE_EXPERIMENTER=1 (PRIME DIRECTIVE, add-free-path).

Proves:
  * with the flag ON, run_exact_route calls the free investigator with the goal
    (the domain, since there's no gate-1 hypothesis on the de-funnel path),
    records its findings on the baton (director read-back), and ends the run;
  * with the flag OFF, the caged composition path runs and the free investigator
    is NOT called (byte-behaviour unchanged).

Call-free: the free investigator is injected; the caged path uses a scripted
in-process code probe; record_run_outcome is patched.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton  # noqa: E402
from supervisor import Logger, run_exact_route  # noqa: E402


def _fake_free_result(goal):
    return {"goal": goal, "summary": "s",
            "findings": [{"label": "a", "value": 1, "verified": True,
                          "reproduce": "f.py"},
                         {"label": "b", "value": 2, "verified": False,
                          "reproduce": ""}],
            "publishable": True}


def _scripted_caged_strategy(state):
    # a judged stop with no probes — enough to exercise the caged path without
    # composing anything (we only care that the free path was NOT taken)
    return {"stop": True, "stop_reason": "done"}


class _RouteCase(unittest.TestCase):
    def _run(self, *, flag_on, free_investigate, exact_strategy=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="free-wire-test",
                      created_at="2026-07-23T00:00:00+00:00", mode="auto",
                      payload={"domain": "characterize descriptor space"})
        outcomes: list[str] = []
        env = {"FREE_EXPERIMENTER": "1"} if flag_on else {"FREE_EXPERIMENTER": "0"}
        with patch.dict("os.environ", env, clear=False), patch(
            "supervisor.record_run_outcome",
            side_effect=lambda b, how_far, retry=0: outcomes.append(how_far),
        ):
            run_exact_route(logger, baton, run_dir, "auto",
                            exact_strategy=exact_strategy,
                            free_investigate=free_investigate)
        return baton, outcomes, (run_dir / "log.txt").read_text()


class TestFlagOnRoutesToFree(_RouteCase):
    def test_free_investigator_gets_the_goal_and_ends_the_run(self):
        seen = {}

        def fake_free(goal, run_id=None):
            seen["goal"] = goal
            seen["run_id"] = run_id
            return _fake_free_result(goal)

        baton, outcomes, log = self._run(flag_on=True, free_investigate=fake_free)

        self.assertEqual(seen["goal"], "characterize descriptor space")  # = domain
        self.assertEqual(seen["run_id"], "free-wire-test")
        self.assertIn("FREE EXPERIMENTER", log)
        # findings recorded for the director (1 of 2 verified)
        self.assertEqual(baton._verification,
                         {"publishable": True, "verified": 1, "total": 2})
        self.assertEqual(len(outcomes), 1)
        self.assertIn("free investigation", outcomes[0])
        self.assertIn("publishable", outcomes[0])


class TestFlagOffKeepsTheCagedPath(_RouteCase):
    def test_free_investigator_is_not_called(self):
        called = {"free": False}

        def fake_free(goal, run_id=None):
            called["free"] = True
            return _fake_free_result(goal)

        _baton, outcomes, log = self._run(
            flag_on=False, free_investigate=fake_free,
            exact_strategy=_scripted_caged_strategy)

        self.assertFalse(called["free"])          # free path NOT taken
        self.assertNotIn("FREE EXPERIMENTER", log)
        self.assertIn("EXACT ROUTE", log)         # the caged route ran
        self.assertEqual(len(outcomes), 1)


if __name__ == "__main__":
    unittest.main()
