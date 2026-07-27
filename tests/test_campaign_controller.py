"""
test_campaign_controller.py — Step 29: the campaign loop.

Call-free: NO model calls, NO network, NO docker. The docker-bound solver adapter
is replaced by a deterministic spy so the escape test fires offline; the REAL
maturity hook, REAL dispatch seam, REAL run entry constructor, REAL numeric
compare, and REAL locked schema run unmocked.

Run directly: venv/bin/python3 tests/test_campaign_controller.py
"""

from __future__ import annotations

import shutil
import sys
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import schemas
import supervisor
import tools.experiment_picker as ep
from baton import Baton
from stages import campaign_controller as cc
from stages.stage4_case_builder import CaseSynthesisError
from tools import substrate_dispatch, substrate_registry as registry

RUNS = ROOT / "runs"


def _trust_baton(run_id: str, substrate_id: str, label: str = "trust") -> Baton:
    b = Baton(run_id=run_id, created_at="2026-07-19T00:00:00Z", mode="auto")
    b.payload = {
        "domain": "biology",
        "chosen_hypothesis": {"id": "h1", "statement": "s", "rationale": "r"},
        "substrate_id": substrate_id,
        "experiment_spec": {
            "title": "t",
            "mini_experiment": {"runs": [{"model": "iML1515"}]},
            "qoi": {"name": "growth_rate"},
            "parameters": [],
        },
        "fidelity_verdict": {
            "label": label,
            "rationale": "the model's reasoning",
            "right_instrument": "the right instrument text",
        },
    }
    return b


def _spy_cobrapy_summary():
    """A realistic run_cobrapy/ngspice-shaped summary (the only stubbed part —
    the docker-bound solve). run_entry_constructor_for('cobrapy') builds a real
    entry from it via ngspice_run_entry."""
    return {"valid": True, "qoi": 0.873, "diagnostics": {"note": "spy"}, "runtime_s": 0.5}


def _fixed_strategy(points, predicted=None, reasoning="fixed test plan"):
    def strat(spec, prior_results, budget_remaining):
        return {
            "points": list(points),
            "reasoning": reasoning,
            "predicted_qoi_per_point": (
                list(predicted) if predicted is not None else [None] * len(points)
            ),
        }
    return strat


class CampaignBase(unittest.TestCase):
    def setUp(self):
        self._made: list[Path] = []

    def tearDown(self):
        for d in self._made:
            shutil.rmtree(d, ignore_errors=True)

    def _cleanup(self, run_id: str):
        self._made.append(RUNS / run_id)


class TestOptInDefault(CampaignBase):
    def test_flag_off_by_default(self):
        # D5: the campaign is OFF unless explicitly opted in.
        self.assertFalse(cc.campaign_enabled())

    def test_flag_on_delegates(self):
        # stage4.run delegates to run_campaign only when the flag is set.
        import stages.stage4_simulation as s4

        called = {"n": 0}

        def fake_campaign(baton):
            called["n"] += 1
            return baton

        with unittest.mock.patch.dict("os.environ", {cc.CAMPAIGN_ENV: "1"}):
            with unittest.mock.patch.object(cc, "run_campaign", fake_campaign):
                b = _trust_baton("camptest-delegate", "cobrapy")
                s4.run(b)
        self.assertEqual(called["n"], 1)

    def test_flag_on_real_integration_through_stage4_run(self):
        # END-TO-END: the flag routes stage4.run into the REAL run_campaign,
        # which produces a real executed result (docker call stubbed only).
        import stages.stage4_simulation as s4

        run_id = "camptest-integration"
        self._cleanup(run_id)
        cc.STRATEGIES["_int_fixed"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_int_fixed", None)
        b = _trust_baton(run_id, "cobrapy")
        with unittest.mock.patch.dict("os.environ", {cc.CAMPAIGN_ENV: "1"}):
            with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
                with unittest.mock.patch.object(
                    cc, "adapter_for", lambda sid: (lambda *a: _spy_cobrapy_summary())
                ):
                    with unittest.mock.patch.object(cc, "DEFAULT_STRATEGY", "_int_fixed"):
                        out = s4.run(b)
        self.assertEqual(out.payload["execution_results"]["status"], "executed")
        self.assertGreaterEqual(len(out.payload["execution_results"]["runs"]), 1)


class TestEscapeCobrapyAuto(CampaignBase):
    """T2 (top-risk escape): a campaign on cobrapy in AUTO mode must produce an
    ACTUAL solver run entry — not skipped_defer, not a tidy zero-run record."""

    def test_campaign_produces_real_run_entry_not_skip(self):
        run_id = "camptest-escape"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy")
        spy = {"calls": 0}

        def spy_adapter(sid, params, case_name, roles, qreq):
            spy["calls"] += 1
            return _spy_cobrapy_summary()

        cc.STRATEGIES["_t2_fixed"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_t2_fixed", None)
        # the docker call is the ONLY stub; routing + entry construction are real
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: spy_adapter):
                out = cc.run_campaign(b, strategy_key="_t2_fixed")

        er = out.payload["execution_results"]
        # THE assertion: a real run entry exists, and the status is NOT the
        # skipped/zero-run shape a "looks clean but ran nothing" run would have.
        self.assertEqual(er["status"], "executed")
        self.assertNotEqual(er["status"], "skipped_defer")
        self.assertGreaterEqual(len(er["runs"]), 1)
        self.assertTrue(er["runs"][0]["converged"])
        self.assertIn("qoi_value", er["runs"][0])
        self.assertGreaterEqual(spy["calls"], 1, "the solver adapter must actually be invoked")

    def test_dispatch_seam_genuinely_wired_to_cobrapy(self):
        # The spy substitutes only the docker call; prove the REAL seam routes
        # cobrapy to its real adapter (not read from config — resolved live).
        self.assertIs(
            substrate_dispatch.adapter_for("cobrapy"),
            substrate_dispatch._cobrapy_adapter,
        )


class TestNoLLMInControllerAndCompare(CampaignBase):
    """T3: zero call_stage_model in the controller / compare path."""

    def test_no_call_stage_model_in_controller_source(self):
        src = (ROOT / "stages" / "campaign_controller.py").read_text()
        self.assertNotIn("call_stage_model", src)

    def test_compare_is_pure_numeric(self):
        self.assertTrue(cc.compare_prediction(1.0, 1.0)["matched"])
        self.assertTrue(cc.compare_prediction(1.0, 1.04)["matched"])  # within 5%
        self.assertFalse(cc.compare_prediction(1.0, 2.0)["matched"])
        self.assertEqual(cc.compare_prediction(None, 1.0)["reason"], "no_prediction")
        self.assertEqual(cc.compare_prediction(1.0, None)["reason"], "no_qoi_value")


class TestBounded(CampaignBase):
    """T4: a campaign that never converges halts at the budget."""

    def test_never_converges_halts_at_budget(self):
        run_id = "camptest-bounded"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy")

        def spy_adapter(sid, params, case_name, roles, qreq):
            return _spy_cobrapy_summary()

        # predicted None => compare never matches => runs to the budget.
        cc.STRATEGIES["_t4_noconv"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_t4_noconv", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: spy_adapter):
                out = cc.run_campaign(b, strategy_key="_t4_noconv")

        summary = _read_summary(run_id)
        self.assertEqual(summary["iterations_used"], cc.MAX_CAMPAIGN_ITERS)
        self.assertEqual(summary["termination_reason"], "budget_exhausted")
        self.assertEqual(len(out.payload["execution_results"]["runs"]), cc.MAX_CAMPAIGN_ITERS)


class TestFailLoudOnDegradation(CampaignBase):
    """T5: the planner's silent uniform-coverage fallback surfaces LOUDLY."""

    def test_fallback_raises_campaign_degraded(self):
        run_id = "camptest-fallback"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy")

        def fallback_strategy(spec, prior_results, budget_remaining):
            # the REAL planner fallback object (reasoning starts with "fallback:")
            return ep._uniform_coverage_fallback(spec, budget_remaining)

        cc.STRATEGIES["_t5_fallback"] = fallback_strategy
        self.addCleanup(cc.STRATEGIES.pop, "_t5_fallback", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(
                cc, "adapter_for", lambda sid: (lambda *a: _spy_cobrapy_summary())
            ):
                with self.assertRaises(cc.CampaignDegraded):
                    cc.run_campaign(b, strategy_key="_t5_fallback")

    def test_real_fallback_reasoning_matches_guard(self):
        # bind the guard to the REAL fallback signal, not a hand-typed string.
        fb = ep._uniform_coverage_fallback(
            {"parameters": [{"name": "reynolds_number", "role": "sweep", "min": 100, "max": 400}]}, 2
        )
        self.assertTrue(fb["reasoning"].startswith("fallback:"))


class TestStrategySocket(CampaignBase):
    """P4/D4: STRATEGIES mirrors the ANALYTIC_ESTIMATORS registry idiom."""

    def test_default_strategy_registered(self):
        self.assertIs(cc.STRATEGIES[cc.DEFAULT_STRATEGY], ep.propose_next_points)

    def test_second_strategy_is_one_line_registration(self):
        run_id = "camptest-socket"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy")
        used = {"key": None}

        def second_planner(spec, prior_results, budget_remaining):
            used["key"] = "second_planner"
            return {"points": [{"min_growth": 0.1}], "reasoning": "second", "predicted_qoi_per_point": [None]}

        # ONE line to register a competing planner; no judge, no tournament.
        cc.STRATEGIES["second_planner"] = second_planner
        self.addCleanup(cc.STRATEGIES.pop, "second_planner", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(
                cc, "adapter_for", lambda sid: (lambda *a: _spy_cobrapy_summary())
            ):
                cc.run_campaign(b, strategy_key="second_planner")
        self.assertEqual(used["key"], "second_planner")

    def test_unknown_strategy_raises(self):
        self._cleanup("camptest-badkey")
        b = _trust_baton("camptest-badkey", "cobrapy")
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with self.assertRaises(KeyError):
                cc.run_campaign(b, strategy_key="does_not_exist")


class TestParityAndSchema(CampaignBase):
    def test_defer_campaign_skips(self):
        run_id = "camptest-defer"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy", label="defer")
        out = cc.run_campaign(b)
        self.assertEqual(out.payload["execution_results"], {"status": "skipped_defer"})

    def test_records_outside_baton_and_locked_schema_holds(self):
        run_id = "camptest-d2"
        self._cleanup(run_id)
        b = _trust_baton(run_id, "cobrapy")
        cc.STRATEGIES["_d2_fixed"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_d2_fixed", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(
                cc, "adapter_for", lambda sid: (lambda *a: _spy_cobrapy_summary())
            ):
                out = cc.run_campaign(b, strategy_key="_d2_fixed")

        # D2: campaign detail lives OUTSIDE the baton.
        self.assertTrue((RUNS / run_id / "campaign" / "summary.json").exists())
        self.assertTrue((RUNS / run_id / "campaign" / "iteration_1.json").exists())
        # execution_results carries ONLY the locked shape — no campaign keys.
        er = out.payload["execution_results"]
        self.assertLessEqual(set(er.keys()), {"status", "runs", "flag", "reason"})
        self.assertEqual(er["status"], "executed")
        # every run entry stays within the LOCKED run-entry key set (schemas.py
        # RUN_ENTRY_KEYS) — the campaign did NOT widen the run-entry schema.
        for entry in er["runs"]:
            self.assertLessEqual(set(entry.keys()), set(schemas.RUN_ENTRY_KEYS))
        # exactly ONE history note (a single stage-4-equivalent result).
        s4_notes = [h for h in out.history if h["stage"] == "stage4_simulation"]
        self.assertEqual(len(s4_notes), 1)


def _sweep_baton(run_id: str, sc: dict | None = None) -> Baton:
    """A trust baton whose spec declares a reynolds_number sweep (for the
    adaptive planner) and, optionally, a success_criterion (feature #2)."""
    b = _trust_baton(run_id, "cobrapy")
    spec = b.payload["experiment_spec"]
    spec["parameters"] = [
        {"name": "reynolds_number", "role": "sweep", "min": 100, "max": 400}
    ]
    spec["mini_experiment"] = {"runs": [{"reynolds_number": 100}]}
    if sc is not None:
        spec["success_criterion"] = sc
    return b


def _linear_spy(sid, params, case_name, roles, qreq):
    """A deterministic solver spy: qoi is a LINEAR function of the swept param,
    so the adaptive planner's linear-interp prediction holds at the midpoint."""
    re = params.get("reynolds_number", 0)
    return {"valid": True, "qoi": 2.0 + 0.01 * re, "diagnostics": {}, "runtime_s": 0.1}


def _const_spy(value):
    def spy(sid, params, case_name, roles, qreq):
        return {"valid": True, "qoi": value, "diagnostics": {}, "runtime_s": 0.1}
    return spy


class TestAdaptivePlanner(CampaignBase):
    """Feature #1: the deterministic active-learning planner."""

    def test_registered_in_socket(self):
        self.assertIs(cc.STRATEGIES["adaptive_refine"], ep.propose_adaptive_points)

    def test_bootstrap_endpoints(self):
        spec = {"parameters": [{"name": "x", "role": "sweep", "min": 1.0, "max": 5.0}]}
        p0 = ep.propose_adaptive_points(spec, [], 4)
        self.assertEqual(p0["points"], [{"x": 1.0}])
        self.assertFalse(p0["reasoning"].startswith("fallback:"))
        p1 = ep.propose_adaptive_points(spec, [{"point": {"x": 1.0}, "qoi_value": 3.0}], 3)
        self.assertEqual(p1["points"], [{"x": 5.0}])  # the far endpoint

    def test_refines_widest_interval_with_interp_prediction(self):
        spec = {"parameters": [{"name": "x", "role": "sweep", "min": 0.0, "max": 10.0}]}
        prior = [
            {"point": {"x": 0.0}, "qoi_value": 0.0},
            {"point": {"x": 4.0}, "qoi_value": 1.0},   # small change
            {"point": {"x": 10.0}, "qoi_value": 100.0},  # big change -> widest
        ]
        out = ep.propose_adaptive_points(spec, prior, 2)
        self.assertEqual(out["points"], [{"x": 7.0}])  # midpoint of (4,10)
        self.assertEqual(out["predicted_qoi_per_point"], [50.5])  # (1+100)/2

    def test_no_sweep_or_no_budget_returns_empty(self):
        self.assertEqual(ep.propose_adaptive_points({"parameters": []}, [], 4)["points"], [])
        spec = {"parameters": [{"name": "x", "role": "sweep", "min": 0, "max": 1}]}
        self.assertEqual(ep.propose_adaptive_points(spec, [], 0)["points"], [])

    def test_campaign_converges_on_linear_surrogate(self):
        run_id = "camptest-adaptive"
        self._cleanup(run_id)
        b = _sweep_baton(run_id)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: _linear_spy):
                cc.run_campaign(b, strategy_key="adaptive_refine")
        summary = _read_summary(run_id)
        # endpoints (iter1,2) then midpoint (iter3) whose linear-interp
        # prediction matches the linear truth -> resolved -> stop.
        self.assertEqual(summary["termination_reason"], "prediction_within_tolerance")
        self.assertEqual(summary["iterations_used"], 3)


class TestExpectationConsumer(CampaignBase):
    """Feature #2: consuming the spec's two-sided expectation."""

    def test_check_success_criterion_semantics(self):
        sc = {"statement": "s", "threshold": 0.0, "direction": "above",
              "expected_value": 5.0, "tolerance": 0.5}
        within = cc.check_success_criterion(sc, 5.2)
        self.assertTrue(within["within_expectation"])
        self.assertTrue(within["meets_threshold"])
        self.assertFalse(within["anomaly"])
        # passes the headline threshold but 3x outside the expectation band:
        anomaly = cc.check_success_criterion(sc, 15.0)
        self.assertTrue(anomaly["meets_threshold"])
        self.assertFalse(anomaly["within_expectation"])
        self.assertTrue(anomaly["anomaly"])
        # single-sided only (no expected_value/tolerance): two_sided False
        one_sided = cc.check_success_criterion(
            {"statement": "s", "threshold": 0.0, "direction": "above"}, 5.0
        )
        self.assertFalse(one_sided["two_sided"])
        self.assertIsNone(one_sided["within_expectation"])
        # non-numeric observation: honest None
        self.assertIsNone(cc.check_success_criterion(sc, None)["meets_threshold"])

    def test_campaign_stops_on_expectation_confirmed(self):
        run_id = "camptest-expect"
        self._cleanup(run_id)
        sc = {"statement": "s", "threshold": 0.0, "direction": "above",
              "expected_value": 5.0, "tolerance": 0.5}
        b = _sweep_baton(run_id, sc=sc)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: _const_spy(5.0)):
                cc.run_campaign(b, strategy_key="adaptive_refine")
        summary = _read_summary(run_id)
        self.assertEqual(summary["termination_reason"], "expectation_confirmed")
        self.assertEqual(summary["iterations_used"], 1)  # confirmed on the first point
        self.assertEqual(summary["expectation_summary"]["within_expectation"], 1)

    def test_campaign_flags_anomaly_and_keeps_going(self):
        run_id = "camptest-anomaly"
        self._cleanup(run_id)
        # passes threshold (above 0) but far outside the tight expectation band
        sc = {"statement": "s", "threshold": 0.0, "direction": "above",
              "expected_value": 1.0, "tolerance": 0.1}
        b = _sweep_baton(run_id, sc=sc)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: _const_spy(5.0)):
                out = cc.run_campaign(b, strategy_key="adaptive_refine")
        summary = _read_summary(run_id)
        self.assertGreaterEqual(summary["expectation_summary"]["anomalies"], 1)
        self.assertNotEqual(summary["termination_reason"], "expectation_confirmed")
        self.assertEqual(out.payload["execution_results"]["status"], "executed")


class TestSurviveBadPoint(CampaignBase):
    """Feature #4: a single synthesis failure no longer halts the campaign."""

    def test_partial_failure_continues_and_executes(self):
        run_id = "camptest-partial"
        self._cleanup(run_id)
        calls = {"n": 0}

        def flaky_spy(sid, params, case_name, roles, qreq):
            calls["n"] += 1
            if calls["n"] == 1:
                raise CaseSynthesisError("synthetic bad point")
            return _spy_cobrapy_summary()

        cc.STRATEGIES["_f4_fixed"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_f4_fixed", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: flaky_spy):
                out = cc.run_campaign(b := _trust_baton(run_id, "cobrapy"), strategy_key="_f4_fixed")
        er = out.payload["execution_results"]
        self.assertEqual(er["status"], "executed")  # NOT halted by the one failure
        self.assertGreaterEqual(len(er["runs"]), 1)  # real runs survived
        summary = _read_summary(run_id)
        self.assertGreaterEqual(summary["synthesis_failures"], 1)

    def test_all_points_fail_is_honest_halt(self):
        run_id = "camptest-allfail"
        self._cleanup(run_id)

        def always_fail(sid, params, case_name, roles, qreq):
            raise CaseSynthesisError("always bad")

        cc.STRATEGIES["_f4_allfail"] = _fixed_strategy([{"min_growth": 0.1}])
        self.addCleanup(cc.STRATEGIES.pop, "_f4_allfail", None)
        with unittest.mock.patch.object(cc, "select_substrate", lambda spec: "cobrapy"):
            with unittest.mock.patch.object(cc, "adapter_for", lambda sid: always_fail):
                out = cc.run_campaign(_trust_baton(run_id, "cobrapy"), strategy_key="_f4_allfail")
        er = out.payload["execution_results"]
        self.assertEqual(er["status"], "halted_synthesis")
        self.assertEqual(er["runs"], [])
        self.assertIn("reason", er)
        summary = _read_summary(run_id)
        self.assertEqual(summary["iterations_used"], cc.MAX_CAMPAIGN_ITERS)  # bounded
        self.assertEqual(summary["termination_reason"], "all_points_failed_synthesis")


def _read_summary(run_id: str) -> dict:
    import json

    return json.loads((RUNS / run_id / "campaign" / "summary.json").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
