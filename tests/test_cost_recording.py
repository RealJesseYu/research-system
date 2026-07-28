"""test_cost_recording.py — item C (2026-07-28): record what a call ACTUALLY cost.

The token totals the system reported were not costs: cost_meter summed every
integer field of the SDK usage dict, so cache reads (~10% the price of an input
token) were added at face value, while the SDK's own correctly-priced figure —
ResultMessage.total_cost_usd — and num_turns were dropped on the floor.

These tests prove, offline, the whole chain the real figures now travel:

    fake SDK ResultMessage -> model_call._ask_once -> cost_meter
        -> supervisor.record_run_outcome (run_record extras["cost"])
        -> pi_agent.dispatch.read_run_result (RunResult.cost)
        -> pi_agent.study.record_move (the arc entry on disk)
        -> pi_agent.cost_report (dollars/turns per phase; "unknown" never 0)

plus the never-raise discipline (a malformed cost value must not sink a call)
and backward compatibility (a study recorded before this reads as unknown).

Run directly: venv/bin/python3 tests/test_cost_recording.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cost_meter  # noqa: E402
import model_call  # noqa: E402
from claude_agent_sdk.types import (  # noqa: E402
    AssistantMessage,
    ResultMessage,
    TextBlock,
)

_USAGE = {
    "input_tokens": 100,
    "output_tokens": 50,
    "cache_creation_input_tokens": 2000,
    "cache_read_input_tokens": 7000,
}


def _result_message(**overrides):
    kw = dict(
        subtype="success",
        duration_ms=10,
        duration_api_ms=8,
        is_error=False,
        num_turns=17,
        session_id="s",
        total_cost_usd=1.25,
        usage=dict(_USAGE),
    )
    kw.update(overrides)
    return ResultMessage(**kw)


class _MeterIsolated(unittest.TestCase):
    """Every test here resets the shared meter and leaves it clean."""

    def setUp(self):
        cost_meter.reset()

    def tearDown(self):
        cost_meter.reset()


class TestMeterRecordsUsdAndTurns(_MeterIsolated):
    def test_usd_and_turns_accumulate_beside_the_existing_fields(self):
        cost_meter.record_call("model_call", dict(_USAGE), cost_usd=1.25, num_turns=17)
        cost_meter.record_call("model_call", dict(_USAGE), cost_usd=0.75, num_turns=3)
        snap = cost_meter.read()
        # existing fields untouched
        self.assertEqual(snap["model_calls"]["total"], 2)
        self.assertEqual(snap["tokens"]["total"]["cache_read_input_tokens"], 14000)
        # new fields beside them
        self.assertEqual(snap["usd"]["total"], 2.0)
        self.assertEqual(snap["usd"]["calls_with_usd"], 2)
        self.assertEqual(snap["turns"]["total"], 20)
        self.assertEqual(snap["turns"]["calls_with_turns"], 2)

    def test_absent_values_leave_coverage_at_zero_not_a_measured_zero(self):
        cost_meter.record_call("model_call", dict(_USAGE))  # old-signature call
        snap = cost_meter.read()
        self.assertEqual(snap["usd"]["calls_with_usd"], 0)
        self.assertEqual(snap["turns"]["calls_with_turns"], 0)

    def test_malformed_values_are_ignored_never_raised(self):
        # observation-only discipline: a weird SDK value must not sink a call
        cost_meter.record_call("model_call", dict(_USAGE),
                               cost_usd="$1.25", num_turns="seventeen")
        cost_meter.record_call("model_call", dict(_USAGE),
                               cost_usd=True, num_turns=False)  # bools excluded
        snap = cost_meter.read()
        self.assertEqual(snap["model_calls"]["total"], 2)
        self.assertEqual(snap["usd"]["calls_with_usd"], 0)
        self.assertEqual(snap["turns"]["calls_with_turns"], 0)


class TestTheDoorCapturesTheResultMessage(_MeterIsolated):
    """A fake SDK stream through the REAL _ask_once proves the door passes
    total_cost_usd and num_turns into the meter."""

    def test_ask_once_records_dollars_and_turns(self):
        async def fake_query(prompt, options):
            yield AssistantMessage(content=[TextBlock(text='{"ok": true}')],
                                   model="m")
            yield _result_message()

        original = model_call.query
        model_call.query = fake_query
        try:
            reply = model_call._invoke_transport("sys", "user", "some-model")
        finally:
            model_call.query = original
        self.assertEqual(reply, '{"ok": true}')
        snap = cost_meter.read()
        self.assertEqual(snap["usd"]["model_call"], 1.25)
        self.assertEqual(snap["usd"]["calls_with_usd"], 1)
        self.assertEqual(snap["turns"]["model_call"], 17)
        self.assertEqual(snap["tokens"]["model_call"]["cache_read_input_tokens"], 7000)

    def test_a_resultmessage_without_the_fields_still_completes(self):
        # older SDK shape: no total_cost_usd attribute at all is simulated by
        # None (the SDK default); the call must complete and record nothing.
        async def fake_query(prompt, options):
            yield AssistantMessage(content=[TextBlock(text="hello")], model="m")
            yield _result_message(total_cost_usd=None)

        original = model_call.query
        model_call.query = fake_query
        try:
            model_call._invoke_transport("sys", "user", "some-model")
        finally:
            model_call.query = original
        snap = cost_meter.read()
        self.assertEqual(snap["model_calls"]["total"], 1)
        self.assertEqual(snap["usd"]["calls_with_usd"], 0)


class TestDollarsReachAnArcEntry(_MeterIsolated):
    """The VERIFY case from the brief: a fake ResultMessage's dollars and turns
    reach an arc entry, through the same path the token count travels."""

    def test_run_record_to_arc_entry(self):
        from baton import Baton
        from pi_agent.dispatch import MoveResult, read_run_result
        from pi_agent.study import create_study, record_move, study_arc
        import supervisor

        # 1. The run's meter state, as the door leaves it after two calls.
        cost_meter.record_call("model_call", dict(_USAGE), cost_usd=1.25, num_turns=17)
        cost_meter.record_call("model_call", dict(_USAGE), cost_usd=0.75, num_turns=3)

        # 2. The supervisor journals the run_record (capture the journal write).
        captured = {}
        original_append = supervisor.journal_append
        supervisor.journal_append = lambda entry: captured.update(entry)
        try:
            baton = Baton(run_id="r1", created_at="t", mode="auto",
                          payload={"domain": "d"})
            supervisor.record_run_outcome(baton, "completed")
        finally:
            supervisor.journal_append = original_append

        cost = captured["extras"]["cost"]
        # legacy fields intact
        self.assertEqual(cost["calls"], 2)
        self.assertEqual(cost["tokens"], 2 * sum(_USAGE.values()))
        # the field breakdown survives (cache reads separable from real input)
        self.assertEqual(cost["tokens_by_field"]["cache_read_input_tokens"], 14000)
        self.assertEqual(cost["tokens_by_field"]["input_tokens"], 200)
        # the real figures
        self.assertEqual(cost["usd"], 2.0)
        self.assertEqual(cost["turns"], 20)
        self.assertIn("$2.0000", captured["text"])

        # 3. dispatch reads the record back; the whole cost dict rides along.
        with tempfile.TemporaryDirectory() as tmp:
            result = read_run_result(Path(tmp) / "r1", "r1", 0, captured)
            self.assertEqual(result.cost["usd"], 2.0)
            self.assertEqual(result.cost["turns"], 20)

            # 4. record_move writes it into the arc on disk.
            study = create_study("g", studies_root=Path(tmp) / "studies")
            record_move(study, MoveResult(
                move_type="single", run_id="r1", succeeded=True,
                outcome="completed", raw=result.as_dict()))
            entry = study_arc(study)[0]
            self.assertEqual(entry["cost"]["usd"], 2.0)
            self.assertEqual(entry["cost"]["turns"], 20)
            self.assertEqual(
                entry["cost"]["tokens_by_field"]["cache_read_input_tokens"], 14000)

    def test_no_usd_reported_leaves_the_keys_absent_not_zero(self):
        from baton import Baton
        import supervisor

        cost_meter.record_call("model_call", dict(_USAGE))  # tokens only
        captured = {}
        original_append = supervisor.journal_append
        supervisor.journal_append = lambda entry: captured.update(entry)
        try:
            supervisor.record_run_outcome(
                Baton(run_id="r2", created_at="t", mode="auto",
                      payload={"domain": "d"}), "completed")
        finally:
            supervisor.journal_append = original_append
        cost = captured["extras"]["cost"]
        self.assertNotIn("usd", cost)
        self.assertNotIn("turns", cost)
        self.assertNotIn("$", captured["text"])
        # legacy fields still present, unchanged
        self.assertEqual(cost["calls"], 1)


class TestCostReportShowsDollarsAndTurns(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_study(self, study_id, arc):
        d = self.root / study_id
        d.mkdir(parents=True)
        (d / "study.json").write_text(json.dumps(
            {"study_id": study_id, "goal": "g",
             "created_at": "2026-07-28T10:00:00+00:00"}))
        with open(d / "arc.jsonl", "w") as f:
            for e in arc:
                f.write(json.dumps(e) + "\n")

    def test_a_post_item_c_study_reports_dollars_turns_and_cache_fraction(self):
        from pi_agent import cost_report as CR
        self._write_study("s", [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00", "move_type": "single",
             "cost": {"calls": 2, "tokens": 9150, "usd": 1.25, "turns": 17,
                      "tokens_by_field": {"input_tokens": 100,
                                          "output_tokens": 50,
                                          "cache_creation_input_tokens": 2000,
                                          "cache_read_input_tokens": 7000}},
             "results": []},
        ])
        node = CR.study_cost_report("s", self.root)
        row = node["rows"][0]
        self.assertEqual(row["usd"], 1.25)
        self.assertEqual(row["turns"], 17)
        self.assertEqual(node["own_spend"]["usd"], 1.25)
        self.assertEqual(node["own_spend"]["moves_with_usd"], 1)
        self.assertEqual(node["own_spend"]["turns"], 17)
        self.assertEqual(
            node["own_spend"]["tokens_by_field"]["cache_read_input_tokens"], 7000)
        text = CR.render_text(node)
        self.assertIn("$1.25", text)
        self.assertIn("real cost (USD)", text)
        self.assertIn("cache reads are 77%", text)  # 7000 / 9150

    def test_a_pre_item_c_study_reads_as_unknown_never_zero(self):
        from pi_agent import cost_report as CR
        self._write_study("old", [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00", "move_type": "single",
             "cost": {"calls": 2, "tokens": 1000}, "results": []},
        ])
        node = CR.study_cost_report("old", self.root)
        self.assertIsNone(node["rows"][0]["usd"])
        self.assertIsNone(node["rows"][0]["turns"])
        self.assertEqual(node["own_spend"]["moves_with_usd"], 0)
        text = CR.render_text(node)
        self.assertIn("real cost (USD):    unknown", text)
        self.assertNotIn("$0", text)

    def test_a_spawn_row_derives_usd_only_when_the_child_recorded_it(self):
        from pi_agent import cost_report as CR
        self._write_study("p", [
            {"seq": 1, "at": "2026-07-28T11:00:00+00:00",
             "move_type": "spawn_sub_investigation", "cost": None,
             "tool_output": {"child_study_id": "p-sub1"}, "results": []},
        ])
        self._write_study("p-sub1", [
            {"seq": 1, "at": "2026-07-28T11:30:00+00:00", "move_type": "single",
             "cost": {"calls": 2, "tokens": 2000, "usd": 0.5, "turns": 9},
             "results": []},
        ])
        node = CR.study_cost_report("p", self.root)
        spawn = node["rows"][0]
        self.assertEqual(spawn["cost_source"], "derived_from_child")
        self.assertEqual(spawn["usd"], 0.5)
        self.assertEqual(spawn["turns"], 9)
        self.assertEqual(node["tree_spend"]["usd"], 0.5)
        self.assertEqual(node["tree_spend"]["moves_with_usd"], 1)


if __name__ == "__main__":
    unittest.main()
