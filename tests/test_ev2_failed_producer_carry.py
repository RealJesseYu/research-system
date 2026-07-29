"""test_ev2_failed_producer_carry.py — A4 / ev2 (2026-07-29): failed producers
persist, tagged with how they broke, and travel the carry bus as negative
examples.

ev2 (ideation, untested): continuity is carried better by a corpus that
includes failed/superseded re-executable producers — error-tagged, like immune
negative selection — than by a success-only library, because success-only
chains lose the ability to detect that the regime has shifted. Its
memory-policy ancestor was REFUTED (it substituted for history); this is the
ARTIFACT-level form, beside the carry bus, adding a block and removing
nothing. It is a HYPOTHESIS being instrumented for a future measured run, not
a proven fix.

The chain proven offline here:
  free_investigation.json (verified:false + error, already recorded)
    -> dispatch reads them into RunResult.failed_artifacts
    -> record_move maps them to a first-class arc column (only when non-empty)
    -> study_findings surfaces them to the director
    -> _integration_context collects a bounded negative store
       (a failure superseded by a verified same-name file is dropped)
    -> _carry_block appends the clearly-labelled may-use-or-ignore section.

Run directly: venv/bin/python3 tests/test_ev2_failed_producer_carry.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.dispatch import (_read_failed_artifacts,  # noqa: E402
                               MoveResult, read_run_result)
from pi_agent.free_director import (_brief, _carry_block,  # noqa: E402
                                    _integration_context, MAX_CARRIED_FAILED)

PROD = {"kind": "code", "code": "c", "quantity": "n", "emits": ["f"]}


def _write_investigation(run_dir: Path, artifacts):
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "free_investigation.json").write_text(
        json.dumps({"reusable_artifacts": artifacts}))


class TestDispatchReadsFailures(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "r1"

    def tearDown(self):
        self._tmp.cleanup()

    def test_only_unverified_producers_are_read_with_their_reason(self):
        _write_investigation(self.run_dir, [
            {"name": "good.py", "producer": PROD, "verified": True, "error": None},
            {"name": "bad.py", "producer": PROD, "verified": False,
             "error": "producer did not re-emit bad.py"},
        ])
        failed = _read_failed_artifacts(self.run_dir)
        self.assertEqual([f["name"] for f in failed], ["bad.py"])
        self.assertIn("did not re-emit", failed[0]["broke"])

    def test_a_missing_reason_reads_honest_not_blank(self):
        _write_investigation(self.run_dir, [
            {"name": "bad.py", "producer": PROD, "verified": False}])
        self.assertIn("no reason recorded",
                      _read_failed_artifacts(self.run_dir)[0]["broke"])

    def test_a_huge_error_is_capped(self):
        _write_investigation(self.run_dir, [
            {"name": "bad.py", "producer": PROD, "verified": False,
             "error": "x" * 5000}])
        self.assertLessEqual(len(_read_failed_artifacts(self.run_dir)[0]["broke"]),
                             300)

    def test_missing_or_malformed_file_is_no_failures_never_a_crash(self):
        self.assertEqual(_read_failed_artifacts(self.run_dir), [])
        self.run_dir.mkdir(parents=True)
        (self.run_dir / "free_investigation.json").write_text("{torn")
        self.assertEqual(_read_failed_artifacts(self.run_dir), [])

    def test_read_run_result_carries_them_and_keeps_reusables_verified_only(self):
        _write_investigation(self.run_dir, [
            {"name": "good.py", "producer": PROD, "verified": True},
            {"name": "bad.py", "producer": PROD, "verified": False, "error": "e"},
        ])
        rr = read_run_result(self.run_dir, "r1", 0, None)
        self.assertEqual([a["name"] for a in rr.reusable_artifacts], ["good.py"])
        self.assertEqual([a["name"] for a in rr.failed_artifacts], ["bad.py"])
        self.assertEqual(rr.as_dict()["failed_artifacts"], rr.failed_artifacts)


class ArcCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("g", study_id="s", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _record(self, run_id, raw):
        S.record_move(self.study,
                      MoveResult("single", run_id, True, "completed", raw))


class TestArcColumn(ArcCase):
    def test_failed_artifacts_are_a_first_class_column_not_tool_output(self):
        fa = [{"name": "bad.py", "producer": PROD, "broke": "regime shifted"}]
        self._record("s-m1", {"failed_artifacts": fa})
        entry = json.loads(self.study.arc_path.read_text().strip())
        self.assertEqual(entry["failed_artifacts"], fa)
        self.assertNotIn("failed_artifacts", entry["tool_output"])

    def test_without_failures_the_arc_line_is_byte_identical_to_before(self):
        self._record("s-m1", {"publishable": True})
        entry = json.loads(self.study.arc_path.read_text().strip())
        self.assertNotIn("failed_artifacts", entry)

    def test_study_findings_surfaces_them_to_the_director(self):
        fa = [{"name": "bad.py", "producer": PROD, "broke": "e"}]
        self._record("s-m1", {"failed_artifacts": fa})
        self._record("s-m2", {})
        e1, e2 = S.study_findings(self.study)
        self.assertEqual(e1["failed_artifacts"], fa)
        self.assertNotIn("failed_artifacts", e2)


class TestCarryBus(ArcCase):
    def test_the_negative_store_is_collected_with_provenance(self):
        self._record("s-m1", {"failed_artifacts": [
            {"name": "bad.py", "producer": PROD, "broke": "overflow at N>1e6"}]})
        ctx = _integration_context(self.study)
        self.assertEqual(len(ctx["failed"]), 1)
        self.assertEqual(ctx["failed"][0]["from"], "s-m1")
        self.assertEqual(ctx["failed"][0]["broke"], "overflow at N>1e6")

    def test_a_failure_superseded_by_a_verified_same_name_file_is_dropped(self):
        self._record("s-m1", {"failed_artifacts": [
            {"name": "design.py", "producer": PROD, "broke": "v1 broke"}]})
        self._record("s-m2", {"reusable_artifacts": [
            {"name": "design.py", "producer": PROD}]})
        ctx = _integration_context(self.study)
        self.assertEqual(ctx["failed"], [])          # the fix carries instead
        self.assertEqual([f["name"] for f in ctx["files"]], ["design.py"])

    def test_the_negative_store_is_bounded(self):
        for i in range(MAX_CARRIED_FAILED + 3):
            self._record(f"s-m{i+1}", {"failed_artifacts": [
                {"name": f"bad{i}.py", "producer": PROD, "broke": "e"}]})
        self.assertEqual(len(_integration_context(self.study)["failed"]),
                         MAX_CARRIED_FAILED)

    def test_carry_block_appends_the_may_use_or_ignore_section(self):
        block = _carry_block(
            [{"name": "good.py", "producer": PROD}],
            [{"name": "bad.py", "producer": PROD, "broke": "regime shifted"}])
        self.assertIn("BUILD ON", block)
        self.assertIn("PRODUCERS THAT FAILED", block)
        self.assertIn("regime shifted", block)
        self.assertIn("use or ignore", block)        # information, not instruction

    def test_success_only_carry_is_byte_identical_to_before_ev2(self):
        files = [{"name": "good.py", "producer": PROD}]
        self.assertEqual(_carry_block(files), _carry_block(files, []))
        self.assertNotIn("PRODUCERS THAT FAILED", _carry_block(files))
        self.assertEqual(_carry_block([], []), "")

    def test_the_brief_carries_the_negative_store_to_a_dispatched_move(self):
        self._record("s-m1", {"failed_artifacts": [
            {"name": "bad.py", "producer": PROD, "broke": "diverged at Re>300"}]})
        brief = _brief("next question?", self.study, {"reasoning": "r"})
        self.assertIn("PRODUCERS THAT FAILED", brief)
        self.assertIn("diverged at Re>300", brief)


if __name__ == "__main__":
    unittest.main()
