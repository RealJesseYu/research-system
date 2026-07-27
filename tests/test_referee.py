"""test_referee.py — the artifact review of a finished study paper.

Call-free (the referee agent is injected; no model calls). Proves:
  - a study with no paper.md is refused honestly ({error}, no raise);
  - the review bundle handed to the agent contains the paper, the wall's
    claims (with code), and the verified/unverified split;
  - findings land in referee.json + referee_report.md beside the paper;
  - high/med findings are APPENDED to paper.md deterministically; low-severity
    ones stay in the report; zero findings append nothing;
  - the schema validator rejects a finding without evidence or with a category
    outside the taxonomy;
  - REFEREE=0 disables; a crashing agent returns {error} and never raises.

Run directly: venv/bin/python3 tests/test_referee.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from stages.referee import (_validate, referee_study_paper,  # noqa: E402
                            referee_study_paper_by_id)


def _mk_study(root: Path):
    study = S.create_study("test goal", studies_root=root)
    S.record_move(
        study,
        MoveResult(move_type="single", run_id="r-referee-test", succeeded=True,
                   outcome="completed",
                   raw={"findings": [
                       {"label": "swept e", "value": 1.5, "verified": True},
                       {"label": "unrepro", "value": 9.9, "verified": False},
                   ]}),
        finding="why this phase",
    )
    return study


def _finding(sev="high", cat="mechanism_mismatch"):
    return {"id": "R-01", "category": cat,
            "claim": "label says swept, code hardcodes",
            "evidence": "code line `e = 2` vs paper section 3",
            "severity": sev, "confidence": 0.9}


class RefereeTests(unittest.TestCase):
    def setUp(self):
        os.environ.pop("REFEREE", None)
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = _mk_study(self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_no_paper_is_honest_error(self):
        out = referee_study_paper(self.study, call=lambda *a, **k: (_ for _ in ()))
        self.assertIn("error", out)
        self.assertIn("no paper.md", out["error"])

    def test_bundle_reaches_agent_and_reports_land(self):
        (self.study.dir / "paper.md").write_text("# P\nVERIFIED 1.5 swept e\n")
        seen = {}

        def fake_call(stage, prompt, stage_input, schema, **kw):
            # agent_workspace scopes the TOOLED transport's cwd via a
            # contextvar (it never chdirs this process) — read it the way the
            # transport does, which also proves the workspace was set.
            from model_call import _AGENT_CWD
            cwd = Path(_AGENT_CWD.get())
            seen["files"] = sorted(p.name for p in cwd.iterdir())
            seen["findings_json"] = json.loads((cwd / "findings.json").read_text())
            return ({"findings": [_finding("high"), _finding("low")],
                     "summary": "one real, one nit"}, {})

        out = referee_study_paper(self.study, call=fake_call)
        self.assertNotIn("error", out)
        self.assertEqual(seen["files"],
                         ["claims.json", "findings.json", "paper.md"])
        self.assertEqual(
            [f["value"] for f in seen["findings_json"]["verified"]], [1.5])
        self.assertEqual(
            [f["value"] for f in seen["findings_json"]["unverified"]], [9.9])
        report = json.loads((self.study.dir / "referee.json").read_text())
        self.assertEqual(len(report["findings"]), 2)
        self.assertTrue((self.study.dir / "referee_report.md").is_file())

    def test_high_med_appended_low_not(self):
        (self.study.dir / "paper.md").write_text("# P\n")
        call = lambda *a, **k: ({"findings": [_finding("high"),
                                              _finding("low")],
                                 "summary": "s"}, {})  # noqa: E731
        out = referee_study_paper(self.study, call=call)
        self.assertEqual(out["appended"], 1)
        text = (self.study.dir / "paper.md").read_text()
        self.assertIn("## Referee findings (artifact review)", text)
        self.assertEqual(text.count("label says swept"), 1)  # high only

    def test_zero_findings_append_nothing(self):
        (self.study.dir / "paper.md").write_text("# P\n")
        call = lambda *a, **k: ({"findings": [], "summary": "clean"}, {})  # noqa: E731
        out = referee_study_paper(self.study, call=call)
        self.assertEqual(out["appended"], 0)
        self.assertNotIn("Referee findings",
                         (self.study.dir / "paper.md").read_text())

    def test_validator_rejects_bad_findings(self):
        self.assertTrue(_validate({"findings": [{"id": "R-01",
                                                 "category": "vibes",
                                                 "severity": "high",
                                                 "evidence": "x"}]}))
        self.assertTrue(_validate({"findings": [dict(_finding(),
                                                     evidence="  ")]}))
        self.assertEqual(_validate({"findings": [_finding()],
                                    "summary": "s"}), [])

    def test_kill_switch_and_crash_paths(self):
        (self.study.dir / "paper.md").write_text("# P\n")
        os.environ["REFEREE"] = "0"
        try:
            out = referee_study_paper(self.study,
                                      call=lambda *a, **k: (None, None))
            self.assertIn("error", out)
        finally:
            os.environ.pop("REFEREE", None)

        def boom(*a, **k):
            raise RuntimeError("agent died")
        out = referee_study_paper(self.study, call=boom)
        self.assertIn("error", out)
        self.assertIn("referee review failed", out["error"])

    def test_by_id_missing_study_is_error(self):
        out = referee_study_paper_by_id("nope", studies_root=self.root,
                                        call=lambda *a, **k: (None, None))
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
