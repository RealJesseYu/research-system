"""
test_gate_headers.py — standalone tests of the supervisor's gate display
headers. Zero model calls: build_gate2_header and build_gate5_header are
pure payload -> str functions with no I/O, exercised here against canned
payloads (the parse_gate1_selection pattern). Display-only helpers must
never raise, so the missing-field cases matter as much as the happy path.

Run directly: venv/bin/python3 tests/test_gate_headers.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from supervisor import build_gate2_header, build_gate5_header

CANNED_SPEC_PAYLOAD = {
    "domain": "fluid dynamics",
    "chosen_hypothesis": {"id": "h3", "statement": "…", "rationale": "…"},
    "experiment_spec": {
        "title": "Obstacle-induced recirculation in a lid-driven cavity",
        "qoi": {
            "name": "mean_velocity_magnitude",
            "units": "m/s",
            "definition": "…",
            "how_extracted": "…",
        },
        "full_experiment": {"design": "…", "estimated_run_count": 12},
    },
}

CANNED_VERDICT_PAYLOAD = {
    "fidelity_verdict": {
        "label": "defer",
        "rationale": "The spec requires a scalar-field extraction the instrument cannot provide.",
        "right_instrument": "none — route to human/real experiment",
    }
}

CANNED_EXECUTED_PAYLOAD = {
    "fidelity_verdict": {
        "label": "trust",
        "rationale": "In-envelope baseline sweep.",
        "right_instrument": "yes",
    },
    "execution_results": {
        "status": "executed",
        "runs": [
            {"converged": True, "qoi_value": 0.4168353, "wall_clock_s": 21.4},
            {"converged": False, "qoi_error": "not extractable by contract", "wall_clock_s": 9.1},
        ],
    },
}

CANNED_SKIPPED_PAYLOAD = {
    "fidelity_verdict": {
        "label": "defer",
        "rationale": "Out of contract.",
        "right_instrument": "none",
    },
    "execution_results": {"status": "skipped_defer"},
}

CANNED_HALTED_PAYLOAD = {
    "fidelity_verdict": {
        "label": "trust",
        "rationale": "Judged in-envelope.",
        "right_instrument": "yes",
    },
    "execution_results": {
        "status": "halted_synthesis",
        "runs": [],
        "reason": "run 1 of 3: unsupported parameters: floor_amplitude, floor_wavelength",
    },
}


class TestGate2Header(unittest.TestCase):
    def test_happy_path_has_all_three_facts(self):
        line = build_gate2_header(CANNED_SPEC_PAYLOAD)
        self.assertIn("Obstacle-induced recirculation in a lid-driven cavity", line)
        self.assertIn("mean_velocity_magnitude", line)
        self.assertIn("12", line)
        self.assertEqual(len(line.splitlines()), 1)

    def test_missing_spec_renders_placeholders_not_raise(self):
        line = build_gate2_header({"domain": "fluid dynamics"})
        self.assertIn("?", line)

    def test_malformed_spec_renders_placeholders_not_raise(self):
        line = build_gate2_header({"experiment_spec": "not a dict"})
        self.assertIn("?", line)


class TestGate5Header(unittest.TestCase):
    def test_happy_path_is_prominent_and_complete(self):
        block = build_gate5_header(CANNED_VERDICT_PAYLOAD)
        self.assertIn("FIDELITY VERDICT: DEFER", block)
        self.assertIn(
            "The spec requires a scalar-field extraction the instrument cannot provide.",
            block,
        )
        self.assertIn("none — route to human/real experiment", block)

    def test_missing_verdict_renders_placeholders_not_raise(self):
        block = build_gate5_header({})
        self.assertIn("FIDELITY VERDICT: ?", block)

    def test_no_execution_results_means_no_execution_line(self):
        block = build_gate5_header(CANNED_VERDICT_PAYLOAD)
        self.assertNotIn("EXECUTION", block)

    def test_executed_lists_status_and_per_run_one_liners(self):
        block = build_gate5_header(CANNED_EXECUTED_PAYLOAD)
        self.assertIn("EXECUTION: executed", block)
        self.assertIn("run 1: converged true, qoi 0.4168353", block)
        self.assertIn("run 2: converged false, qoi_error not extractable by contract", block)

    def test_skipped_defer_states_nothing_executed(self):
        block = build_gate5_header(CANNED_SKIPPED_PAYLOAD)
        self.assertIn("EXECUTION: skipped_defer", block)
        self.assertIn("nothing executed: defer verdict", block)
        self.assertNotIn("run 1", block)

    def test_halted_synthesis_states_reason(self):
        block = build_gate5_header(CANNED_HALTED_PAYLOAD)
        self.assertIn("EXECUTION: halted_synthesis", block)
        self.assertIn(
            "reason: run 1 of 3: unsupported parameters: floor_amplitude, floor_wavelength",
            block,
        )

    def test_malformed_execution_results_never_raise(self):
        block = build_gate5_header({"execution_results": "not a dict"})
        self.assertNotIn("EXECUTION", block)
        block = build_gate5_header({"execution_results": {"status": "executed", "runs": "nope"}})
        self.assertIn("EXECUTION: executed", block)
        block = build_gate5_header({"execution_results": {"status": "halted_synthesis"}})
        self.assertIn("reason: ?", block)


if __name__ == "__main__":
    unittest.main()
