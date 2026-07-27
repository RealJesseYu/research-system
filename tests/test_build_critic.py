"""test_build_critic.py — "could I actually build this today?", asked before a human does.

HOW THIS WAS FOUND. The owner pasted a finished glider design study into a fresh
chat and asked whether it could be built. The reply named six true things the
whole apparatus had missed: no structural check, no pitch axis, no cut files, a
performance figure that was a prediction not a promise, a handling hazard, and an
autopilot closing only one loop. NONE was a correctness failure — nothing was
wrong, things were ABSENT — which is exactly why the wall (numbers) and the
referee (words vs code) were both blind to them.

So this is a third lens: the practitioner's. Its findings are routed BACK TO THE
DIRECTOR for one recorded response, because most of them are answerable.

Call-free; the model door is injected.

Run directly: venv/bin/python3 tests/test_build_critic.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from stages import build_critic as BC  # noqa: E402

CRITIQUE = {
    "verdict": "Buildable in outline, but nothing structural was checked.",
    "usable_today": False,
    "findings": [
        {"issue": "No structural check on the spar",
         "why_it_matters": "the wing could fold at load",
         "what_would_close_it": "a beam-bending margin calculation",
         "severity": "high"},
        {"issue": "No pitch axis anywhere",
         "why_it_matters": "it cannot be trimmed to fly",
         "what_would_close_it": "static margin and elevator sizing",
         "severity": "high"},
    ],
}
RESPONSE = {
    "responses": [
        {"issue": "No structural check on the spar", "disposition": "accepted",
         "reasoning": "a real oversight; beam margins are arithmetic and should "
                      "have been computed."},
        {"issue": "No pitch axis anywhere", "disposition": "out_of_scope",
         "reasoning": "the goal named heading hold; the deliverable is not "
                      "flyable without it and that is disclosed."},
    ],
    "next_priorities": ["compute the spar margin", "size the elevator"],
    "overall": "Read this as a sizing study, not a build package.",
}


class CriticTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("design a glider", studies_root=self.root)
        S.record_move(self.study, MoveResult(
            "single", "r1", True, "completed",
            {"findings": [{"label": "glide ratio", "value": 12.0, "verified": True}]}),
            finding="sized it")
        (self.study.dir / "paper.md").write_text("# The design\nGlide ratio 12.0.\n")

    def tearDown(self):
        self._tmp.cleanup()

    def _call(self, critique=CRITIQUE, response=RESPONSE):
        seen = {}

        def call(stage, sp, inp, schema, **kw):
            seen.setdefault("stages", []).append(stage)
            seen[stage] = inp
            return (dict(critique) if stage == BC.CRITIC_STAGE else dict(response)), {}
        return call, seen


class TestTheCritiqueItself(CriticTestCase):
    def test_it_reads_the_deliverable_and_the_evidence(self):
        call, seen = self._call()
        out = BC.critique_study(self.study, call=call)
        inp = seen[BC.CRITIC_STAGE]
        self.assertIn("The design", inp["deliverable"])
        self.assertEqual(inp["verified_findings"][0]["label"], "glide ratio")
        self.assertEqual(len(out["findings"]), 2)
        self.assertFalse(out["usable_today"])

    def test_the_prompt_asks_the_practitioner_question_not_correctness(self):
        p = BC.SYSTEM_PROMPT
        self.assertIn("starting tomorrow, what would happen?", p)
        self.assertIn("You are NOT checking whether the numbers are right", p)
        self.assertIn("things are simply absent", p)

    def test_it_names_the_absence_classes_that_were_actually_missed(self):
        p = BC.SYSTEM_PROMPT
        for cls in ("an axis nobody checked", "drawings you cannot cut from",
                    "really a prediction", "hazard or failure mode"):
            self.assertIn(cls, p)

    def test_it_is_told_not_to_manufacture_complaints(self):
        self.assertIn("do not manufacture a complaint", BC.SYSTEM_PROMPT)

    def test_no_paper_is_an_error_not_a_crash(self):
        (self.study.dir / "paper.md").unlink()
        self.assertIn("error", BC.critique_study(self.study, call=self._call()[0]))

    def test_a_failing_model_is_an_error_not_a_crash(self):
        def boom(*a, **k):
            raise RuntimeError("transport died")
        self.assertIn("error", BC.critique_study(self.study, call=boom))


class TestTheDirectorAnswers(CriticTestCase):
    def test_findings_go_back_and_the_response_is_recorded(self):
        call, seen = self._call()
        resp = BC.director_response(self.study, CRITIQUE, call=call)
        self.assertEqual(seen[BC.RESPONSE_STAGE]["findings"], CRITIQUE["findings"])
        self.assertEqual(len(resp["responses"]), 2)

    def test_the_response_prompt_forbids_dressing_an_oversight_as_scope(self):
        self.assertIn("one dressed up as a scope decision costs you the reader's "
                      "trust", BC.RESPONSE_PROMPT)

    def test_no_findings_means_no_call(self):
        called = []
        BC.director_response(self.study, {"findings": []},
                             call=lambda *a, **k: called.append(1))
        self.assertEqual(called, [])


class TestTheRecord(CriticTestCase):
    def test_both_sides_land_in_the_paper(self):
        call, _ = self._call()
        out = BC.critique_and_respond(self.study.study_id, studies_root=self.root,
                                      call=call)
        self.assertEqual(out["findings"], 2)
        paper = (self.study.dir / "paper.md").read_text()
        self.assertIn("Build critique", paper)
        self.assertIn("No structural check on the spar", paper)
        self.assertIn("accepted", paper)          # the director's disposition
        self.assertIn("out_of_scope", paper)
        self.assertIn("compute the spar margin", paper)   # next priorities

    def test_the_section_says_neither_party_wrote_it(self):
        """A record of a challenge and its answer must not be authored by either
        side — it is assembled by Python."""
        call, _ = self._call()
        BC.critique_and_respond(self.study.study_id, studies_root=self.root, call=call)
        self.assertIn("neither party wrote this section",
                      (self.study.dir / "paper.md").read_text())

    def test_the_json_record_lands_beside_the_paper(self):
        call, _ = self._call()
        BC.critique_and_respond(self.study.study_id, studies_root=self.root, call=call)
        rec = json.loads((self.study.dir / "build_critique.json").read_text())
        self.assertIn("critique", rec)
        self.assertIn("response", rec)

    def test_an_unknown_study_is_an_error(self):
        out = BC.critique_and_respond("nope", studies_root=self.root)
        self.assertIn("error", out)


class TestItIsAnOutsideReader(unittest.TestCase):
    def test_the_critic_has_its_own_model_tier(self):
        """The authoring model is the worst reader of what it forgot to include."""
        import models
        self.assertIn("critic", models._TIER_DEFAULT)
        self.assertEqual(models._ALIASES["fable"], "claude-fable-5")

    def test_it_can_be_pointed_at_an_outside_model(self):
        import os
        from unittest.mock import patch
        import models
        with patch.dict(os.environ, {"RESEARCH_MODEL_CRITIC": "fable"}):
            self.assertEqual(models.model_for("critic"), "claude-fable-5")

    def test_it_is_disableable(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {"BUILD_CRITIC": "0"}):
            self.assertFalse(BC._enabled())


class TestTheDoctrineFixThatPromptedThis(unittest.TestCase):
    def test_the_experimenter_must_check_every_axis_not_just_the_named_one(self):
        from stages.free_experimenter import SYSTEM_PROMPT as p
        self.assertIn("CHECK EVERY AXIS THE THING DEPENDS ON", p)
        self.assertIn("the axis nobody checked is usually the one that bites", p)

    def test_a_physical_deliverable_must_emit_fabrication_artifacts(self):
        from stages.free_experimenter import SYSTEM_PROMPT as p
        self.assertIn("EMIT WHAT SOMEONE WOULD ACTUALLY BUILD FROM", p)
        self.assertIn("A table of dimensions is not a plan", p)
        self.assertIn("start cutting material", p)


class TestProportionality(unittest.TestCase):
    """MEASURED FAILURE. The glider design study spent 55M tokens on a problem
    its owner could do in five minutes, and came out 10% design / 90% validation:
    three independent routes to one glide ratio, Lyapunov cross-checked against
    Monte Carlo, gain margin by two methods, a 32-corner robustness sweep, and
    route-agreement findings comparing all of it to itself.

    The cause was the incentive, not the model. Verified findings are the only
    thing the system scores, so three routes to one easy number yield three
    verified findings while attempting something harder yields numbers that are
    harder to verify. The gradient pointed at over-validating something simple."""

    def test_the_experimenter_is_told_one_check_is_enough(self):
        from stages.free_experimenter import SYSTEM_PROMPT as p
        self.assertIn("ONE GOOD CHECK PER CLAIM", p)
        self.assertIn("BREADTH BEATS DEPTH", p)

    def test_it_names_when_a_second_route_actually_earns_its_keep(self):
        """Not a ban — a surprising result or a load-bearing number deserves one."""
        from stages.free_experimenter import SYSTEM_PROMPT as p
        self.assertIn("a result that is surprising", p)
        self.assertIn("the whole conclusion rests on", p)

    def test_an_easy_question_should_be_escalated_not_padded(self):
        from stages.free_experimenter import SYSTEM_PROMPT as p
        self.assertIn("has not done more work, it has done less", p)

    def test_the_director_must_match_scale_to_difficulty(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("MATCH THE SCALE OF THE WORK TO THE DIFFICULTY", p)
        self.assertIn("Budget is not a target to hit", p)

    def test_the_director_is_shown_the_actual_failure(self):
        """Naming the specific way it went wrong beats a general exhortation."""
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("three independent routes", p)
        self.assertIn("That is effort, not progress", p)

    def test_the_director_must_report_an_over_budgeted_goal(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("easier than its budget assumed", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
