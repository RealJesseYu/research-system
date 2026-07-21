"""
test_pi_study.py — the study store (chunk 3): a persistent identity an arc of
moves accumulates under.

WHAT THIS PROVES. A study is minted once and reloads; the arc records moves in
order and never overwrites itself; the PI reads its OWN arc (scoped, not the
global journal window); the study's constraint binds every move it runs; and
moves get study-scoped run_ids so they stop colliding. All offline — the move
dispatcher is injected, so no subprocess and no model call.

Run directly: venv/bin/python3 tests/test_pi_study.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pi_agent.dispatch import Move, MoveResult, MoveType  # noqa: E402
from pi_agent import study as S  # noqa: E402


class StudyCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def mk(self, goal="does E. coli growth rate change?", **kw):
        return S.create_study(goal, studies_root=self.root, **kw)


class TestIdentity(StudyCase):
    def test_create_writes_identity_and_returns_study(self):
        st = self.mk(allowed_substrates=["cobrapy"], study_id="study-x")
        self.assertTrue((self.root / "study-x" / "study.json").is_file())
        self.assertEqual(st.goal, "does E. coli growth rate change?")
        self.assertEqual(st.allowed_substrates, ["cobrapy"])

    def test_goal_must_be_non_empty(self):
        with self.assertRaises(ValueError):
            self.mk(goal="   ")

    def test_reopening_an_existing_id_raises(self):
        self.mk(study_id="study-x")
        with self.assertRaises(FileExistsError):
            self.mk(study_id="study-x")

    def test_load_round_trips_the_identity(self):
        self.mk(allowed_substrates=["cobrapy", "rdkit"], mode="human", study_id="study-y")
        st = S.load_study("study-y", studies_root=self.root)
        self.assertEqual(st.goal, "does E. coli growth rate change?")
        self.assertEqual(st.allowed_substrates, ["cobrapy", "rdkit"])
        self.assertEqual(st.mode, "human")

    def test_loading_an_unknown_study_raises(self):
        with self.assertRaises(FileNotFoundError):
            S.load_study("no-such-study", studies_root=self.root)

    def test_a_minted_id_has_the_study_prefix(self):
        st = self.mk()
        self.assertTrue(st.study_id.startswith("study-"))


class TestArc(StudyCase):
    def _mr(self, run_id, succeeded, outcome, publishable=None):
        return MoveResult(
            move_type="single", run_id=run_id, succeeded=succeeded,
            outcome=outcome, raw={"publishable": publishable},
        )

    def test_arc_is_empty_before_the_first_move(self):
        st = self.mk()
        self.assertEqual(S.study_arc(st), [])
        self.assertEqual(S.move_count(st), 0)

    def test_moves_accumulate_in_order_and_do_not_overwrite(self):
        st = self.mk(study_id="study-arc")
        S.record_move(st, self._mr("study-arc-m1", True, "completed", True), finding="rate drops at low O2")
        S.record_move(st, self._mr("study-arc-m2", False, "halted_barren_budget_spent"), finding="spec measured nothing")
        arc = S.study_arc(st)
        self.assertEqual([e["seq"] for e in arc], [1, 2])
        self.assertEqual(arc[0]["finding"], "rate drops at low O2")
        self.assertEqual(arc[1]["outcome"], "halted_barren_budget_spent")
        self.assertEqual(arc[0]["run_id"], "study-arc-m1")

    def test_publishable_is_lifted_out_of_raw(self):
        st = self.mk(study_id="study-pub")
        S.record_move(st, self._mr("study-pub-m1", True, "completed", publishable=True))
        self.assertTrue(S.study_arc(st)[0]["publishable"])

    def test_findings_are_the_scoped_arc_view(self):
        st = self.mk(study_id="study-find")
        S.record_move(st, self._mr("m1", True, "completed", True), finding="A")
        S.record_move(st, self._mr("m2", True, "completed", True), finding="B")
        findings = S.study_findings(st)
        self.assertEqual([f["finding"] for f in findings], ["A", "B"])
        self.assertEqual([f["seq"] for f in findings], [1, 2])

    def test_a_move_with_no_finding_still_appears(self):
        st = self.mk(study_id="study-none")
        S.record_move(st, self._mr("m1", False, "halted at gate after_stage_2"))
        f = S.study_findings(st)
        self.assertEqual(len(f), 1)
        self.assertIsNone(f[0]["finding"])
        self.assertEqual(f[0]["outcome"], "halted at gate after_stage_2")

    def test_arc_survives_reload_in_a_fresh_object(self):
        st = self.mk(study_id="study-reload")
        S.record_move(st, self._mr("m1", True, "completed", True), finding="kept")
        reloaded = S.load_study("study-reload", studies_root=self.root)
        self.assertEqual(S.study_findings(reloaded)[0]["finding"], "kept")

    def test_next_move_run_id_is_study_scoped_and_ordered(self):
        st = self.mk(study_id="study-ids")
        self.assertEqual(S.next_move_run_id(st), "study-ids-m1")
        S.record_move(st, self._mr("study-ids-m1", True, "completed", True))
        self.assertEqual(S.next_move_run_id(st), "study-ids-m2")


class TestRunStudyMove(StudyCase):
    """The glue: a move run under a study is constrained, id'd, and recorded."""

    def _fake_invoke(self, capture):
        def invoke(move, runs_root=Path("runs")):
            capture["move"] = move
            capture["runs_root"] = runs_root
            return MoveResult(
                move_type=move.type.value, run_id=move.run_id, succeeded=True,
                outcome="completed", raw={"publishable": True},
            )
        return invoke

    def test_study_constraint_is_stamped_onto_the_move(self):
        st = self.mk(allowed_substrates=["cobrapy"], study_id="study-c")
        cap = {}
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q"), invoke=self._fake_invoke(cap))
        self.assertEqual(cap["move"].allowed_substrates, ["cobrapy"])

    def test_move_gets_a_study_scoped_run_id(self):
        st = self.mk(study_id="study-r")
        cap = {}
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q"), invoke=self._fake_invoke(cap))
        self.assertEqual(cap["move"].run_id, "study-r-m1")

    def test_the_move_is_recorded_in_the_arc(self):
        st = self.mk(study_id="study-rec")
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q"),
                         finding="first result", invoke=self._fake_invoke({}))
        arc = S.study_arc(st)
        self.assertEqual(len(arc), 1)
        self.assertEqual(arc[0]["finding"], "first result")
        self.assertEqual(arc[0]["run_id"], "study-rec-m1")

    def test_a_conflicting_move_constraint_is_refused_not_silently_overridden(self):
        st = self.mk(allowed_substrates=["cobrapy"], study_id="study-conflict")
        with self.assertRaises(ValueError) as ctx:
            S.run_study_move(st, Move(MoveType.SINGLE, domain="q", allowed_substrates=["rdkit"]),
                             invoke=self._fake_invoke({}))
        self.assertIn("whole arc", str(ctx.exception))

    def test_a_matching_move_constraint_is_allowed(self):
        st = self.mk(allowed_substrates=["cobrapy"], study_id="study-match")
        cap = {}
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q", allowed_substrates=["cobrapy"]),
                         invoke=self._fake_invoke(cap))
        self.assertEqual(cap["move"].allowed_substrates, ["cobrapy"])

    def test_successive_moves_get_distinct_run_ids(self):
        st = self.mk(study_id="study-seq")
        cap1, cap2 = {}, {}
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q"), invoke=self._fake_invoke(cap1))
        S.run_study_move(st, Move(MoveType.CAMPAIGN, domain="q"), invoke=self._fake_invoke(cap2))
        self.assertEqual(cap1["move"].run_id, "study-seq-m1")
        self.assertEqual(cap2["move"].run_id, "study-seq-m2")
        self.assertEqual([e["move_type"] for e in S.study_arc(st)], ["single", "campaign"])

    def test_study_mode_flows_to_a_default_move(self):
        st = self.mk(mode="human", study_id="study-mode")
        cap = {}
        S.run_study_move(st, Move(MoveType.SINGLE, domain="q"), invoke=self._fake_invoke(cap))
        self.assertEqual(cap["move"].mode, "human")


if __name__ == "__main__":
    unittest.main(verbosity=2)
