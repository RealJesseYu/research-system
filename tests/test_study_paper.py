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


# --------------------------------------------------------------------------
# Citation check — found live in study-20260725T073215Z, where the paper agent
# wrote an unverified ratio into Results labelled "independently reproduced".
# --------------------------------------------------------------------------

from stages.study_paper import (_correction_block,  # noqa: E402
                                unsupported_reproduction_claims)


class TestCitationCheck(unittest.TestCase):
    def test_flags_a_rejected_value_claimed_as_reproduced(self):
        """The exact live failure: the wall rejected 128.0 (it reproduced as
        127.49004) and the paper called it independently reproduced."""
        line = "- Ratio at D=64: **128** — *independently reproduced*."
        out = unsupported_reproduction_claims(line, [64.0], [128.0])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["values"], [128.0])

    def test_a_verified_value_is_not_flagged(self):
        line = "- Ratio at D=32: **64** — *independently reproduced*."
        self.assertEqual(unsupported_reproduction_claims(line, [64.0], [128.0]), [])

    def test_rounding_is_tolerated(self):
        """A paper legitimately rounds; the check catches rejected values, not
        significant figures."""
        line = "- Converged mass **16.8731** kg — *independently reproduced*."
        self.assertEqual(
            unsupported_reproduction_claims(line, [16.87314], [999.0]), [])

    def test_a_line_that_makes_no_reproduction_claim_is_ignored(self):
        """Mentioning an unverified number is fine — Limitations must be able to
        discuss it. Only asserting reproduction is policed."""
        line = "- The D=64 ratio of 128 did not reproduce and is reported as a caveat."
        self.assertEqual(unsupported_reproduction_claims(line, [64.0], [128.0]), [])

    def test_the_exact_live_line_is_flagged(self):
        """THE REGRESSION THAT MATTERS. An earlier version of this check exempted a
        line that also carried a verified number. On the real line, '64' is a
        DIMENSION LABEL (D=64) that happens to equal the verified D=32 ratio, so
        the exemption excused the very defect the check exists to catch."""
        line = ("- Forward-FE-solve ratio FD/adjoint at D=64, matched convergence "
                "(tol=1e-5): **128x** — *independently reproduced*.")
        out = unsupported_reproduction_claims(line, [64.0], [128.0])
        self.assertEqual(len(out), 1)
        self.assertIn(128.0, out[0]["values"])

    def test_a_value_verified_in_one_phase_is_not_flagged_elsewhere(self):
        """CALIBRATED AGAINST THE REAL PAPER. A study can measure the same quantity
        twice and have it reproduce in one phase but not another (live: a converged
        mass verified at phase 4, unverified at phase 3). Citing the value that DID
        reproduce is legitimate — flagging it produced 6 false positives."""
        line = "- Converged mass 16.86625 kg — *independently reproduced*."
        self.assertEqual(
            unsupported_reproduction_claims(line, [16.86625], [16.8662]), [])

    def test_an_honest_disclaimer_line_is_not_flagged(self):
        """A Limitations line saying a number did NOT reproduce contains a marker
        substring but is the opposite of an over-claim; flagging it would punish
        exactly the honesty the paper is asked for."""
        line = ("- **Unverified:** the FE validation of 1.18e-13 was not reproduced "
                "by the re-run.")
        self.assertEqual(unsupported_reproduction_claims(line, [], [1.18e-13]), [])

    def test_a_figure_caption_over_claiming_is_flagged(self):
        """The live paper over-claimed in a caption as well as in Results."""
        line = "![Ratio doubles to 128x. Both points independently reproduced.](f.png)"
        self.assertEqual(
            len(unsupported_reproduction_claims(line, [64.0], [128.0])), 1)

    def test_the_correction_block_names_the_values(self):
        block = _correction_block([{"line": "bad claim", "values": [128.0]}])
        self.assertIn("Correction", block)
        self.assertIn("128.0", block)
        self.assertIn("must not be relied on", block)

    def test_check_never_raises_on_junk(self):
        for junk in (None, "", "no numbers here reproduced by magic"):
            unsupported_reproduction_claims(junk, [1.0], [2.0])


class TestCorrectionIsAppendedToTheSavedPaper(StudyPaperTestCase):
    def test_an_overclaiming_paper_gets_a_correction_appended(self):
        _record(self.study, results=[
            {"label": "good", "value": 64.0, "verified": True},
            {"label": "bad", "value": 128.0, "verified": False}])

        def call(stage, sp, inp, schema, **kw):
            (S.study_scratch_dir(self.study) / "paper.md").write_text(
                "# P\n- Ratio 128 — independently reproduced.\n")
            return ({"paper_file": "paper.md", "figures": [],
                     "human_must_validate": []}, {})

        out = write_study_paper(self.study, call=call)
        saved = (self.study.dir / "paper.md").read_text()
        self.assertIn("Correction", saved)
        self.assertIn("128.0", saved)
        self.assertEqual(len(out["unsupported_claims"]), 1)

    def test_an_honest_paper_is_saved_unchanged(self):
        _record(self.study, results=[{"label": "good", "value": 64.0, "verified": True}])

        def call(stage, sp, inp, schema, **kw):
            (S.study_scratch_dir(self.study) / "paper.md").write_text(
                "# P\n- Ratio 64 — independently reproduced.\n")
            return ({"paper_file": "paper.md", "figures": [],
                     "human_must_validate": []}, {})

        out = write_study_paper(self.study, call=call)
        self.assertEqual(out["unsupported_claims"], [])
        self.assertNotIn("Correction", (self.study.dir / "paper.md").read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
