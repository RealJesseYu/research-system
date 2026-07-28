"""test_cost_report.py — the offline per-phase cost report (roadmap item 1).

Proves the instrument OFFLINE on constructed studies: per-row cost/wall-clock/
tokens-per-verified, spawn rows derived from the child's arc roll-up, the
recursive tree total, the degenerate no-experiments study (spend must NOT read
as zero), truncated and malformed studies (must never raise), and — when the
real studies/ corpus is present on this machine — a sweep over every study in
it, plus a pin on the known-correct glider tree total.

Run directly: venv/bin/python3 tests/test_cost_report.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent import cost_report as CR  # noqa: E402
from pi_agent.study import STUDIES_ROOT  # noqa: E402


def _write_study(root: Path, study_id: str, *, goal: str = "g",
                 created_at: str = "2026-07-28T10:00:00+00:00",
                 arc: list = None, report: dict = None) -> Path:
    d = root / study_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "study.json").write_text(json.dumps(
        {"study_id": study_id, "goal": goal, "created_at": created_at}))
    if arc is not None:
        with open(d / "arc.jsonl", "w") as f:
            for e in arc:
                f.write((e if isinstance(e, str) else json.dumps(e)) + "\n")
    if report is not None:
        (d / "report.json").write_text(json.dumps(report))
    return d


class _Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestPerPhaseRows(_Base):
    def test_rows_carry_cost_wall_clock_and_tokens_per_verified(self):
        arc = [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00", "move_type": "single",
             "cost": {"calls": 2, "tokens": 1000}, "finding": "first probe",
             "results": [{"label": "x", "value": 1, "verified": True},
                         {"label": "y", "value": 2, "verified": False}]},
            {"seq": 2, "at": "2026-07-28T10:15:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 500}, "finding": "second probe",
             "results": []},
        ]
        _write_study(self.root, "s", arc=arc)
        node = CR.study_cost_report("s", self.root)
        self.assertTrue(node["exists"])
        self.assertEqual(len(node["rows"]), 2)
        r1, r2 = node["rows"]
        # first row's wall-clock runs from the study's created_at (10:00 -> 10:05)
        self.assertEqual(r1["wall_seconds"], 300.0)
        self.assertEqual(r2["wall_seconds"], 600.0)
        self.assertEqual(r1["calls"], 2)
        self.assertEqual(r1["tokens"], 1000)
        self.assertEqual(r1["cost_source"], "measured")
        self.assertEqual(r1["verified"], 1)
        self.assertEqual(r1["claims"], 2)
        self.assertEqual(r1["tokens_per_verified"], 1000)  # 1000 tokens / 1 verified
        self.assertIsNone(r2["tokens_per_verified"])       # nothing verified
        self.assertEqual(node["own_spend"],
                         {"calls": 3, "tokens": 1500, "moves_with_cost": 2, "moves": 2})

    def test_unmeasured_cost_reads_as_unknown_never_zero(self):
        arc = [{"seq": 1, "at": "2026-07-28T10:05:00+00:00",
                "move_type": "call_ideation", "cost": None, "results": []}]
        _write_study(self.root, "s", arc=arc)
        node = CR.study_cost_report("s", self.root)
        row = node["rows"][0]
        self.assertIsNone(row["calls"])
        self.assertIsNone(row["tokens"])
        self.assertEqual(row["cost_source"], "unknown")
        # ...and the renderer prints "?" for it, not 0
        self.assertIn("?", CR.render_text(node))

    def test_measured_zero_is_distinct_from_unknown(self):
        arc = [{"seq": 1, "at": "2026-07-28T10:05:00+00:00",
                "move_type": "read_memory", "cost": {"calls": 0, "tokens": 0},
                "results": []}]
        _write_study(self.root, "s", arc=arc)
        row = CR.study_cost_report("s", self.root)["rows"][0]
        self.assertEqual(row["tokens"], 0)
        self.assertEqual(row["cost_source"], "measured")


class TestSpawnDerivation(_Base):
    def _tree(self):
        _write_study(self.root, "p", arc=[
            {"seq": 1, "at": "2026-07-28T11:00:00+00:00",
             "move_type": "spawn_sub_investigation", "cost": None,
             "tool_output": {"child_study_id": "p-sub1"},
             "results": [{"label": "m", "value": 3, "verified": True}]},
            {"seq": 2, "at": "2026-07-28T12:00:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 700}, "results": []},
        ])
        _write_study(self.root, "p-sub1", arc=[
            {"seq": 1, "at": "2026-07-28T11:30:00+00:00", "move_type": "single",
             "cost": {"calls": 2, "tokens": 2000}, "results": []},
        ])

    def test_spawn_row_is_derived_from_the_child_arc(self):
        self._tree()
        node = CR.study_cost_report("p", self.root)
        spawn = node["rows"][0]
        self.assertEqual(spawn["cost_source"], "derived_from_child")
        self.assertEqual(spawn["tokens"], 2000)
        self.assertEqual(spawn["child_study_id"], "p-sub1")
        # derived cost is marked in the rendered table
        self.assertIn("derived from the child study's arc roll-up", CR.render_text(node))

    def test_tree_total_is_the_recursive_arc_roll_up(self):
        self._tree()
        node = CR.study_cost_report("p", self.root)
        # own arc counts only what THIS study measured (spawn row stays null)
        self.assertEqual(node["own_spend"]["tokens"], 700)
        self.assertEqual(node["tree_spend"],
                         {"calls": 3, "tokens": 2700, "studies": 2,
                          "moves_with_cost": 2, "moves": 3})

    def test_child_on_disk_but_not_linked_still_joins_the_tree(self):
        # a spawn still in flight (or a truncated arc) leaves the child unlinked
        _write_study(self.root, "p", arc=[])
        _write_study(self.root, "p-sub1", arc=[
            {"seq": 1, "at": "2026-07-28T11:30:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 900}, "results": []}])
        node = CR.study_cost_report("p", self.root)
        self.assertEqual(node["unlinked_children"], ["p-sub1"])
        self.assertEqual(node["tree_spend"]["tokens"], 900)

    def test_a_cycle_terminates(self):
        # a child that (impossibly) links back at its parent must not loop
        _write_study(self.root, "p", arc=[
            {"seq": 1, "at": "2026-07-28T11:00:00+00:00",
             "move_type": "spawn_sub_investigation",
             "tool_output": {"child_study_id": "p-sub1"}, "results": []}])
        _write_study(self.root, "p-sub1", arc=[
            {"seq": 1, "at": "2026-07-28T11:30:00+00:00",
             "move_type": "spawn_sub_investigation",
             "cost": {"calls": 1, "tokens": 100},
             "tool_output": {"child_study_id": "p"}, "results": []}])
        node = CR.study_cost_report("p", self.root)
        self.assertEqual(node["tree_spend"]["studies"], 2)
        self.assertEqual(node["tree_spend"]["tokens"], 100)


class TestDegenerateAndBrokenStudies(_Base):
    def test_zero_experiment_study_does_not_report_spend_as_zero(self):
        # the study-20260727T045848Z shape: capability/decide rows with no cost,
        # all real spend sitting in the report's process-side field
        arc = [{"seq": 1, "at": "2026-07-28T10:05:00+00:00",
                "move_type": "call_ideation", "cost": None, "results": []}]
        _write_study(self.root, "s", arc=arc, report={
            "decider_spend": {"calls": 68, "tokens": 15_171_280},
            "total_spend": {"calls": 68, "tokens": 15_171_280}})
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(node["own_spend"]["tokens"], 0)
        self.assertEqual(node["report_process_spend"]["tokens"], 15_171_280)
        self.assertEqual(node["grand_total_tokens"], 15_171_280)
        self.assertIn("15,171,280", CR.render_text(node))

    def test_process_spend_field_is_preferred_over_the_old_name(self):
        _write_study(self.root, "s", arc=[], report={
            "process_spend": {"calls": 3, "tokens": 300},
            "decider_spend": {"calls": 9, "tokens": 900}})
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(node["report_process_spend"], {"calls": 3, "tokens": 300})

    def test_process_residual_subtracts_arc_attributed_capability_spend(self):
        # post-metering shape: a capability row's cost came out of the same
        # process meter the report's delta reads, so the grand total must not
        # count it twice
        arc = [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00",
             "move_type": "call_ideation",
             "cost": {"calls": 4, "tokens": 400}, "results": []},
            {"seq": 2, "at": "2026-07-28T10:15:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 5000}, "results": []},
        ]
        _write_study(self.root, "s", arc=arc, report={
            "process_spend": {"calls": 10, "tokens": 1000}})
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(node["process_residual"], {"calls": 6, "tokens": 600})
        # tree (5400) + residual (600), NOT tree + full process delta (6400)
        self.assertEqual(node["grand_total_tokens"], 6000)

    def test_missing_study_reads_as_absent_not_a_crash(self):
        node = CR.study_cost_report("no-such-study", self.root)
        self.assertFalse(node["exists"])
        self.assertIn("no such study directory on disk", node["notes"])
        CR.render_text(node)  # must not raise either

    def test_truncated_study_with_no_arc_and_no_report(self):
        d = self.root / "s"
        d.mkdir()
        (d / "study.json").write_text(json.dumps({"study_id": "s", "goal": "g"}))
        node = CR.study_cost_report("s", self.root)
        self.assertTrue(node["exists"])
        self.assertEqual(node["rows"], [])
        self.assertIsNone(node["arc_source"])
        self.assertTrue(any("nothing recorded" in n for n in node["notes"]))
        CR.render_text(node)

    def test_torn_arc_line_is_skipped_and_counted(self):
        arc = [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 100}, "results": []},
            '{"seq": 2, "at": "2026-07-28T10:1',  # torn mid-append
        ]
        _write_study(self.root, "s", arc=arc)
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(len(node["rows"]), 1)
        self.assertEqual(node["torn_lines"], 1)
        self.assertTrue(any("unreadable arc line" in n for n in node["notes"]))

    def test_arc_falls_back_to_the_report_copy_when_arc_jsonl_is_missing(self):
        _write_study(self.root, "s", report={"arc": [
            {"seq": 1, "at": "2026-07-28T10:05:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 100}, "results": []}]})
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(len(node["rows"]), 1)
        self.assertEqual(node["arc_source"], "report.json (arc.jsonl missing)")

    def test_garbage_fields_degrade_per_row_not_per_study(self):
        arc = [
            {"seq": "x", "at": 12345, "move_type": None,
             "cost": "not-a-dict", "results": "not-a-list"},
            {"seq": 2, "at": "2026-07-28T10:15:00+00:00", "move_type": "single",
             "cost": {"calls": 1, "tokens": 500}, "results": []},
        ]
        _write_study(self.root, "s", arc=arc)
        node = CR.study_cost_report("s", self.root)
        self.assertEqual(len(node["rows"]), 2)
        self.assertEqual(node["rows"][0]["cost_source"], "unknown")
        self.assertEqual(node["rows"][1]["tokens"], 500)
        CR.render_text(node)


class TestRealCorpus(unittest.TestCase):
    """The instrument must hold against every study actually on disk. Skipped
    quietly on a machine without the studies/ evidence corpus."""

    def test_every_study_on_disk_reports_without_raising(self):
        if not STUDIES_ROOT.is_dir():
            self.skipTest("no studies/ corpus on this machine")
        ids = sorted(d.name for d in STUDIES_ROOT.iterdir() if d.is_dir())
        for sid in ids:
            node = CR.study_cost_report(sid, STUDIES_ROOT)
            self.assertTrue(node["exists"], sid)
            CR.render_text(node)  # rendering must not raise either

    def test_glider_tree_total_matches_the_hand_derived_number(self):
        # study-20260726T185547Z's root report says 18,919,715; arithmetic over
        # the three arcs proves the tree is 54,013,618 (roadmap item 1 brief).
        if not (STUDIES_ROOT / "study-20260726T185547Z").is_dir():
            self.skipTest("glider study not on this machine")
        node = CR.study_cost_report("study-20260726T185547Z", STUDIES_ROOT)
        self.assertEqual(node["tree_spend"]["tokens"], 54_013_618)
        self.assertEqual(node["tree_spend"]["studies"], 3)


if __name__ == "__main__":
    unittest.main()
