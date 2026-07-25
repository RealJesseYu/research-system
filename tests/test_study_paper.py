"""test_study_paper.py — the study-level write-up (task 2).

Before this, a director-run study produced NO paper at all: free_paper.py writes
up ONE run, the director never invoked it, and dispatch looked for a paper at a
deleted-pipeline path that could never exist.

Call-free (the paper agent is injected; no model calls, no Docker). Proves:
  - the agent is given ONLY the wall-verified numbers as results, with unverified
    ones separated as caveats — the split is made in Python, never left to the
    writing agent;
  - the arc's shape (which phase produced what, and why) reaches the paper;
  - a study where NOTHING reproduced is refused honestly rather than written up;
  - paper.md and its figures land beside the study so relative links resolve;
  - a figure the agent named but never wrote is skipped, not faked;
  - every failure path returns an error and never raises.

Run directly: venv/bin/python3 tests/test_study_paper.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.study as S  # noqa: E402
from pi_agent.dispatch import MoveResult  # noqa: E402
from stages.study_paper import (_validate, collect_study_evidence,  # noqa: E402
                                write_study_paper, write_study_paper_by_id)


def _record(study, *, results=(), move_type="single", finding="why", artifacts=()):
    S.record_move(
        study,
        MoveResult(move_type=move_type, run_id="r", succeeded=True,
                   outcome="completed",
                   raw={"findings": list(results),
                        "reusable_artifacts": list(artifacts)}),
        finding=finding,
    )


class StudyPaperTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.study = S.create_study("does the arm design hold?", studies_root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def _agent(self, *, figures=(), write_figures=True, paper=True):
        """A fake paper agent that writes into whatever cwd it was given."""
        seen = {}

        def fake_call(stage, sp, inp, schema, **kw):
            seen["input"] = inp
            scratch = S.study_scratch_dir(self.study)
            if paper:
                (scratch / "paper.md").write_text("# Paper\nreach = 0.42 (reproduced).")
            if write_figures:
                for f in figures:
                    (scratch / f).write_bytes(b"\x89PNG")
            return ({"paper_file": "paper.md", "figures": list(figures),
                     "human_must_validate": ["check the unverified guess"]},
                    {"model": "fake"})

        return fake_call, seen


class TestEvidenceCollection(StudyPaperTestCase):
    def test_verified_and_unverified_are_split_in_python(self):
        _record(self.study, results=[
            {"label": "reach", "value": 0.42, "verified": True},
            {"label": "guess", "value": 9.9, "verified": False}])
        ev = collect_study_evidence(self.study)
        self.assertEqual([f["label"] for f in ev["verified_findings"]], ["reach"])
        self.assertEqual([f["label"] for f in ev["unverified_findings"]], ["guess"])
        self.assertEqual(ev["counts"], {"verified": 1, "unverified": 1, "phases": 1})

    def test_arc_shape_travels(self):
        """The paper must be able to describe the investigation, not just list
        numbers — so which phase produced what, and why, reaches the agent."""
        _record(self.study, move_type="single", finding="probe the cheap case",
                results=[{"label": "a", "value": 1, "verified": True}])
        _record(self.study, move_type="call_integration", finding="do they compose?",
                results=[{"label": "joint", "value": 2, "verified": True}])
        ev = collect_study_evidence(self.study)
        self.assertEqual([p["phase"] for p in ev["arc"]], ["single", "call_integration"])
        self.assertEqual(ev["arc"][1]["why_this_phase"], "do they compose?")
        self.assertEqual(ev["verified_findings"][1]["from_phase"], 2)

    def test_reusable_artifacts_are_named(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}],
                artifacts=[{"name": "arm.json", "producer": {"kind": "code"}}])
        ev = collect_study_evidence(self.study)
        self.assertEqual(ev["reusable_artifacts"], [{"name": "arm.json"}])


class TestWriteStudyPaper(StudyPaperTestCase):
    def test_agent_sees_only_verified_numbers_as_results(self):
        _record(self.study, results=[
            {"label": "reach", "value": 0.42, "verified": True},
            {"label": "guess", "value": 9.9, "verified": False}])
        call, seen = self._agent()
        out = write_study_paper(self.study, call=call)
        self.assertEqual([f["label"] for f in seen["input"]["verified_findings"]],
                         ["reach"])
        self.assertEqual(seen["input"]["unverified_findings"][0]["label"], "guess")
        self.assertTrue(out["paper_path"].endswith("paper.md"))
        self.assertIn("check the unverified guess", out["human_must_validate"])

    def test_paper_lands_beside_the_study(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])
        call, _ = self._agent()
        write_study_paper(self.study, call=call)
        self.assertTrue((self.study.dir / "paper.md").is_file())

    def test_figures_are_copied_beside_the_paper(self):
        """paper.md embeds figures with relative links, so they must sit next to
        it where a reader opens it."""
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])
        call, _ = self._agent(figures=["fig1.png"])
        out = write_study_paper(self.study, call=call)
        self.assertEqual(out["figures"], ["fig1.png"])
        self.assertTrue((self.study.dir / "fig1.png").is_file())

    def test_a_figure_named_but_never_written_is_skipped_not_faked(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])
        call, _ = self._agent(figures=["ghost.png"], write_figures=False)
        out = write_study_paper(self.study, call=call)
        self.assertEqual(out["figures"], [])
        self.assertFalse((self.study.dir / "ghost.png").exists())

    def test_a_figure_path_escaping_the_dir_is_refused(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])
        call, _ = self._agent(figures=["../escape.png"])
        out = write_study_paper(self.study, call=call)
        self.assertEqual(out["figures"], [])


class TestHonestRefusals(StudyPaperTestCase):
    def test_a_study_where_nothing_reproduced_is_refused(self):
        """Writing this up would dress narration as findings — the exact failure
        the verification wall exists to prevent."""
        _record(self.study, results=[{"label": "guess", "value": 9.9, "verified": False}])
        called = []
        out = write_study_paper(self.study, call=lambda *a, **k: called.append(1))
        self.assertIn("nothing reproduced", out["error"])
        self.assertEqual(called, [])  # no spend on an unwritable paper

    def test_an_empty_study_is_refused(self):
        out = write_study_paper(self.study, call=lambda *a, **k: None)
        self.assertIn("error", out)

    def test_an_agent_failure_is_an_error_not_a_crash(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])

        def boom(*a, **k):
            raise RuntimeError("transport died")

        out = write_study_paper(self.study, call=boom)
        self.assertIn("transport died", out["error"])

    def test_agent_that_reports_a_file_it_never_wrote(self):
        _record(self.study, results=[{"label": "a", "value": 1, "verified": True}])
        call, _ = self._agent(paper=False)
        out = write_study_paper(self.study, call=call)
        self.assertIn("no such file", out["error"])

    def test_unknown_study_id_is_an_error(self):
        out = write_study_paper_by_id("nope", studies_root=self.root)
        self.assertIn("no such study", out["error"])


class TestValidator(unittest.TestCase):
    def test_requires_a_paper_file_and_a_validate_list(self):
        self.assertEqual(_validate({"paper_file": "paper.md",
                                    "human_must_validate": []}), [])
        self.assertTrue(_validate({"paper_file": "", "human_must_validate": []}))
        self.assertTrue(_validate({"paper_file": "p.md", "human_must_validate": "x"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
