"""
test_experiment_picker.py — 19-lite picker + analytic cheap-first ladder.

ZERO live model calls: call_stage_model is fully mocked. Covers the picker's
accept / re-ask / uniform-coverage-fallback paths and its 2-attempt bound, plus
the analytic ladder's Courant/wall-time math (against hand-computed numbers),
its registry honest-None behavior, and the point-record attachment.

Run directly: venv/bin/python3 tests/test_experiment_picker.py
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import experiment_picker as ep


def _cavity_spec(sweep: bool = False) -> dict:
    """A lid-driven-cavity spec. When sweep=True, lid_velocity is a sweep
    parameter (for the fallback coverage test); otherwise all fixed."""
    lid = (
        {"name": "lid_velocity", "role": "sweep", "units": "m/s", "min": 1.0, "max": 2.0}
        if sweep
        else {"name": "lid_velocity", "role": "fixed", "units": "m/s", "value": 2.0}
    )
    return {
        "hypothesis_id": "h1",
        "title": "cavity test spec",
        "parameters": [
            lid,
            {"name": "cavity_length", "role": "fixed", "units": "m", "value": 1.0},
            {"name": "mesh_resolution", "role": "fixed", "units": "cells", "value": 64},
            {"name": "time_step", "role": "fixed", "units": "s", "value": 0.002},
            {"name": "end_time", "role": "fixed", "units": "s", "value": 20.0},
        ],
    }


VALID_PROPOSAL = {
    "ack_run_id": None,
    "points": [{"lid_velocity": 1.5}, {"lid_velocity": 2.0}],
    "reasoning": "bracket the two ends of the swept range",
    "predicted_qoi_per_point": [0.3, 0.42],
}


# --- Picker: accept / re-ask / fallback ------------------------------------


class TestPickerAccept(unittest.TestCase):
    def test_valid_first_reply_accepted_one_call(self):
        with patch(
            "tools.experiment_picker.call_stage_model",
            return_value=(dict(VALID_PROPOSAL), {}),
        ) as mock:
            out = ep.propose_next_points(_cavity_spec(sweep=True), [], 4)
        self.assertEqual(mock.call_count, 1)
        self.assertEqual(out["points"], VALID_PROPOSAL["points"])
        self.assertEqual(out["reasoning"], VALID_PROPOSAL["reasoning"])
        self.assertEqual(out["predicted_qoi_per_point"], [0.3, 0.42])
        # The pin is used, this tool only.
        _, kwargs = mock.call_args
        self.assertEqual(kwargs.get("model"), ep.PICKER_MODEL)
        self.assertEqual(ep.PICKER_MODEL, "claude-sonnet-4-6")  # workhorse tier, 2026-07-20


class TestPickerReask(unittest.TestCase):
    def test_bad_then_good_reasks_once(self):
        bad = {"points": "not a list", "reasoning": "", "predicted_qoi_per_point": []}
        with patch(
            "tools.experiment_picker.call_stage_model",
            side_effect=[(bad, {}), (dict(VALID_PROPOSAL), {})],
        ) as mock:
            out = ep.propose_next_points(_cavity_spec(sweep=True), [], 4)
        self.assertEqual(mock.call_count, 2)
        # The second call carried the validation error (the re-ask).
        second_input = mock.call_args_list[1].args[2]
        self.assertIn("validation_error", second_input)
        self.assertEqual(out["points"], VALID_PROPOSAL["points"])


class TestPickerFallback(unittest.TestCase):
    def test_two_bad_replies_degrade_with_notice(self):
        bad = {"points": [], "reasoning": "", "predicted_qoi_per_point": []}
        buf = io.StringIO()
        with patch(
            "tools.experiment_picker.call_stage_model",
            side_effect=[(bad, {}), (bad, {})],
        ) as mock, redirect_stdout(buf):
            out = ep.propose_next_points(_cavity_spec(sweep=True), [], 4)
        self.assertEqual(mock.call_count, ep.PICKER_MAX_ATTEMPTS)  # never exceeds 2
        self.assertEqual(mock.call_count, 2)
        self.assertIn("NOTICE", buf.getvalue())
        self.assertIn("uniform-coverage fallback", buf.getvalue())
        # Uniform coverage across the swept lid_velocity, 4 points.
        self.assertEqual(len(out["points"]), 4)
        self.assertEqual(
            [p["lid_velocity"] for p in out["points"]],
            [1.0, 1.333333, 1.666667, 2.0],
        )
        # Fixed values merged into every point; predictions honest-None.
        self.assertTrue(all(p["cavity_length"] == 1.0 for p in out["points"]))
        self.assertEqual(out["predicted_qoi_per_point"], [None, None, None, None])

    def test_model_exception_degrades_never_crashes(self):
        buf = io.StringIO()
        with patch(
            "tools.experiment_picker.call_stage_model",
            side_effect=RuntimeError("transport exhausted"),
        ) as mock, redirect_stdout(buf):
            out = ep.propose_next_points(_cavity_spec(sweep=True), [], 2)
        self.assertEqual(mock.call_count, 2)  # attempt + one re-ask, then fallback
        self.assertIn("NOTICE", buf.getvalue())
        self.assertEqual(len(out["points"]), 2)  # budget_remaining caps it


# --- Ladder: estimator math, registry, attachment --------------------------


class TestLadderMath(unittest.TestCase):
    def test_courant_and_walltime_hand_checked(self):
        params = {
            "cavity_length": 1.0,
            "mesh_resolution": 64,
            "lid_velocity": 2.0,
            "time_step": 0.002,
            "end_time": 20.0,
        }
        est = ep.lid_driven_cavity_estimate(params)
        # dx = 1/64 = 0.015625 ; courant = 2*0.002/0.015625 = 0.256
        self.assertEqual(est["dx"], 0.015625)
        self.assertEqual(est["courant"], 0.256)
        # n_steps = 20/0.002 = 10000 ; wall = 10000 * {2.3, 4.1} ms
        self.assertEqual(est["n_steps"], 10000)
        self.assertEqual(est["predicted_wall_time_s"], {"low": 23.0, "high": 41.0})
        self.assertEqual(est["per_step_ms_range"], [2.3, 4.1])
        self.assertEqual(est["family"], "lid_driven_cavity")

    def test_missing_input_is_none_not_crash(self):
        self.assertIsNone(ep.lid_driven_cavity_estimate({"cavity_length": 1.0}))

    def test_zero_divisor_is_none(self):
        self.assertIsNone(
            ep.lid_driven_cavity_estimate(
                {
                    "cavity_length": 1.0,
                    "mesh_resolution": 0,
                    "lid_velocity": 2.0,
                    "time_step": 0.002,
                    "end_time": 20.0,
                }
            )
        )


class TestRegistryHonestNone(unittest.TestCase):
    def test_unknown_family_is_none(self):
        non_cavity = {
            "parameters": [
                {"name": "pressure", "role": "fixed", "units": "Pa", "value": 5.0}
            ]
        }
        self.assertIsNone(ep.spec_family(non_cavity))
        self.assertIsNone(ep.analytic_estimate(non_cavity, {"pressure": 5.0}))
        rec = ep.build_point_record(non_cavity, {"pressure": 5.0}, predicted_qoi=1.0)
        self.assertNotIn("analytic_estimate", rec)
        self.assertNotIn("source", rec)
        self.assertEqual(rec["predicted_qoi"], 1.0)

    def test_cavity_family_detected(self):
        self.assertEqual(ep.spec_family(_cavity_spec()), "lid_driven_cavity")


class TestLadderAttachment(unittest.TestCase):
    def test_point_record_carries_estimate_and_source(self):
        spec = _cavity_spec(sweep=True)  # cavity_length etc. are fixed in spec
        rec = ep.build_point_record(spec, {"lid_velocity": 1.5}, predicted_qoi=0.3)
        self.assertEqual(rec["source"], "analytic")
        self.assertIn("analytic_estimate", rec)
        # The fixed spec values were merged under the point for the estimate.
        self.assertEqual(rec["analytic_estimate"]["family"], "lid_driven_cavity")
        self.assertEqual(rec["predicted_qoi"], 0.3)

    def test_attach_over_proposal(self):
        spec = _cavity_spec(sweep=True)
        proposal = {
            "points": [{"lid_velocity": 1.0}, {"lid_velocity": 2.0}],
            "predicted_qoi_per_point": [0.1, None],
            "reasoning": "x",
        }
        records = ep.attach_analytic_estimates(spec, proposal)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r["source"] == "analytic" for r in records))
        self.assertEqual(records[0]["predicted_qoi"], 0.1)
        self.assertNotIn("predicted_qoi", records[1])  # None not attached


if __name__ == "__main__":
    unittest.main()
