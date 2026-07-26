"""test_ideation_brief.py — ideation is briefed like the experimenter.

Ideation used to receive ONLY the string the director typed: no goal, no verified
results, no artifacts. The experimenter got a proper brief on 2026-07-25 and this
was never matched, which made the apparatus useless for exactly the case it
should be strongest at — "half the system is already built and verified, now find
me a hypothesis for the next function." The director would have had to retype the
whole state of the work into one prompt string, and could not hand over an
artifact at all.

Offline; no model calls, no ideation runs.

Run directly: venv/bin/python3 tests/test_ideation_brief.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.capabilities import _ideation_brief  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402


def _producer(name):
    return {"name": name, "producer": {"kind": "code", "code": "c",
                                       "quantity": "q", "emits": [name]}}


class IdeationBriefTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("build a working arm", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, results=(), artifacts=()):
        S.record_move(
            self.study,
            MoveResult("single", "r1", True, "completed",
                       {"findings": list(results),
                        "reusable_artifacts": list(artifacts)}),
            finding="a move")


class TestBriefContents(IdeationBriefTestCase):
    def test_a_fresh_study_gets_the_question_unchanged(self):
        """Nothing built yet => byte-identical to before this existed."""
        self.assertEqual(_ideation_brief("what next?", self.study), "what next?")

    def test_the_goal_travels_once_work_exists(self):
        self._record(results=[{"label": "reach", "value": 0.42, "verified": True}])
        out = _ideation_brief("what next?", self.study)
        self.assertTrue(out.startswith("what next?"))
        self.assertIn("build a working arm", out)

    def test_established_results_travel_and_are_marked_settled(self):
        self._record(results=[{"label": "reach", "value": 0.42, "verified": True}])
        out = _ideation_brief("what next?", self.study)
        self.assertIn("reach = 0.42", out)
        self.assertIn("do not propose re-measuring it", out)

    def test_unverified_findings_are_never_offered_as_foundation(self):
        """An unreproduced number is not something to build a hypothesis on."""
        self._record(results=[{"label": "guess", "value": 9.9, "verified": False}])
        self.assertEqual(_ideation_brief("q", self.study), "q")

    def test_artifacts_travel_as_rerunnable_producers(self):
        """THE ROBOT CASE: 'the arm is built, hypothesise the next function.'"""
        self._record(artifacts=[_producer("arm.json")])
        out = _ideation_brief("what next?", self.study)
        self.assertIn("arm.json", out)
        self.assertIn("WORK ALREADY BUILT", out)
        self.assertIn("build ON", out)

    def test_it_asks_for_hypotheses_that_go_further(self):
        self._record(artifacts=[_producer("arm.json")])
        out = _ideation_brief("q", self.study)
        self.assertIn("take this further over ones that start from nothing", out)


class TestBriefNeverBreaksTheCall(IdeationBriefTestCase):
    def test_a_broken_study_object_returns_the_question(self):
        class Broken:
            goal = "g"

            @property
            def dir(self):
                raise RuntimeError("disk gone")

        self.assertEqual(_ideation_brief("q", Broken()), "q")


if __name__ == "__main__":
    unittest.main(verbosity=2)
