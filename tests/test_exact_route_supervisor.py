"""test_exact_route_supervisor.py — the exact-tool path wired into the supervisor.

Phase 3, R-ROUTE-4 (docs/memo_phase3_routing.md); default-on since M1
(docs/memo_m1_exact_route_default.md). Proves the contained branch at gate 1:
when gate 1 chose an EXACT instrument (and EXACT_ROUTE is not 0), the experimenter
loop REPLACES static stages 2-5 and the run ends there; an approximate instrument
(or EXACT_ROUTE=0) keeps the static pipeline + fidelity gate, unchanged.

Call-free: zero model calls, zero docker. The gate-1 chooser is patched (as in
test_loop_controller) and the experimenter strategy is a SCRIPTED code-only
composition — the live agent's outing is the owner's Terminal job. record_run_outcome
is patched (captured, never journaled). Everything else — the real gate-1 flow,
the real registry class lookup, the real branch — runs live.

Run directly: venv/bin/python3 tests/test_exact_route_supervisor.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baton import Baton  # noqa: E402
from supervisor import Logger, run_relay  # noqa: E402
from test_loop_controller import StubRelay  # noqa: E402


class _FakeFreeInvestigator:
    """Stands in for the free experimenter (brick 4a): records the goal it was
    given and returns a verified finding. No substrate cage, no composition."""

    def __init__(self):
        self.calls = 0
        self.goal = None

    def __call__(self, goal, run_id=None):
        self.calls += 1
        self.goal = goal
        return {"goal": goal, "summary": "s",
                "findings": [{"label": "a", "value": 1, "verified": True,
                              "reproduce": "f.py"}],
                "publishable": True}


class ExactRouteCase(unittest.TestCase):
    def drive(self, *, substrate_id: str, flag_on: bool, free_investigate=None):
        stubs = StubRelay(["exit"])  # decisions unused when the route ends early
        self._tmp = tempfile.TemporaryDirectory()
        run_dir = Path(self._tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(run_id="exact-route-test",
                      created_at="2026-07-21T00:00:00+00:00", mode="auto",
                      payload={"domain": "stub domain"})
        outcomes: list[str] = []
        # Default-on since M1: set the env explicitly either way so an ambient
        # EXACT_ROUTE can never leak in — "1" arms the route, "0" is the
        # kill-switch that forces the legacy static path.
        env = {"EXACT_ROUTE": "1"} if flag_on else {"EXACT_ROUTE": "0"}
        with patch.dict("os.environ", env, clear=False), patch(
            "supervisor.record_run_outcome",
            side_effect=lambda b, how_far, retry=0: outcomes.append(how_far),
        ), patch(
            "supervisor.gate1_chooser.choose_hypothesis",
            side_effect=lambda run_id, hyps, run_dir: {
                "chosen_id": hyps[0]["id"], "substrate_id": substrate_id,
                "fallback": False},
        ):
            run_relay(logger, baton, run_dir, "auto",
                      stages=stubs.stages(), free_investigate=free_investigate)
        self.baton = baton
        return stubs, run_dir, outcomes, (run_dir / "log.txt").read_text()

    def tearDown(self):
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()


class TestExactInstrumentTakesTheFreeExperimenter(ExactRouteCase):
    def test_the_route_fires_and_ends_the_run_after_gate_1(self):
        free = _FakeFreeInvestigator()
        stubs, _run_dir, outcomes, log = self.drive(
            substrate_id="rdkit", flag_on=True, free_investigate=free)

        # the exact instrument routed to the FREE experimenter (brick 4a)
        self.assertIn("FREE EXPERIMENTER", log)
        self.assertIn("publishable=True", log)
        # the free experimenter drove, with the gate-1 hypothesis as its goal
        self.assertEqual(free.calls, 1)
        self.assertIsNotNone(free.goal)
        # stages 2-6 were REPLACED — none of the static stages ran
        self.assertEqual(stubs.stage2_inputs, [])
        self.assertEqual(stubs.stage6_calls, 0)
        # the run ended with a free-investigation outcome
        self.assertEqual(len(outcomes), 1)
        self.assertIn("free investigation", outcomes[0])
        self.assertIn("publishable", outcomes[0])
        # history stops at stage 1 — no stage-2..6 entries
        stages_run = [h["stage"] for h in self.baton.history]
        self.assertEqual(stages_run, ["stage1_ideation"])


class TestApproximateInstrumentKeepsTheStaticPipeline(ExactRouteCase):
    def test_approximate_instrument_runs_the_full_static_pipeline(self):
        """Cavity is approximate — it must NOT take the free/experimenter path;
        it keeps stages 2-5 + the fidelity gate (the free experimenter is never
        called)."""
        free = _FakeFreeInvestigator()
        stubs, _run_dir, outcomes, log = self.drive(
            substrate_id="cavity_2d_cfd", flag_on=True, free_investigate=free)
        self.assertNotIn("FREE EXPERIMENTER", log)
        self.assertEqual(free.calls, 0)
        # the static pipeline ran end to end (stage 2 authored, stage 6 acked)
        self.assertEqual(len(stubs.stage2_inputs), 1)
        self.assertEqual(stubs.stage6_calls, 1)


class TestBranchPredicatesGateTheRoute(unittest.TestCase):
    """The branch is `exact_route_active() and routed_instrument_is_exact(baton)`.
    Unit-testing both halves proves the gating directly, without depending on a
    stub's ability to author a valid spec for every instrument."""

    def _baton(self, **payload):
        return Baton(run_id="pred", created_at="2026-07-21T00:00:00+00:00",
                     mode="auto", payload=payload)

    def test_the_route_is_on_by_default_with_a_kill_switch(self):
        # M1 (2026-07-21): default-on. Unset and "1" both arm the route; only
        # EXACT_ROUTE=0 forces the legacy static path.
        import os
        from supervisor import exact_route_active
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("EXACT_ROUTE", None)
            self.assertTrue(exact_route_active())
        with patch.dict("os.environ", {"EXACT_ROUTE": "1"}):
            self.assertTrue(exact_route_active())
        with patch.dict("os.environ", {"EXACT_ROUTE": "0"}):
            self.assertFalse(exact_route_active())

    def test_only_a_positive_exact_answer_takes_the_route(self):
        from supervisor import routed_instrument_is_exact
        self.assertTrue(routed_instrument_is_exact(self._baton(substrate_id="rdkit")))
        # approximate, missing, and unknown all keep the static path — an
        # ambiguity never skips the fidelity gate
        self.assertFalse(routed_instrument_is_exact(
            self._baton(substrate_id="cavity_2d_cfd")))
        self.assertFalse(routed_instrument_is_exact(self._baton(domain="d")))
        self.assertFalse(routed_instrument_is_exact(
            self._baton(substrate_id="no_such_substrate")))


if __name__ == "__main__":
    unittest.main()
