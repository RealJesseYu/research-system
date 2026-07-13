"""
test_triage_battery.py — offline tests for the Step-20.7 Stage-5 triage battery
(harness/triage_battery.py). ZERO real model calls: model_call._invoke_transport
is patched with a fake that echoes the run_id and returns canned thoughts, and the
cwd is redirected to a tmp dir so the real Stage-5 path's mandatory transcripts land
under the tmp runs/, never the project's.

Covers: case loading + the six-key/vocabulary guards; the pure scoring function;
report shape and GREEN/RED logic; an all-correct run going GREEN through the REAL
Stage-5 door under fake transport; and a fabricated wrong placement correctly FAILing.

Run directly: venv/bin/python3 tests/test_triage_battery.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import model_call  # noqa: E402
from harness import triage_battery  # noqa: E402
from stages.stage5_thought_layer import DECISION_VALUES, TRIAGE_VALUES  # noqa: E402

CASES_DIR = Path(__file__).resolve().parent.parent / "harness" / "triage_cases"


def _canned_reply(run_id: str, triage: str, decision: str) -> str:
    return json.dumps(
        {
            "ack_run_id": run_id,
            "thought": {
                "assessment": "canned assessment for the offline transport fake.",
                "surprise_triage": triage,
                "iterate_decision": decision,
                "justification": "canned justification.",
                "learned_summary": "canned learned summary.",
            },
        }
    )


def _fake_transport_factory(answers: dict[str, tuple[str, str]]):
    """Build a fake _invoke_transport that reads the run_id out of the assembled
    user_turn, derives the case_id (run_id = triage-<ts>-<case_id>), and returns
    the canned (triage, decision) for that case. Also records every user_turn it
    saw so a test can assert only prompt_inputs reached the model."""
    seen: list[dict] = []

    def fake(system_prompt: str, user_turn: str, model: str) -> str:
        payload = json.loads(user_turn)
        seen.append(payload)
        run_id = payload["run_id"]
        case_id = run_id.split("-", 2)[2]
        triage, decision = answers[case_id]
        return _canned_reply(run_id, triage, decision)

    fake.seen = seen  # type: ignore[attr-defined]
    return fake


class TestLoadCases(unittest.TestCase):
    def test_four_cases_sealed_shape(self):
        cases = triage_battery.load_cases(CASES_DIR)
        self.assertEqual(len(cases), 4)
        ids = [c["case_id"] for c in cases]
        self.assertEqual(
            sorted(ids),
            ["broken_bc", "coarse_mesh", "envelope_drift", "genuine_surprise"],
        )
        for c in cases:
            for k in triage_battery.CASE_KEYS:
                self.assertIn(k, c)
            self.assertEqual(
                set(c["prompt_inputs"]), triage_battery.PROMPT_INPUT_KEYS
            )

    def test_prompt_inputs_carry_no_answer_key_substring(self):
        # The Stage-5 door's tripwire refuses any serialized input containing
        # "answer_key"; the expectation lives OUTSIDE prompt_inputs.
        for c in triage_battery.load_cases(CASES_DIR):
            self.assertNotIn("answer_key", json.dumps(c["prompt_inputs"]))

    def test_expectations_within_vocabulary(self):
        for c in triage_battery.load_cases(CASES_DIR):
            exp = c["expectation"]
            self.assertTrue(exp["triage_allowed"])
            self.assertTrue(exp["decision_allowed"])
            for t in exp["triage_allowed"]:
                self.assertIn(t, TRIAGE_VALUES)
            for d in exp["decision_allowed"]:
                self.assertIn(d, DECISION_VALUES)

    def test_none_is_never_an_expected_triage(self):
        # All four are problem cases; a clean-consistent "none" is never a home.
        for c in triage_battery.load_cases(CASES_DIR):
            self.assertNotIn("none", c["expectation"]["triage_allowed"])

    def test_malformed_prompt_inputs_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = {
                "case_id": "x", "plan_case": "x", "provenance": {},
                "prompt_inputs": {"run_id": "x"},  # not the six keys
                "expectation": {"triage_allowed": ["none"], "decision_allowed": ["exit"]},
            }
            (Path(d) / "bad.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                triage_battery.load_cases(Path(d))

    def test_out_of_vocabulary_expectation_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            bad = {
                "case_id": "x", "plan_case": "x", "provenance": {},
                "prompt_inputs": {k: None for k in triage_battery.PROMPT_INPUT_KEYS},
                "expectation": {"triage_allowed": ["not_a_triage"], "decision_allowed": ["exit"]},
            }
            (Path(d) / "bad.json").write_text(json.dumps(bad))
            with self.assertRaises(ValueError):
                triage_battery.load_cases(Path(d))


class TestScoreThought(unittest.TestCase):
    def _case(self, triage_allowed, decision_allowed):
        return {
            "case_id": "c", "plan_case": "p",
            "expectation": {"triage_allowed": triage_allowed, "decision_allowed": decision_allowed},
        }

    def _thought(self, triage, decision):
        return {
            "assessment": "a", "surprise_triage": triage, "iterate_decision": decision,
            "justification": "j", "learned_summary": "l",
        }

    def test_pass_requires_both(self):
        case = self._case(["setup_error"], ["back_to_design"])
        r = triage_battery.score_thought(case, self._thought("setup_error", "back_to_design"), {"attempts": 1, "fence_stripped": False})
        self.assertTrue(r["passed"])
        self.assertTrue(r["triage_pass"] and r["decision_pass"])

    def test_wrong_triage_fails(self):
        case = self._case(["setup_error"], ["back_to_design"])
        r = triage_battery.score_thought(case, self._thought("none", "back_to_design"), {})
        self.assertFalse(r["passed"])
        self.assertFalse(r["triage_pass"])
        self.assertTrue(r["decision_pass"])

    def test_wrong_decision_fails(self):
        case = self._case(["setup_error"], ["back_to_design"])
        r = triage_battery.score_thought(case, self._thought("setup_error", "exit"), {})
        self.assertFalse(r["passed"])
        self.assertTrue(r["triage_pass"])
        self.assertFalse(r["decision_pass"])

    def test_multi_value_allowed_lists(self):
        case = self._case(["out_of_envelope", "setup_error"], ["more_data", "back_to_design"])
        r = triage_battery.score_thought(case, self._thought("out_of_envelope", "more_data"), {})
        self.assertTrue(r["passed"])


class TestBuildReport(unittest.TestCase):
    def _rec(self, cid, passed):
        return {
            "case_id": cid, "plan_case": cid, "triage": "setup_error", "decision": "exit",
            "triage_allowed": ["setup_error"], "decision_allowed": ["exit"],
            "triage_pass": passed, "decision_pass": passed, "passed": passed,
            "assessment": "a", "justification": "j", "learned_summary": "l",
            "attempts": 1, "fence_stripped": False, "run_id": f"triage-x-{cid}",
        }

    def test_all_pass_green(self):
        rep = triage_battery.build_report([self._rec("a", True), self._rec("b", True)], "x", 1.2)
        self.assertEqual(rep["status"], "GREEN")
        self.assertEqual(rep["passed_count"], 2)
        self.assertEqual(rep["misses"], [])

    def test_one_fail_red_with_miss(self):
        rep = triage_battery.build_report([self._rec("a", True), self._rec("b", False)], "x", 1.2)
        self.assertEqual(rep["status"], "RED")
        self.assertEqual(rep["passed_count"], 1)
        self.assertEqual(len(rep["misses"]), 1)
        self.assertEqual(rep["misses"][0]["case_id"], "b")

    def test_empty_is_red(self):
        rep = triage_battery.build_report([], "x", 0.0)
        self.assertEqual(rep["status"], "RED")


class TestRunBatteryFakeTransport(unittest.TestCase):
    """The REAL Stage-5 door, driven under a fake transport in a tmp cwd."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._cwd = os.getcwd()
        os.chdir(self._tmp.name)
        self.report_path = Path(self._tmp.name) / "triage_last_run.json"

    def tearDown(self):
        os.chdir(self._cwd)
        self._tmp.cleanup()

    def _all_correct_answers(self):
        # One defensible correct (triage, decision) per case, all in-list.
        return {
            "broken_bc": ("setup_error", "back_to_design"),
            "coarse_mesh": ("out_of_envelope", "more_data"),
            "genuine_surprise": ("genuine_surprise", "more_data"),
            "envelope_drift": ("out_of_envelope", "back_to_design"),
        }

    def test_all_correct_is_green(self):
        fake = _fake_transport_factory(self._all_correct_answers())
        with patch.object(model_call, "_invoke_transport", fake):
            rc = triage_battery.run_battery(report_path=self.report_path, cases_dir=CASES_DIR)
        self.assertEqual(rc, 0)
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report["status"], "GREEN")
        self.assertEqual(report["passed_count"], 4)
        self.assertEqual(report["total"], 4)
        # Every case scored PASS.
        self.assertTrue(all(c["passed"] for c in report["cases"]))

    def test_only_prompt_inputs_reach_model(self):
        fake = _fake_transport_factory(self._all_correct_answers())
        with patch.object(model_call, "_invoke_transport", fake):
            triage_battery.run_battery(report_path=self.report_path, cases_dir=CASES_DIR)
        # The Stage-5 door's tripwire enforces exactly the six keys; assert the
        # model never saw provenance/expectation and never an "answer_key".
        for payload in fake.seen:
            self.assertEqual(set(payload), triage_battery.PROMPT_INPUT_KEYS)
            self.assertNotIn("expectation", payload)
            self.assertNotIn("provenance", payload)
            self.assertNotIn("answer_key", json.dumps(payload))

    def test_fabricated_wrong_placement_fails(self):
        # broken_bc mis-triaged as a clean "none" — the battery must catch it.
        answers = self._all_correct_answers()
        answers["broken_bc"] = ("none", "exit")
        fake = _fake_transport_factory(answers)
        with patch.object(model_call, "_invoke_transport", fake):
            rc = triage_battery.run_battery(report_path=self.report_path, cases_dir=CASES_DIR)
        self.assertEqual(rc, 1)
        report = json.loads(self.report_path.read_text())
        self.assertEqual(report["status"], "RED")
        self.assertEqual(report["passed_count"], 3)
        miss_ids = [m["case_id"] for m in report["misses"]]
        self.assertEqual(miss_ids, ["broken_bc"])
        broken = next(c for c in report["cases"] if c["case_id"] == "broken_bc")
        self.assertFalse(broken["passed"])
        self.assertFalse(broken["triage_pass"])


if __name__ == "__main__":
    unittest.main()
