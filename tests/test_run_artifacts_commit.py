"""test_run_artifacts_commit.py — the WRITE half of auto-committing what a run
produces (2026-07-30).

EVERY TEST RUNS AGAINST A THROWAWAY GIT REPO in a temp dir. Nothing here may
write a ref, an object, or a byte into this project's own .git — that is the
single most expensive mistake available in this task, and the fixture is what
makes it impossible rather than unlikely.

The cases that matter are the ones that cost something when they are wrong:

  - the index, HEAD and working tree are untouched (several sessions commit to
    this tree concurrently; a study can finish at 03:00 mid-`git add`);
  - two studies racing for the ref both survive, and neither forces;
  - the tree ACCUMULATES, so the branch tip still holds a study from months ago;
  - a credential-shaped string keeps its file out of the commit entirely;
  - a git failure is reported and dropped, never raised into the arc.

Run directly: venv/bin/python3 tests/test_run_artifacts_commit.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_artifacts_commit as rac  # noqa: E402
from tools import run_code_snapshot as snap  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo)] + list(args),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise AssertionError(f"git {args}: {proc.stderr.decode()}")
    return proc.stdout.decode()


class _Repo(unittest.TestCase):
    """A temp project that looks like this one: a git repo with a real HEAD and
    a real index, runs/<id>/workspace and studies/<id>/ beneath it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.name", "Test Runner")
        _git(self.root, "config", "user.email", "test@example.invalid")
        (self.root / "tracked.txt").write_text("the working branch's own file\n")
        _git(self.root, "add", "tracked.txt")
        _git(self.root, "commit", "-q", "-m", "initial")
        self.git_dir = self.root / ".git"

    def tearDown(self):
        self._tmp.cleanup()

    # -- fixture builders -------------------------------------------------
    def make_study(self, study_id: str, *, goal: str = "a goal",
                   runs: list = (), parent: str = None) -> Path:
        d = self.root / "studies" / study_id
        d.mkdir(parents=True, exist_ok=True)
        (d / "study.json").write_text(json.dumps(
            {"study_id": study_id, "goal": goal, "parent_study_id": parent}))
        with open(d / "arc.jsonl", "a") as f:
            for i, run_id in enumerate(runs, 1):
                f.write(json.dumps({"seq": i, "run_id": run_id}) + "\n")
        return d

    def write(self, rel: str, content: str = "x") -> Path:
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def commit(self, study_id: str, **kw):
        return rac.commit_run_artifacts(
            study_id, project_root=self.root, git_dir=self.git_dir,
            quiet=True, **kw)

    def show(self, path: str) -> str:
        return _git(self.root, "show", f"{rac.REF}:{path}")

    def tip_paths(self) -> set:
        out = _git(self.root, "ls-tree", "-r", "--name-only", rac.REF)
        return {line for line in out.splitlines() if line}


class TestItCommits(_Repo):
    def test_a_studys_code_lands_on_the_branch_and_reads_back(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/fit.py", "def fit(): return 42\n")
        self.write("studies/study-1/director_workspace/notes.md", "# notes\n")
        result = self.commit("study-1")
        self.assertTrue(result["committed"], result)
        self.assertEqual(result["files"], 2)
        self.assertEqual(self.show("runs/study-1-m1/workspace/fit.py"),
                         "def fit(): return 42\n")
        self.assertEqual(self.show("studies/study-1/director_workspace/notes.md"),
                         "# notes\n")

    def test_the_commit_message_names_the_study_and_its_arc_position(self):
        self.make_study("study-1", goal="measure the thing",
                        runs=["study-1-m1", "study-1-m2"])
        self.write("runs/study-1-m1/workspace/a.py")
        result = self.commit("study-1")
        message = _git(self.root, "log", "-1", "--format=%B", rac.REF)
        self.assertIn("study-1", message)
        self.assertIn("2 run(s) in the arc", message)
        self.assertIn("measure the thing", message)
        self.assertTrue(result["commit"])

    def test_a_deliverables_figures_are_committed_but_a_workspaces_are_not(self):
        # THE OWNER'S FIGURE RULING. studies/<id>/deliverable is the curated
        # boundary; a workspace .png is a scratch plot and a workspace .pdf is
        # usually a paper the agent fetched off the web.
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("studies/study-1/deliverable/fig1.png", "PNGDATA")
        self.write("studies/study-1/deliverable/paper.md", "# paper\n")
        self.write("runs/study-1-m1/workspace/scratch.png", "PNGDATA")
        self.write("runs/study-1-m1/workspace/fetched.pdf", "PDFDATA")
        self.write("runs/study-1-m1/workspace/real.py", "x = 1\n")
        self.commit("study-1")
        self.assertEqual(self.tip_paths(), {
            "studies/study-1/deliverable/fig1.png",
            "studies/study-1/deliverable/paper.md",
            "runs/study-1-m1/workspace/real.py",
        })

    def test_a_spawned_sub_studys_work_rides_in_its_parents_commit(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.make_study("study-1-sub1", runs=["study-1-sub1-m1"],
                        parent="study-1")
        self.write("runs/study-1-m1/workspace/a.py")
        self.write("runs/study-1-sub1-m1/workspace/b.py")
        self.commit("study-1")
        self.assertEqual(self.tip_paths(), {
            "runs/study-1-m1/workspace/a.py",
            "runs/study-1-sub1-m1/workspace/b.py"})

    def test_an_executable_script_keeps_its_mode(self):
        # A restored backup whose driver script will not run is a worse backup.
        self.make_study("study-1", runs=["study-1-m1"])
        p = self.write("runs/study-1-m1/workspace/drive.sh", "#!/bin/sh\n")
        os.chmod(p, 0o755)
        self.commit("study-1")
        listing = _git(self.root, "ls-tree", "-r", rac.REF)
        self.assertIn("100755", listing)

    def test_a_second_study_does_not_erase_the_first(self):
        # THE ACCUMULATION RULE. Each commit's tree is the parent's tree with
        # the new study overlaid; without that, the tip would hold only the last
        # study and the whole point (findable six months later) is lost.
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/first.py")
        self.make_study("study-2", runs=["study-2-m1"])
        self.write("runs/study-2-m1/workspace/second.py")
        self.commit("study-1")
        self.commit("study-2")
        self.assertEqual(self.tip_paths(), {"runs/study-1-m1/workspace/first.py",
                                            "runs/study-2-m1/workspace/second.py"})
        self.assertEqual(len(_git(self.root, "log", "--format=%H",
                                  rac.REF).split()), 2)

    def test_history_is_chronological_and_parented(self):
        for i in (1, 2, 3):
            self.make_study(f"study-{i}", runs=[f"study-{i}-m1"])
            self.write(f"runs/study-{i}-m1/workspace/f{i}.py")
            self.commit(f"study-{i}")
        subjects = _git(self.root, "log", "--format=%s", rac.REF).split("\n")
        subjects = [s for s in subjects if s]
        self.assertEqual([s.split()[2] for s in subjects],
                         ["study-3", "study-2", "study-1"])

    def test_re_committing_an_unchanged_study_is_a_no_op(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        first = self.commit("study-1")
        second = self.commit("study-1")
        self.assertTrue(first["committed"])
        self.assertFalse(second["committed"])
        self.assertEqual(second["skipped"], "identical to the current tip")
        self.assertEqual(len(_git(self.root, "log", "--format=%H",
                                  rac.REF).split()), 1)

    def test_a_dry_run_writes_no_ref_and_no_object(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        result = self.commit("study-1", dry_run=True)
        self.assertFalse(result["committed"])
        self.assertEqual(result["files"], 1)
        self.assertNotIn("run-artifacts", _git(self.root, "show-ref") or "")


class TestItNeverTouchesTheRepoState(_Repo):
    def _snapshot(self) -> tuple:
        index = self.git_dir / "index"
        return (
            _git(self.root, "status", "--porcelain"),
            _git(self.root, "rev-parse", "HEAD"),
            _git(self.root, "symbolic-ref", "HEAD"),
            index.read_bytes() if index.is_file() else None,
        )

    def test_status_head_and_index_are_byte_identical_after_a_commit(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        self.write("untracked_in_worktree.txt", "a human's in-flight edit\n")
        before = self._snapshot()
        self.commit("study-1")
        self.assertEqual(self._snapshot(), before)

    def test_the_working_tree_file_is_not_modified_or_removed(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py", "original\n")
        self.commit("study-1")
        self.assertEqual((self.root / "runs/study-1-m1/workspace/a.py").read_text(),
                         "original\n")
        self.assertEqual((self.root / "tracked.txt").read_text(),
                         "the working branch's own file\n")

    def test_the_module_uses_plumbing_only(self):
        # The design's first property. `git add` anywhere here would open the
        # shared index, which is exactly the collision the branch scheme exists
        # to avoid.
        source = Path(rac.__file__).read_text()
        # Quoted forms only: these are the strings that would reach argv. The
        # prose above may say "no checkout" — it is the ARGUMENT that matters.
        for verb in ("add", "read-tree", "write-tree", "checkout", "reset",
                     "push", "symbolic-ref", "merge", "stash", "apply"):
            for quoted in (f'"{verb}"', f"'{verb}'"):
                self.assertNotIn(quoted, source, quoted)
        verbs = {"rev-parse", "ls-tree", "hash-object", "mktree",
                 "commit-tree", "update-ref"}
        found = {v for v in
                 ("rev-parse", "ls-tree", "hash-object", "mktree",
                  "commit-tree", "update-ref") if f'"{v}"' in source}
        self.assertEqual(found, verbs)


class TestTheRefRace(_Repo):
    def test_a_lost_race_rebuilds_on_the_new_tip_instead_of_forcing(self):
        # Two studies finishing seconds apart. The loser must re-read the tip,
        # rebuild on the winner's commit, and keep BOTH — never force.
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/mine.py")
        self.make_study("study-2", runs=["study-2-m1"])
        self.write("runs/study-2-m1/workspace/theirs.py")

        real_cas = rac.Plumbing.update_ref_cas
        state = {"raced": False}

        def racing_cas(plumbing, ref, new, old):
            if not state["raced"]:
                state["raced"] = True
                # Another session commits between our read and our swap.
                rac.commit_run_artifacts(
                    "study-2", project_root=self.root, git_dir=self.git_dir,
                    quiet=True)
                return False
            return real_cas(plumbing, ref, new, old)

        rac.Plumbing.update_ref_cas = racing_cas
        try:
            result = self.commit("study-1")
        finally:
            rac.Plumbing.update_ref_cas = real_cas
        self.assertTrue(state["raced"])
        self.assertTrue(result["committed"], result)
        self.assertEqual(self.tip_paths(), {"runs/study-1-m1/workspace/mine.py",
                                            "runs/study-2-m1/workspace/theirs.py"})

    def test_losing_every_retry_commits_nothing_and_clobbers_nothing(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/mine.py")
        self.make_study("study-2", runs=["study-2-m1"])
        self.write("runs/study-2-m1/workspace/theirs.py")
        self.commit("study-2")
        winner = _git(self.root, "rev-parse", rac.REF).strip()

        real_cas = rac.Plumbing.update_ref_cas
        rac.Plumbing.update_ref_cas = lambda *a, **k: False
        try:
            result = self.commit("study-1")
        finally:
            rac.Plumbing.update_ref_cas = real_cas
        self.assertFalse(result["committed"])
        self.assertIn("nothing was forced", result["error"])
        self.assertEqual(_git(self.root, "rev-parse", rac.REF).strip(), winner)

    def test_update_ref_is_a_compare_and_swap_in_both_directions(self):
        # THE TRAP, tested directly rather than only through the loop above.
        # A wrong-old-value swap and a create-when-it-already-exists must BOTH
        # be refused; an unconditional `update-ref REF NEW` would do neither.
        git = rac.Plumbing(self.git_dir, self.root)
        head = _git(self.root, "rev-parse", "HEAD").strip()
        other = git.commit_tree(rac.EMPTY_TREE, None, "a distinct commit\n")
        self.assertNotEqual(head, other)
        self.assertTrue(git.update_ref_cas(rac.REF, head, None))   # create
        self.assertFalse(git.update_ref_cas(rac.REF, other, None))  # create again
        self.assertFalse(git.update_ref_cas(
            rac.REF, other, "0" * 40))                              # wrong old
        self.assertEqual(_git(self.root, "rev-parse", rac.REF).strip(), head)
        self.assertTrue(git.update_ref_cas(rac.REF, other, head))   # right old

    def test_the_first_commit_demands_the_ref_not_exist(self):
        # The compare-and-swap form, not an unconditional write: a ref that
        # appeared between our read and our swap must not be overwritten.
        git = rac.Plumbing(self.git_dir, self.root)
        self.assertIsNone(git.tip(rac.REF))
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        self.commit("study-1")
        self.assertIsNotNone(git.tip(rac.REF))


class TestTheSecretScan(_Repo):
    def test_a_key_shaped_string_keeps_its_file_out_of_the_commit(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/leak.py",
                   "KEY = 'sk-ant-" + "A" * 40 + "'\n")
        self.write("runs/study-1-m1/workspace/clean.py", "x = 1\n")
        result = self.commit("study-1")
        self.assertIn("runs/study-1-m1/workspace/leak.py", result["withheld"])
        self.assertEqual(self.tip_paths(), {"runs/study-1-m1/workspace/clean.py"})

    def test_a_withheld_file_is_never_hashed_into_the_object_store(self):
        # Withholding it from the TREE would not be enough: a blob written and
        # then left out of the tree is still reachable by sha, and would be
        # pushed with the ref.
        self.make_study("study-1", runs=["study-1-m1"])
        secret = "sk-ant-" + "B" * 40
        self.write("runs/study-1-m1/workspace/leak.py", f"KEY = '{secret}'\n")
        self.write("runs/study-1-m1/workspace/clean.py", "x = 1\n")
        self.commit("study-1")
        blobs = _git(self.root, "cat-file", "--batch-all-objects",
                     "--batch-check=%(objecttype) %(objectname)")
        for line in blobs.splitlines():
            kind, _, sha = line.partition(" ")
            if kind == "blob":
                self.assertNotIn(secret, _git(self.root, "cat-file", "blob",
                                              sha.strip()))

    def test_a_value_copied_out_of_this_trees_env_is_caught(self):
        # THE SPECIFIC RISK. This project keeps an MP_API_KEY in .env, and an
        # agent could in principle have echoed it into a file it wrote — where
        # it would carry no recognisable prefix at all.
        (self.root / ".env").write_text("MP_API_KEY=zZqQ8vTt19PlausibleKey42\n")
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/echoed.py",
                   "url = 'https://api?key=zZqQ8vTt19PlausibleKey42'\n")
        result = self.commit("study-1")
        self.assertEqual(list(result["withheld"]),
                         ["runs/study-1-m1/workspace/echoed.py"])
        self.assertIn("matches a value in this tree's .env",
                      result["withheld"]["runs/study-1-m1/workspace/echoed.py"])

    def test_the_report_names_the_rule_and_never_the_value(self):
        self.make_study("study-1", runs=["study-1-m1"])
        secret = "ghp_" + "C" * 36
        self.write("runs/study-1-m1/workspace/leak.py", f"t = '{secret}'\n")
        self.write("runs/study-1-m1/workspace/clean.py", "x = 1\n")
        result = self.commit("study-1")
        rendered = json.dumps(result["withheld"])
        self.assertIn("github token", rendered)
        self.assertNotIn(secret, rendered)
        message = _git(self.root, "log", "-1", "--format=%B", rac.REF)
        self.assertIn("WITHHELD by the secret scan", message)
        self.assertNotIn(secret, message)

    def test_a_study_whose_every_file_is_withheld_commits_nothing(self):
        # Not an error and not a partial commit: there is simply nothing left to
        # write, and the ref must not gain an empty commit for it.
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/leak.py",
                   "K = 'sk-ant-" + "D" * 40 + "'\n")
        result = self.commit("study-1")
        self.assertFalse(result["committed"])
        self.assertEqual(result["skipped"], "nothing selected")
        self.assertEqual(len(result["withheld"]), 1)
        self.assertNotIn("run-artifacts", _git(self.root, "show-ref") or "")

    def test_the_env_style_shapes_are_caught(self):
        for i, content in enumerate((
            "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI0K7MDENGbPxRfiCYEXAMPLEKEY\n",
            "export DB_PASSWORD='sup3rl0ngp4ssw0rdvalue'\n",
            "-----BEGIN RSA PRIVATE KEY-----\nMIIE\n",
            "AKIAIOSFODNN7EXAMPLE\n",
        )):
            self.write(f"runs/r{i}/workspace/f.txt", content)
        findings = rac.scan_fileset(
            rac.snapshot_files(sorted(self.root.glob("runs/*/workspace")),
                               self.root), self.root)
        self.assertEqual(len(findings), 4, findings)

    def test_ordinary_source_and_a_binary_figure_are_clean(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/model.py",
                   "import numpy as np\n\n\ndef f(x):\n    return np.exp(-x)\n")
        (self.root / "studies/study-1/deliverable").mkdir(parents=True)
        (self.root / "studies/study-1/deliverable/fig.png").write_bytes(
            b"\x89PNG\r\n\x1a\n\x00\x00sk-ant-notreallyakey\x00")
        result = self.commit("study-1")
        self.assertEqual(result["withheld"], {})
        self.assertEqual(result["files"], 2)


class TestItIsNeverFatal(_Repo):
    def test_a_broken_git_dir_is_reported_not_raised(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        result = rac.commit_run_artifacts(
            "study-1", project_root=self.root,
            git_dir=self.root / "no-such-git-dir", quiet=True)
        self.assertFalse(result["committed"])
        self.assertTrue(result["error"])

    def test_an_unknown_study_is_a_skip_not_an_error(self):
        result = self.commit("study-that-never-existed")
        self.assertFalse(result["committed"])
        self.assertIsNone(result["error"])
        self.assertEqual(result["skipped"], "nothing selected")

    def test_a_study_whose_arc_is_torn_still_commits_what_it_can(self):
        d = self.make_study("study-1", runs=["study-1-m1"])
        with open(d / "arc.jsonl", "a") as f:
            f.write('{"seq": 2, "run_id": "study-1-m2"\n')  # torn line
        self.write("runs/study-1-m1/workspace/a.py")
        result = self.commit("study-1")
        self.assertTrue(result["committed"])
        self.assertEqual(result["files"], 1)

    def test_a_file_that_vanishes_mid_snapshot_does_not_sink_the_commit(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        doomed = self.write("runs/study-1-m1/workspace/b.py")
        real_scan = rac.scan_fileset

        def scan_then_delete(files, project_root):
            out = real_scan(files, project_root)
            doomed.unlink()
            return out

        rac.scan_fileset = scan_then_delete
        try:
            result = self.commit("study-1")
        finally:
            rac.scan_fileset = real_scan
        self.assertTrue(result["committed"], result)
        self.assertEqual(result["files"], 1)


class TestBackfill(_Repo):
    def test_one_commit_per_root_study_oldest_first(self):
        for i in (1, 2):
            self.make_study(f"study-{i}", runs=[f"study-{i}-m1"])
            self.write(f"runs/study-{i}-m1/workspace/f{i}.py")
        self.make_study("study-1-sub1", runs=["study-1-sub1-m1"],
                        parent="study-1")
        self.write("runs/study-1-sub1-m1/workspace/child.py")
        results = rac.backfill(project_root=self.root, git_dir=self.git_dir,
                               quiet=True)
        committed = [r for r in results if r["committed"]]
        self.assertEqual([r["study_id"] for r in committed],
                         ["study-1", "study-2"])
        self.assertIn("runs/study-1-sub1-m1/workspace/child.py",
                      self.tip_paths())

    def test_runs_no_study_claims_are_backed_up_too(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/claimed.py")
        self.write("runs/standalone-run/workspace/orphan.py")
        results = rac.backfill(project_root=self.root, git_dir=self.git_dir,
                               quiet=True)
        self.assertEqual(results[-1]["study_id"], "runs with no study arc")
        self.assertIn("runs/standalone-run/workspace/orphan.py",
                      self.tip_paths())

    def test_a_backfill_dry_run_writes_nothing(self):
        self.make_study("study-1", runs=["study-1-m1"])
        self.write("runs/study-1-m1/workspace/a.py")
        rac.backfill(project_root=self.root, git_dir=self.git_dir,
                     dry_run=True, quiet=True)
        self.assertEqual(_git(self.root, "show-ref").count("run-artifacts"), 0)


class TestTheProductionSwitch(unittest.TestCase):
    def test_it_is_off_unless_asked_for(self):
        saved = os.environ.pop(rac.ENV_FLAG, None)
        try:
            self.assertFalse(rac.commit_enabled())
            self.assertTrue(rac.commit_enabled(flag=True))
            os.environ[rac.ENV_FLAG] = "1"
            self.assertTrue(rac.commit_enabled())
            os.environ[rac.ENV_FLAG] = "0"
            self.assertFalse(rac.commit_enabled())
        finally:
            os.environ.pop(rac.ENV_FLAG, None)
            if saved is not None:
                os.environ[rac.ENV_FLAG] = saved


class TestSelectionIsNotReimplemented(_Repo):
    def test_it_defers_to_run_code_snapshot_for_every_rule(self):
        # A .venv, a 40 MB dump and a .env inside a workspace are all refused by
        # the selection module; this module must not have its own opinion.
        self.make_study("study-1", runs=["study-1-m1"])
        ws = "runs/study-1-m1/workspace/"
        self.write(ws + ".venv/lib/site-packages/numpy/core.py")
        self.write(ws + "dump.json", "0" * (snap.MAX_DATA_BYTES + 1))
        self.write(ws + ".env", "SECRET=1")
        self.write(ws + "mine.py", "x = 1\n")
        self.commit("study-1")
        self.assertEqual(self.tip_paths(), {ws + "mine.py"})


if __name__ == "__main__":
    unittest.main()
