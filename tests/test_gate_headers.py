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

from supervisor import (
    build_gate1_neartie_display,
    build_gate2_header,
    build_gate5_header,
    build_thought_block,
)

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

    def test_refine_flag_present_renders_flag_line(self):
        payload = {
            "execution_results": {
                "status": "executed",
                "runs": [{"converged": True, "qoi_value": 0.42, "wall_clock_s": 11.4}],
                "flag": "refine — survivors require downstream confirmation",
            }
        }
        block = build_gate5_header(payload)
        self.assertIn("flag: refine — survivors require downstream confirmation", block)

    def test_refine_flag_absent_means_no_flag_line(self):
        block = build_gate5_header(CANNED_EXECUTED_PAYLOAD)
        self.assertNotIn("flag:", block)

    def test_thought_present_renders_boxed_block(self):
        payload = {
            "thought": {
                "assessment": "…",
                "surprise_triage": "setup_error",
                "iterate_decision": "back_to_design",
                "justification": "The runs never executed.",
                "learned_summary": "…",
            }
        }
        block = build_thought_block(payload)
        self.assertIn("THOUGHT", block)
        self.assertIn("triage: setup_error", block)
        self.assertIn("decision: back_to_design", block)
        self.assertIn("justification: The runs never executed.", block)
        header = build_gate5_header(payload)
        self.assertIn("THOUGHT", header)

    def test_thought_absent_means_no_thought_block(self):
        self.assertEqual(build_thought_block(CANNED_EXECUTED_PAYLOAD), "")
        self.assertEqual(build_thought_block({"thought": "not a dict"}), "")
        self.assertNotIn("THOUGHT", build_gate5_header(CANNED_EXECUTED_PAYLOAD))

    def test_malformed_execution_results_never_raise(self):
        block = build_gate5_header({"execution_results": "not a dict"})
        self.assertNotIn("EXECUTION", block)
        block = build_gate5_header({"execution_results": {"status": "executed", "runs": "nope"}})
        self.assertIn("EXECUTION: executed", block)
        block = build_gate5_header({"execution_results": {"status": "halted_synthesis"}})
        self.assertIn("reason: ?", block)


class TestGate1NearTieDisplay(unittest.TestCase):
    """17-CLOSE: the near-tie Elo table + research-overview summaries shown
    at gate 1 in human mode, driven with canned files (display-only; reads
    stage1 evidence, never the payload)."""

    CANNED_STATE = {
        "elo_init": 1200.0,
        "k_factor": 32,
        "final_ranking": [
            {"id": "h1", "elo": 1230.5612},
            {"id": "h2", "elo": 1229.7698},
            {"id": "h4", "elo": 1184.0, "deduped_by": "h1"},
        ],
    }
    CANNED_OVERVIEW = {
        "round": 2,
        "directions": [
            {"summary": "Geometry controls vortex-strength scaling.", "justification": "…"},
            {"summary": "Corner-eddy cascade onset is aspect-ratio-set.", "justification": "…"},
        ],
    }

    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.stage1 = Path(self._tmp.name) / "stage1"
        self.stage1.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _write(self, name, obj):
        import json

        (self.stage1 / name).write_text(json.dumps(obj))

    def test_both_files_render_table_and_summaries(self):
        self._write("tournament_state.json", self.CANNED_STATE)
        self._write("research_overview.json", self.CANNED_OVERVIEW)
        block = build_gate1_neartie_display(self.stage1)
        self.assertIn("tournament Elo (final round)", block)
        # The 17-C near-tie shape: ranks 1 and 2 visibly 0.79 Elo apart.
        self.assertIn("rank 1: h1  elo 1230.6", block)
        self.assertIn("rank 2: h2  elo 1229.8", block)
        self.assertIn("rank 3: h4  elo 1184.0", block)
        self.assertIn("research-overview directions", block)
        self.assertIn("- Geometry controls vortex-strength scaling.", block)
        self.assertIn("- Corner-eddy cascade onset is aspect-ratio-set.", block)

    def test_state_only_renders_table_without_directions(self):
        self._write("tournament_state.json", self.CANNED_STATE)
        block = build_gate1_neartie_display(self.stage1)
        self.assertIn("rank 1: h1", block)
        self.assertNotIn("research-overview", block)

    def test_neither_file_renders_nothing(self):
        self.assertEqual(build_gate1_neartie_display(self.stage1), "")
        # A missing stage1 dir entirely must also render nothing, not raise.
        self.assertEqual(
            build_gate1_neartie_display(self.stage1 / "does-not-exist"), ""
        )

    def test_malformed_files_never_raise(self):
        (self.stage1 / "tournament_state.json").write_text("{not json")
        (self.stage1 / "research_overview.json").write_text("[]")
        self.assertEqual(build_gate1_neartie_display(self.stage1), "")
        self._write("tournament_state.json", {"final_ranking": [{"id": "h1"}, "junk"]})
        block = build_gate1_neartie_display(self.stage1)
        self.assertIn("rank 1: h1  elo ?", block)
        self.assertIn("rank 2: ?  elo ?", block)


if __name__ == "__main__":
    unittest.main()
