"""
test_pi_loop.py — the PI decider and the research loop (chunk 4: the mind).

WHAT THIS PROVES. The loop runs the researcher's cycle — decide, run, read,
decide again — accumulating an arc under a study, stops on the PI's own judgment
OR the move budget (whichever first), ends gracefully if the decider fails, and
writes a report. The decider's judgment is a REAL Opus call through the standard
door; that path is proven with ONLY the model transport faked (no spend), which
is what makes "the decision is a model call, not a policy" real and testable.

Offline throughout: the loop's decide/run_move are injected with fakes for the
mechanics, and the one live-path test fakes model_call._invoke_transport exactly
as the triage battery does.

Run directly: venv/bin/python3 tests/test_pi_loop.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import model_call  # noqa: E402
from pi_agent import decider, loop  # noqa: E402
from pi_agent import study as S  # noqa: E402
from pi_agent.dispatch import MoveResult, MoveType  # noqa: E402


# --------------------------------------------------------------------------
# The decision validator — tested directly, like the gate-1 chooser's.
# --------------------------------------------------------------------------

class TestDecisionValidator(unittest.TestCase):
    def _v(self, arc_len=1):
        return decider.make_decision_validator("study-1", arc_len)

    def _ok(self, **over):
        base = {
            "ack": "study-1", "reading": "the last run stood", "decision": "run_single",
            "rationale": "open a sharper line", "next_domain": "does X hold at low Y?",
            "instrument": None, "stop_reason": None,
        }
        base.update(over)
        return base

    def test_a_well_formed_run_decision_passes(self):
        self.assertEqual(self._v()(self._ok()), [])

    def test_ack_must_echo_the_study_id(self):
        errs = self._v()(self._ok(ack="wrong"))
        self.assertTrue(any("ack" in e for e in errs))

    def test_decision_must_be_in_the_enum(self):
        errs = self._v()(self._ok(decision="run_chain"))  # not offered in v1
        self.assertTrue(any("decision must be one of" in e for e in errs))

    def test_run_move_requires_a_next_domain(self):
        errs = self._v()(self._ok(decision="run_campaign", next_domain="  "))
        self.assertTrue(any("next_domain" in e for e in errs))

    def test_stop_requires_a_stop_reason(self):
        errs = self._v()(self._ok(decision="stop", next_domain=None, stop_reason=None))
        self.assertTrue(any("stop_reason" in e for e in errs))

    def test_stop_is_valid_with_a_reason(self):
        self.assertEqual(
            self._v()(self._ok(decision="stop", next_domain=None, stop_reason="goal answered")),
            [],
        )

    def test_reading_may_be_null_only_on_the_first_turn(self):
        self.assertEqual(self._v(arc_len=0)(self._ok(reading=None)), [])
        errs = self._v(arc_len=2)(self._ok(reading=None))
        self.assertTrue(any("reading" in e for e in errs))

    def test_extra_fields_are_rejected(self):
        errs = self._v()(self._ok(surprise="x"))
        self.assertTrue(any("not allowed" in e for e in errs))

    def test_a_named_instrument_must_be_on_the_menu(self):
        v = decider.make_decision_validator("study-1", 1, ("cobrapy", "rdkit"))
        self.assertEqual(v(self._ok(instrument="cobrapy")), [])         # on menu
        errs = v(self._ok(instrument="cavity_2d_cfd"))                   # off menu
        self.assertTrue(any("instrument must be one of the menu" in e for e in errs))

    def test_a_null_instrument_is_always_valid(self):
        v = decider.make_decision_validator("study-1", 1, ("cobrapy",))
        self.assertEqual(v(self._ok(instrument=None)), [])

    def test_instrument_must_be_null_on_stop(self):
        v = decider.make_decision_validator("study-1", 1, ("cobrapy",))
        errs = v(self._ok(decision="stop", next_domain=None, stop_reason="done", instrument="cobrapy"))
        self.assertTrue(any("instrument must be null" in e for e in errs))


# --------------------------------------------------------------------------
# decide() — records the decision under the study; call injected.
# --------------------------------------------------------------------------

class TestDecide(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("a goal", study_id="study-d", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_decide_returns_and_records_the_decision(self):
        canned = {
            "ack": "study-d", "reading": None, "decision": "run_single",
            "rationale": "start here", "next_domain": "first question", "stop_reason": None,
        }

        def fake_call(stage, prompt, stage_input, schema, model=None, extra_validator=None, capabilities=None):
            # The door would validate; here assert the validator passes the canned reply.
            self.assertEqual(extra_validator(canned), [])
            return canned, {"model": model, "attempts": 1}

        out = decider.decide(self.study, [], {"moves_used": 0, "max_moves": 3}, call=fake_call)
        self.assertEqual(out["decision"], "run_single")
        rec = self.study.dir / "decisions" / "decide1.json"
        self.assertTrue(rec.is_file())
        self.assertEqual(json.loads(rec.read_text())["decision"]["next_domain"], "first question")

    def test_decider_input_carries_goal_constraint_budget_and_arc(self):
        st = S.create_study("g2", allowed_substrates=["cobrapy"], study_id="study-in", studies_root=self.root)
        payload = decider.build_decider_input(st, [{"seq": 1}], {"moves_used": 1, "max_moves": 4})
        self.assertEqual(payload["goal"], "g2")
        self.assertEqual(payload["instrument_constraint"], ["cobrapy"])
        self.assertEqual(payload["budget"]["moves_used"], 1)
        self.assertEqual(payload["arc_so_far"], [{"seq": 1}])
        self.assertNotIn("run_id", payload)  # no runs/ transcript pollution

    def test_decider_input_carries_the_instrument_menu(self):
        st = S.create_study("g3", allowed_substrates=["cobrapy"], study_id="study-menu", studies_root=self.root)
        payload = decider.build_decider_input(st, [], {"moves_used": 0, "max_moves": 3})
        menu = payload["instrument_menu"]
        self.assertEqual([m["substrate_id"] for m in menu], ["cobrapy"])
        # The PI reasons over what the tool does, not just its name.
        self.assertIn("can_measure", menu[0])
        self.assertIn("can_vary", menu[0])

    def test_unconstrained_study_menu_is_every_routable_instrument(self):
        from tools import substrate_registry as registry
        st = S.create_study("g4", study_id="study-open", studies_root=self.root)
        ids = [m["substrate_id"] for m in decider.build_decider_input(st, [], {})["instrument_menu"]]
        self.assertEqual(set(ids), set(registry.routable_ids()))


# --------------------------------------------------------------------------
# investigate() — the loop mechanics, decide + run_move injected.
# --------------------------------------------------------------------------

class TestInvestigate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_run_move(self, study, move, finding=None, runs_root=None):
        # Record like the real run_study_move, without dispatching anything.
        return S.record_move(
            study,
            MoveResult(move.type.value, move.run_id or f"{study.study_id}-mX", True, "completed", {"publishable": True}),
            finding=finding,
        )

    def _run_move_with_cost(self, calls, tokens):
        def run_move(study, move, finding=None, runs_root=None):
            return S.record_move(
                study,
                MoveResult(
                    move.type.value,
                    move.run_id or f"{study.study_id}-mX",
                    True,
                    "completed",
                    {"publishable": True, "cost": {"calls": calls, "tokens": tokens}},
                ),
                finding=finding,
            )
        return run_move

    def test_runs_spend_is_summed_from_per_move_cost(self):
        script = [
            {"decision": "run_single", "next_domain": "d1", "rationale": "r"},
            {"decision": "run_single", "next_domain": "d2", "rationale": "r"},
            {"decision": "stop", "stop_reason": "done"},
        ]
        report = loop.investigate(
            "g", studies_root=self.root,
            decide=self._scripted_decider(script),
            run_move=self._run_move_with_cost(10, 1000),
            study_id="study-cost",
        )
        self.assertEqual(report["runs_spend"]["calls"], 20)
        self.assertEqual(report["runs_spend"]["tokens"], 2000)
        self.assertEqual(report["runs_spend"]["moves_with_cost"], 2)
        self.assertEqual(report["runs_spend"]["moves_run"], 2)
        # total_spend folds in the decider's own spend on top of the runs'.
        self.assertEqual(
            report["total_spend"]["calls"],
            report["decider_spend"]["calls"] + 20,
        )

    def test_a_move_with_no_cost_contributes_nothing_and_is_not_counted(self):
        # _fake_run_move records no cost — runs_spend stays zero with zero coverage.
        script = [
            {"decision": "run_single", "next_domain": "d1", "rationale": "r"},
            {"decision": "stop", "stop_reason": "done"},
        ]
        report = loop.investigate(
            "g", studies_root=self.root,
            decide=self._scripted_decider(script),
            run_move=self._fake_run_move, study_id="study-nocost",
        )
        self.assertEqual(report["runs_spend"]["calls"], 0)
        self.assertEqual(report["runs_spend"]["moves_with_cost"], 0)
        self.assertEqual(report["runs_spend"]["moves_run"], 1)

    def _scripted_decider(self, script):
        """Return a decide() that yields the next scripted decision each call."""
        calls = {"n": 0}

        def decide(study, arc, budget):
            d = script[calls["n"]]
            calls["n"] += 1
            return d
        decide.calls = calls
        return decide

    def _run(self, script, **kw):
        return loop.investigate(
            "a goal",
            studies_root=self.root,
            decide=self._scripted_decider(script),
            run_move=self._fake_run_move,
            **kw,
        )

    def test_loop_runs_moves_until_the_pi_stops(self):
        script = [
            {"decision": "run_single", "rationale": "open", "next_domain": "q1"},
            {"decision": "run_campaign", "rationale": "sweep", "next_domain": "q2"},
            {"decision": "stop", "rationale": "done", "stop_reason": "goal answered"},
        ]
        report = self._run(script, max_moves=10, study_id="study-stop")
        self.assertEqual(report["moves_run"], 2)
        self.assertEqual(report["termination"]["reason"], "pi_judged_complete")
        self.assertEqual(report["termination"]["detail"], "goal answered")
        self.assertEqual([m["move_type"] for m in report["arc"]], ["single", "campaign"])

    def test_move_budget_is_a_hard_ceiling_even_if_the_pi_never_stops(self):
        # A decider that always wants another move must still be stopped.
        never_stop = [
            {"decision": "run_single", "rationale": "again", "next_domain": f"q{i}"} for i in range(20)
        ]
        report = self._run(never_stop, max_moves=3, study_id="study-cap")
        self.assertEqual(report["moves_run"], 3)
        self.assertEqual(report["termination"]["reason"], "move_budget_spent")

    def test_budget_is_checked_before_deciding_so_no_over_budget_move_starts(self):
        # With max_moves=0 the loop must stop before the first decision.
        decided = {"n": 0}

        def counting_decide(study, arc, budget):
            decided["n"] += 1
            return {"decision": "stop", "rationale": "x", "stop_reason": "x"}

        report = loop.investigate("g", studies_root=self.root, max_moves=0,
                                  decide=counting_decide, run_move=self._fake_run_move,
                                  study_id="study-zero")
        self.assertEqual(report["moves_run"], 0)
        self.assertEqual(decided["n"], 0)  # never even asked to decide
        self.assertEqual(report["termination"]["reason"], "move_budget_spent")

    def test_a_decider_failure_ends_the_study_gracefully(self):
        def boom(study, arc, budget):
            raise RuntimeError("model door gave up")

        report = loop.investigate("g", studies_root=self.root, decide=boom,
                                  run_move=self._fake_run_move, study_id="study-fail")
        self.assertEqual(report["termination"]["reason"], "decider_failed")
        self.assertIn("model door gave up", report["termination"]["detail"])
        self.assertEqual(report["moves_run"], 0)

    def test_a_halted_move_is_not_a_loop_error_the_pi_responds_next_turn(self):
        # run_move records a halt; the loop keeps going and the decider then stops.
        def halting_run_move(study, move, finding=None, runs_root=None):
            return S.record_move(
                study,
                MoveResult(move.type.value, "r", False, "halted_barren_budget_spent", {"publishable": None}),
                finding=finding,
            )

        script = [
            {"decision": "run_single", "rationale": "try", "next_domain": "q1"},
            {"decision": "stop", "rationale": "that path is dead", "stop_reason": "halted, revising is futile"},
        ]
        report = loop.investigate("g", studies_root=self.root,
                                  decide=self._scripted_decider(script),
                                  run_move=halting_run_move, study_id="study-halt")
        self.assertEqual(report["moves_run"], 1)
        self.assertEqual(report["arc"][0]["outcome"], "halted_barren_budget_spent")
        self.assertEqual(report["termination"]["reason"], "pi_judged_complete")

    def test_report_is_written_to_disk_and_carries_the_spend_note(self):
        script = [{"decision": "stop", "rationale": "x", "stop_reason": "y"}]
        report = self._run(script, study_id="study-report")
        self.assertTrue((self.root / "study-report" / "report.json").is_file())
        self.assertIn("max_moves", report["spend_note"])
        self.assertIn("calls", report["decider_spend"])

    def test_constraint_is_carried_into_the_study(self):
        script = [{"decision": "stop", "rationale": "x", "stop_reason": "y"}]
        loop.investigate("g", allowed_substrates=["cobrapy"], studies_root=self.root,
                         decide=self._scripted_decider(script), run_move=self._fake_run_move,
                         study_id="study-con")
        st = S.load_study("study-con", studies_root=self.root)
        self.assertEqual(st.allowed_substrates, ["cobrapy"])

    def test_a_named_instrument_narrows_the_dispatched_move(self):
        # The PI picks an instrument for the move; it reaches the move as a
        # one-element allow-set (which the run's chooser is then forced to).
        captured = {}

        def capturing_run_move(study, move, finding=None, runs_root=None):
            captured["allowed"] = move.allowed_substrates
            return S.record_move(
                study, MoveResult(move.type.value, "r", True, "completed", {"publishable": True}),
                finding=finding,
            )

        script = [
            {"decision": "run_single", "rationale": "the surprise points to FEA",
             "next_domain": "does bending stress explain it?", "instrument": "cobrapy"},
            {"decision": "stop", "rationale": "done", "stop_reason": "answered"},
        ]
        loop.investigate("g", allowed_substrates=["cobrapy", "rdkit"], studies_root=self.root,
                         decide=self._scripted_decider(script), run_move=capturing_run_move,
                         study_id="study-pick")
        self.assertEqual(captured["allowed"], ["cobrapy"])

    def test_a_null_instrument_leaves_the_move_for_the_run_to_choose(self):
        captured = {}

        def capturing_run_move(study, move, finding=None, runs_root=None):
            captured["allowed"] = move.allowed_substrates
            return S.record_move(
                study, MoveResult(move.type.value, "r", True, "completed", {"publishable": True}),
                finding=finding,
            )

        script = [
            {"decision": "run_single", "rationale": "open", "next_domain": "q", "instrument": None},
            {"decision": "stop", "rationale": "done", "stop_reason": "answered"},
        ]
        loop.investigate("g", studies_root=self.root,
                         decide=self._scripted_decider(script), run_move=capturing_run_move,
                         study_id="study-nopick")
        self.assertIsNone(captured["allowed"])


# --------------------------------------------------------------------------
# THE REAL PATH: decide() through the actual door, only the transport faked.
# --------------------------------------------------------------------------

class TestRealDeciderPathTransportFaked(unittest.TestCase):
    """Proves the decision is a genuine model call: build_decider_input ->
    call_stage_model -> validator -> recorded decision, with ONLY
    model_call._invoke_transport replaced. No spend."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("does the growth rate change below optimum?",
                                    allowed_substrates=["cobrapy"], study_id="study-real",
                                    studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_decide_runs_through_the_real_door(self):
        canned = json.dumps({
            "ack": "study-real",
            "reading": None,
            "decision": "run_single",
            "rationale": "open the investigation on the core question",
            "next_domain": "is LP-predicted growth invariant just below the optimum?",
            "fan_domains": None,
            "instrument": None,
            "stop_reason": None,
        })

        seen = {}

        def fake_transport(system_prompt, user_turn, model):
            seen["model"] = model
            seen["payload"] = json.loads(user_turn)
            return canned

        with mock.patch.object(model_call, "_invoke_transport", fake_transport):
            out = decider.decide(self.study, [], {"moves_used": 0, "max_moves": 4})

        # The real door validated the reply, echoed the study_id, and returned it.
        self.assertEqual(out["decision"], "run_single")
        self.assertEqual(out["ack"], "study-real")
        # It went to Opus, and the model saw the goal + constraint + budget.
        self.assertEqual(seen["model"], decider.PI_DECIDER_MODEL)
        self.assertEqual(seen["payload"]["goal"], "does the growth rate change below optimum?")
        self.assertEqual(seen["payload"]["instrument_constraint"], ["cobrapy"])
        # The decision was recorded under the study.
        self.assertTrue((self.study.dir / "decisions" / "decide1.json").is_file())

    def test_a_reply_that_violates_the_schema_is_re_asked_then_fails_loudly(self):
        # The door re-asks a bad reply MAX_ATTEMPTS times, then raises — the
        # decider does not paper over a model that will not answer in shape.
        bad = json.dumps({"ack": "study-real", "decision": "banana"})

        with mock.patch.object(model_call, "_invoke_transport", lambda s, u, m: bad):
            with self.assertRaises(Exception):
                decider.decide(self.study, [], {"moves_used": 0, "max_moves": 4})


if __name__ == "__main__":
    unittest.main(verbosity=2)
