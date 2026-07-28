"""test_free_director.py — the free director shell (Phase 2, docs/free_director_plan.md).

Proves, entirely offline (model transport faked, no subprocess runs):
  - the loop runs the open-action-space cycle and stops on the director's judgment;
  - the BUDGET is a hard ceiling — a director that never stops is bounded by it;
  - the decision cap backstops a director that loops on an unwired capability;
  - an unwired capability is recorded HONESTLY (not faked, not dropped) and the
    director reads it next turn;
  - per-run cost aggregates into the report the same way the enum loop's does;
  - the action validator enforces the open vocabulary and per-action fields.

Run directly: venv/bin/python3 tests/test_free_director.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent import free_decider  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402


# --------------------------------------------------------------------------
# The action validator.
# --------------------------------------------------------------------------

class TestActionValidator(unittest.TestCase):
    def _v(self, arc_len=1, choosable=("rdkit", "cobrapy")):
        return free_decider.make_action_validator("study-1", arc_len, choosable)

    def _ok(self, **over):
        base = {
            "ack": "study-1", "reading": "the last run measured X",
            "reasoning": "probe the cheap case first", "action": "run_experiment",
            "domain": "does X hold?", "instrument": None, "campaign": False,
            "budget_moves": None, "detail": None, "stop_reason": None,
        }
        base.update(over)
        return base

    def test_a_well_formed_run_experiment_passes(self):
        self.assertEqual(self._v()(self._ok()), [])

    def test_ack_must_echo_the_study_id(self):
        self.assertTrue(self._v()(self._ok(ack="nope")))

    def test_action_must_be_in_the_vocabulary(self):
        self.assertTrue(self._v()(self._ok(action="run_single")))  # an enum verb, not ours

    def test_run_experiment_requires_a_domain(self):
        self.assertTrue(self._v()(self._ok(domain="  ")))

    def test_spawn_requires_a_positive_budget_moves(self):
        errs = self._v()(self._ok(action="spawn_sub_investigation", domain="sub Q", budget_moves=0))
        self.assertTrue(errs)
        # a bool must not pass as an int
        errs2 = self._v()(self._ok(action="spawn_sub_investigation", domain="sub Q", budget_moves=True))
        self.assertTrue(errs2)
        # a valid spawn is accepted
        self.assertEqual(
            self._v()(self._ok(action="spawn_sub_investigation", domain="sub Q",
                               budget_moves=3, instrument=None)),
            [],
        )

    def test_call_tools_require_a_detail(self):
        for act in ("call_ideation", "call_validation", "call_data_analysis", "write_memory"):
            self.assertTrue(self._v()(self._ok(action=act, domain=None, detail=None)),
                            f"{act} with no detail should fail")
            self.assertEqual(
                self._v()(self._ok(action=act, domain=None, detail="do the thing")),
                [], f"{act} with a detail should pass",
            )

    def test_stop_requires_a_reason(self):
        self.assertTrue(self._v()(self._ok(action="stop", domain=None, stop_reason=None)))
        self.assertEqual(
            self._v()(self._ok(action="stop", domain=None, stop_reason="goal answered")), []
        )

    def test_call_integration_needs_no_domain_or_detail(self):
        # integration synthesizes its own domain from the arc; detail is optional.
        self.assertEqual(
            self._v()(self._ok(action="call_integration", domain=None, detail=None)), []
        )
        self.assertEqual(
            self._v()(self._ok(action="call_integration", domain=None,
                               detail="total mass under 5")), []
        )

    def test_call_integration_may_force_an_on_menu_instrument(self):
        # call_integration dispatches a run (via run_move), so — like
        # run_experiment — it may name an instrument (regression: this used to be
        # rejected and caused a live RE-ASK, 2026-07-25).
        self.assertEqual(
            self._v()(self._ok(action="call_integration", domain=None,
                               instrument="rdkit", detail="compose them")), []
        )
        # ...but only one on the menu.
        self.assertTrue(
            self._v()(self._ok(action="call_integration", domain=None,
                               instrument="not_a_tool", detail="x"))
        )

    def test_instrument_only_on_run_experiment_and_on_menu(self):
        # a named instrument on a non-run action is rejected
        self.assertTrue(
            self._v()(self._ok(action="stop", domain=None, stop_reason="done", instrument="rdkit"))
        )
        # off-menu instrument rejected
        self.assertTrue(self._v()(self._ok(instrument="not_a_tool")))
        # on-menu instrument accepted
        self.assertEqual(self._v()(self._ok(instrument="rdkit")), [])

    def test_reading_may_be_null_only_on_the_first_turn(self):
        self.assertEqual(self._v(arc_len=0)(self._ok(reading=None)), [])
        self.assertTrue(self._v(arc_len=2)(self._ok(reading=None)))

    def test_extra_fields_are_rejected(self):
        self.assertTrue(self._v()(self._ok(surprise="x")))


# --------------------------------------------------------------------------
# The loop.
# --------------------------------------------------------------------------

class TestDirectorWorkspaceConfinement(unittest.TestCase):
    """The director is a FULL agent in the foreground; its tool cwd must be confined
    to the study scratch dir so scratch files never land in the repo root (the
    stray-file / shadowed-package hazard, 2026-07-25)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_decide_action_confines_tool_cwd_to_the_study_scratch_dir(self):
        import model_call
        from pi_agent.free_decider import decide_action
        study = S.create_study("g", study_id="s", studies_root=self.root)
        seen = {}

        def probing_call(*a, **k):
            # what the SDK would receive as the tooled agent's cwd, mid-call
            seen["cwd"] = model_call._workspace_option_kwargs(True).get("cwd")
            return ({"ack": "s", "reasoning": "r", "action": "stop",
                     "stop_reason": "x"}, {})

        decide_action(study, [], {"remaining": 3}, call=probing_call)
        self.assertIsNotNone(seen["cwd"])                      # a workspace was active
        self.assertIn("director_workspace", str(seen["cwd"]))  # ...the study's, not root
        self.assertTrue((self.root / "s" / "director_workspace").is_dir())


class TestFreeInvestigate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _scripted(self, script):
        calls = {"n": 0}

        def decide(study, arc, budget):
            d = script[min(calls["n"], len(script) - 1)]
            calls["n"] += 1
            return d
        decide.calls = calls
        return decide

    def _run_move(self, cost=None, findings=None):
        def run_move(study, move, finding=None, runs_root=None):
            raw = {"publishable": True}
            if cost is not None:
                raw["cost"] = cost
            if findings is not None:
                raw["findings"] = findings
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX",
                           True, "completed", raw),
                finding=finding,
            )
        return run_move

    def _act(self, action, **over):
        base = {"ack": "s", "reading": "r", "reasoning": "because", "action": action,
                "domain": None, "instrument": None, "campaign": False,
                "budget_moves": None, "detail": None, "stop_reason": None}
        base.update(over)
        return base

    def test_loop_runs_experiments_until_the_director_stops(self):
        script = [
            self._act("run_experiment", domain="q1"),
            self._act("run_experiment", domain="q2"),
            self._act("stop", stop_reason="answered"),
        ]
        report = free_investigate(
            "goal", budget=Budget(10), studies_root=self.root,
            decide_action=self._scripted(script), run_move=self._run_move(),
            study_id="s",
        )
        self.assertEqual(report["moves_run"], 2)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")
        self.assertEqual(report["director"], "free")

    def test_budget_is_a_hard_ceiling_even_if_the_director_never_stops(self):
        # Always ask to run an experiment; a budget of 3 must stop it at 3.
        report = free_investigate(
            "g", budget=Budget(3), studies_root=self.root,
            decide_action=self._scripted([self._act("run_experiment", domain="q")]),
            run_move=self._run_move(), study_id="s",
        )
        self.assertEqual(report["moves_run"], 3)
        self.assertEqual(report["termination"]["reason"], "budget_spent")
        self.assertEqual(report["budget_final"]["remaining"], 0)

    def test_a_failed_capability_is_recorded_honestly_not_faked(self):
        # whatever the capability executor returns, the loop records it faithfully
        # — a failure is surfaced, never dropped or dressed as success.
        def failing_exec(name, action, study, budget, seq):
            return {"succeeded": False, "outcome": "call_ideation_empty",
                    "detail": "no candidates"}
        script = [
            self._act("call_ideation", domain="q"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(5), studies_root=self.root,
            decide_action=self._scripted(script), run_move=self._run_move(),
            execute_capability=failing_exec, study_id="s",
        )
        self.assertEqual(report["moves_run"], 0)  # a capability is not an experiment
        cap = [e for e in report["arc"] if e["move_type"] == "call_ideation"]
        self.assertEqual(len(cap), 1)
        self.assertFalse(cap[0]["succeeded"])
        self.assertEqual(cap[0]["outcome"], "call_ideation_empty")

    def test_decision_cap_backstops_a_director_making_no_progress(self):
        # A capability that spends no budget and never stops can only be ended by
        # the decision cap (injected no-op executor; no real side effects).
        def noop_exec(name, action, study, budget, seq):
            return {"succeeded": False, "outcome": "noop", "detail": "no progress"}
        report = free_investigate(
            "g", budget=Budget(2), studies_root=self.root,
            decide_action=self._scripted([self._act("read_memory")]),
            run_move=self._run_move(), execute_capability=noop_exec,
            max_decisions=5, study_id="s",
        )
        self.assertEqual(report["termination"]["reason"], "decision_cap")
        self.assertEqual(report["decisions_made"], 5)
        self.assertEqual(report["budget_final"]["remaining"], 2)  # nothing spent

    def test_real_recursion_child_runs_and_verified_findings_bubble_up(self):
        # End-to-end offline recursion: the parent spawns; a REAL child
        # free_investigate runs on the carved budget with faked child seams; only
        # the child's verified findings bubble into the parent arc.
        import pi_agent.capabilities as C

        child_script = [
            self._act("run_experiment", domain="child q"),
            self._act("stop", stop_reason="child done"),
        ]
        child_run_move = self._run_move(
            findings=[{"label": "yield", "value": 1.5, "verified": True}]
        )

        def child_investigate(domain, child_budget, child_id, parent_study):
            return free_investigate(
                domain, budget=child_budget, mode=parent_study.mode,
                allowed_substrates=parent_study.allowed_substrates,
                study_id=child_id, parent_study_id=parent_study.study_id,
                studies_root=parent_study.studies_root,
                decide_action=self._scripted(child_script), run_move=child_run_move,
            )

        def parent_exec(name, action, study, budget, seq):
            if name == "spawn_sub_investigation":
                return C.run_spawn(action, study, budget, seq, investigate=child_investigate)
            return C.execute(name, action, study, budget, seq)

        parent_script = [
            self._act("spawn_sub_investigation", domain="sub q", budget_moves=3),
            self._act("stop", stop_reason="parent done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(parent_script), run_move=self._run_move(),
            execute_capability=parent_exec, study_id="parent",
        )
        spawn = [e for e in report["arc"] if e["move_type"] == "spawn_sub_investigation"]
        self.assertEqual(len(spawn), 1)
        self.assertTrue(spawn[0]["succeeded"])
        # the child's VERIFIED finding bubbled up into the parent arc as a result.
        results = spawn[0]["results"]
        self.assertEqual(results, [{"label": "yield", "value": 1.5, "verified": True}])
        # the parent ran no experiment of its own; the child's move is in the child.
        self.assertEqual(report["moves_run"], 0)
        # budget conservation: parent 6 - 3 allocated = 3 left; the child spent 1.
        self.assertEqual(report["budget_final"]["remaining"], 3)
        # the child study is parent-linked on disk.
        child = S.load_study("parent-sub1", studies_root=self.root)
        self.assertEqual(child.parent_study_id, "parent")

    def test_a_live_capability_result_lands_in_the_arc_for_the_next_decision(self):
        # Inject a capability executor that mimics ideation returning hypotheses,
        # proving the loop records a successful capability and spends its budget.
        def fake_exec(name, action, study, budget, seq):
            budget.spend(1)
            return {"succeeded": True, "outcome": "ideation_done",
                    "hypotheses": [{"id": "h1", "statement": "try X"}],
                    "detail": "1 candidate"}
        script = [
            self._act("call_ideation", domain="what to try?"),
            self._act("run_experiment", domain="try X"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(script), run_move=self._run_move(),
            execute_capability=fake_exec, study_id="s",
        )
        idea = [e for e in report["arc"] if e["move_type"] == "call_ideation"]
        self.assertEqual(len(idea), 1)
        self.assertTrue(idea[0]["succeeded"])
        self.assertEqual(report["moves_run"], 1)          # the one experiment
        self.assertEqual(report["budget_final"]["remaining"], 4)  # 6 - ideation - experiment

    def test_a_director_failure_ends_the_study_gracefully(self):
        def boom(study, arc, budget):
            raise RuntimeError("model door gave up")
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=boom, run_move=self._run_move(), study_id="s",
        )
        self.assertEqual(report["termination"]["reason"], "director_failed")
        self.assertIn("model door gave up", report["termination"]["detail"])
        self.assertEqual(report["moves_run"], 0)

    def test_runs_spend_is_summed_from_per_move_cost(self):
        script = [
            self._act("run_experiment", domain="q1"),
            self._act("run_experiment", domain="q2"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(10), studies_root=self.root,
            decide_action=self._scripted(script),
            run_move=self._run_move(cost={"calls": 7, "tokens": 700}),
            study_id="s",
        )
        self.assertEqual(report["runs_spend"]["calls"], 14)
        self.assertEqual(report["runs_spend"]["tokens"], 1400)
        self.assertEqual(report["runs_spend"]["moves_with_cost"], 2)

    def test_runs_spend_counts_experiment_moves_only_not_capability_rows(self):
        # A capability row's metered cost came out of THIS process's meter — the
        # same meter the process-delta term reads — so runs_spend summing it too
        # would double-count it in total_spend.
        def fake_exec(name, action, study, budget, seq):
            budget.spend(1)
            return {"succeeded": True, "outcome": "ideation_done",
                    "hypotheses": [{"id": "h1", "statement": "try X"}],
                    "cost": {"calls": 4, "tokens": 400}}
        script = [
            self._act("call_ideation", domain="q"),
            self._act("run_experiment", domain="try X"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(script),
            run_move=self._run_move(cost={"calls": 1, "tokens": 700}),
            execute_capability=fake_exec, study_id="s",
        )
        idea = [e for e in report["arc"] if e["move_type"] == "call_ideation"]
        self.assertEqual(idea[0]["cost"], {"calls": 4, "tokens": 400})  # recorded...
        self.assertEqual(report["runs_spend"]["tokens"], 700)           # ...not resummed
        self.assertEqual(report["runs_spend"]["moves_run"], 1)
        self.assertEqual(
            report["total_spend"]["tokens"],
            report["process_spend"]["tokens"] + 700,
        )

    def test_report_carries_tree_spend_and_the_renamed_process_spend(self):
        # A parent that spawns a real (offline) child: total_spend still covers
        # only THIS study — the glider root under-counted its tree ~3x that way —
        # so the report now carries tree_spend, the recursive arc roll-up, as a
        # NEW field beside the untouched total_spend.
        import pi_agent.capabilities as C

        child_script = [
            self._act("run_experiment", domain="child q"),
            self._act("stop", stop_reason="child done"),
        ]
        child_run_move = self._run_move(cost={"calls": 2, "tokens": 2000})

        def child_investigate(domain, child_budget, child_id, parent_study):
            return free_investigate(
                domain, budget=child_budget, mode=parent_study.mode,
                study_id=child_id, parent_study_id=parent_study.study_id,
                studies_root=parent_study.studies_root,
                decide_action=self._scripted(child_script), run_move=child_run_move,
            )

        def parent_exec(name, action, study, budget, seq):
            return C.run_spawn(action, study, budget, seq, investigate=child_investigate)

        parent_script = [
            self._act("spawn_sub_investigation", domain="sub q", budget_moves=3),
            self._act("run_experiment", domain="own q"),
            self._act("stop", stop_reason="parent done"),
        ]
        report = free_investigate(
            "goal", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(parent_script),
            run_move=self._run_move(cost={"calls": 1, "tokens": 700}),
            execute_capability=parent_exec, study_id="parent",
        )
        # the rename: process_spend is the honest name for the process delta.
        self.assertIn("calls", report["process_spend"])
        self.assertNotIn("decider_spend", report)
        # total_spend keeps its meaning (this study only) for existing readers.
        self.assertEqual(
            report["total_spend"]["tokens"],
            report["process_spend"]["tokens"] + report["runs_spend"]["tokens"],
        )
        self.assertEqual(report["runs_spend"]["tokens"], 700)
        # tree_spend rolls up the child's arc too — the tree-correct number.
        self.assertEqual(report["tree_spend"]["tokens"], 2700)
        self.assertEqual(report["tree_spend"]["calls"], 3)
        self.assertEqual(report["tree_spend"]["studies"], 2)

    def test_integration_dispatches_a_verified_experiment_over_the_verified_parts(self):
        # run an experiment that produces a verified finding, then call_integration:
        # it must dispatch a real run whose domain names the verified part.
        captured = {}

        # first move yields a verified finding; second is the integration call.
        def run_move(study, move, finding=None, runs_root=None):
            captured.setdefault("domains", []).append(move.domain)
            findings = None
            if move.domain.startswith("measure part A"):
                findings = [{"label": "massA", "value": 3.2, "verified": True}]
            raw = {"publishable": True}
            if findings:
                raw["findings"] = findings
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX",
                           True, "completed", raw),
                finding=finding,
            )
        script = [
            self._act("run_experiment", domain="measure part A"),
            self._act("call_integration", detail="total mass under 5"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "build a light frame", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(script), run_move=run_move, study_id="s",
        )
        # two experiment moves ran (the part measurement + the integration check).
        self.assertEqual(report["moves_run"], 2)
        integ_domain = captured["domains"][1]
        self.assertIn("Integration check", integ_domain)
        self.assertIn("massA=3.2", integ_domain)          # the verified part travelled in
        self.assertIn("total mass under 5", integ_domain)  # the joint criterion

    def test_integration_offers_reusable_file_producers_to_the_experimenter(self):
        # a run produces a verified finding AND a reusable file; the integration
        # domain must carry the file's PRODUCER for the experimenter to inline.
        captured = {}
        prod = {"kind": "code", "code": "c", "quantity": "n", "emits": ["seq.fasta"]}

        def run_move(study, move, finding=None, runs_root=None):
            captured.setdefault("domains", []).append(move.domain)
            raw = {"publishable": True}
            if move.domain.startswith("make the sequence"):
                raw["findings"] = [{"label": "len", "value": 4.0, "verified": True}]
                raw["reusable_artifacts"] = [{"name": "seq.fasta", "producer": prod}]
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX",
                           True, "completed", raw),
                finding=finding,
            )
        script = [
            self._act("run_experiment", domain="make the sequence"),
            self._act("call_integration", detail="assemble the sequence"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "design a construct", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(script), run_move=run_move, study_id="s",
        )
        integ_domain = captured["domains"][1]
        self.assertIn("Integration check", integ_domain)
        self.assertIn("seq.fasta", integ_domain)       # the file name
        self.assertIn("emits", integ_domain)           # the producer recipe travelled in
        self.assertIn("INLINE", integ_domain)          # the instruction to regenerate it

    def test_integration_runs_when_only_reusable_files_exist(self):
        # no scalar parts, but a reusable file present -> integration still dispatches.
        prod = {"kind": "code", "code": "c", "quantity": "n", "emits": ["d.csv"]}

        def run_move(study, move, finding=None, runs_root=None):
            raw = {"publishable": True}
            if move.domain.startswith("make data"):
                raw["reusable_artifacts"] = [{"name": "d.csv", "producer": prod}]
            return S.record_move(
                study,
                MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX",
                           True, "completed", raw),
                finding=finding,
            )
        script = [
            self._act("run_experiment", domain="make data"),
            self._act("call_integration"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(6), studies_root=self.root,
            decide_action=self._scripted(script), run_move=run_move, study_id="s",
        )
        self.assertEqual(report["moves_run"], 2)  # the make-data run + the integration
        integ = [e for e in report["arc"] if e["move_type"] == "call_integration"]
        self.assertEqual(len(integ), 0)  # integration was dispatched as a run, not a no-op

    def test_integration_with_nothing_verified_is_an_honest_noop(self):
        script = [
            self._act("call_integration", detail="compose them"),
            self._act("stop", stop_reason="done"),
        ]
        report = free_investigate(
            "g", budget=Budget(4), studies_root=self.root,
            decide_action=self._scripted(script), run_move=self._run_move(),
            study_id="s",
        )
        self.assertEqual(report["moves_run"], 0)  # nothing dispatched
        cap = [e for e in report["arc"] if e["move_type"] == "call_integration"]
        self.assertEqual(len(cap), 1)
        self.assertEqual(cap[0]["outcome"], "integration_nothing_to_compose")
        self.assertEqual(report["budget_final"]["remaining"], 4)  # no move spent

    def test_report_is_written_to_disk(self):
        report = free_investigate(
            "g", budget=Budget(2), studies_root=self.root,
            decide_action=self._scripted([self._act("stop", stop_reason="done")]),
            run_move=self._run_move(), study_id="s",
        )
        written = (self.root / "s" / "report.json")
        self.assertTrue(written.is_file())


if __name__ == "__main__":
    unittest.main()
