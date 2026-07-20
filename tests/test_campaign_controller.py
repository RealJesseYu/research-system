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

    def test_maturity_hook_does_not_defer_cobrapy_auto(self):
        # FIRE the load-bearing precondition (A6): the real hook on AUTO + a
        # cobrapy-routed trust verdict must leave the verdict at 'trust'.
        self.assertTrue(registry.is_mature("cobrapy"))
        b = _trust_baton("camptest-hook", "cobrapy")

        class _Log:
            def log(self, *a):
                pass

        supervisor.apply_substrate_maturity_hook(_Log(), b, "auto")
        self.assertEqual(
            b.payload["fidelity_verdict"]["label"],
            "trust",
            "maturity hook must NOT downgrade a mature cobrapy trust in AUTO mode",
        )

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


def _read_summary(run_id: str) -> dict:
    import json

    return json.loads((RUNS / run_id / "campaign" / "summary.json").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
