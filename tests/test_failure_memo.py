"""
test_failure_memo.py — code-authored failure memos (19-lite/retry build).

ZERO model calls: the memo is built purely from on-disk baton snapshots. Covers
every required section, byte-stability, multi-pass rendering + loop-bound
inference, graceful behavior on an empty/absent run dir, and — crucially — that
the file the producer writes is the exact file the R-WIN-1 reader glob finds.

Run directly: venv/bin/python3 tests/test_failure_memo.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.failure_memo import MEMO_FILENAME, write_failure_memo


def _snap(run_dir: Path, name: str, payload: dict) -> None:
    (run_dir / name).write_text(json.dumps({"payload": payload}))


def _build_total_defer_run(run_dir: Path) -> None:
    """A single-pass total-defer run: defer verdict, nothing executed, exit."""
    domain = "passive mixing in laminar lid-driven cavity flows"
    chosen = {"id": "h2", "statement": "concentration-variance decay peaks above Re_c"}
    spec = {"qoi": {"name": "concentration_variance_decay_rate"}}
    verdict = {
        "label": "defer",
        "rationale": "The 2D velocity-only substrate carries no scalar-transport physics.",
        "right_instrument": "none — route to human/real experiment",
    }
    _snap(run_dir, "baton_after_stage_1.json", {"domain": domain, "hypotheses": []})
    _snap(run_dir, "baton_after_gate_1.json", {"domain": domain, "chosen_hypothesis": chosen})
    _snap(
        run_dir,
        "baton_after_stage_2.json",
        {"domain": domain, "chosen_hypothesis": chosen, "experiment_spec": spec},
    )
    _snap(
        run_dir,
        "baton_after_stage_3.json",
        {"domain": domain, "chosen_hypothesis": chosen, "experiment_spec": spec,
         "fidelity_verdict": verdict},
    )
    _snap(
        run_dir,
        "baton_after_stage_4.json",
        {"domain": domain, "experiment_spec": spec, "fidelity_verdict": verdict,
         "execution_results": {"status": "skipped_defer"}},
    )
    _snap(
        run_dir,
        "baton_after_stage_5.json",
        {"domain": domain, "experiment_spec": spec, "fidelity_verdict": verdict,
         "execution_results": {"status": "skipped_defer"}, "iterate_decision": "exit"},
    )


REQUIRED_SECTIONS = (
    "FAILURE MEMO — run",
    "DOMAIN / ASK:",
    "CHOSEN HYPOTHESIS:",
    "REQUESTED QoI:",
    "FIDELITY VERDICTS (by pass):",
    "GATE-5 DECISIONS (by pass):",
    "EXECUTION:",
    "QoI / EXTRACTION BLOCKERS:",
    "LOOP-BOUND STATE:",
)


class TestMemoContent(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name) / "20260704T090024Z"
        self.run_dir.mkdir()
        _build_total_defer_run(self.run_dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_all_required_sections_present(self):
        path = write_failure_memo(self.run_dir)
        self.assertIsNotNone(path)
        text = path.read_text()
        for section in REQUIRED_SECTIONS:
            self.assertIn(section, text, f"missing section: {section}")
        # Content sanity.
        self.assertIn("passive mixing in laminar lid-driven cavity flows", text)
        self.assertIn("h2", text)
        self.assertIn("concentration_variance_decay_rate", text)
        self.assertIn("pass 1: defer", text)
        self.assertIn("pass 1: exit", text)
        self.assertIn("0 solver run(s) executed", text)
        self.assertIn("0 loop-back(s) observed", text)

    def test_byte_stable(self):
        path = write_failure_memo(self.run_dir)
        first = path.read_text()
        second_path = write_failure_memo(self.run_dir)
        self.assertEqual(first, second_path.read_text())

    def test_filename_is_memo_filename(self):
        path = write_failure_memo(self.run_dir)
        self.assertEqual(path.name, MEMO_FILENAME)


class TestMultiPass(unittest.TestCase):
    def test_per_pass_and_loop_bound_inference(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "multi"
        run_dir.mkdir()
        _build_total_defer_run(run_dir)
        # Add a pass-2 stage-3 and stage-5: highest pass = 2 -> 1 loop-back.
        _snap(run_dir, "baton_after_stage_3_pass2.json",
              {"fidelity_verdict": {"label": "refine", "rationale": "finer solve could correct"}})
        _snap(run_dir, "baton_after_stage_5_pass2.json", {"iterate_decision": "more_data"})
        text = write_failure_memo(run_dir).read_text()
        self.assertIn("pass 1: defer", text)
        self.assertIn("pass 2: refine", text)
        self.assertIn("pass 1: exit", text)
        self.assertIn("pass 2: more_data", text)
        self.assertIn("1 loop-back(s) observed", text)
        self.assertIn("highest pass = 2", text)


class TestRobustness(unittest.TestCase):
    def test_empty_run_dir_never_raises(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_dir = Path(tmp.name) / "empty"
        run_dir.mkdir()
        path = write_failure_memo(run_dir)  # no snapshots at all
        self.assertIsNotNone(path)
        text = path.read_text()
        self.assertIn("(unknown)", text)
        self.assertIn("(no fidelity verdict on disk)", text)

    def test_absent_run_dir_returns_none(self):
        self.assertIsNone(write_failure_memo(Path("/no/such/run/dir/at/all")))


class TestReaderGlobMatch(unittest.TestCase):
    """The producer's file is the exact file the R-WIN-1 reader glob finds."""

    def test_reader_finds_written_memo(self):
        from stages import generation_strategies as gs

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run_id = "readerglob-run"
        cwd = os.getcwd()
        try:
            os.chdir(tmp.name)  # reader globs the RELATIVE runs/<id>/ path
            run_dir = Path("runs") / run_id
            run_dir.mkdir(parents=True)
            _build_total_defer_run(run_dir)
            written = write_failure_memo(run_dir)
            self.assertTrue(written.match("*failure_memo*.txt"))  # producer side
            found = gs.read_recent_failure_memo(run_id)  # reader side
            self.assertIsNotNone(found)
            self.assertIn("FAILURE MEMO — run", found)
        finally:
            os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
