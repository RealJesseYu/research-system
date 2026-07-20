"""
test_stage_crash.py — the supervisor's crash handling. Zero model calls.

Two layers:
  * run_single_stage (Step 16, JC1b) logs a stage crash and re-raises it as
    StageCrashed — the terminal memo/record/exit no longer lives here.
  * run_relay (wide crash-recovery fix, 2026-07-19) catches StageCrashed and,
    while its crash budget lasts, journals a dead-end + loops back to ideation;
    on exhaustion it takes the honest terminal halt (memo + crashed run_record
    + exit 1). This is the "run into a problem -> go back, remember it, avoid
    it next round" path.

record_run_outcome and journal_append are patched out so no test appends to the
real journal.

Run directly: venv/bin/python3 tests/test_stage_crash.py
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

from baton import Baton
from supervisor import (
    MAX_CRASH_LOOPBACKS,
    Logger,
    StageCrashed,
    run_relay,
    run_single_stage,
)
from test_stage2_spec import CHOSEN_ID, make_valid_spec

HYPOTHESES = [
    {"id": CHOSEN_ID, "statement": "stub hypothesis one", "rationale": "stub rationale one"},
    {"id": "h9", "statement": "stub hypothesis two", "rationale": "stub rationale two"},
]


def _make_baton() -> Baton:
    return Baton(
        run_id="test-crash",
        created_at="2026-07-06T00:00:00+00:00",
        mode="auto",
        payload={"domain": "canned"},
    )


class TestRunSingleStage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self._tmp.name) / "log.txt"
        self.logger = Logger(self.log_path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_normal_stage_passes_through_unchanged(self):
        baton = _make_baton()

        def healthy_stage(b):
            b.add_history("healthy_stage", "did the thing")
            return b

        with patch("supervisor.record_run_outcome") as recorded:
            out = run_single_stage(self.logger, baton, "healthy_stage", healthy_stage)
            recorded.assert_not_called()
        self.assertIs(out, baton)
        self.assertEqual(out.history[-1]["note"], "did the thing")
        # Catch is silent on success: nothing was ever written to the log.
        self.assertFalse(self.log_path.exists())

    def test_raising_stage_logs_and_raises_stagecrashed(self):
        # WIDE FIX: run_single_stage no longer exits or records — it logs the
        # crash and re-raises StageCrashed for run_relay to handle.
        baton = _make_baton()

        def exploding_stage(b):
            raise RuntimeError("boom: first line\nsecond line never logged")

        with patch("supervisor.record_run_outcome") as recorded:
            with self.assertRaises(StageCrashed) as ctx:
                run_single_stage(
                    self.logger, baton, "exploding_stage", exploding_stage
                )
            self.assertEqual(ctx.exception.stage_name, "exploding_stage")
            self.assertIsInstance(ctx.exception.original, RuntimeError)
            recorded.assert_not_called()  # terminal handling moved to run_relay
        log = self.log_path.read_text()
        self.assertIn(
            "STAGE-CRASH stage=exploding_stage exception=RuntimeError: boom: first line",
            log,
        )
        self.assertIn("STAGE-CRASH | ", log)  # traceback tail present
        self.assertNotIn("second line never logged", log.split("STAGE-CRASH | ")[0])


class CrashAtStage3Relay:
    """Schema-valid stubs through gate 2, then stage 3 raises the first
    `crash_times` times (the real min_growth unroutable-spec shape) and defers
    thereafter. Reuses make_valid_spec so the post-stage boundaries and gates
    pass exactly as in a real auto run."""

    def __init__(self, crash_times: int):
        self.crash_times = crash_times
        self.stage1_calls = 0
        self.stage3_calls = 0
        self.reached_stage6 = 0

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
        baton.payload = {
            "domain": baton.payload["domain"],
            "hypotheses": copy.deepcopy(HYPOTHESES),
            "hypotheses_ranked": True,
        }
        baton.add_history("stage1_ideation", "stub ranked")
        return baton

    def stage2(self, baton):
        baton.payload = {
            "domain": baton.payload["domain"],
            "chosen_hypothesis": baton.payload["chosen_hypothesis"],
            "substrate_id": baton.payload["substrate_id"],
            "experiment_spec": make_valid_spec(),
        }
        baton.add_history("stage2_experiment_design", "stub spec")
        return baton

    def stage3(self, baton):
        self.stage3_calls += 1
        if self.stage3_calls <= self.crash_times:
            raise LookupError(
                "no routable substrate can serve this spec: declared "
                "parameters ['min_growth']"
            )
        payload = dict(baton.payload)
        payload["fidelity_verdict"] = {
            "label": "defer",
            "rationale": "stub defer",
            "right_instrument": "none — route to human/real experiment",
        }
        baton.payload = payload
        baton.add_history("stage3_fidelity_gate", "stub defer")
        return baton

    def stage4(self, baton):
        payload = dict(baton.payload)
        payload["execution_results"] = {"status": "skipped_defer"}
        baton.payload = payload
        baton.add_history("stage4_simulation", "stub skipped")
        return baton

    def stage5(self, baton):
        payload = dict(baton.payload)
        payload["thought"] = {
            "assessment": "a",
            "surprise_triage": "none",
            "iterate_decision": "exit",
            "justification": "j",
            "learned_summary": "s",
        }
        payload["iterate_decision"] = "exit"
        baton.payload = payload
        baton.add_history("stage5_thought_layer", "stub thought exit")
        return baton

    def stage6(self, baton):
        self.reached_stage6 += 1
        baton.add_history("stage6_paper", "stub ack")
        return baton


class CrashAtStage1Relay:
    """Stage 1 raises the first `crash_times` times BEFORE any hypothesis
    exists — the real OpenAlex-400 shape from run 20260719T225522Z. A crash
    here is pre-gate-1, so no dead-end should be journaled."""

    def __init__(self, crash_times: int):
        self.crash_times = crash_times
        self.stage1_calls = 0
        self.reached_stage6 = 0

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
        if self.stage1_calls <= self.crash_times:
            raise RuntimeError(
                "OpenAlex request failed with HTTP 400 and was not retried further"
            )
        baton.payload = {
            "domain": baton.payload["domain"],
            "hypotheses": copy.deepcopy(HYPOTHESES),
            "hypotheses_ranked": True,
        }
        baton.add_history("stage1_ideation", "stub ranked")
        return baton

    # never reached while stage 1 keeps crashing; present for interface parity
    def stage2(self, baton):
        return baton

    def stage3(self, baton):
        return baton

    def stage4(self, baton):
        return baton

    def stage5(self, baton):
        return baton

    def stage6(self, baton):
        self.reached_stage6 += 1
        return baton


class RelayCrashRecoveryCase(unittest.TestCase):
    def _drive(
        self,
        crash_times,
        mode="auto",
        relay_cls=CrashAtStage3Relay,
        crash_recovery_env=None,
    ):
        # crash_recovery_env: value forced into the CRASH_RECOVERY env for this
        # run ("1" to opt in), or None to force the var UNSET (default-off).
        stubs = relay_cls(crash_times)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(
            run_id="crash-relay-test",
            created_at="2026-07-19T00:00:00+00:00",
            mode=mode,
            payload={"domain": "canned"},
        )
        outcomes, journaled = [], []
        exit_code = "no-exit"
        # patch.dict snapshots and restores os.environ; mutating inside the body
        # guarantees the var is genuinely UNSET for the default-off case (a bare
        # override cannot REMOVE a pre-existing key), then restored on exit.
        with patch.dict(os.environ, {}, clear=False), patch(
            "supervisor.record_run_outcome",
            side_effect=lambda b, how_far, retry=0: outcomes.append(how_far),
        ), patch(
            "supervisor.journal_append",
            side_effect=lambda entry: journaled.append(entry),
        ), patch(
            "supervisor.gate1_chooser.choose_hypothesis",
            side_effect=lambda run_id, hyps, rd: {
                "chosen_id": hyps[0]["id"],
                "substrate_id": "cavity_2d_cfd",
                "fallback": False,
            },
        ):
            if crash_recovery_env is None:
                os.environ.pop("CRASH_RECOVERY", None)
            else:
                os.environ["CRASH_RECOVERY"] = crash_recovery_env
            try:
                run_relay(logger, baton, run_dir, mode, stages=stubs.stages())
            except SystemExit as exc:
                exit_code = exc.code
        log = (run_dir / "log.txt").read_text()
        dead_ends = [e for e in journaled if e.get("kind") == "learned_summary"]
        return stubs, run_dir, outcomes, dead_ends, log, exit_code


class TestCrashRecoveryLoopsBack(RelayCrashRecoveryCase):
    def test_transient_crash_recovers_and_reaches_a_paper(self):
        # Stage 3 crashes twice, then succeeds: the run must loop back to
        # ideation twice, journal a dead-end each time, and still reach stage 6.
        # RE-HOMED: crash recovery is now auto+env-gated, so this opted-in path
        # sets CRASH_RECOVERY=1 (B4c — the feature still works when opted in).
        stubs, run_dir, outcomes, dead_ends, log, exit_code = self._drive(
            crash_times=2, crash_recovery_env="1"
        )
        self.assertEqual(exit_code, "no-exit")  # no hard exit
        self.assertEqual(stubs.stage1_calls, 3)  # initial + 2 recoveries
        self.assertEqual(stubs.reached_stage6, 1)  # produced a paper
        self.assertEqual(len(dead_ends), 2)
        for entry in dead_ends:
            # WORDING CORRECTED 2026-07-20: the entry no longer asserts the
            # approach "could not be modeled by any available instrument" —
            # the supervisor cannot know that, and on 20260719T231117Z the
            # claim was false twice over (a missing QoI key, not an
            # instrument limit). It now states the crash and marks the cause
            # unattributed, so Reflection cannot discard good science on it.
            self.assertIn("CRASH (recovery loop-back)", entry["text"])
            self.assertIn("CAUSE NOT ATTRIBUTED", entry["text"])
            self.assertNotIn("could not be modeled", entry["text"])
            self.assertIn("stage3_fidelity_gate", entry["text"])
        self.assertIn(
            "CRASH-RECOVERY: crash at stage3_fidelity_gate — looping back "
            "to ideation (recovery 1 of 2)",
            log,
        )
        self.assertIn("recovery 2 of 2", log)
        self.assertEqual(outcomes[-1], "completed")


class TestCrashRecoveryBudgetExhausts(RelayCrashRecoveryCase):
    def test_persistent_crash_halts_honestly_after_budget(self):
        # Stage 3 always crashes: recovery fires MAX_CRASH_LOOPBACKS times, then
        # the honest terminal halt (memo + crashed run_record + exit 1).
        # RE-HOMED: opted-in path (B4d — budget still bounds it when enabled).
        stubs, run_dir, outcomes, dead_ends, log, exit_code = self._drive(
            crash_times=99, crash_recovery_env="1"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stubs.stage1_calls, 1 + MAX_CRASH_LOOPBACKS)
        self.assertEqual(stubs.reached_stage6, 0)
        self.assertEqual(len(dead_ends), MAX_CRASH_LOOPBACKS)
        self.assertIn(f"CRASH-RECOVERY: budget spent ({MAX_CRASH_LOOPBACKS})", log)
        self.assertIn("CRASHED at stage stage3_fidelity_gate", log)
        self.assertTrue(outcomes[-1].startswith("crashed at stage3_fidelity_gate: LookupError:"))
        self.assertTrue((run_dir / "failure_memo.txt").is_file())


class TestPreGate1CrashJournalsNoDeadEnd(RelayCrashRecoveryCase):
    def test_stage1_crash_recovers_without_polluting_memory(self):
        # The exact run 20260719T225522Z shape: stage 1 crashes (OpenAlex 400)
        # before any hypothesis exists. It must still loop back and honestly
        # halt after the budget — but journal ZERO dead-ends, so the
        # learned_summary memory baseline (kill-rate md5 pin) is untouched.
        # RE-HOMED: opted-in path — this exercises the gated loopback's
        # no-dead-end pre-gate-1 behavior, so it sets CRASH_RECOVERY=1.
        stubs, run_dir, outcomes, dead_ends, log, exit_code = self._drive(
            crash_times=99, relay_cls=CrashAtStage1Relay, crash_recovery_env="1"
        )
        self.assertEqual(exit_code, 1)
        self.assertEqual(stubs.stage1_calls, 1 + MAX_CRASH_LOOPBACKS)  # looped back
        self.assertEqual(dead_ends, [])  # no false lesson written
        self.assertIn("no chosen_hypothesis", log)
        self.assertIn(f"CRASH-RECOVERY: budget spent ({MAX_CRASH_LOOPBACKS})", log)


class TestCrashRecoveryGateLoudPath(RelayCrashRecoveryCase):
    """The gate's DEFAULT: a crash halts loud on the FIRST occurrence, with no
    loopback, whenever crash recovery is not explicitly opted into (human mode,
    or auto with the env unset). Escapes proven by FIRING, not by reading."""

    def test_human_mode_halts_loud_on_first_crash(self):
        # B4a: mode="human" — env is irrelevant (auto-only), so even with the
        # env opted in a persistent crash must exit 1 on the FIRST crash with NO
        # loopback. Crash at stage 1 (pre-gate-1) so no human gate prompt is
        # reached — the crash gate is what we are exercising, not the gates.
        stubs, run_dir, outcomes, dead_ends, log, exit_code = self._drive(
            crash_times=99,
            mode="human",
            relay_cls=CrashAtStage1Relay,
            crash_recovery_env="1",
        )
        self.assertEqual(exit_code, 1)  # exited
        self.assertEqual(stubs.stage1_calls, 1)  # ran once, never looped back
        self.assertEqual(stubs.reached_stage6, 0)
        self.assertEqual(dead_ends, [])  # loopback never journaled a dead-end
        self.assertNotIn("looping back", log)  # no loopback line
        self.assertNotIn("recovery 1 of", log)
        self.assertIn("CRASH-RECOVERY: disabled", log)  # loud-halt reason
        self.assertIn("CRASHED at stage stage1_ideation", log)
        self.assertTrue((run_dir / "failure_memo.txt").is_file())

    def test_auto_mode_env_unset_halts_loud_on_first_crash(self):
        # B4b: mode="auto", env UNSET — default-off proven. First crash exits 1,
        # no loopback.
        stubs, run_dir, outcomes, dead_ends, log, exit_code = self._drive(
            crash_times=99, mode="auto", crash_recovery_env=None
        )
        self.assertEqual(exit_code, 1)  # exited
        self.assertEqual(stubs.stage1_calls, 1)  # ran once, never looped back
        self.assertEqual(stubs.reached_stage6, 0)
        self.assertEqual(dead_ends, [])
        self.assertNotIn("looping back", log)
        self.assertIn("CRASH-RECOVERY: disabled", log)
        self.assertIn("CRASHED at stage stage3_fidelity_gate", log)
        self.assertTrue((run_dir / "failure_memo.txt").is_file())


if __name__ == "__main__":
    unittest.main()
