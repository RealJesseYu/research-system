"""test_resume_study.py — item B (2026-07-28): resumability at move granularity.

A long run's likeliest death is a usage window five hours in; the arc is fully
on disk (studies/<id>/arc.jsonl, decisions/, report.json, runs/<run_id>/), so
resume is RECONSTRUCTION from evidence, not new state to persist. These tests
prove, offline:

  - relaunching against an existing study id rebuilds the arc and continues
    from the NEXT move — completed moves are never re-run;
  - the fresh budget is debited by what the arc shows consumed (a spent study
    resumes straight into an honest budget_spent stop, never a second budget);
  - the token ceiling resumes too: prior in-process spend is reconstructed
    from the arc's capability rows, prior run spend from its experiment rows;
  - an ORPHANED run (dispatched before the death, finished after it, never
    recorded) is recovered from its run evidence and recorded — not re-run,
    and its id is never re-minted;
  - resume of a missing/unnamed study fails loudly, never silently fresh.

Run directly: venv/bin/python3 tests/test_resume_study.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.dispatch as dispatch_mod  # noqa: E402
import pi_agent.study as S  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from pi_agent.free_director import (  # noqa: E402
    _moves_consumed,
    _prior_arc_tokens_outside_runs,
    _recover_orphan_runs,
    free_investigate,
)


def _entry(move_type="single", run_id="r", outcome="completed", cost=None,
           tool_output=None):
    return MoveResult(move_type, run_id, True, outcome,
                      {"publishable": True,
                       **({"cost": cost} if cost else {}),
                       **(tool_output or {})})


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "studies"
        self.runs = Path(self._tmp.name) / "runs"
        self.runs.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _dead_study(self, study_id="s", moves=2, cost=None):
        """A study as a died director leaves it: identity + arc, no report."""
        study = S.create_study("the goal", study_id=study_id,
                               studies_root=self.root)
        for i in range(moves):
            S.record_move(study, _entry(run_id=f"{study_id}-m{i + 1}",
                                        cost=cost))
        return study

    def _scripted(self, script):
        calls = {"n": 0}

        def decide(study, arc, budget):
            d = script[min(calls["n"], len(script) - 1)]
            calls["n"] += 1
            return d
        decide.calls = calls
        return decide

    def _act(self, action, **over):
        base = {"ack": "s", "reading": "r", "reasoning": "because",
                "action": action, "domain": None, "instrument": None,
                "campaign": False, "budget_moves": None, "detail": None,
                "stop_reason": None}
        base.update(over)
        return base

    def _recording_run_move(self, seen):
        def run_move(study, move, finding=None, runs_root=None):
            seen.append(move)
            if not move.run_id:
                move.run_id = S.next_move_run_id(study)
            return S.record_move(
                study, MoveResult(move.type.value, move.run_id, True,
                                  "completed", {"publishable": True}),
                finding=finding)
        return run_move


class TestResumeContinuesFromTheNextMove(_Base):
    def test_completed_moves_are_read_not_re_run(self):
        self._dead_study("s", moves=2)
        seen = []
        arcs_seen = []

        def decide(study, arc, budget):
            arcs_seen.append(arc)
            if len(arcs_seen) == 1:
                return self._act("run_experiment", domain="the next question")
            return self._act("stop", stop_reason="done")

        report = free_investigate(
            None, budget=Budget(10), studies_root=self.root,
            runs_root=self.runs, study_id="s", resume=True,
            decide_action=decide, run_move=self._recording_run_move(seen))

        # the director's FIRST decision already read both completed moves
        self.assertEqual(len(arcs_seen[0]), 2)
        # exactly one new move ran, with the next id — nothing re-ran
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].run_id, "s-m3")  # next id — never a re-mint
        arc = S.study_arc(S.load_study("s", studies_root=self.root))
        self.assertEqual(len(arc), 3)
        self.assertEqual(arc[2]["seq"], 3)
        # the report says it resumed, and from where
        self.assertEqual(report["resumed_from"]["arc_entries_at_resume"], 2)
        self.assertEqual(report["goal"], "the goal")  # the recorded goal rules

    def test_resume_requires_a_study_id_and_an_existing_study(self):
        with self.assertRaises(ValueError):
            free_investigate(None, budget=Budget(2), studies_root=self.root,
                             resume=True)
        with self.assertRaises(FileNotFoundError):
            free_investigate(None, budget=Budget(2), studies_root=self.root,
                             study_id="never-existed", resume=True)


class TestBudgetIsRebuiltFromTheArc(_Base):
    def test_the_fresh_budget_is_debited_by_recorded_consumption(self):
        self._dead_study("s", moves=2)
        report = free_investigate(
            None, budget=Budget(5), studies_root=self.root, runs_root=self.runs,
            study_id="s", resume=True,
            decide_action=self._scripted([self._act("stop", stop_reason="x")]),
            run_move=self._recording_run_move([]))
        self.assertEqual(report["resumed_from"]
                         ["moves_reconstructed_as_consumed"], 2)
        self.assertEqual(report["budget_final"]["remaining"], 3)

    def test_a_spent_study_resumes_into_an_honest_stop_not_a_second_budget(self):
        self._dead_study("s", moves=5)
        decide = self._scripted([self._act("run_experiment", domain="q")])
        report = free_investigate(
            None, budget=Budget(5), studies_root=self.root, runs_root=self.runs,
            study_id="s", resume=True, decide_action=decide,
            run_move=self._recording_run_move([]))
        self.assertEqual(report["termination"]["reason"], "budget_spent")
        self.assertEqual(decide.calls["n"], 0)  # no decision, no re-run

    def test_the_token_ceiling_resumes_too(self):
        # prior spend: one run (700k, counted from the arc's experiment rows)
        # plus one capability row (400k — the DEAD process's in-process spend,
        # reconstructed as the prior-tokens offset). 1.1M >= the 1M ceiling, so
        # the resumed study stops on its token budget before dispatching.
        study = S.create_study("g", study_id="s", studies_root=self.root)
        S.record_move(study, _entry(run_id="s-m1",
                                    cost={"calls": 1, "tokens": 700_000}))
        S.record_move(study, _entry(move_type="call_ideation", run_id="s-cap2",
                                    cost={"calls": 4, "tokens": 400_000}))
        decide = self._scripted([self._act("run_experiment", domain="q")])
        report = free_investigate(
            None, budget=Budget(10), studies_root=self.root, runs_root=self.runs,
            study_id="s", resume=True, token_budget=1_000_000,
            decide_action=decide, run_move=self._recording_run_move([]))
        self.assertEqual(report["termination"]["reason"], "token_budget_spent")
        self.assertEqual(decide.calls["n"], 0)
        self.assertEqual(report["resumed_from"]
                         ["prior_in_process_tokens_reconstructed"], 400_000)


class TestOrphanRecovery(_Base):
    """A run dispatched before the death that FINISHED after it: on disk as
    runs/<study>-m<N>/ plus its journal run_record, but absent from the arc."""

    def _with_orphan(self, run_record):
        study = self._dead_study("s", moves=1)
        (self.runs / "s-m2").mkdir()
        original = dispatch_mod._fetch_run_record
        dispatch_mod._fetch_run_record = lambda rid: run_record
        try:
            recovered = _recover_orphan_runs(study, self.runs)
        finally:
            dispatch_mod._fetch_run_record = original
        return study, recovered

    def test_a_finished_orphan_is_recorded_from_its_evidence_not_re_run(self):
        record = {"kind": "run_record", "extras": {
            "how_far": "completed free investigation (publishable)",
            "verification": {"publishable": True, "verified": 3, "total": 3},
            "cost": {"calls": 2, "tokens": 1_234_567, "usd": 4.2, "turns": 180},
        }}
        study, recovered = self._with_orphan(record)
        self.assertEqual(recovered, 1)
        arc = S.study_arc(study)
        self.assertEqual(len(arc), 2)
        entry = arc[1]
        self.assertEqual(entry["move_type"], "recovered_run")
        self.assertEqual(entry["run_id"], "s-m2")
        self.assertIn("completed free investigation", entry["outcome"])
        self.assertEqual(entry["cost"]["tokens"], 1_234_567)
        self.assertEqual(entry["cost"]["usd"], 4.2)
        # the next minted move id never collides with the orphan
        self.assertEqual(S.next_move_run_id(study), "s-m3")

    def test_an_orphan_that_died_without_journaling_reads_as_orphaned(self):
        study, recovered = self._with_orphan(None)
        self.assertEqual(recovered, 1)
        entry = S.study_arc(study)[1]
        self.assertIn("orphaned_run", entry["outcome"])
        self.assertIn("not re-run", entry["outcome"])
        self.assertFalse(entry["succeeded"])

    def test_recovery_is_idempotent(self):
        study, _ = self._with_orphan(None)
        original = dispatch_mod._fetch_run_record
        dispatch_mod._fetch_run_record = lambda rid: None
        try:
            again = _recover_orphan_runs(study, self.runs)
        finally:
            dispatch_mod._fetch_run_record = original
        self.assertEqual(again, 0)
        self.assertEqual(len(S.study_arc(study)), 2)


class TestReconstructionArithmetic(_Base):
    def test_moves_consumed_counts_spends_and_skips_refusals(self):
        arc = [
            {"move_type": "single", "outcome": "completed"},
            {"move_type": "campaign", "outcome": "completed"},
            {"move_type": "recovered_run", "outcome": "completed x"},
            {"move_type": "call_ideation", "outcome": "ideation_done"},
            # refusals recorded before any spend — zero cost
            {"move_type": "run_experiment", "outcome": "insufficient_budget"},
            {"move_type": "call_integration",
             "outcome": "integration_nothing_to_compose"},
            {"move_type": "spawn_sub_investigation",
             "outcome": "spawn_insufficient_budget"},
            # a failed dispatch spent its move before failing
            {"move_type": "run_experiment", "outcome": "run_experiment_failed"},
            # decide/memory rows never touch the pool
            {"move_type": "decide", "outcome": "decision_failed"},
            {"move_type": "write_memory", "outcome": "memory_written"},
        ]
        self.assertEqual(_moves_consumed(arc, self.root), 5)

    def test_spawn_allocation_is_read_from_the_child_report(self):
        child = S.create_study("sub", study_id="s-sub1", studies_root=self.root)
        (child.dir / "report.json").write_text(
            '{"budget_final": {"total_at_node": 4}}')
        arc = [{"move_type": "spawn_sub_investigation",
                "outcome": "sub_investigation_done",
                "tool_output": {"child_study_id": "s-sub1",
                                "child_moves_run": 2}}]
        self.assertEqual(_moves_consumed(arc, self.root), 4)
        # without a child report, the demonstrated moves are the fallback
        arc[0]["tool_output"] = {"child_study_id": "s-gone", "child_moves_run": 2}
        self.assertEqual(_moves_consumed(arc, self.root), 2)

    def test_prior_tokens_covers_everything_outside_experiment_rows(self):
        arc = [
            {"move_type": "single", "cost": {"tokens": 700}},        # live path
            {"move_type": "call_ideation", "cost": {"tokens": 400}},  # offset
            {"move_type": "recovered_run", "cost": {"tokens": 900}},  # offset
            {"move_type": "decide", "cost": None},                    # unknown
        ]
        self.assertEqual(_prior_arc_tokens_outside_runs(arc), 1300)


class TestCliValidation(unittest.TestCase):
    def test_goal_and_resume_are_mutually_exclusive_and_one_is_required(self):
        from pi_agent.__main__ import main
        with self.assertRaises(SystemExit):
            main(["--goal", "g", "--resume-study", "s"])
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
