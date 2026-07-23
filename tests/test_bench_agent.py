"""test_bench_agent.py — stage 4 as an experimenting agent.

Call-free: NO model calls, NO network, NO docker. The bench agent is replaced by
deterministic fakes standing in for its JUDGMENT; everything the judgment feeds
into — the widened socket, spec re-validation, the substrate agreement re-check,
the real run entry constructor, the real locked schema — runs unmocked.

The acceptance case is run 20260720T080610Z: a cobrapy spec that was rejected
"input rejected: missing required field(s): model" three times in 0.0 seconds
while the system had no capacity to look. TestTheAcceptanceCase drives that exact
failure through the campaign and asserts the agent repairs it and gets data.

Run directly: venv/bin/python3 tests/test_bench_agent.py
"""

from __future__ import annotations

import json
import shutil
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import capability_guard  # noqa: E402
import model_call  # noqa: E402
import schemas  # noqa: E402
import supervisor  # noqa: E402
import tools.bench_agent as bench  # noqa: E402
import tools.experiment_picker as ep  # noqa: E402
from baton import Baton  # noqa: E402
from stages import campaign_controller as cc  # noqa: E402

RUNS = ROOT / "runs"


def _cobrapy_baton(run_id: str, spec: dict) -> Baton:
    b = Baton(run_id=run_id, created_at="2026-07-20T00:00:00Z", mode="auto")
    b.payload = {
        "domain": "biology",
        "chosen_hypothesis": {"id": "h5", "statement": "s", "rationale": "r"},
        "substrate_id": "cobrapy",
        "experiment_spec": spec,
        "fidelity_verdict": {
            "label": "trust",
            "rationale": "the model's reasoning",
            "right_instrument": "the right instrument text",
        },
    }
    return b


FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bench" / "cobrapy_failing_spec.json"


def _failing_spec(model="iJO1366") -> dict:
    """Run 20260720T080610Z's ACTUAL stage-2 spec, frozen as a fixture.

    It is a correctly authored spec — it passes validate_spec today — with the
    categorical instrument selector in the regime block, which is the only place
    the schema permits it. Its one defect is a model value the wrapper's
    allowlist rejects. Using the real spec rather than a stub matters: the
    repair the agent makes then has to survive the real locked validator, which
    is the whole point of re-validating a revision.
    """
    spec = json.loads(FIXTURE.read_text())
    spec["regime"]["model"] = model
    return spec


class BenchBase(unittest.TestCase):
    def setUp(self):
        self._made: list[Path] = []

    def tearDown(self):
        for d in self._made:
            shutil.rmtree(d, ignore_errors=True)

    def _cleanup(self, run_id: str):
        self._made.append(RUNS / run_id)

    def _register(self, key, strategy):
        cc.STRATEGIES[key] = strategy
        self.addCleanup(cc.STRATEGIES.pop, key, None)

    def _summary(self, run_id):
        return json.loads((RUNS / run_id / "campaign" / "summary.json").read_text())


class TestSocketWidenedNotReplaced(BenchBase):
    """Evolution, not replacement: the deterministic planners stay registered
    and stay callable exactly as they were."""

    def test_deterministic_planners_are_untouched(self):
        self.assertIs(cc.STRATEGIES["propose_next_points"], ep.propose_next_points)
        self.assertIs(cc.STRATEGIES["adaptive_refine"], ep.propose_adaptive_points)

    def test_agentic_strategy_is_registered_beside_them(self):
        self.assertIs(cc.STRATEGIES["bench_agent"], bench.propose_bench_actions)

    def test_only_context_accepting_strategies_are_offered_context(self):
        self.assertTrue(cc._strategy_accepts_context(bench.propose_bench_actions))
        self.assertFalse(cc._strategy_accepts_context(ep.propose_next_points))
        self.assertFalse(cc._strategy_accepts_context(ep.propose_adaptive_points))

    def test_a_three_argument_planner_is_still_called_with_three(self):
        """The trap this avoids: widening by changing how everyone is CALLED
        makes old fakes raise TypeError instead of asserting, and a whole family
        of contract tests goes silently vacuous."""
        seen = {}

        def old_style(spec, prior_results, budget_remaining):
            seen["args"] = (spec, prior_results, budget_remaining)
            return {"points": [{"x": 1}], "reasoning": "ok",
                    "predicted_qoi_per_point": [None]}

        out = cc._invoke_strategy(old_style, {"s": 1}, [], 5, {"ctx": True})
        self.assertEqual(seen["args"], ({"s": 1}, [], 5))
        self.assertEqual(out["points"], [{"x": 1}])

    def test_a_context_accepting_planner_receives_it(self):
        seen = {}

        def new_style(spec, prior_results, budget_remaining, context=None):
            seen["context"] = context
            return {"points": [], "reasoning": "done", "stop": True,
                    "stop_reason": "enough", "predicted_qoi_per_point": []}

        cc._invoke_strategy(new_style, {}, [], 5, {"substrate_id": "cobrapy"})
        self.assertEqual(seen["context"]["substrate_id"], "cobrapy")


class TestReachableFromARealRun(BenchBase):
    """A strategy registered in the socket but selectable by nothing is built
    and switched off — which is how the campaign loop itself sat dormant behind
    an unset flag."""

    def test_default_is_still_the_deterministic_planner(self):
        with unittest.mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("CAMPAIGN_STRATEGY", None)
            self.assertEqual(cc.resolve_strategy_key(), "propose_next_points")

    def test_the_environment_can_select_the_bench_agent(self):
        with unittest.mock.patch.dict("os.environ",
                                      {"CAMPAIGN_STRATEGY": "bench_agent"}):
            self.assertEqual(cc.resolve_strategy_key(), "bench_agent")

    def test_a_typo_stops_the_run_rather_than_silently_sweeping(self):
        run_id = "bench-typo"
        self._cleanup(run_id)
        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.dict("os.environ",
                                      {"CAMPAIGN_STRATEGY": "bench_agnet"}):
            with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
                with self.assertRaises(KeyError):
                    cc.run_campaign(baton)


class TestProposalValidation(BenchBase):
    """The agent's answer is checked in code, not hoped for in the prompt."""

    def _errs(self, proposal):
        return bench._validate_proposal(proposal)

    def test_a_good_proposal_passes(self):
        self.assertEqual(self._errs({
            "reasoning": "the allowlist rejected the model; trying a permitted one",
            "points": [{"min_growth": 0.4}],
            "predicted_qoi_per_point": [0.87],
        }), [])

    def test_prediction_count_must_match_point_count(self):
        errs = self._errs({"reasoning": "r", "points": [{"x": 1}, {"x": 2}],
                           "predicted_qoi_per_point": [1.0]})
        self.assertTrue(any("read positionally" in e for e in errs))

    def test_point_values_must_be_numbers(self):
        errs = self._errs({"reasoning": "r", "points": [{"model": "iML1515"}],
                           "predicted_qoi_per_point": [None]})
        self.assertTrue(any("must be" in e and "numbers" in e for e in errs))
        self.assertTrue(any("regime" in e for e in errs),
                        "the error should point at the real fix, not just refuse")

    def test_reasoning_may_not_impersonate_the_degraded_planner(self):
        errs = self._errs({"reasoning": "fallback: uniform coverage",
                           "points": [{"x": 1}], "predicted_qoi_per_point": [None]})
        self.assertTrue(any("reserved" in e for e in errs))

    def test_stopping_requires_a_reason(self):
        self.assertTrue(any("stop_reason" in e for e in
                            self._errs({"reasoning": "r", "points": [], "stop": True})))

    def test_proposing_nothing_without_stopping_is_refused(self):
        errs = self._errs({"reasoning": "r", "points": [],
                           "predicted_qoi_per_point": []})
        self.assertTrue(any("stop honestly" in e for e in errs))

    def test_a_revision_must_be_a_whole_spec(self):
        errs = self._errs({"reasoning": "r", "points": [{"x": 1}],
                           "predicted_qoi_per_point": [None],
                           "revised_spec": "regime.model = iML1515"})
        self.assertTrue(any("complete spec object" in e for e in errs))


class TestCapabilityAndCost(BenchBase):
    """The costs the handoff said to surface rather than absorb."""

    def test_the_bench_agent_may_hold_tools_because_it_measures_nothing(self):
        capability_guard.assert_profile_allowed(bench.BENCH_STAGE_NAME, "bench")

    def test_a_stage_that_produces_a_measurement_still_may_not(self):
        with self.assertRaises(capability_guard.CapabilityPairingError):
            capability_guard.assert_profile_allowed("stage4_simulation", "bench")

    def test_the_turn_cap_is_real_and_tighter_than_the_full_backstop(self):
        """A declared budget the code does not enforce is a lie told with a
        number in it — this one is the value handed to the SDK."""
        self.assertLess(bench.BENCH.max_turns, model_call.FULL.max_turns)
        self.assertGreater(bench.BENCH.max_turns, 0)

    def test_it_has_the_full_toolset(self):
        self.assertEqual(bench.BENCH.allowed_tools, model_call.FULL.allowed_tools)
        self.assertTrue(bench.BENCH.uses_tools)

    def test_the_frozen_full_profile_was_not_mutated(self):
        self.assertEqual(model_call.FULL.max_turns, 200)

    def test_a_transport_failure_stops_honestly_rather_than_sweeping(self):
        """No transport retry exists for a tooled call, and a bench agent that
        cannot think must not be silently replaced by a sweep."""
        def explode(*a, **k):
            raise RuntimeError("transport died at turn 55")

        with unittest.mock.patch.object(bench, "call_stage_model", explode):
            out = bench.propose_bench_actions({}, [], 5, context={})
        self.assertTrue(out["stop"])
        self.assertIn("transport died", out["stop_reason"])
        self.assertEqual(out["points"], [])
        self.assertFalse(out["reasoning"].startswith("fallback:"))


class TestTheRealCallPath(BenchBase):
    """The bench agent's ACTUAL call assembly, with only the transport faked.

    Everything else is real: the capability guard runs, the transcript is
    written before the call fires, the validator is enforced inside the door's
    re-ask loop. This is the plumbing a live outing would otherwise discover the
    expensive way.
    """

    def _call(self, replies, spec=None):
        sent = []
        queue = list(replies)

        def transport(system_prompt, user_turn, model, *args, **kwargs):
            sent.append(user_turn)
            return queue.pop(0)

        with unittest.mock.patch.object(model_call, "_invoke_transport", transport):
            out = bench.propose_bench_actions(
                spec if spec is not None else _failing_spec(),
                [{"point": {"min_growth": 0.0},
                  "qoi_error": "input rejected: model 'iJO1366' is not a baked "
                               "allowlist model (allowed: e_coli_core, iML1515)"}],
                5,
                context={"substrate_id": "cobrapy",
                         "wrapper_path": "tools/run_cobrapy.py",
                         "qoi_request": {"quantity": "growth_rate"},
                         "iteration": 2},
            )
        return out, sent

    def test_the_guard_admits_this_stage_and_the_call_completes(self):
        reply = json.dumps({
            "reasoning": "the allowlist rejected iJO1366; using a permitted model",
            "points": [{"min_growth": 0.0}],
            "predicted_qoi_per_point": [0.87],
        })
        out, sent = self._call([reply])
        self.assertEqual(out["points"], [{"min_growth": 0.0}])
        self.assertFalse(out["stop"])

    def test_the_agent_is_shown_the_diagnostic_and_where_to_read_the_constraint(self):
        reply = json.dumps({"reasoning": "r", "points": [{"min_growth": 0.1}],
                            "predicted_qoi_per_point": [None]})
        _out, sent = self._call([reply])
        self.assertIn("allowlist", sent[0])
        self.assertIn("tools/run_cobrapy.py", sent[0])

    def test_a_malformed_proposal_is_re_asked_not_accepted(self):
        bad = json.dumps({"reasoning": "r", "points": [{"min_growth": 0.1}],
                          "predicted_qoi_per_point": []})  # length mismatch
        good = json.dumps({"reasoning": "fixed", "points": [{"min_growth": 0.1}],
                           "predicted_qoi_per_point": [0.5]})
        out, sent = self._call([bad, good])
        self.assertEqual(len(sent), 2, "the bad proposal should have been re-asked")
        self.assertIn("read positionally", sent[1])
        self.assertEqual(out["predicted_qoi_per_point"], [0.5])

    def test_a_spec_repair_survives_the_round_trip(self):
        repaired = _failing_spec("iML1515")
        reply = json.dumps({
            "reasoning": "repairing the model to an allowlisted one",
            "points": [{"min_growth": 0.0}], "predicted_qoi_per_point": [None],
            "revised_spec": repaired,
        })
        out, _sent = self._call([reply])
        self.assertEqual(out["revised_spec"]["regime"]["model"], "iML1515")


class TestDiagnosticsReachTheAgent(BenchBase):
    def test_wrapper_diagnostics_are_passed_through_verbatim(self):
        """The whole design turns on this string arriving intact — a summarized
        diagnostic is exactly the detail that would be lost."""
        rejection = "input rejected: missing required field(s): model"
        digest = bench._diagnostic_digest([
            {"point": {"min_growth": 0.0}, "qoi_error": rejection},
        ])
        self.assertEqual(digest[0]["problem"], rejection)

    def test_synthesis_failures_are_included(self):
        digest = bench._diagnostic_digest([
            {"point": {"x": 1}, "synthesis_error": "run 1 of 3: unsupported parameter"},
        ])
        self.assertIn("unsupported parameter", digest[0]["problem"])

    def test_context_carries_the_wrapper_source_path(self):
        self.assertEqual(cc._wrapper_path("cobrapy"), "tools/run_cobrapy.py")

    def test_an_unknown_substrate_yields_no_pointer_rather_than_raising(self):
        self.assertIsNone(cc._wrapper_path("no_such_substrate"))


class TestSpecRevision(BenchBase):
    """A repaired spec faces the same locked schema stage 2's output faces."""

    def test_a_valid_repair_is_adopted_and_everything_is_re_derived(self):
        """Through the REAL locked validator — no patching."""
        good = _failing_spec(model="iML1515")
        with unittest.mock.patch.object(cc, "_log_line", lambda *a: None):
            spec, resolved, note = cc._revise_spec(
                _failing_spec(), good, "cobrapy", "rev1")
        self.assertEqual(note, "revision accepted")
        self.assertIs(spec, good)
        # everything re-derived from the NEW spec, not left pointing at the old
        self.assertEqual(resolved["substrate_id"], "cobrapy")
        self.assertEqual(resolved["regime_inputs"]["model"], "iML1515")
        self.assertEqual(resolved["qoi_request"], {"quantity": "growth_rate"})

    def test_an_invalid_repair_is_refused_and_the_old_spec_stands(self):
        original = _failing_spec()
        junk = {"title": "not a spec"}
        with unittest.mock.patch.object(cc, "_log_line", lambda *a: None):
            spec, resolved, note = cc._revise_spec(original, junk, "cobrapy", "rev2")
        self.assertIs(spec, original)
        self.assertIsNone(resolved)
        self.assertIn("refused", note)

    def test_a_repair_that_switches_instruments_is_refused(self):
        """The gate decided the instrument. An agent may repair a spec; it may
        not quietly re-route the experiment to a different one."""
        original = _failing_spec()
        with unittest.mock.patch.object(cc, "_log_line", lambda *a: None):
            with unittest.mock.patch.object(
                    cc, "select_substrate", lambda spec: "rdkit"):
                spec, resolved, note = cc._revise_spec(
                    original, _failing_spec("iML1515"), "cobrapy", "rev3")
        self.assertIs(spec, original)
        self.assertIsNone(resolved)
        self.assertIn("refused", note)


class TestAgentStop(BenchBase):
    def test_the_agent_may_end_the_campaign_and_it_is_recorded_as_its_call(self):
        run_id = "bench-stop"
        self._cleanup(run_id)

        def stopper(spec, prior_results, budget_remaining, context=None):
            return {"points": [], "predicted_qoi_per_point": [], "stop": True,
                    "stop_reason": "this instrument cannot test the hypothesis",
                    "reasoning": "no scalar-transport physics here"}

        self._register("stopper", stopper)
        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            cc.run_campaign(baton, strategy_key="stopper")

        summary = self._summary(run_id)
        self.assertEqual(summary["termination_reason"], "agent_stopped")
        self.assertEqual(summary["iterations_used"], 0)

    def test_a_campaign_that_measured_nothing_does_not_claim_it_executed(self):
        """The locked schema says an 'executed' result must carry at least one
        run, so a zero-run 'executed' baton fails the post-stage-4 boundary and
        the supervisor halts the run as a BROKEN INVARIANT. An agent concluding
        'this instrument cannot test this hypothesis' — which the design asks it
        to say out loud — would have been recorded as a corrupted baton."""
        run_id = "bench-nothing"
        self._cleanup(run_id)

        def stopper(spec, prior_results, budget_remaining, context=None):
            return {"points": [], "predicted_qoi_per_point": [], "stop": True,
                    "stop_reason": "no scalar-transport physics on this instrument",
                    "reasoning": "the instrument cannot represent the mechanism"}

        self._register("nothing", stopper)
        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            out = cc.run_campaign(baton, strategy_key="nothing")

        er = out.payload["execution_results"]
        self.assertEqual(er["status"], "halted_synthesis")
        self.assertEqual(er["runs"], [])
        # the honest record says what stopped it, not just that it stopped
        self.assertIn("no scalar-transport physics", er["reason"])
        # THE PROOF: the baton survives the real locked boundary
        self.assertEqual(schemas.validate_payload_post_stage4(out.payload), [])

    def test_the_pre_existing_empty_proposal_route_is_covered_too(self):
        """propose_adaptive_points returns zero points whenever a spec declares
        no sweep — so this route into a schema-invalid baton predates the bench
        agent and is fixed by the same change."""
        run_id = "bench-nopoints"
        self._cleanup(run_id)
        self._register("empty", lambda s, p, b: {
            "points": [], "predicted_qoi_per_point": [],
            "reasoning": "adaptive: no declared sweep range"})

        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            out = cc.run_campaign(baton, strategy_key="empty")

        self.assertEqual(out.payload["execution_results"]["status"], "halted_synthesis")
        self.assertEqual(schemas.validate_payload_post_stage4(out.payload), [])
        self.assertIn("no_points_proposed",
                      out.payload["execution_results"]["reason"])


class TestTheAcceptanceCase(BenchBase):
    """Run 20260720T080610Z, driven through the new stage 4.

    Handed the failing cobrapy spec, the agent reads the rejection, finds the
    allowlist, repairs the input, reruns, and returns real growth-rate data —
    without a relay-level loop-back. The agent's JUDGMENT is faked (this test
    makes no model call); its REPAIR travels the real path.
    """

    def _repairing_agent(self, seen):
        def agent(spec, prior_results, budget_remaining, context=None):
            seen.append({"prior": list(prior_results), "context": dict(context or {})})
            if any(r.get("qoi_value") is not None for r in prior_results):
                return {"points": [], "predicted_qoi_per_point": [], "stop": True,
                        "stop_reason": "the repaired spec produced a real measurement",
                        "reasoning": "the instrument answered; the campaign has data"}
            failures = bench._diagnostic_digest(prior_results)
            if failures and "allowlist" in failures[0]["problem"]:
                # what a scientist does: read the constraint, fix the value
                from tools.run_cobrapy import MODEL_ALLOWLIST
                repaired = json.loads(json.dumps(spec))
                repaired["regime"]["model"] = MODEL_ALLOWLIST[0]
                return {"points": [{"min_growth": 0.0}],
                        "predicted_qoi_per_point": [None],
                        "reasoning": "the model was not in the wrapper's allowlist",
                        "revised_spec": repaired}
            return {"points": [{"min_growth": 0.0}],
                    "predicted_qoi_per_point": [None],
                    "reasoning": "first attempt on the authored spec"}
        return agent

    def test_the_agent_repairs_the_rejection_and_gets_real_data(self):
        run_id = "bench-acceptance"
        self._cleanup(run_id)
        seen = []
        self._register("repairing", self._repairing_agent(seen))

        baton = _cobrapy_baton(run_id, _failing_spec())  # iJO1366 — not allowlisted
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            out = cc.run_campaign(baton, strategy_key="repairing")

        results = json.loads((RUNS / run_id / "stage4" / "results.json").read_text())
        summary = self._summary(run_id)

        # 1. the first point genuinely failed on the allowlist
        first = results["runs"][0]["summary"]
        self.assertFalse(first["valid"])
        self.assertIn("allowlist", first["diagnostics"])

        # 2. the agent SAW that diagnostic
        self.assertTrue(any("allowlist" in (p.get("qoi_error") or "")
                            for p in seen[1]["prior"]))

        # 3. it repaired the spec and the repair was adopted
        self.assertTrue(any(r["outcome"] == "revision accepted"
                            for r in summary["spec_revisions"]))

        # 4. real data came back — a measured growth rate, from the instrument
        entries = out.payload["execution_results"]["runs"]
        measured = [e["qoi_value"] for e in entries if "qoi_value" in e]
        self.assertTrue(measured, "the campaign produced no measurement")
        self.assertGreater(measured[0], 0.0)

        # 5. and it happened INSIDE stage 4 — one consolidated result, one
        #    history note, no relay-level loop-back
        s4_notes = [h for h in out.history if h["stage"] == "stage4_simulation"]
        self.assertEqual(len(s4_notes), 1)
        self.assertEqual(out.payload["execution_results"]["status"], "executed")

    def test_the_measured_value_comes_from_the_instrument_not_the_agent(self):
        """THE HARD BOUNDARY. The agent may loop, fiddle and rebuild; it may not
        decide what the instrument said. Here it predicts a wrong number loudly
        and the record keeps the wrapper's own."""
        run_id = "bench-boundary"
        self._cleanup(run_id)

        def lying_agent(spec, prior_results, budget_remaining, context=None):
            if prior_results:
                return {"points": [], "predicted_qoi_per_point": [], "stop": True,
                        "stop_reason": "done", "reasoning": "one point is enough"}
            return {"points": [{"min_growth": 0.0}],
                    "predicted_qoi_per_point": [999.0],  # a confident fiction
                    "reasoning": "predicting a growth rate of 999"}

        self._register("lying", lying_agent)
        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            out = cc.run_campaign(baton, strategy_key="lying")

        entries = out.payload["execution_results"]["runs"]
        measured = [e["qoi_value"] for e in entries if "qoi_value" in e]
        self.assertTrue(measured)
        self.assertNotEqual(measured[0], 999.0)
        self.assertLess(measured[0], 10.0, "a real E. coli growth rate, not the fiction")

        # the prediction survives as a PREDICTION, compared by code
        summary = self._summary(run_id)
        self.assertEqual(summary["iterations"][0]["predicted_qoi"], 999.0)
        self.assertFalse(summary["iterations"][0]["comparison"]["matched"])

    def test_every_measurement_carries_an_artifact_that_regenerates_it(self):
        """Task 1 and task 2 meet here: an agent may do whatever it likes to GET
        a number precisely because every number it gets must survive an
        independent re-run."""
        run_id = "bench-artifacts"
        self._cleanup(run_id)
        self._register("one_shot", lambda s, p, b, context=None: (
            {"points": [], "predicted_qoi_per_point": [], "stop": True,
             "stop_reason": "done", "reasoning": "enough"} if p else
            {"points": [{"min_growth": 0.0}], "predicted_qoi_per_point": [None],
             "reasoning": "measure the unconstrained optimum"}))

        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            cc.run_campaign(baton, strategy_key="one_shot")

        artifacts = json.loads(
            (RUNS / run_id / "stage4" / "artifacts.json").read_text())["runs"]
        self.assertTrue(artifacts)
        artifact = artifacts[0]["artifact"]
        self.assertEqual(artifact["substrate_id"], "cobrapy")
        self.assertEqual(artifact["typed_input"]["model"], "iML1515")
        self.assertEqual(artifact["typed_input"]["quantity"], "growth_rate")


class TestRegimeThreadingOnTheCampaignPath(BenchBase):
    def test_regime_declared_instrument_inputs_reach_the_wrapper(self):
        """The single-run path threads these; the campaign path did not, so a
        campaign reproduced run 20260720T080610Z's rejection exactly."""
        run_id = "bench-regime"
        self._cleanup(run_id)
        self._register("one", lambda s, p, b, context=None: (
            {"points": [], "predicted_qoi_per_point": [], "stop": True,
             "stop_reason": "done", "reasoning": "enough"} if p else
            {"points": [{"min_growth": 0.0}], "predicted_qoi_per_point": [None],
             "reasoning": "go"}))

        baton = _cobrapy_baton(run_id, _failing_spec("iML1515"))
        with unittest.mock.patch.object(cc, "select_substrate", lambda s: "cobrapy"):
            cc.run_campaign(baton, strategy_key="one")

        results = json.loads((RUNS / run_id / "stage4" / "results.json").read_text())
        params = results["runs"][0]["params"]
        self.assertEqual(params["model"], "iML1515")
        self.assertTrue(results["runs"][0]["summary"]["valid"],
                        "the point should have reached the solver, not been rejected")


if __name__ == "__main__":
    unittest.main()
