"""test_tool_output_reaches_director.py — the researcher must READ its tools.

THE DEFECT (live, study-20260725T073215Z). record_move shaped every arc entry for
EXPERIMENT moves, whose payload lives under "findings". The researcher's TOOLS
answer under their own keys — ideation -> "hypotheses", data analysis ->
"analysis"/"directions", validation -> "concerns" — and none was copied. A
call_ideation arc entry therefore carried NO IDEAS: a full-depth run costing
~15.9M tokens reached the director as a bare "ideation_done" receipt, and it
confabulated a hypothesis to fill the gap. run_spawn only worked because it
happens to answer under "findings".

Offline; no model calls. Proves the payload now rides through record_move into
study_findings for every tool, generically, without per-tool wiring.

Run directly: venv/bin/python3 tests/test_tool_output_reaches_director.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402


class ToolOutputTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.study = S.create_study("the goal", studies_root=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, raw, move_type="call_ideation"):
        S.record_move(
            self.study,
            MoveResult(move_type=move_type, run_id="cap1", succeeded=True,
                       outcome="ideation_done", raw=raw),
            finding="why I called it",
        )
        return S.study_findings(self.study)[-1]


class TestToolPayloadSurvives(ToolOutputTestCase):
    def test_ideation_hypotheses_reach_the_researcher(self):
        """The exact live failure: ideas produced, ideas never seen."""
        hyps = [{"id": "h1", "statement": "an idea"},
                {"id": "h2", "statement": "another"}]
        entry = self._record({"succeeded": True, "outcome": "ideation_done",
                              "hypotheses": hyps, "depth": "full",
                              "detail": "2 candidate directions"})
        self.assertEqual(entry["tool_output"]["hypotheses"], hyps)
        self.assertEqual(entry["tool_output"]["depth"], "full")
        self.assertIn("2 candidate directions", entry["tool_output"]["detail"])

    def test_data_analysis_payload_reaches_the_researcher(self):
        entry = self._record({"analysis": "the trend is sublinear",
                              "directions": ["try D=128"]},
                             move_type="call_data_analysis")
        self.assertEqual(entry["tool_output"]["analysis"], "the trend is sublinear")
        self.assertEqual(entry["tool_output"]["directions"], ["try D=128"])

    def test_validation_concerns_reach_the_researcher(self):
        entry = self._record({"concerns": ["the baseline is not matched"]},
                             move_type="call_validation")
        self.assertEqual(entry["tool_output"]["concerns"],
                         ["the baseline is not matched"])

    def test_a_new_tool_needs_no_wiring_here(self):
        """Generic by construction: a tool invented tomorrow is carried too."""
        entry = self._record({"whatever_key": [1, 2, 3]}, move_type="call_future")
        self.assertEqual(entry["tool_output"]["whatever_key"], [1, 2, 3])


class TestExperimentMovesAreUnchanged(ToolOutputTestCase):
    def test_experiment_fields_still_map_to_their_named_slots(self):
        entry = self._record(
            {"findings": [{"label": "x", "value": 1, "verified": True}],
             "publishable": True, "cost": {"calls": 3},
             "reusable_artifacts": [{"name": "a.json", "producer": {}}],
             "succeeded": True, "outcome": "completed"},
            move_type="single")
        self.assertEqual(entry["results"][0]["label"], "x")
        self.assertEqual(entry["cost"], {"calls": 3})
        self.assertEqual(entry["reusable_artifacts"][0]["name"], "a.json")
        # every key was mapped, so nothing spills into tool_output
        self.assertEqual(entry["tool_output"], {})

    def test_spawn_findings_keep_working(self):
        """run_spawn answers under 'findings' and was the ONLY tool that worked;
        it must keep working unchanged."""
        entry = self._record(
            {"findings": [{"label": "child", "value": 2, "verified": True}],
             "child_study_id": "s-sub1"},
            move_type="spawn_sub_investigation")
        self.assertEqual(entry["results"][0]["label"], "child")
        self.assertEqual(entry["tool_output"]["child_study_id"], "s-sub1")

    def test_a_move_with_no_raw_is_not_a_crash(self):
        entry = self._record({})
        self.assertEqual(entry["tool_output"], {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
