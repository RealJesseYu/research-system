"""test_incremental_emission.py — T0.2: a move cut off still leaves its numbers.

THE FAILURE, re-derived from studies/study-20260730T034915Z/ (not from its
write-up): m15 reported 34 findings with 0 artifacts and 0 verified; m16 reported
26 with 0 and 0. Both computed every number for real and died before writing a
single producer file. m15's workspace still contains `make_producers.py` — the
batch emitter it wrote and never ran.

The mechanism under test is the PICKUP: what `tools.emit_finding.emit` writes
enters the record whether or not the agent survives to mention it. Everything
here runs offline — the sandbox is injected.

Run directly: venv/bin/python3 tests/test_incremental_emission.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages import free_experimenter as FE  # noqa: E402
from tools import emit_finding as EM  # noqa: E402


def ok(value):
    """A sandbox that reproduces `value`."""
    return lambda spec: {"valid": True, "qoi": value, "diagnostics": None}


def fails(msg="ModuleNotFoundError: no module named 'requests'"):
    return lambda spec: {"valid": False, "qoi": None, "diagnostics": msg}


class TestEmitPersistsImmediately(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        (self.ws / "m_b_sn.py").write_text(
            "metrics = {}\nmetrics['b_sn'] = 3.6537\n")

    def test_one_line_lands_a_finished_finding(self):
        out = EM.emit("m_b_sn.py", "b_sn", units="1", label="SN exponent",
                      workspace=self.ws, runner=ok(3.6537))
        self.assertTrue(out["emitted"])
        self.assertEqual(out["value"], 3.6537)
        recs = EM.read_emitted(self.ws)
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["quantity"], "b_sn")
        self.assertEqual(r["value"], 3.6537)
        self.assertEqual(r["units"], "1")
        self.assertTrue(r["verified"])
        self.assertEqual(r["artifact"], {"file": "m_b_sn.py", "quantity": "b_sn"})
        self.assertTrue(r["reproduce"])

    def test_the_channel_survives_a_torn_last_line(self):
        """A move killed mid-write leaves a partial line. Losing the fifteen good
        records above it to that is the exact failure this mechanism exists to
        stop, so a bad line is skipped and counts for nothing."""
        EM.emit("m_b_sn.py", "b_sn", workspace=self.ws, runner=ok(1.0))
        with open(self.ws / EM.EMITTED_FILENAME, "a") as fh:
            fh.write('{"quantity": "torn", "val')
        self.assertEqual([r["quantity"] for r in EM.read_emitted(self.ws)],
                         ["b_sn"])

    def test_a_producer_that_cannot_run_emits_NOTHING_and_says_why(self):
        """The channel holds proven producers only — a failed one would put an
        unbacked number into the record from nowhere. The agent is told now,
        while it can still fix it, which is the second half of the point."""
        out = EM.emit("m_b_sn.py", "b_sn", workspace=self.ws, runner=fails())
        self.assertFalse(out["emitted"])
        self.assertIn("no module named 'requests'", out["error"])
        self.assertEqual(EM.read_emitted(self.ws), [])

    def test_a_missing_file_is_a_result_not_an_exception(self):
        out = EM.emit("never_written.py", "x", workspace=self.ws, runner=ok(1))
        self.assertFalse(out["emitted"])
        self.assertIn("write the file first", out["error"])

    def test_a_sandbox_that_explodes_is_reported_not_raised(self):
        def boom(spec):
            raise RuntimeError("docker is not running")
        out = EM.emit("m_b_sn.py", "b_sn", workspace=self.ws, runner=boom)
        self.assertFalse(out["emitted"])
        self.assertIn("docker is not running", out["error"])

    def test_the_producer_value_wins_over_the_callers(self):
        """emit() cannot manufacture a number: the file's own computation is the
        value of record, and a disagreement is recorded rather than resolved."""
        out = EM.emit("m_b_sn.py", "b_sn", value=99.0,
                      workspace=self.ws, runner=ok(3.6537))
        self.assertEqual(out["value"], 3.6537)
        self.assertIn("artifact of record", out["note"])
        self.assertEqual(EM.read_emitted(self.ws)[0]["value"], 3.6537)

    def test_a_file_outside_the_workspace_is_refused(self):
        with self.assertRaises(EM.EmitError):
            EM.emit("../../etc/hosts", "x", workspace=self.ws, runner=ok(1))

    def test_a_quantity_is_required(self):
        with self.assertRaises(EM.EmitError):
            EM.emit("m_b_sn.py", "  ", workspace=self.ws, runner=ok(1))

    def test_a_declared_profile_travels_onto_the_artifact(self):
        EM.emit("m_b_sn.py", "b_sn", profile="heavy",
                workspace=self.ws, runner=ok(1.0))
        self.assertEqual(EM.read_emitted(self.ws)[0]["artifact"]["profile"],
                         "heavy")

    def test_no_channel_file_means_no_records(self):
        self.assertEqual(EM.read_emitted(self.ws), [])
        self.assertFalse((self.ws / EM.EMITTED_FILENAME).exists())


class TestMerge(unittest.TestCase):
    """The pickup. Keyed on quantity NAME, mechanically, never on label."""

    def test_the_m16_shape_an_emitted_number_missing_from_the_report(self):
        merged, n = FE._merge_emitted(
            [{"label": "something else", "value": 1, "verified": False}],
            [{"quantity": "sigma", "value": 1.46, "verified": True,
              "artifact": {"file": "m_sigma.py", "quantity": "sigma"}}])
        self.assertEqual(n, 1)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1]["quantity"], "sigma")
        self.assertTrue(merged[1]["verified"])

    def test_the_m15_shape_a_reported_number_with_no_artifact_is_upgraded(self):
        """34 real numbers, every artifact field empty. If a producer for that
        quantity was emitted, the finding adopts it instead of dying a caveat."""
        merged, n = FE._merge_emitted(
            [{"label": "SN exponent", "value": 3.6537, "verified": False,
              "quantity": "b_sn"}],
            [{"quantity": "b_sn", "value": 3.6537, "verified": True,
              "units": "1", "reproduce": "python3 m_b_sn.py",
              "artifact": {"file": "m_b_sn.py", "quantity": "b_sn"}}])
        self.assertEqual(n, 0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["artifact"]["file"], "m_b_sn.py")
        self.assertTrue(merged[0]["verified"])
        self.assertEqual(merged[0]["units"], "1")
        self.assertEqual(merged[0]["label"], "SN exponent")  # the agent's words

    def test_the_agents_own_artifact_wins(self):
        merged, n = FE._merge_emitted(
            [{"label": "a", "value": 2.0, "verified": True,
              "artifact": {"file": "mine.py", "quantity": "b_sn"}}],
            [{"quantity": "b_sn", "value": 3.0, "verified": True,
              "artifact": {"file": "m_b_sn.py", "quantity": "b_sn"}}])
        self.assertEqual(n, 0)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["artifact"]["file"], "mine.py")
        self.assertEqual(merged[0]["value"], 2.0)

    def test_emit_and_report_both_is_a_merge_not_a_duplicate(self):
        merged, n = FE._merge_emitted(
            [{"label": "a", "value": 1.0, "verified": True,
              "artifact": {"file": "m_a.py", "quantity": "a"}}],
            [{"quantity": "a", "value": 1.0, "verified": True,
              "artifact": {"file": "m_a.py", "quantity": "a"}}])
        self.assertEqual((n, len(merged)), (0, 1))

    def test_a_re_emitted_name_does_not_multiply(self):
        """Two emissions of one name is a contradiction, and adjudicating it is
        the quantity register's job (T0.1) — not this function's. First wins."""
        merged, n = FE._merge_emitted([], [
            {"quantity": "a", "value": 1.0, "verified": True,
             "artifact": {"file": "m_a.py", "quantity": "a"}},
            {"quantity": "a", "value": 9.0, "verified": True,
             "artifact": {"file": "m_a2.py", "quantity": "a"}}])
        self.assertEqual((n, len(merged)), (1, 1))
        self.assertEqual(merged[0]["value"], 1.0)

    def test_empty_channel_changes_nothing(self):
        findings = [{"label": "a", "value": 1, "verified": False}]
        merged, n = FE._merge_emitted(findings, [])
        self.assertEqual((merged, n), (findings, 0))

    def test_the_input_list_is_not_mutated(self):
        findings = [{"label": "a", "value": 1, "verified": False,
                     "quantity": "a"}]
        FE._merge_emitted(findings, [
            {"quantity": "a", "value": 1, "verified": True,
             "artifact": {"file": "m_a.py", "quantity": "a"}}])
        self.assertFalse(findings[0]["verified"])

    def test_quantity_name_resolution_matches_the_register(self):
        self.assertEqual(FE._finding_quantity(
            {"artifact": {"file": "f.py", "quantity": "a"}, "quantity": "b"}),
            "a")
        self.assertEqual(FE._finding_quantity({"quantity": "b"}), "b")
        self.assertIsNone(FE._finding_quantity({"label": "x"}))
        self.assertIsNone(FE._finding_quantity("not a dict"))


class TestEndToEndThroughTheStage(unittest.TestCase):
    """The whole point, exercised at the level the study failed at."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cwd = Path.cwd()
        import os
        os.chdir(root)
        self.addCleanup(os.chdir, self.cwd)
        self.run_dir = root / "runs" / "r1"
        (self.run_dir / "workspace").mkdir(parents=True)
        self.ws = self.run_dir / "workspace"

    def _emit(self, name, value):
        (self.ws / f"m_{name}.py").write_text(f"metrics = {{'{name}': {value}}}\n")
        EM.emit(f"m_{name}.py", name, workspace=self.ws, runner=ok(value))

    def _verify_all(self, claims, run_id=None):
        (self.run_dir / "verification.json").write_text("{}")
        return {"verdicts": [{"claim_index": i, "verified": True}
                             for i, _ in enumerate(claims)]}

    def test_a_cut_off_move_that_reported_nothing_still_lands_its_numbers(self):
        self._emit("b_sn", 3.6537)
        self._emit("sigma", 1.4624)
        result = FE.run_free_investigation(
            "q", run_id="r1",
            call=lambda *a, **k: ({"summary": "cut off", "findings": [],
                                   "publishable": False}, None),
            verify=self._verify_all, gate=lambda ra: [])
        self.assertEqual(sorted(f["quantity"] for f in result["findings"]),
                         ["b_sn", "sigma"])
        self.assertTrue(all(f["verified"] for f in result["findings"]))
        on_disk = json.loads(
            (self.run_dir / "free_investigation.json").read_text())
        self.assertEqual(len(on_disk["findings"]), 2)

    def test_a_crash_after_emission_still_writes_the_record_then_re_raises(self):
        self._emit("b_sn", 3.6537)

        def boom(*a, **k):
            raise RuntimeError("transport died")

        with self.assertRaises(RuntimeError):
            FE.run_free_investigation("q", run_id="r1", call=boom,
                                      verify=self._verify_all,
                                      gate=lambda ra: [])
        on_disk = json.loads(
            (self.run_dir / "free_investigation.json").read_text())
        self.assertEqual(on_disk["findings"][0]["quantity"], "b_sn")
        self.assertFalse(on_disk["publishable"])
        self.assertIn("crashed during the investigation", on_disk["summary"])
        self.assertIn("transport died", on_disk["summary"])

    def test_a_crash_with_NOTHING_emitted_is_unchanged_no_record_written(self):
        def boom(*a, **k):
            raise RuntimeError("transport died")

        with self.assertRaises(RuntimeError):
            FE.run_free_investigation("q", run_id="r1", call=boom,
                                      verify=self._verify_all,
                                      gate=lambda ra: [])
        self.assertFalse((self.run_dir / "free_investigation.json").exists())

    def test_no_emission_leaves_the_run_exactly_as_before(self):
        result = FE.run_free_investigation(
            "q", run_id="r1",
            call=lambda *a, **k: ({"summary": "s", "findings": [
                {"label": "a", "value": 1, "verified": False}],
                "publishable": False}, None),
            verify=self._verify_all, gate=lambda ra: [])
        self.assertEqual(result["findings"],
                         [{"label": "a", "value": 1, "verified": False}])
        self.assertFalse((self.ws / EM.EMITTED_FILENAME).exists())


class TestNothingIsGated(unittest.TestCase):
    """ADDITIVE, and pinned as such: emission may not block, fail or shape a move."""

    def test_no_new_required_field(self):
        self.assertEqual(FE.SCHEMA["required"],
                         ["summary", "findings", "publishable"])

    def test_the_validator_never_mentions_emission(self):
        errors = FE._validate_free_result({
            "summary": "s",
            "findings": [{"label": "a", "value": 1, "verified": False}],
            "publishable": True})
        self.assertEqual(errors, [])

    def test_nothing_in_production_calls_emit(self):
        """The agent calls it or it does not. No stage may call it FOR the agent —
        that would be the harness authoring findings."""
        root = Path(__file__).resolve().parent.parent
        callers = []
        for p in list((root / "stages").rglob("*.py")) + \
                list((root / "pi_agent").rglob("*.py")) + \
                list((root / "tools").rglob("*.py")):
            if p.name == "emit_finding.py":
                continue
            if "emit_finding import emit\n" in p.read_text() or \
                    "emit_finding.emit(" in p.read_text():
                callers.append(p.name)
        self.assertEqual(callers, [])


class TestTheBriefAndTheWindUpAgree(unittest.TestCase):
    def test_the_brief_teaches_the_affordance(self):
        self.assertIn("EMIT EACH NUMBER THE MOMENT YOU HAVE IT",
                      FE.SYSTEM_PROMPT)
        self.assertIn("from tools.emit_finding import emit", FE.SYSTEM_PROMPT)
        self.assertIn("gates nothing", FE.SYSTEM_PROMPT)

    def test_the_wind_up_does_not_ask_for_a_tool_call_it_has_just_denied(self):
        """The trap: the wind-up is the one moment the agent is listening AND the
        one moment it can do nothing — the same tracker denies every tool call
        (m16's transcript shows a Write denied carrying this exact text). So the
        message says 'name a file you already wrote', never 'write one'."""
        import model_call
        msg = model_call._WIND_UP_MESSAGE
        self.assertIn("is picked up automatically", msg)
        self.assertIn("do not promise a file you have not already written", msg)
        self.assertIn("No tool call will be permitted now", msg)
        self.assertNotIn("write your producer", msg.lower())


if __name__ == "__main__":
    unittest.main()
