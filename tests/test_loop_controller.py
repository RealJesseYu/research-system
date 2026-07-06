"""
test_loop_controller.py — deterministic tests of the Step-16 loop controller
(supervisor.run_relay) with STUB stages: zero model calls, zero docker.

The stubs produce payloads that satisfy the locked boundary schemas (the
spec is the canned valid spec from test_stage2_spec, chosen id pinned), so
the relay's real schema enforcement runs live inside every test. Stage 5's
stub reads its iterate decision from a scripted queue — one decision per
stage-5 execution — which is how each test chooses its loop path.

record_run_outcome is patched (captured, not journaled): the real journal
is append-only evidence and tests must not write to it. Everything else —
snapshots, log lines, payload surgery, pass numbering — is verified from
the test's temp run dir, read back from disk.

Includes the Part-2c end-to-end loop test: one full back_to_design loop
(pass 1 non-exit -> re-entry -> pass 2 exit), verifying pass-aware
snapshots, stage 2 twice in history, prior_thought in the pass-2 stage-2
input and payload, and the final run_record.

Run directly: venv/bin/python3 tests/test_loop_controller.py
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from baton import Baton
from supervisor import Logger, run_relay
from test_stage2_spec import CHOSEN_ID, make_valid_spec

DOMAIN = "stub loop-controller domain"

HYPOTHESES = [
    {"id": CHOSEN_ID, "statement": "stub hypothesis one", "rationale": "stub rationale one"},
    {"id": "h9", "statement": "stub hypothesis two", "rationale": "stub rationale two"},
]

VALID_VERDICT = {
    "label": "trust",
    "rationale": "stub verdict rationale",
    "right_instrument": "stub instrument",
}

VALID_EXECUTION = {
    "status": "executed",
    "runs": [{"converged": True, "wall_clock_s": 1.0, "qoi_value": 0.5}],
}


def make_thought(decision: str, tag: str) -> dict:
    return {
        "assessment": f"stub assessment ({tag})",
        "surprise_triage": "none",
        "iterate_decision": decision,
        "justification": f"stub justification ({tag})",
        "learned_summary": f"stub learned summary ({tag})",
    }


class StubRelay:
    """Builds a stub stage list; records what stage 2 received per call."""

    def __init__(self, decisions: list[str]):
        self.decisions = list(decisions)  # consumed by stage-5 executions
        self.stage2_inputs: list[dict] = []
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

    def stage1(self, baton: Baton) -> Baton:
        baton.payload = {
            "domain": baton.payload["domain"],
            "hypotheses": copy.deepcopy(HYPOTHESES),
            "hypotheses_ranked": True,
        }
        baton.add_history("stage1_ideation", "stub ranked 2")
        return baton

    def stage2(self, baton: Baton) -> Baton:
        # Record exactly what this pass's stage 2 received (its "input").
        self.stage2_inputs.append(copy.deepcopy(baton.payload))
        prior = baton.payload.get("prior_thought")
        baton.payload = {
            "domain": baton.payload["domain"],
            "chosen_hypothesis": baton.payload["chosen_hypothesis"],
            "experiment_spec": make_valid_spec(),
        }
        if prior is not None:
            baton.payload["prior_thought"] = prior
        baton.add_history("stage2_experiment_design", "stub spec")
        return baton

    def stage3(self, baton: Baton) -> Baton:
        payload = dict(baton.payload)
        payload["fidelity_verdict"] = dict(VALID_VERDICT)
        baton.payload = payload
        baton.add_history("stage3_fidelity_gate", "stub verdict trust")
        return baton

    def stage4(self, baton: Baton) -> Baton:
        payload = dict(baton.payload)
        payload["execution_results"] = copy.deepcopy(VALID_EXECUTION)
        baton.payload = payload
        baton.add_history("stage4_simulation", "stub executed")
        return baton

    def stage5(self, baton: Baton) -> Baton:
        decision = self.decisions.pop(0)
        thought = make_thought(decision, f"stage5 call {len(self.stage2_inputs)}")
        payload = dict(baton.payload)
        payload["thought"] = thought
        payload["iterate_decision"] = decision
        baton.payload = payload
        baton.add_history("stage5_thought_layer", f"stub thought {decision}")
        return baton

    def stage6(self, baton: Baton) -> Baton:
        self.stage6_calls += 1
        baton.add_history("stage6_paper", "stub ack")
        return baton


class LoopControllerCase(unittest.TestCase):
    def drive(self, decisions: list[str]) -> tuple[StubRelay, Path, list, str]:
        """Run the relay to completion; return (stubs, run_dir, outcomes, log)."""
        stubs = StubRelay(decisions)
        self._tmp = tempfile.TemporaryDirectory()
        run_dir = Path(self._tmp.name)
        logger = Logger(run_dir / "log.txt")
        baton = Baton(
            run_id="loop-test",
            created_at="2026-07-06T00:00:00+00:00",
            mode="auto",
            payload={"domain": DOMAIN},
        )
        outcomes: list[str] = []
        with patch(
            "supervisor.record_run_outcome",
            side_effect=lambda b, how_far: outcomes.append(how_far),
        ):
            run_relay(logger, baton, run_dir, "auto", stages=stubs.stages())
        log = (run_dir / "log.txt").read_text()
        self.baton = baton
        return stubs, run_dir, outcomes, log

    def tearDown(self):
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def history_stages(self) -> list[str]:
        return [h["stage"] for h in self.baton.history]


class TestExitPathUnchanged(LoopControllerCase):
    def test_exit_runs_all_six_stages_once(self):
        stubs, run_dir, outcomes, log = self.drive(["exit"])
        for n in range(1, 7):
            self.assertTrue((run_dir / f"baton_after_stage_{n}.json").is_file())
        self.assertFalse(list(run_dir.glob("*_pass*.json")))
        self.assertEqual(stubs.stage6_calls, 1)
        self.assertEqual(outcomes, ["completed"])
        self.assertIn("GATE after_stage_5 [auto]: model=exit enacted=exit (accepted)", log)
        self.assertEqual(len(self.baton.history), 6)


class TestBackToDesignLoop(LoopControllerCase):
    def test_reenters_at_stage_2_with_reduced_payload(self):
        stubs, run_dir, outcomes, log = self.drive(["back_to_design", "exit"])
        # Pass-2 stage-2 input: exactly the surgically reduced payload.
        self.assertEqual(len(stubs.stage2_inputs), 2)
        self.assertEqual(
            sorted(stubs.stage2_inputs[1]),
            ["chosen_hypothesis", "domain", "prior_thought"],
        )
        self.assertEqual(
            stubs.stage2_inputs[1]["prior_thought"],
            make_thought("back_to_design", "stage5 call 1"),
        )
        # Pass-aware snapshots for the re-entered stages only.
        for n in (2, 3, 4, 5):
            self.assertTrue((run_dir / f"baton_after_stage_{n}_pass2.json").is_file())
        self.assertFalse((run_dir / "baton_after_stage_1_pass2.json").exists())
        self.assertTrue((run_dir / "baton_after_stage_6.json").is_file())
        # prior_thought persisted into the pass-2 payload and snapshots.
        snap = json.loads((run_dir / "baton_after_stage_2_pass2.json").read_text())
        self.assertIn("prior_thought", snap["payload"])
        # History: one entry per execution — stage 2 appears twice.
        self.assertEqual(self.history_stages().count("stage2_experiment_design"), 2)
        self.assertEqual(len(self.baton.history), 10)  # 5 + 4 rerun + stage 6
        self.assertEqual(outcomes, ["completed"])
        self.assertIn("LOOP-BACK (back_to_design)", log)
        self.assertIn("SCHEMA OK after gate 1 (pass 2)", log)
        self.assertIn("SCHEMA OK after stage 2 (pass 2)", log)


class TestBackToIdeationLoop(LoopControllerCase):
    def test_reenters_at_stage_1_with_domain_only(self):
        stubs, run_dir, outcomes, log = self.drive(["back_to_ideation", "exit"])
        # The pass-2 stage-2 input carries NO prior_thought (design fact:
        # ideation re-entry hands context via the journal, not the baton).
        self.assertEqual(len(stubs.stage2_inputs), 2)
        self.assertNotIn("prior_thought", stubs.stage2_inputs[1])
        self.assertIn("LOOP-BACK (back_to_ideation): payload reduced to {domain}", log)
        self.assertTrue((run_dir / "baton_after_stage_1_pass2.json").is_file())
        self.assertTrue((run_dir / "baton_after_gate_1_pass2.json").is_file())
        self.assertEqual(self.history_stages().count("stage1_ideation"), 2)
        self.assertEqual(outcomes, ["completed"])


class TestMoreDataStops(LoopControllerCase):
    def test_more_data_ends_run_without_stage_6(self):
        stubs, run_dir, outcomes, log = self.drive(["more_data"])
        self.assertEqual(stubs.stage6_calls, 0)
        self.assertFalse((run_dir / "baton_after_stage_6.json").exists())
        self.assertEqual(outcomes, ["completed_more_data_unwired"])
        self.assertIn(
            "MORE_DATA requires Phase-C experimentation intelligence (Step 19) "
            "— ending run with recommendation",
            log,
        )


class TestLoopBound(LoopControllerCase):
    def test_third_non_exit_decision_forces_stop(self):
        stubs, run_dir, outcomes, log = self.drive(
            ["back_to_design", "back_to_design", "back_to_design"]
        )
        self.assertEqual(stubs.stage6_calls, 0)
        self.assertEqual(outcomes, ["completed_loop_bound_forced_exit"])
        self.assertIn("LOOP BOUND reached (2) — forced exit with recommendation", log)
        # Stage 2 ran three times: pass-2 and pass-3 snapshots exist.
        self.assertTrue((run_dir / "baton_after_stage_2_pass2.json").is_file())
        self.assertTrue((run_dir / "baton_after_stage_2_pass3.json").is_file())
        self.assertEqual(self.history_stages().count("stage2_experiment_design"), 3)


class TestFullLoopEndToEnd(LoopControllerCase):
    """Part 2c: one full back_to_design loop verified from the temp run dir."""

    def test_full_loop_from_disk(self):
        stubs, run_dir, outcomes, log = self.drive(["back_to_design", "exit"])

        # Pass-aware snapshots on disk: pass 1 unsuffixed, pass 2 suffixed.
        names = sorted(p.name for p in run_dir.glob("baton_after_*.json"))
        self.assertEqual(
            names,
            [
                "baton_after_gate_1.json",
                "baton_after_stage_1.json",
                "baton_after_stage_2.json",
                "baton_after_stage_2_pass2.json",
                "baton_after_stage_3.json",
                "baton_after_stage_3_pass2.json",
                "baton_after_stage_4.json",
                "baton_after_stage_4_pass2.json",
                "baton_after_stage_5.json",
                "baton_after_stage_5_pass2.json",
                "baton_after_stage_6.json",
            ],
        )
        # prior_thought in the pass-2 stage-2 input AND in the final payload
        # (it persists through the second pass, per the ruled schema change).
        self.assertIn("prior_thought", stubs.stage2_inputs[1])
        final = json.loads((run_dir / "baton_after_stage_6.json").read_text())
        self.assertEqual(
            final["payload"]["prior_thought"],
            make_thought("back_to_design", "stage5 call 1"),
        )
        # History shows stage 2 twice, in execution order.
        stages_in_order = [h["stage"] for h in final["history"]]
        self.assertEqual(stages_in_order.count("stage2_experiment_design"), 2)
        # Final run_record status.
        self.assertEqual(outcomes, ["completed"])
        self.assertIn("model=exit enacted=exit (accepted)", log)


if __name__ == "__main__":
    unittest.main()
