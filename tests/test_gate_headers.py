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


if __name__ == "__main__":
    unittest.main()
