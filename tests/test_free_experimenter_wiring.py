"""test_free_experimenter_wiring.py — run_exact_route hosts the FREE experimenter.

Brick 4a (2026-07-23): the caged composition path was PURGED — run_exact_route now
ALWAYS routes the goal to the free experimenter (a full agent, no substrate limit;
PRIME DIRECTIVE). No flag. Proves the goal reaches the free investigator, its
findings are recorded for the director, and the run ends.

Call-free: the free investigator is injected; record_run_outcome is patched.
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


class TestRunExactRouteIsFree(unittest.TestCase):
    def test_free_investigator_gets_the_goal_and_ends_the_run(self):
        seen = {}

        def fake_free(goal, run_id=None):
            seen["goal"] = goal
            seen["run_id"] = run_id
            return _fake_free_result(goal)

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="free-wire-test",
                      created_at="2026-07-23T00:00:00+00:00", mode="auto",
                      payload={"domain": "characterize descriptor space"})
        outcomes: list[str] = []
        with patch("supervisor.record_run_outcome",
                   side_effect=lambda b, how_far, retry=0: outcomes.append(how_far)):
            run_exact_route(logger, baton, run_dir, "auto",
                            free_investigate=fake_free)

        # the goal (= domain, no gate-1 hypothesis) reached the free agent
        self.assertEqual(seen["goal"], "characterize descriptor space")
        self.assertEqual(seen["run_id"], "free-wire-test")
        log = (run_dir / "log.txt").read_text()
        self.assertIn("FREE EXPERIMENTER", log)
        # findings recorded for the director (1 of 2 verified)
        self.assertEqual(baton._verification,
                         {"publishable": True, "verified": 1, "total": 2})
        self.assertEqual(len(outcomes), 1)
        self.assertIn("free investigation", outcomes[0])
        self.assertIn("publishable", outcomes[0])


if __name__ == "__main__":
    unittest.main()
