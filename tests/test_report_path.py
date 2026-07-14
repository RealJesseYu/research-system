"""
test_report_path.py — 18-prep: per-launch kill-rate report isolation.

Tonight's Step-18 ledger runs THREE batteries in parallel; each must write
its machine report to its own file. These tests prove the --report-path
threading offline: run_battery is exercised with a STUBBED _launch_one
(zero model calls, zero sleeps, zero run dirs) so the REAL report-writing
path runs end-to-end; print_dry_run's stub-write behavior is proven the
same way. The default path stays byte-for-byte the historical behavior:
harness/killrate_last_run.json for a live battery, NOTHING written for a
default dry run.

Also pins the Step-18 memory checksum: EXPECTED_MEMORY_MD5 must equal the
battery's own derivation (md5[:8] of json.dumps(entries, indent=2)) over
the journal's current recent-3 learned summaries — the same read
stage1_ideation performs at runs/<id>/stage1/retrieved_memory.json write
time. If the journal gains learned summaries after 18-prep, this test
fails LOUDLY: re-derive and re-ruling, never silently.

Run directly: venv/bin/python3 tests/test_report_path.py
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness import killrate_battery

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class _IsolatedCwd:
    """18-hygiene mixin: chdir into an isolated tmp dir for the duration of the
    test and restore afterwards. Several suite modules (test_evolution,
    test_memory_reach, test_transport_retry, test_triage_battery) chdir into a
    TemporaryDirectory; if one of them errors AFTER os.chdir but before its
    tearDown restores cwd, the process's cwd is left pointing at a dir that is
    then cleaned up. A later test that does NOT chdir inherits that dead cwd —
    the shared-state/ordering cause of the flaky report-path failures observed
    in full-discovery mode (n=3). Capturing cwd defensively (getcwd itself
    raises FileNotFoundError on a deleted cwd) and pinning a fresh valid cwd
    makes these tests order-independent."""

    def _enter_isolated_cwd(self, tmpdir: Path) -> None:
        try:
            self._saved_cwd = os.getcwd()
        except (FileNotFoundError, OSError):
            # A prior test already left cwd on a deleted dir; restore to the
            # repo root rather than propagate the corruption.
            self._saved_cwd = str(_PROJECT_ROOT)
        os.chdir(tmpdir)

    def _leave_isolated_cwd(self) -> None:
        os.chdir(self._saved_cwd)


def _fake_record(slot: str, domain: str, rounds: int) -> dict:
    """A scored, comparable slot record with every key run_battery reads."""
    return {
        "run_id": f"killrate-fake-{slot}",
        "slot": slot,
        "wall_s": 0.0,
        "exception": None,
        "memory_md5": killrate_battery.EXPECTED_MEMORY_MD5,
        "comparable": True,
        "cost_delta": {"model_calls": {}, "attempts": {}},
        "reject_stats": {"total": {"calls": 0, "rejects": 0, "reject_rate": 0.0}},
        "signals": {},
        "status": "scored",
        "k": 1,
        "k_reason": None,
        "initial_survivor_count": 1,
        "deep_verify_discards": 0,
        "deep_verify_kill_rate": 0.0,
        "abort_reason": None,
        "variants_emitted": 0,
        "variants_accepted": 0,
        "variants_emitted_total": 0,
        "variants_accepted_total": 0,
        "rounds_completed": rounds,
        "termination_reason": "round_budget_exhausted",
    }


class StubbedBattery(_IsolatedCwd, unittest.TestCase):
    """run_battery with _launch_one stubbed: the real report path logic
    runs, nothing model-shaped fires, no runs/ dirs are created."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self._enter_isolated_cwd(self.tmpdir)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._leave_isolated_cwd)
        # The default report file is redirected into the temp dir so no
        # test can ever touch the repo's real killrate_last_run.json.
        self.default_path = self.tmpdir / "killrate_last_run.json"
        patches = [
            patch.object(killrate_battery, "KILLRATE_LAST_RUN_PATH", self.default_path),
            patch.object(killrate_battery, "INTER_RUN_SLEEP_S", 0),
            patch.object(
                killrate_battery,
                "_launch_one",
                side_effect=lambda slot, domain, rounds: _fake_record(slot, domain, rounds),
            ),
            patch.object(killrate_battery, "current_model_pins", return_value={}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_default_path_unchanged(self):
        """No report_path -> the report lands at KILLRATE_LAST_RUN_PATH."""
        rc = killrate_battery.run_battery(repeats=1)
        self.assertEqual(rc, 0)
        self.assertTrue(self.default_path.exists())
        report = json.loads(self.default_path.read_text())
        self.assertEqual(report["report_path"], str(self.default_path))

    def test_custom_path_used_and_default_untouched(self):
        """--report-path redirects the report; the default file is not written."""
        custom = self.tmpdir / "killrate_18_T1.json"
        rc = killrate_battery.run_battery(repeats=1, report_path=custom)
        self.assertEqual(rc, 0)
        self.assertTrue(custom.exists())
        self.assertFalse(self.default_path.exists())
        report = json.loads(custom.read_text())
        self.assertEqual(report["report_path"], str(custom))
        self.assertEqual(report["repeats"], 1)

    def test_two_distinct_paths_do_not_collide(self):
        """Two batteries with distinct report paths -> two distinct reports,
        each self-attributing, neither clobbered."""
        path_a = self.tmpdir / "killrate_18_T2.json"
        path_b = self.tmpdir / "killrate_18_T3.json"
        killrate_battery.run_battery(repeats=1, rounds=4, report_path=path_a)
        killrate_battery.run_battery(repeats=2, rounds=1, report_path=path_b)
        report_a = json.loads(path_a.read_text())
        report_b = json.loads(path_b.read_text())
        self.assertEqual(report_a["report_path"], str(path_a))
        self.assertEqual(report_b["report_path"], str(path_b))
        self.assertEqual((report_a["repeats"], report_a["rounds"]), (1, 4))
        self.assertEqual((report_b["repeats"], report_b["rounds"]), (2, 1))
        self.assertEqual(len(report_a["slots"]), 2)   # 1 repeat x 2 domains
        self.assertEqual(len(report_b["slots"]), 4)   # 2 repeats x 2 domains
        self.assertFalse(self.default_path.exists())


class DryRunStub(_IsolatedCwd, unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self._enter_isolated_cwd(self.tmpdir)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._leave_isolated_cwd)
        self.default_path = self.tmpdir / "killrate_last_run.json"
        p1 = patch.object(killrate_battery, "KILLRATE_LAST_RUN_PATH", self.default_path)
        p2 = patch.object(killrate_battery, "current_model_pins", return_value={})
        p1.start(); p2.start()
        self.addCleanup(p1.stop)
        self.addCleanup(p2.stop)

    def test_default_dry_run_writes_nothing(self):
        killrate_battery.print_dry_run(2, 1)
        self.assertFalse(self.default_path.exists())
        self.assertEqual(list(self.tmpdir.iterdir()), [])

    def test_explicit_report_path_writes_plan_stub(self):
        target = self.tmpdir / "killrate_18_T1.json"
        killrate_battery.print_dry_run(2, 1, report_path=target)
        stub = json.loads(target.read_text())
        self.assertTrue(stub["dry_run"])
        self.assertEqual(stub["mode"], "killrate")
        self.assertEqual((stub["repeats"], stub["rounds"]), (2, 1))
        self.assertEqual(stub["planned_slots"], ["same1", "same2", "alt1", "alt2"])
        self.assertFalse(self.default_path.exists())


class MemoryPin(unittest.TestCase):
    def test_pin_matches_live_journal_derivation(self):
        """EXPECTED_MEMORY_MD5 == the battery's own derivation over the
        journal as it stands. Fails loudly the moment the journal gains a
        learned summary after 18-prep."""
        from memory.journal import journal_recent_by_kind

        entries = journal_recent_by_kind("learned_summary", 3)
        derived = hashlib.md5(
            json.dumps(entries, indent=2).encode()
        ).hexdigest()[:8]
        self.assertEqual(killrate_battery.EXPECTED_MEMORY_MD5, derived)


if __name__ == "__main__":
    unittest.main()
