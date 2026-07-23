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

import os  # noqa: E402

from baton import Baton  # noqa: E402
from supervisor import Logger, run_exact_route, run_relay  # noqa: E402


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


class TestProductionDefaultsToFree(unittest.TestCase):
    """A production run goes STRAIGHT to the free agent — no gate-1, no stages
    2-5 (PRIME DIRECTIVE). The static pipeline and its LEGACY_PIPELINE kill-switch
    were DELETED 2026-07-23 (the free-agent purge); free is the only path."""

    def _baton_logger(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="prod-default", created_at="2026-07-23T00:00:00+00:00",
                      mode="auto", payload={"domain": "some question"})
        return logger, baton, run_dir

    def test_free_is_the_default(self):
        logger, baton, run_dir = self._baton_logger()
        called = {"free": False}
        with patch("supervisor.run_exact_route",
                   side_effect=lambda *a, **k: called.__setitem__("free", True)), \
                patch.dict("os.environ", {}, clear=False):
            os.environ.pop("LEGACY_PIPELINE", None)
            run_relay(logger, baton, run_dir, "auto")  # production => free
        self.assertTrue(called["free"])


class TestIdeationRoute(unittest.TestCase):
    """OPTIONAL ideation route: run the Co-Scientist apparatus first, then hand
    the free agent the tournament-ranked hypotheses as candidate leads — strong
    hypotheses feeding a free investigation, NOT a gate."""

    def _run(self, *, ideate, ideate_fn):
        seen = {}

        def fake_free(goal, run_id=None):
            seen["goal"] = goal
            return {"goal": goal, "summary": "s", "findings": [],
                    "publishable": False}

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="ideate-test",
                      created_at="2026-07-23T00:00:00+00:00", mode="auto",
                      payload={"domain": "cavity mixing"})
        with patch("supervisor.record_run_outcome", side_effect=lambda *a, **k: None):
            run_relay(logger, baton, run_dir, "auto", free_investigate=fake_free,
                      ideate=ideate, ideate_fn=ideate_fn)
        return seen["goal"], (run_dir / "log.txt").read_text()

    def test_ranked_hypotheses_reach_the_free_agent_as_leads(self):
        def fake_ideate(baton):
            baton.payload["hypotheses"] = [
                {"id": "h1", "statement": "vortex shedding drives the mixing"},
                {"id": "h2", "statement": "shear-layer instability dominates"}]
            baton.payload["hypotheses_ranked"] = True
            return baton

        goal, log = self._run(ideate=True, ideate_fn=fake_ideate)
        self.assertIn("cavity mixing", goal)                       # domain kept
        self.assertIn("vortex shedding drives the mixing", goal)   # rank-1 lead
        self.assertIn("shear-layer instability dominates", goal)   # breadth: all
        self.assertIn("not restricted to them", goal)              # not a cage
        self.assertIn("IDEATION ROUTE", log)

    def test_ideation_failure_falls_back_to_the_bare_domain(self):
        def boom(baton):
            raise RuntimeError("ideation exploded")

        goal, log = self._run(ideate=True, ideate_fn=boom)
        self.assertEqual(goal, "cavity mixing")   # bare domain; run continues
        self.assertIn("falling back", log)

    def test_off_by_default_is_the_bare_domain(self):
        goal, _ = self._run(ideate=False, ideate_fn=None)
        self.assertEqual(goal, "cavity mixing")


if __name__ == "__main__":
    unittest.main()
