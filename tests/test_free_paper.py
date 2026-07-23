"""test_free_paper.py — the optional paper route for the free architecture.

Call-free: the paper agent is injected. Proves the write-up is sourced from the
WALL-VERIFIED findings (not the agent's self-report), copies paper.md up to the
run dir, and never raises on failure.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.free_paper import _validate, write_free_paper  # noqa: E402


class TestWriteFreePaper(unittest.TestCase):
    def _setup_run(self, verdicts, goal="q"):
        run_dir = Path("runs") / "pap"
        (run_dir / "workspace").mkdir(parents=True)
        (run_dir / "verification.json").write_text(json.dumps({"verdicts": verdicts}))
        (run_dir / "free_investigation.json").write_text(
            json.dumps({"goal": goal, "summary": "s"}))
        return run_dir

    def test_writes_paper_from_verified_findings_only(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self._setup_run([
                    {"label": "sum", "verified": True, "reproduced": 42},
                    {"label": "guess", "verified": False, "reason": "no_artifact"}])
                seen = {}

                def fake_call(stage, sp, inp, schema, **kw):
                    seen["input"] = inp
                    # the agent writes paper.md into its workspace (cwd in prod)
                    (Path("runs") / "pap" / "workspace" / "paper.md").write_text(
                        "# Paper\nsum = 42 (reproduced).")
                    return ({"paper_file": "paper.md", "figures": [],
                             "human_must_validate": ["check the 'guess' finding"]},
                            {"model": "f"})

                out = write_free_paper("pap", call=fake_call)
            finally:
                os.chdir(cwd)
        # the agent got ONLY the verified value as a result; the caveat separately
        self.assertEqual(seen["input"]["verified_findings"],
                         [{"label": "sum", "value": 42}])
        self.assertEqual(seen["input"]["unverified_findings"][0]["label"], "guess")
        self.assertTrue(out["paper_path"].endswith("paper.md"))
        self.assertIn("check the 'guess' finding", out["human_must_validate"])

    def test_no_run_dir_is_an_error_not_a_crash(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                out = write_free_paper("nope", call=lambda *a, **k: ({}, {}))
            finally:
                os.chdir(cwd)
        self.assertIn("error", out)

    def test_agent_failure_returns_error_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self._setup_run([{"label": "x", "verified": True, "reproduced": 1}])

                def boom(*a, **k):
                    raise RuntimeError("model down")

                out = write_free_paper("pap", call=boom)
            finally:
                os.chdir(cwd)
        self.assertIn("error", out)

    def test_reported_file_not_written_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            cwd = os.getcwd()
            os.chdir(d)
            try:
                self._setup_run([{"label": "x", "verified": True, "reproduced": 1}])
                out = write_free_paper(
                    "pap",
                    call=lambda *a, **k: (
                        {"paper_file": "paper.md", "human_must_validate": []},
                        {"model": "f"}))  # claims paper.md but writes nothing
            finally:
                os.chdir(cwd)
        self.assertIn("error", out)

    def test_validator(self):
        self.assertTrue(
            any("paper_file" in e for e in _validate({"human_must_validate": []})))
        self.assertEqual(
            _validate({"paper_file": "p.md", "human_must_validate": []}), [])


if __name__ == "__main__":
    unittest.main()
