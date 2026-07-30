"""test_blockers_reach_the_human.py — the blocker channel (2026-07-30).

MEASURED FAILURE. `blocked_on` existed only as a line in runs/<id>/log.txt, which
nobody reads mid-study. So it reached neither studies/, nor the director's next
turn, nor liveview — which already HAS a BLOCKED: render path and had nothing to
show it. Cost on study-20260730T034915Z: an ask for LTPP FWD data, and m15's "run
`python3 make_producers.py`, ~10 s, no network" — ten seconds of a person's time
that would have verified 34 findings.

The three consumers were already built and already agree on the shape (a list of
dicts with `need` and `human_action`). Only the plumbing between the experimenter
and the arc was missing:

    free_experimenter result -> supervisor log      (existed)
                             -> run_record extras   (NEW)
                             -> read_run_result     (NEW)
                             -> MoveResult.raw      (NEW)
                             -> arc tool_output     (already generic)
                             -> director / liveview / CLI  (already built)

NOTHING HERE ENDS AN ARC. A blocker is a report, not a gate — only the director
stops a study — so these tests also pin that a blocked run still completes.

Run directly: venv/bin/python3 tests/test_blockers_reach_the_human.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent.dispatch import RunResult, read_run_result  # noqa: E402
from pi_agent.study import create_study, record_move, study_findings  # noqa: E402

BLOCKER = {
    "need": "LTPP FWD deflection data",
    "why": "needed to fit the subgrade modulus term",
    "human_action": "download the SDR from infopave.fhwa.dot.gov and place it in "
                    "the workspace",
    "workaround_used": None,
}
TEN_SECONDS = {
    "need": "run `python3 make_producers.py`",
    "why": "emits the scalar producers for the 34 unverified findings",
    "human_action": "run it in the m15 workspace, ~10 s, no network",
    "workaround_used": None,
}


class TestRunRecordToRunResult(unittest.TestCase):
    def test_blocked_on_travels_out_of_the_run_record(self):
        with tempfile.TemporaryDirectory() as d:
            r = read_run_result(
                Path(d), "run-1", 0,
                {"extras": {"how_far": "completed free investigation",
                            "blocked_on": [BLOCKER, TEN_SECONDS]}},
            )
        self.assertEqual(len(r.blocked_on), 2)
        self.assertEqual(r.blocked_on[0]["need"], "LTPP FWD deflection data")

    def test_absent_blocker_is_an_empty_list_never_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                read_run_result(Path(d), "run-1", 0, {"extras": {}}).blocked_on, [])
            # no run_record at all (the run died without journaling)
            self.assertEqual(
                read_run_result(Path(d), "run-1", 1, None).blocked_on, [])

    def test_it_is_in_as_dict_which_is_what_becomes_the_move_raw(self):
        r = RunResult(run_id="r", exit_code=0, run_dir="d", has_run_record=True,
                      blocked_on=[BLOCKER])
        self.assertEqual(r.as_dict()["blocked_on"], [BLOCKER])


class TestArcAndDirector(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.study = create_study("goal", study_id="s",
                                  studies_root=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def _move(self, **raw):
        base = {"run_id": "s-m1", "outcome": "completed free investigation",
                "publishable": False, "findings": [], "blocked_on": []}
        base.update(raw)
        return {"move_type": "single", "run_id": base["run_id"],
                "succeeded": True, "outcome": base["outcome"], "raw": base}

    def test_a_blocker_lands_in_the_arc_entrys_tool_output(self):
        """tool_output is the generic 'whatever the tool returned' channel, and
        blocked_on is deliberately NOT in _ARC_MAPPED_KEYS, so it rides for free
        — which is exactly the shape liveview and the CLI already read."""
        entry = record_move(self.study, self._move(blocked_on=[BLOCKER]),
                            finding="blocked on data")
        self.assertEqual(entry["tool_output"]["blocked_on"], [BLOCKER])
        on_disk = [json.loads(l) for l in open(self.study.arc_path)]
        self.assertEqual(on_disk[0]["tool_output"]["blocked_on"], [BLOCKER])

    def test_the_director_sees_it_on_its_next_turn(self):
        record_move(self.study, self._move(blocked_on=[TEN_SECONDS]), finding="f")
        seen = study_findings(self.study)
        self.assertEqual(seen[0]["tool_output"]["blocked_on"], [TEN_SECONDS])
        self.assertIn("~10 s, no network",
                      seen[0]["tool_output"]["blocked_on"][0]["human_action"])

    def test_the_shape_matches_what_liveview_renders(self):
        """liveview/render.py prints f"{b['need']} — YOU CAN: {b['human_action']}"
        off liveview/reader.py's tool_output.get("blocked_on"); this pins the two
        keys it dereferences."""
        entry = record_move(self.study, self._move(blocked_on=[BLOCKER]))
        for b in entry["tool_output"]["blocked_on"]:
            self.assertIn("need", b)
            self.assertIn("human_action", b)

    def test_a_blocker_does_not_end_the_arc(self):
        """NOTHING ENDS AN ARC BUT THE DIRECTOR. A blocked move is recorded as a
        successful, completed move and the study keeps going."""
        entry = record_move(self.study, self._move(blocked_on=[BLOCKER]))
        self.assertTrue(entry["succeeded"])
        self.assertEqual(entry["outcome"], "completed free investigation")
        record_move(self.study, self._move(run_id="s-m2"))
        self.assertEqual(len(study_findings(self.study)), 2)


class TestSupervisorRecordsIt(unittest.TestCase):
    def test_record_run_outcome_puts_blockers_in_extras(self):
        import supervisor
        from baton import Baton

        captured = {}

        def fake_append(entry):
            captured.update(entry)

        real = supervisor.journal_append
        supervisor.journal_append = fake_append
        try:
            b = Baton(run_id="r", created_at="t", mode="auto", payload={})
            b._blocked_on = [BLOCKER]
            supervisor.record_run_outcome(b, "completed free investigation")
        finally:
            supervisor.journal_append = real
        self.assertEqual(captured["extras"]["blocked_on"], [BLOCKER])
        self.assertIn("blocked_on=1", captured["text"])

    def test_an_unblocked_run_record_is_unchanged(self):
        import supervisor
        from baton import Baton

        captured = {}
        real = supervisor.journal_append
        supervisor.journal_append = lambda e: captured.update(e)
        try:
            b = Baton(run_id="r", created_at="t", mode="auto", payload={})
            supervisor.record_run_outcome(b, "completed free investigation")
        finally:
            supervisor.journal_append = real
        self.assertNotIn("blocked_on", captured["extras"])
        self.assertNotIn("blocked_on", captured["text"])


if __name__ == "__main__":
    unittest.main()
