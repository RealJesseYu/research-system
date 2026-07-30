"""test_study_deliverable.py — C1: study-close packaging.

Call-free (the model choosing files is injected; no model calls, no Docker).
Proves:
  - candidates are built ENTIRELY from tools.run_code_snapshot.py's own
    classification: small/code-shaped files surface as "kept", legitimately
    big/off-whitelist files surface as "other" with their skip reason, and
    anything run_code_snapshot refuses for safety (credential-shaped names,
    dotfiles, symlinks, escapes) never surfaces as a candidate at all;
  - the study's director_workspace is included as a candidate source beside
    every move's runs/<id>/workspace;
  - a chosen (run_id, path) not present in the offered candidates is refused,
    never copied, never re-asked;
  - evidence and deliverable size/count caps are real backstops, hit
    smallest-file-first so a single huge choice cannot starve small ones;
  - a basename collision across two workspaces is resolved deterministically
    and reproduce_steps text is rewritten to match;
  - the README is written by Python, never by the selecting model;
  - every failure path (no paper, disabled, nothing chosen, bad call) returns
    an error and never raises.

Run directly: venv/bin/python3 tests/test_study_deliverable.py
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
from stages.study_deliverable import (  # noqa: E402
    DIRECTOR_WORKSPACE_ID, _assign_final_names, _candidate_set,
    _legit_data_skip, _substitute_final_names, _validate,
    package_study_deliverable, package_study_deliverable_by_id,
    workspace_candidates,
)


def _write(path: Path, content: bytes | str = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        content = content.encode()
    path.write_bytes(content)


class DeliverableTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._owd = os.getcwd()
        os.chdir(self.root)
        self.study = S.create_study("build a thing", studies_root=Path("studies"))
        (self.study.dir / "paper.md").write_text("# Paper\nheadline (reproduced).")

    def tearDown(self):
        os.chdir(self._owd)
        self._tmp.cleanup()

    def _record_move(self, run_id, *, results=()):
        S.record_move(
            self.study,
            MoveResult(move_type="single", run_id=run_id, succeeded=True,
                      outcome="completed",
                      raw={"findings": list(results)}),
            finding="why",
        )

    def _workspace(self, run_id):
        d = Path("runs") / run_id / "workspace"
        d.mkdir(parents=True, exist_ok=True)
        return d


class TestCandidateBuilding(DeliverableTestCase):
    def test_kept_files_surface_as_deliverable_candidates(self):
        self._record_move("r1")
        ws = self._workspace("r1")
        _write(ws / "lib.h", "int x;")
        cands = workspace_candidates(self.study)
        self.assertEqual([c["path"] for c in cands["r1"]["kept"]], ["lib.h"])

    def test_big_offwhitelist_files_surface_as_other_with_their_reason(self):
        self._record_move("r1")
        ws = self._workspace("r1")
        _write(ws / "data.bin", b"\x00" * 1000)
        cands = workspace_candidates(self.study)
        other = cands["r1"]["other"]
        self.assertEqual([c["path"] for c in other], ["data.bin"])
        self.assertIn("extension .bin not on the whitelist", other[0]["skipped_because"])
        self.assertEqual(other[0]["bytes"], 1000)

    def test_credential_shaped_files_never_become_candidates(self):
        self._record_move("r1")
        ws = self._workspace("r1")
        _write(ws / ".env", "SECRET=1")
        _write(ws / "id_rsa", "not a real key")
        cands = workspace_candidates(self.study)
        all_paths = {c["path"] for c in cands["r1"]["kept"]} | \
                   {c["path"] for c in cands["r1"]["other"]}
        self.assertNotIn(".env", all_paths)
        self.assertNotIn("id_rsa", all_paths)

    def test_legit_data_skip_excludes_safety_reasons(self):
        self.assertTrue(_legit_data_skip("extension .bin not on the whitelist"))
        self.assertTrue(_legit_data_skip("1,000,000 bytes over the 65,536 cap (data, not source)"))
        self.assertFalse(_legit_data_skip("denylisted name (credential-shaped)"))
        self.assertFalse(_legit_data_skip("dotfile (config or state, not authored source)"))
        self.assertFalse(_legit_data_skip("symlink (never followed out of the workspace)"))

    def test_director_workspace_is_a_candidate_source(self):
        scratch = S.study_scratch_dir(self.study)
        _write(scratch / "region_map.md", "# regions")
        cands = workspace_candidates(self.study)
        self.assertIn(DIRECTOR_WORKSPACE_ID, cands)
        self.assertEqual([c["path"] for c in cands[DIRECTOR_WORKSPACE_ID]["kept"]],
                         ["region_map.md"])

    def test_a_move_with_no_workspace_on_disk_contributes_nothing(self):
        self._record_move("ghost")  # no workspace dir ever created
        cands = workspace_candidates(self.study)
        self.assertNotIn("ghost", cands)


class TestValidateShape(unittest.TestCase):
    def test_missing_summary_is_an_error(self):
        errs = _validate({"deliverable_files": [], "evidence_files": [],
                          "reproduce_steps": []})
        self.assertTrue(any("deliverable_summary" in e for e in errs))

    def test_entries_need_run_id_and_path(self):
        errs = _validate({"deliverable_summary": "x",
                          "deliverable_files": [{"note": "no ids"}],
                          "evidence_files": [], "reproduce_steps": []})
        self.assertTrue(any("deliverable_files[0]" in e for e in errs))

    def test_a_well_formed_response_validates_clean(self):
        errs = _validate({"deliverable_summary": "the library",
                          "deliverable_files": [{"run_id": "r1", "path": "lib.h"}],
                          "evidence_files": [], "reproduce_steps": ["make"]})
        self.assertEqual(errs, [])


class TestCollisionHandling(unittest.TestCase):
    def test_no_collision_keeps_bare_basenames(self):
        chosen = [{"run_id": "r1", "path": "lib.h"}, {"run_id": "r2", "path": "tool.py"}]
        named = _assign_final_names(chosen)
        self.assertEqual([e["final_name"] for e in named], ["lib.h", "tool.py"])

    def test_a_basename_collision_prefixes_the_second_entry(self):
        chosen = [{"run_id": "r1", "path": "verify.py"},
                 {"run_id": "r2", "path": "sub/verify.py"}]
        named = _assign_final_names(chosen)
        self.assertEqual(named[0]["final_name"], "verify.py")
        self.assertEqual(named[1]["final_name"], "r2__verify.py")

    def test_reproduce_steps_are_rewritten_for_a_renamed_file(self):
        steps = ["python3 verify.py lib.h"]
        out = _substitute_final_names(steps, {"verify.py": "r2__verify.py"})
        self.assertEqual(out, ["python3 r2__verify.py lib.h"])

    def test_no_rename_map_leaves_steps_untouched(self):
        steps = ["make check"]
        self.assertEqual(_substitute_final_names(steps, {}), steps)


class TestPackaging(DeliverableTestCase):
    def _fake_call(self, deliverable_files=(), evidence_files=(), reproduce_steps=(),
                   summary="the library"):
        def call(stage, sp, inp, schema, **kw):
            return ({
                "deliverable_summary": summary,
                "deliverable_files": list(deliverable_files),
                "evidence_files": list(evidence_files),
                "reproduce_steps": list(reproduce_steps),
            }, {"model": "fake"})
        return call

    def test_end_to_end_copies_exactly_what_was_chosen(self):
        self._record_move("m1", results=[{"label": "worst err", "value": 4.5e-13,
                                          "verified": True}])
        ws = self._workspace("m1")
        _write(ws / "lib.h", "int lib;")
        _write(ws / "grid.bin", b"\x00" * 2000)
        _write(ws / "junk.bin", b"\x00" * 5000)

        call = self._fake_call(
            deliverable_files=[{"run_id": "m1", "path": "lib.h", "note": "the header"}],
            evidence_files=[{"run_id": "m1", "path": "grid.bin", "note": "recompute input"}],
            reproduce_steps=["python3 check.py grid.bin"])
        out = package_study_deliverable(self.study, call=call)

        self.assertNotIn("error", out)
        dest = Path(out["deliverable_dir"])
        self.assertTrue((dest / "lib.h").is_file())
        self.assertTrue((dest / "evidence" / "grid.bin").is_file())
        self.assertFalse((dest / "junk.bin").exists())
        self.assertFalse((dest / "evidence" / "junk.bin").exists())
        readme = (dest / "README.md").read_text()
        self.assertIn("worst err", readme)
        self.assertIn("4.5e-13", readme)
        self.assertIn("Not independently executed", readme)
        manifest = json.loads((dest / "deliverable_manifest.json").read_text())
        self.assertEqual(manifest["deliverable_summary"], "the library")

    def test_a_hallucinated_path_is_refused_not_copied(self):
        self._record_move("m1")
        ws = self._workspace("m1")
        _write(ws / "lib.h", "int lib;")

        call = self._fake_call(
            deliverable_files=[
                {"run_id": "m1", "path": "lib.h", "note": "real"},
                {"run_id": "m1", "path": "../../../etc/passwd", "note": "escape attempt"},
                {"run_id": "m1", "path": "invented_file.h", "note": "never existed"},
            ])
        out = package_study_deliverable(self.study, call=call)

        self.assertNotIn("error", out)
        self.assertEqual(out["deliverable_files"], ["lib.h"])
        dest = Path(out["deliverable_dir"])
        manifest = json.loads((dest / "deliverable_manifest.json").read_text())
        reasons = [s["reason"] for s in manifest["deliverable_skipped"]]
        self.assertTrue(any("not one of the offered candidates" in r for r in reasons))

    def test_an_oversized_evidence_file_is_capped_not_silently_shrunk(self):
        self._record_move("m1")
        ws = self._workspace("m1")
        _write(ws / "small.bin", b"\x00" * 100)
        _write(ws / "huge.bin", b"\x00" * 200)

        call = self._fake_call(
            evidence_files=[{"run_id": "m1", "path": "small.bin"},
                           {"run_id": "m1", "path": "huge.bin"}])
        # patch the caps down so the test does not need a real 20 MB file
        import stages.study_deliverable as SD
        old_file_cap = SD.MAX_EVIDENCE_FILE_BYTES
        SD.MAX_EVIDENCE_FILE_BYTES = 150
        try:
            out = package_study_deliverable(self.study, call=call)
        finally:
            SD.MAX_EVIDENCE_FILE_BYTES = old_file_cap

        self.assertEqual(out["evidence_files"], ["small.bin"])
        dest = Path(out["deliverable_dir"])
        manifest = json.loads((dest / "deliverable_manifest.json").read_text())
        self.assertTrue(any("huge.bin" == s["path"] and "cap" in s["reason"]
                           for s in manifest["evidence_skipped"]))

    def test_small_files_survive_a_total_cap_even_with_one_huge_choice(self):
        self._record_move("m1")
        ws = self._workspace("m1")
        _write(ws / "a.bin", b"\x00" * 10)
        _write(ws / "b.bin", b"\x00" * 10)
        _write(ws / "huge.bin", b"\x00" * 1000)

        call = self._fake_call(
            evidence_files=[{"run_id": "m1", "path": "huge.bin"},
                           {"run_id": "m1", "path": "a.bin"},
                           {"run_id": "m1", "path": "b.bin"}])
        import stages.study_deliverable as SD
        old_total = SD.MAX_EVIDENCE_TOTAL_BYTES
        old_file = SD.MAX_EVIDENCE_FILE_BYTES
        SD.MAX_EVIDENCE_TOTAL_BYTES = 25
        SD.MAX_EVIDENCE_FILE_BYTES = 2000
        try:
            out = package_study_deliverable(self.study, call=call)
        finally:
            SD.MAX_EVIDENCE_TOTAL_BYTES = old_total
            SD.MAX_EVIDENCE_FILE_BYTES = old_file

        self.assertEqual(sorted(out["evidence_files"]), ["a.bin", "b.bin"])

    def test_a_basename_collision_across_workspaces_is_resolved_on_disk(self):
        self._record_move("m1")
        self._record_move("m2")
        _write(self._workspace("m1") / "verify.py", "# m1")
        _write(self._workspace("m2") / "verify.py", "# m2")

        call = self._fake_call(
            deliverable_files=[{"run_id": "m1", "path": "verify.py"},
                              {"run_id": "m2", "path": "verify.py"}],
            reproduce_steps=["python3 verify.py"])
        out = package_study_deliverable(self.study, call=call)
        dest = Path(out["deliverable_dir"])
        self.assertTrue((dest / "verify.py").is_file())
        self.assertTrue((dest / "m2__verify.py").is_file())
        readme = (dest / "README.md").read_text()
        self.assertIn("m2__verify.py", readme)

    def test_nothing_named_is_an_honest_error_not_an_empty_directory(self):
        self._record_move("m1")
        _write(self._workspace("m1") / "lib.h", "int x;")
        out = package_study_deliverable(self.study, call=self._fake_call())
        self.assertIn("error", out)
        self.assertFalse((self.study.dir / "deliverable").exists())

    def test_no_paper_is_an_error_not_a_crash(self):
        (self.study.dir / "paper.md").unlink()
        out = package_study_deliverable(self.study, call=self._fake_call())
        self.assertIn("no paper.md", out["error"])

    def test_a_failing_model_call_is_an_error_not_a_crash(self):
        self._record_move("m1")
        _write(self._workspace("m1") / "lib.h", "int x;")

        def call(*a, **kw):
            raise RuntimeError("boom")

        out = package_study_deliverable(self.study, call=call)
        self.assertIn("deliverable selection failed", out["error"])

    def test_the_kill_switch_disables_packaging(self):
        self._record_move("m1")
        _write(self._workspace("m1") / "lib.h", "int x;")
        os.environ["PACKAGE_DELIVERABLE"] = "0"
        try:
            out = package_study_deliverable(self.study, call=self._fake_call())
        finally:
            del os.environ["PACKAGE_DELIVERABLE"]
        self.assertIn("disabled", out["error"])

    def test_the_readme_credits_neither_party_wrote_it(self):
        # The model chooses files; Python renders the README. This is checked by
        # construction (_render_readme takes no call/model), but the visible
        # smoke test is that a model given no chance to write prose still gets a
        # complete, well-formed README.
        self._record_move("m1")
        _write(self._workspace("m1") / "lib.h", "int x;")
        out = package_study_deliverable(
            self.study,
            call=self._fake_call(
                deliverable_files=[{"run_id": "m1", "path": "lib.h"}]))
        readme = (Path(out["deliverable_dir"]) / "README.md").read_text()
        self.assertIn("Assembled automatically", readme)
        self.assertIn("## Paper", readme)

    def test_by_id_wraps_an_unknown_study(self):
        out = package_study_deliverable_by_id("no-such-study")
        self.assertIn("no such study", out["error"])


class TestCandidateSet(unittest.TestCase):
    def test_flattens_kept_and_other_across_workspaces(self):
        candidates = {
            "r1": {"kept": [{"path": "a.h", "bytes": 1}],
                  "other": [{"path": "b.bin", "bytes": 2, "skipped_because": "x"}]},
            "r2": {"kept": [], "other": []},
        }
        self.assertEqual(_candidate_set(candidates),
                         {("r1", "a.h"), ("r1", "b.bin")})


if __name__ == "__main__":
    unittest.main()
