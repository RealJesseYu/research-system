"""
test_schemas.py — standalone tests of the Step-15 locked baton-payload
schemas. Zero model calls: every validator is a pure payload -> [errors]
function.

The passing cases are built from REAL disk evidence, not invented shapes:
the base payload is specs/step15_executed_payload.json (tracked; the exact
hand-authored payload RUN B handfeed4-20260706T045314Z executed), and the
execution_results / thought blocks are embedded verbatim from that run's
baton_after_stage_4.json / baton_after_stage_5.json; the skipped_defer
block is RUN A 20260706T044214Z's, and the halted_synthesis block plus
refine verdict are RUN C handfeed4-20260706T045429Z's (the halted case is
therefore a disclosed composite: RUN C's verdict and execution_results on
RUN B's spec base, each piece verbatim from its cited run — runs/ is not
tracked, so tests cannot read the run dirs directly).

Run directly: venv/bin/python3 tests/test_schemas.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from schemas import (
    validate_payload_post_gate1,
    validate_payload_post_stage2,
    validate_payload_post_stage3,
    validate_payload_post_stage4,
    validate_payload_post_stage5,
)

_PAYLOAD_FILE = (
    Path(__file__).resolve().parent.parent / "specs" / "step15_executed_payload.json"
)


def _base_post_stage3() -> dict:
    """RUN B's pre-stage-4 payload: the tracked hand-authored payload file
    minus its provenance note (dropped by the handfeed before use)."""
    payload = json.loads(_PAYLOAD_FILE.read_text())
    payload.pop("provenance")
    return payload


# Verbatim from runs/handfeed4-20260706T045314Z/baton_after_stage_4.json (RUN B).
RUN_B_EXECUTION_RESULTS = {
    "status": "executed",
    "runs": [
        {"converged": True, "wall_clock_s": 13.03, "qoi_value": 0.4168353},
        {"converged": True, "wall_clock_s": 13.1, "qoi_value": 0.1930067},
    ],
}

# Verbatim from runs/handfeed4-20260706T045314Z/baton_after_stage_5.json (RUN B).
RUN_B_THOUGHT = {
    "assessment": (
        "Both runs executed and converged cleanly (final residuals ~1e-7 to "
        "1e-8, global continuity ~1e-19, Courant < 0.61), yielding "
        "volAverage(mag(U)) = 0.4168 m/s at lid 2.0 and 0.1930 m/s at lid "
        "1.0. These match the predicted values (~0.4168 and ~0.1930, ratio "
        "~2.16) essentially exactly, and the success criterion (>0.3 at lid "
        "2.0) is met with 0.4168. Re spans 100-200, inside the validated "
        "laminar envelope, so the results are valid and physically realistic."
    ),
    "surprise_triage": "none",
    "iterate_decision": "exit",
    "justification": (
        "The converged QoIs reproduce both predicted values to four "
        "significant figures and clear the success threshold, so the "
        "baseline is confirmed with nothing left to probe."
    ),
    "learned_summary": (
        "The verdict-gated cavity_2d instrument reproduces the baseline "
        "lid-driven cavity mean speed to ~0.4168 m/s (lid 2.0) and ~0.1930 "
        "m/s (lid 1.0) at Re 100-200, confirming the end-to-end executed "
        "path is trustworthy."
    ),
}

# Verbatim from runs/20260706T044214Z/baton_after_stage_4.json (RUN A).
RUN_A_EXECUTION_RESULTS = {"status": "skipped_defer"}

# Verbatim from runs/handfeed4-20260706T045429Z/baton_after_stage_4.json (RUN C).
RUN_C_EXECUTION_RESULTS = {
    "status": "halted_synthesis",
    "runs": [],
    "reason": (
        "run 1 of 3: cannot build: Re, cavity_height, cavity_width, "
        "mesh_cells_per_meter, s_amplitude_fraction not in the buildable set "
        "(kinematic_viscosity, lid_velocity, cavity_length, mesh_resolution, "
        "end_time, time_step)"
    ),
    "flag": "refine — survivors require downstream confirmation",
}

# Verbatim from the same RUN C baton.
RUN_C_REFINE_VERDICT = {
    "label": "refine",
    "rationale": (
        "The 2D laminar solver genuinely handles this cavity-class physics "
        "and directly computes vol_avg_speed, but it is being extrapolated "
        "well past its validated envelope (Re 2.5x higher, an unproven "
        "multi-block staircase mesh, no mesh-independence at the S-throat) "
        "so it yields a reliable predicted screen, not a reality-confirmed "
        "answer."
    ),
    "right_instrument": (
        "cavity_2d (used as a screening filter; survivors require "
        "mesh-independence confirmation and real-world/human validation at "
        "Re=500)"
    ),
}


class TestPostGate1(unittest.TestCase):
    # Truth-edited Step 23.5 (R-23.5-4): the post-gate-1 payload is exactly
    # {domain, chosen_hypothesis, substrate_id}; every constructed payload
    # here gained substrate_id, and the missing/empty escapes are new.

    def test_run_b_shape_passes(self):
        base = _base_post_stage3()
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": "cavity_2d_cfd",
        }
        self.assertEqual(validate_payload_post_gate1(payload), [])

    def test_missing_domain_fails(self):
        base = _base_post_stage3()
        payload = {
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": "cavity_2d_cfd",
        }
        self.assertTrue(
            any("'domain'" in e for e in validate_payload_post_gate1(payload))
        )

    def test_extra_payload_key_fails(self):
        base = _base_post_stage3()
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": "cavity_2d_cfd",
            "hypotheses": [],
        }
        self.assertTrue(
            any("'hypotheses'" in e for e in validate_payload_post_gate1(payload))
        )

    def test_missing_substrate_id_fails(self):
        # R-23.5-4 escape: the widened schema rejects a payload without the
        # decided instrument — no optional-key softening.
        base = _base_post_stage3()
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
        }
        self.assertTrue(
            any("'substrate_id'" in e for e in validate_payload_post_gate1(payload))
        )

    def test_empty_substrate_id_fails(self):
        # R-23.5-4 escape: empty and whitespace-only are both rejected.
        base = _base_post_stage3()
        for empty in ("", "   "):
            payload = {
                "domain": base["domain"],
                "chosen_hypothesis": base["chosen_hypothesis"],
                "substrate_id": empty,
            }
            self.assertTrue(
                any(
                    "substrate_id must be a non-empty string" in e
                    for e in validate_payload_post_gate1(payload)
                )
            )

    def test_empty_statement_fails(self):
        base = _base_post_stage3()
        chosen = dict(base["chosen_hypothesis"], statement="   ")
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": chosen,
            "substrate_id": "cavity_2d_cfd",
        }
        self.assertTrue(
            any("statement" in e for e in validate_payload_post_gate1(payload))
        )

    def test_extra_hypothesis_key_fails(self):
        base = _base_post_stage3()
        chosen = dict(base["chosen_hypothesis"], rank=1)
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": chosen,
            "substrate_id": "cavity_2d_cfd",
        }
        self.assertTrue(
            any("'rank'" in e for e in validate_payload_post_gate1(payload))
        )

    def test_non_dict_payload_fails(self):
        self.assertEqual(
            validate_payload_post_gate1(None), ["the payload must be a JSON object."]
        )


class TestPostStage2(unittest.TestCase):
    # Truth-edited Step 23.5 (R-23.5-4): downstream boundaries widened by
    # derivation — constructed payloads carry substrate_id.
    def test_run_b_shape_passes(self):
        base = _base_post_stage3()
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": base["substrate_id"],
            "experiment_spec": base["experiment_spec"],
        }
        self.assertEqual(validate_payload_post_stage2(payload), [])

    def test_missing_spec_fails(self):
        base = _base_post_stage3()
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": base["substrate_id"],
        }
        self.assertTrue(
            any(
                "'experiment_spec'" in e
                for e in validate_payload_post_stage2(payload)
            )
        )

    def test_spec_internals_deferred_to_validate_spec(self):
        # Wrong hypothesis_id: the enum pin is validate_spec's rule, and the
        # boundary validator must surface it rather than re-implement it.
        base = _base_post_stage3()
        spec = dict(base["experiment_spec"], hypothesis_id="h9")
        payload = {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": base["substrate_id"],
            "experiment_spec": spec,
        }
        self.assertTrue(
            any("hypothesis_id" in e for e in validate_payload_post_stage2(payload))
        )


class TestPostStage3(unittest.TestCase):
    def test_run_b_shape_passes(self):
        self.assertEqual(validate_payload_post_stage3(_base_post_stage3()), [])

    def test_wrong_label_enum_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(
            payload["fidelity_verdict"], label="approve"
        )
        self.assertTrue(
            any("label" in e for e in validate_payload_post_stage3(payload))
        )

    def test_missing_right_instrument_fails(self):
        payload = _base_post_stage3()
        verdict = dict(payload["fidelity_verdict"])
        del verdict["right_instrument"]
        payload["fidelity_verdict"] = verdict
        self.assertTrue(
            any(
                "right_instrument" in e
                for e in validate_payload_post_stage3(payload)
            )
        )

    def test_empty_rationale_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(payload["fidelity_verdict"], rationale="")
        self.assertTrue(
            any("rationale" in e for e in validate_payload_post_stage3(payload))
        )

    def test_extra_verdict_key_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(
            payload["fidelity_verdict"], confidence=0.9
        )
        self.assertTrue(
            any("'confidence'" in e for e in validate_payload_post_stage3(payload))
        )


class TestPostStage4(unittest.TestCase):
    def _executed_payload(self) -> dict:
        payload = _base_post_stage3()
        payload["execution_results"] = json.loads(
            json.dumps(RUN_B_EXECUTION_RESULTS)
        )
        return payload

    def test_run_b_executed_passes(self):
        self.assertEqual(validate_payload_post_stage4(self._executed_payload()), [])

    def test_run_a_skipped_defer_passes(self):
        payload = _base_post_stage3()
        # RUN A's verdict was defer; the base verdict is trust — swap the
        # label so the composite matches a real defer run's consistency.
        payload["fidelity_verdict"] = dict(
            payload["fidelity_verdict"], label="defer"
        )
        payload["execution_results"] = dict(RUN_A_EXECUTION_RESULTS)
        self.assertEqual(validate_payload_post_stage4(payload), [])

    def test_run_c_halted_refine_passes(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(RUN_C_REFINE_VERDICT)
        payload["execution_results"] = dict(RUN_C_EXECUTION_RESULTS)
        self.assertEqual(validate_payload_post_stage4(payload), [])

    def test_wrong_status_enum_fails(self):
        payload = self._executed_payload()
        payload["execution_results"] = {"status": "crashed"}
        self.assertTrue(
            any("status" in e for e in validate_payload_post_stage4(payload))
        )

    def test_skipped_defer_with_extra_key_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(
            payload["fidelity_verdict"], label="defer"
        )
        payload["execution_results"] = {"status": "skipped_defer", "runs": []}
        self.assertTrue(
            any("'runs'" in e for e in validate_payload_post_stage4(payload))
        )

    def test_executed_with_no_runs_fails(self):
        payload = self._executed_payload()
        payload["execution_results"] = {"status": "executed", "runs": []}
        self.assertTrue(
            any("at least one run" in e for e in validate_payload_post_stage4(payload))
        )

    def test_run_entry_with_both_qoi_keys_fails(self):
        payload = self._executed_payload()
        payload["execution_results"]["runs"][0]["qoi_error"] = "also an error"
        self.assertTrue(
            any("exactly one of" in e for e in validate_payload_post_stage4(payload))
        )

    def test_run_entry_with_neither_qoi_key_fails(self):
        payload = self._executed_payload()
        del payload["execution_results"]["runs"][0]["qoi_value"]
        self.assertTrue(
            any("exactly one of" in e for e in validate_payload_post_stage4(payload))
        )

    def test_non_bool_converged_fails(self):
        payload = self._executed_payload()
        payload["execution_results"]["runs"][0]["converged"] = "yes"
        self.assertTrue(
            any("converged" in e for e in validate_payload_post_stage4(payload))
        )

    def test_flag_on_trust_verdict_fails(self):
        payload = self._executed_payload()
        payload["execution_results"]["flag"] = (
            "refine — survivors require downstream confirmation"
        )
        self.assertTrue(
            any("'flag'" in e for e in validate_payload_post_stage4(payload))
        )

    def test_flag_missing_on_refine_halt_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(RUN_C_REFINE_VERDICT)
        results = dict(RUN_C_EXECUTION_RESULTS)
        del results["flag"]
        payload["execution_results"] = results
        self.assertTrue(
            any("'flag'" in e for e in validate_payload_post_stage4(payload))
        )

    def test_halted_without_reason_fails(self):
        payload = _base_post_stage3()
        payload["fidelity_verdict"] = dict(RUN_C_REFINE_VERDICT)
        results = dict(RUN_C_EXECUTION_RESULTS)
        del results["reason"]
        payload["execution_results"] = results
        self.assertTrue(
            any("reason" in e for e in validate_payload_post_stage4(payload))
        )


class TestPriorThought(unittest.TestCase):
    """Ruled change, Step 16: optional prior_thought at post-gate-1
    (loop-back re-entry), tolerated at every later boundary."""

    def _gate1_payload(self) -> dict:
        base = _base_post_stage3()
        # Truth-edited Step 23.5 (R-23.5-4): three-key post-gate-1 shape.
        return {
            "domain": base["domain"],
            "chosen_hypothesis": base["chosen_hypothesis"],
            "substrate_id": "cavity_2d_cfd",
        }

    def test_absent_passes(self):
        self.assertEqual(validate_payload_post_gate1(self._gate1_payload()), [])

    def test_present_and_valid_passes_post_gate1(self):
        payload = self._gate1_payload()
        payload["prior_thought"] = dict(RUN_B_THOUGHT)
        self.assertEqual(validate_payload_post_gate1(payload), [])

    def test_present_and_malformed_fails(self):
        payload = self._gate1_payload()
        bad = dict(RUN_B_THOUGHT)
        bad["surprise_triage"] = "shrug"
        del bad["justification"]
        payload["prior_thought"] = bad
        errors = validate_payload_post_gate1(payload)
        self.assertTrue(any("prior_thought surprise_triage" in e for e in errors))
        self.assertTrue(any("prior_thought justification" in e for e in errors))

    def test_persists_through_pass2_boundaries(self):
        # The same prior_thought must be tolerated at post-stage-2 through
        # post-stage-5 (it rides the payload through the whole second pass).
        payload = _base_post_stage3()
        payload["prior_thought"] = dict(RUN_B_THOUGHT)
        self.assertEqual(validate_payload_post_stage3(payload), [])
        payload["execution_results"] = json.loads(json.dumps(RUN_B_EXECUTION_RESULTS))
        self.assertEqual(validate_payload_post_stage4(payload), [])
        payload["thought"] = dict(RUN_B_THOUGHT)
        payload["iterate_decision"] = "exit"
        self.assertEqual(validate_payload_post_stage5(payload), [])


class TestPostStage5(unittest.TestCase):
    def _run_b_payload(self) -> dict:
        payload = _base_post_stage3()
        payload["execution_results"] = json.loads(
            json.dumps(RUN_B_EXECUTION_RESULTS)
        )
        payload["thought"] = dict(RUN_B_THOUGHT)
        payload["iterate_decision"] = "exit"
        return payload

    def test_run_b_shape_passes(self):
        self.assertEqual(validate_payload_post_stage5(self._run_b_payload()), [])

    def test_missing_thought_field_fails(self):
        payload = self._run_b_payload()
        del payload["thought"]["justification"]
        self.assertTrue(
            any("justification" in e for e in validate_payload_post_stage5(payload))
        )

    def test_empty_learned_summary_fails(self):
        payload = self._run_b_payload()
        payload["thought"]["learned_summary"] = ""
        self.assertTrue(
            any("learned_summary" in e for e in validate_payload_post_stage5(payload))
        )

    def test_wrong_triage_enum_fails(self):
        payload = self._run_b_payload()
        payload["thought"]["surprise_triage"] = "surprised"
        self.assertTrue(
            any("surprise_triage" in e for e in validate_payload_post_stage5(payload))
        )

    def test_wrong_decision_enum_fails(self):
        payload = self._run_b_payload()
        payload["thought"]["iterate_decision"] = "retry"
        payload["iterate_decision"] = "retry"
        self.assertTrue(
            any("iterate_decision" in e for e in validate_payload_post_stage5(payload))
        )

    def test_decision_mismatch_fails(self):
        payload = self._run_b_payload()
        payload["iterate_decision"] = "more_data"
        self.assertTrue(
            any("must match" in e for e in validate_payload_post_stage5(payload))
        )

    def test_extra_thought_field_fails(self):
        payload = self._run_b_payload()
        payload["thought"]["confidence"] = "high"
        self.assertTrue(
            any("'confidence'" in e for e in validate_payload_post_stage5(payload))
        )

    def test_extra_payload_key_fails(self):
        payload = self._run_b_payload()
        payload["notes"] = "extra"
        self.assertTrue(
            any("'notes'" in e for e in validate_payload_post_stage5(payload))
        )


class TestSubstrateIdRequiredAtEveryBoundary(unittest.TestCase):
    """Step 23.5 (build-chat ruling on the 2d/3c split, condition 3): the
    widened downstream boundaries all REQUIRE substrate_id — no boundary
    where the key is optional. One parametrized escape across boundaries."""

    def _boundary_payloads(self):
        base = _base_post_stage3()
        post_stage2 = {
            k: base[k]
            for k in ("domain", "chosen_hypothesis", "substrate_id", "experiment_spec")
        }
        post_stage3 = dict(base)
        post_stage4 = dict(base)
        post_stage4["execution_results"] = json.loads(
            json.dumps(RUN_B_EXECUTION_RESULTS)
        )
        post_stage5 = dict(post_stage4)
        post_stage5["thought"] = dict(RUN_B_THOUGHT)
        post_stage5["iterate_decision"] = "exit"
        return [
            (validate_payload_post_gate1, {
                k: base[k] for k in ("domain", "chosen_hypothesis", "substrate_id")
            }),
            (validate_payload_post_stage2, post_stage2),
            (validate_payload_post_stage3, post_stage3),
            (validate_payload_post_stage4, post_stage4),
            (validate_payload_post_stage5, post_stage5),
        ]

    def test_every_boundary_requires_substrate_id(self):
        for validator, payload in self._boundary_payloads():
            with self.subTest(boundary=validator.__name__):
                self.assertEqual(validator(payload), [])
                stripped = {k: v for k, v in payload.items() if k != "substrate_id"}
                self.assertTrue(
                    any("'substrate_id'" in e for e in validator(stripped))
                )

    def test_every_boundary_rejects_empty_substrate_id(self):
        for validator, payload in self._boundary_payloads():
            with self.subTest(boundary=validator.__name__):
                emptied = dict(payload, substrate_id="   ")
                self.assertTrue(
                    any(
                        "substrate_id must be a non-empty string" in e
                        for e in validator(emptied)
                    )
                )


if __name__ == "__main__":
    unittest.main()
