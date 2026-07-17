"""
test_retry_total_defer.py — retry-on-total-defer control (19-lite/retry build).

ZERO model calls: STUB stages produce a DEFER verdict + skipped_defer execution
(a total defer), the gate-1 chooser is mocked, record_run_outcome is captured
(never journaled). Proves:
  - the retry fires ONLY on flag + auto mode + total defer;
  - the hard cap of 1 retry per run;
  - a failure memo is written;
  - FEASIBILITY_NUDGE is forced on for the retried Stage 1 and restored after;
  - the loop-bound counter is untouched by the retry (an explicit test);
  - human mode ignores the flag;
  - flag-off control flow is the pre-build path (byte-identical branches).

Run directly: venv/bin/python3 tests/test_retry_total_defer.py
"""

from __future__ import annotations

import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import supervisor
from baton import Baton
from supervisor import Logger, run_relay
from test_stage2_spec import CHOSEN_ID, make_valid_spec

DOMAIN = "stub retry domain"
HYPOTHESES = [
    {"id": CHOSEN_ID, "statement": "stub hypothesis one", "rationale": "stub rationale one"},
    {"id": "h9", "statement": "stub hypothesis two", "rationale": "stub rationale two"},
]
DEFER_VERDICT = {
    "label": "defer",
    "rationale": "stub defer rationale",
    "right_instrument": "none — route to human/real experiment",
}
SKIPPED_EXECUTION = {"status": "skipped_defer"}


def make_thought(decision: str) -> dict:
    return {
        "assessment": "stub assessment",
        "surprise_triage": "none",
        "iterate_decision": decision,
        "justification": "stub justification",
        "learned_summary": "stub learned summary",
    }


class DeferStubRelay:
    """Stub stages that ALWAYS defer (total defer): records the nudge env seen
    by each Stage-1 execution and the decision queue drives gate 5."""

    def __init__(self, decisions):
        self.decisions = list(decisions)
        self.stage1_nudge_env = []  # FEASIBILITY_NUDGE value seen per Stage-1 run
        self.stage2_nudge_env = []  # ...and per Stage-2 run (AFTER the restore point)
        self.stage1_calls = 0
        self.stage6_calls = 0

    def stages(self):
        return [
            ("stage1_ideation", self.stage1),
            ("stage2_experiment_design", self.stage2),
            ("stage3_fidelity_gate", self.stage3),
            ("stage4_simulation", self.stage4),
            ("stage5_thought_layer", self.stage5),
            ("stage6_paper", self.stage6),
        ]

    def stage1(self, baton):
        self.stage1_calls += 1
        self.stage1_nudge_env.append(os.environ.get("FEASIBILITY_NUDGE"))
        baton.payload = {
            "domain": baton.payload["domain"],
            "hypotheses": copy.deepcopy(HYPOTHESES),
            "hypotheses_ranked": True,
        }
        baton.add_history("stage1_ideation", "stub ranked")
        return baton

    def stage2(self, baton):
        # Stage 2 runs immediately AFTER the retried Stage 1 returns, i.e. after
        # the supervisor's nudge-env restore point — so it observes the restore.
        self.stage2_nudge_env.append(os.environ.get("FEASIBILITY_NUDGE"))
        prior = baton.payload.get("prior_thought")
        baton.payload = {
            "domain": baton.payload["domain"],
            "chosen_hypothesis": baton.payload["chosen_hypothesis"],
            # Truth-edited Step 23.5 (R-23.5-4): the stub mirrors the real
            # stage 2 — the gate-decided instrument travels the payload.
            "substrate_id": baton.payload["substrate_id"],
            "experiment_spec": make_valid_spec(),
        }
        if prior is not None:
            baton.payload["prior_thought"] = prior
        baton.add_history("stage2_experiment_design", "stub spec")
        return baton

    def stage3(self, baton):
        payload = dict(baton.payload)
        payload["fidelity_verdict"] = dict(DEFER_VERDICT)
        baton.payload = payload
        baton.add_history("stage3_fidelity_gate", "stub defer")
        return baton

    def stage4(self, baton):
        payload = dict(baton.payload)
        payload["execution_results"] = dict(SKIPPED_EXECUTION)
        baton.payload = payload
        baton.add_history("stage4_simulation", "stub skipped_defer")
        return baton

    def stage5(self, baton):
        decision = self.decisions.pop(0)
        payload = dict(baton.payload)
        payload["thought"] = make_thought(decision)
        payload["iterate_decision"] = decision
        baton.payload = payload
        baton.add_history("stage5_thought_layer", f"stub thought {decision}")
        return baton

    def stage6(self, baton):
        self.stage6_calls += 1
        baton.add_history("stage6_paper", "stub ack")
        return baton


class RetryCase(unittest.TestCase):
    def drive(self, decisions, mode="auto", env=None, inputs=None):
        stubs = DeferStubRelay(decisions)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        run_dir = Path(self._tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(
            run_id="retry-test",
            created_at="2026-07-14T00:00:00+00:00",
            mode=mode,
            payload={"domain": DOMAIN},
        )
        outcomes = []  # (how_far, retry_on_total_defer)
        env = env or {}
        patches = [
            patch(
                "supervisor.record_run_outcome",
                side_effect=lambda b, how_far, retry=0: outcomes.append((how_far, retry)),
            ),
            patch(
                "supervisor.gate1_chooser.choose_hypothesis",
                # Truth-edited Step 23.5 (R-23.5-1/2): the record carries
                # substrate_id; null would loudly halt the auto gate.
                side_effect=lambda run_id, hyps, run_dir: {
                    "chosen_id": hyps[0]["id"],
                    "substrate_id": "cavity_2d_cfd",
                    "fallback": False,
                },
            ),
            patch.dict(os.environ, env, clear=False),
        ]
        if inputs is not None:
            patches.append(patch("builtins.input", side_effect=inputs))
            patches.append(patch("supervisor.override_append"))
        # Ensure a clean FEASIBILITY_NUDGE baseline unless the test sets it.
        if "FEASIBILITY_NUDGE" not in env:
            os.environ.pop("FEASIBILITY_NUDGE", None)
        ctx = patches
        for p in ctx:
            p.start()
        try:
            run_relay(logger, baton, run_dir, mode, stages=stubs.stages())
        finally:
            for p in reversed(ctx):
                p.stop()
        log = (run_dir / "log.txt").read_text()
        self.baton = baton
        return stubs, run_dir, outcomes, log


class TestRetryFires(RetryCase):
    def test_flag_auto_total_defer_retries_once(self):
        stubs, run_dir, outcomes, log = self.drive(
            ["exit", "exit"], mode="auto", env={"RETRY_ON_TOTAL_DEFER": "1"}
        )
        # Stage 1 ran twice (original + one retried ideation pass).
        self.assertEqual(stubs.stage1_calls, 2)
        self.assertIn("RETRY_ON_TOTAL_DEFER: total defer", log)
        # Terminal: the SECOND total defer exits normally (cap reached).
        self.assertEqual(outcomes[-1], ("completed", 1))
        self.assertEqual(stubs.stage6_calls, 1)
        # Memo written.
        self.assertTrue((run_dir / "failure_memo.txt").is_file())
        self.assertIn("FAILURE-MEMO written", log)

    def test_hard_cap_is_one(self):
        # Three exits available, but only ONE retry may fire.
        stubs, run_dir, outcomes, log = self.drive(
            ["exit", "exit", "exit"], mode="auto", env={"RETRY_ON_TOTAL_DEFER": "1"}
        )
        self.assertEqual(stubs.stage1_calls, 2)  # not 3
        self.assertEqual(log.count("looping back to stage 1"), 1)
        self.assertEqual(outcomes[-1], ("completed", 1))


class TestNudgeEnvForcedThenRestored(RetryCase):
    def test_nudge_on_for_retried_pass_only_and_restored(self):
        stubs, run_dir, outcomes, log = self.drive(
            ["exit", "exit"], mode="auto", env={"RETRY_ON_TOTAL_DEFER": "1"}
        )
        # Pass 1 saw the nudge off/unset; the retried Stage 1 saw it forced on;
        # the retried Stage 2 (which runs after the restore point) saw it back
        # to unset — proving the force did not leak past the retried ideation.
        self.assertEqual(len(stubs.stage1_nudge_env), 2)
        self.assertIn(stubs.stage1_nudge_env[0], (None, "off", ""))
        self.assertEqual(stubs.stage1_nudge_env[1], "on")
        self.assertIsNone(stubs.stage2_nudge_env[1])  # restored (was unset)
        self.assertIn("feasibility nudge env restored", log)

    def test_prior_nudge_value_restored_not_clobbered(self):
        stubs, run_dir, outcomes, log = self.drive(
            ["exit", "exit"],
            mode="auto",
            env={"RETRY_ON_TOTAL_DEFER": "1", "FEASIBILITY_NUDGE": "off"},
        )
        # The retried Stage 1 forced it on; the retried Stage 2 (post-restore)
        # sees the ORIGINAL "off" value, not a clobbered default.
        self.assertEqual(stubs.stage1_nudge_env[1], "on")
        self.assertEqual(stubs.stage2_nudge_env[1], "off")


class TestLoopBoundUntouched(RetryCase):
    def test_retry_does_not_consume_loopback_budget(self):
        # After the retry, the retried lineage still gets a FULL two loop-backs
        # before the loop bound forces exit — proving the retry counter is
        # separate from loopbacks_used (hard rule c).
        stubs, run_dir, outcomes, log = self.drive(
            ["exit", "back_to_design", "back_to_design", "back_to_design"],
            mode="auto",
            env={"RETRY_ON_TOTAL_DEFER": "1"},
        )
        self.assertIn("RETRY_ON_TOTAL_DEFER: total defer", log)
        self.assertIn("LOOP BOUND reached (2)", log)  # the FULL bound was available
        self.assertEqual(outcomes[-1], ("completed_loop_bound_forced_exit", 1))
        self.assertEqual(stubs.stage1_calls, 2)  # retry re-ran stage 1 once


class TestFlagOffAndHumanMode(RetryCase):
    def test_flag_off_no_retry(self):
        stubs, run_dir, outcomes, log = self.drive(["exit"], mode="auto", env={})
        self.assertEqual(stubs.stage1_calls, 1)  # no retried pass
        self.assertNotIn("RETRY_ON_TOTAL_DEFER", log)
        self.assertFalse(list(run_dir.glob("*_pass*.json")))
        self.assertEqual(outcomes[-1], ("completed", 0))
        self.assertEqual(stubs.stage6_calls, 1)

    def test_flag_explicit_zero_no_retry(self):
        stubs, run_dir, outcomes, log = self.drive(
            ["exit"], mode="auto", env={"RETRY_ON_TOTAL_DEFER": "0"}
        )
        self.assertEqual(stubs.stage1_calls, 1)
        self.assertNotIn("RETRY_ON_TOTAL_DEFER", log)

    def test_human_mode_ignores_flag(self):
        # Human mode: flag on, but the retry must not fire. Gate inputs are
        # scripted (gate1 rank 1, gate1 instrument — the R-23.5-3 second
        # prompt, truth-edited Step 23.5 — gate2 y, gate5 exit=accept 'a').
        stubs, run_dir, outcomes, log = self.drive(
            ["exit"],
            mode="human",
            env={"RETRY_ON_TOTAL_DEFER": "1"},
            inputs=["1", "cavity_2d_cfd", "y", "a"],
        )
        self.assertEqual(stubs.stage1_calls, 1)
        self.assertNotIn("RETRY_ON_TOTAL_DEFER", log)
        self.assertEqual(outcomes[-1][0], "completed")


class TestIsTotalDefer(unittest.TestCase):
    def _baton(self, verdict_label, execution):
        return Baton(
            run_id="x",
            created_at="2026-07-14T00:00:00+00:00",
            mode="auto",
            payload={
                "domain": DOMAIN,
                "fidelity_verdict": {"label": verdict_label} if verdict_label else {},
                "execution_results": execution,
            },
        )

    def test_defer_and_skipped_is_total_defer(self):
        self.assertTrue(supervisor.is_total_defer(self._baton("defer", {"status": "skipped_defer"})))

    def test_executed_is_not_total_defer(self):
        b = self._baton("trust", {"status": "executed", "runs": [{"converged": True}]})
        self.assertFalse(supervisor.is_total_defer(b))

    def test_defer_with_executed_runs_is_not_total_defer(self):
        # Defensive: a defer verdict but a non-empty runs list is not "total".
        b = self._baton("defer", {"status": "executed", "runs": [{"converged": True}]})
        self.assertFalse(supervisor.is_total_defer(b))


if __name__ == "__main__":
    unittest.main()
