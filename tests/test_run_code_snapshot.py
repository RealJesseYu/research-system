"""test_run_code_snapshot.py — which run-produced files are commit-worthy
(2026-07-28).

The owner asked for the code a run produces to be committed to git
automatically. This is the half that could be decided on evidence: WHICH files.
WHERE the commits land is an owner ruling (docs/memo_auto_commit_run_code.md),
so nothing in the module under test touches git — and one of these tests holds
that line, because a later edit that quietly adds a `git commit` here would be
implementing a scheme nobody ruled on.

The cases that matter are the ones a naive whitelist gets wrong: a virtualenv
inside the workspace (two real ones exist in this tree, and they hold most of
the 5,020 .py files under runs/), a .env, a private key, a symlink pointing
out, and a 40 MB result dump.

Run directly: venv/bin/python3 tests/test_run_code_snapshot.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_code_snapshot as snap  # noqa: E402


class _Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, rel: str, content: str = "x") -> Path:
        p = self.ws / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
        return p

    def kept(self):
        return {str(r) for r in snap.select(self.ws)[0]}

    def skip_reason(self, rel: str):
        for r, reason in snap.select(self.ws)[1]:
            if str(r) == rel:
                return reason
        return None


class TestWhatIsKept(_Workspace):
    def test_the_agents_own_source_is_kept(self):
        for rel in ("remez.py", "phi_lin.h", "test_phi.c", "run.sh",
                    "README.md", "Makefile", "fam.f90"):
            self.write(rel)
        self.assertEqual(self.kept(), {"remez.py", "phi_lin.h", "test_phi.c",
                                       "run.sh", "README.md", "Makefile",
                                       "fam.f90"})

    def test_nested_source_is_kept(self):
        self.write("bench/harness/drive.py")
        self.assertIn("bench/harness/drive.py", self.kept())

    def test_a_small_result_file_is_kept(self):
        self.write("fit.json", "{}")
        self.assertEqual(self.kept(), {"fit.json"})


class TestFiguresComeOnlyFromADeliverable(_Workspace):
    """Owner ruling, 2026-07-30. Figures are kept from studies/<id>/deliverable/
    — the curated boundary stages/study_deliverable.py assembles — and from
    nowhere else. MEASURED the day of the ruling: across 87 workspaces the
    figure-class extensions were 380 files / 189.8 MB, of which 306 files /
    178.3 MB were .pdf — papers the agent FETCHED off the web, not anything it
    produced. The deliverable's 11 figures were 1.2 MB."""

    def test_a_scratch_plot_in_a_workspace_is_left_out(self):
        self.write("fig1.png", "notreallyapng")
        self.write("fetched_paper.pdf", "notreallyapdf")
        self.write("plot.py", "import matplotlib\n")
        self.assertEqual(self.kept(), {"plot.py"})
        self.assertIn("outside a deliverable", self.skip_reason("fig1.png"))

    def test_the_same_figure_in_a_deliverable_is_kept(self):
        deliverable = self.ws / snap.DELIVERABLE_DIRNAME
        deliverable.mkdir()
        (deliverable / "fig1.png").write_text("notreallyapng")
        (deliverable / "paper.pdf").write_text("notreallyapdf")
        kept, _ = snap.select(deliverable)
        self.assertEqual({str(r) for r in kept}, {"fig1.png", "paper.pdf"})

    def test_the_rule_can_be_forced_either_way_for_a_caller_that_knows(self):
        self.write("fig1.png", "notreallyapng")
        self.assertEqual({str(r) for r in snap.select(self.ws, figures=True)[0]},
                         {"fig1.png"})
        self.assertEqual(snap.select(self.ws, figures=False)[0], [])

    def test_a_deliverable_is_discovered_as_a_snapshot_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "studies" / "s1" / "deliverable").mkdir(parents=True)
            (root / "studies" / "s1" / "director_workspace").mkdir(parents=True)
            found = {p.name for p in snap.workspaces(root)}
            self.assertEqual(found, {"deliverable", "director_workspace"})


class TestWhatIsRefused(_Workspace):
    def test_a_virtualenv_inside_the_workspace_is_pruned_whole(self):
        # THE case a bare extension whitelist gets wrong. Two run workspaces in
        # this tree really do carry a .venv.
        self.write(".venv/lib/python3.14/site-packages/numpy/core.py")
        self.write(".venv/pyvenv.cfg")
        self.write("mine.py")
        self.assertEqual(self.kept(), {"mine.py"})

    def test_site_packages_and_caches_are_pruned_at_any_depth(self):
        self.write("deps/site-packages/pkg/mod.py")
        self.write("__pycache__/mine.cpython-314.pyc")
        self.write("node_modules/left-pad/index.js")
        self.write("thing.egg-info/PKG-INFO")
        self.write("mine.py")
        self.assertEqual(self.kept(), {"mine.py"})

    def test_a_git_directory_inside_a_workspace_is_never_walked(self):
        self.write(".git/config", "[core]")
        self.assertEqual(self.kept(), set())

    def test_credentials_are_refused_by_name_even_when_textual(self):
        for rel in (".env", "id_rsa", "server.pem", "credentials.json",
                    "mcp_servers.json"):
            self.write(rel, "SECRET=1")
        self.assertEqual(self.kept(), set())

    def test_dotfiles_are_skipped_so_the_denylist_need_not_be_exhaustive(self):
        self.write(".env.production", "KEY=1")
        self.assertEqual(self.kept(), set())
        self.assertIn("dotfile", self.skip_reason(".env.production") or "")

    def test_compiled_and_binary_output_is_not_on_the_whitelist(self):
        for rel in ("mod.so", "a.out", "model.npy", "data.zip", "lib.dylib"):
            self.write(rel)
        self.assertEqual(self.kept(), set())

    def test_a_large_result_dump_is_left_in_the_run_evidence(self):
        self.write("dump.json", "0" * (snap.MAX_DATA_BYTES + 1))
        self.assertEqual(self.kept(), set())
        self.assertIn("already run evidence", self.skip_reason("dump.json"))

    def test_a_large_source_file_is_still_capped(self):
        self.write("huge.py", "#" * (snap.MAX_FILE_BYTES + 1))
        self.assertEqual(self.kept(), set())

    def test_the_data_cap_is_tighter_than_the_source_cap(self):
        # The measured reason both exist: one cap kept 23 MB of result dumps
        # for 1.7 MB of actual source.
        self.assertLess(snap.MAX_DATA_BYTES, snap.MAX_FILE_BYTES)

    def test_a_symlink_out_of_the_workspace_is_not_followed(self):
        outside = Path(self._tmp.name).parent / "outside_secret.py"
        outside.write_text("token = 'sk-live'")
        try:
            (self.ws / "link.py").symlink_to(outside)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.assertEqual(self.kept(), set())
        outside.unlink()

    def test_every_refusal_carries_a_reason(self):
        self.write("mod.so")
        self.write(".env")
        for _, reason in snap.select(self.ws)[1]:
            self.assertTrue(reason.strip())


class TestBulkDataDropsArePruned(_Workspace):
    """Rule 7, added 2026-07-30 after the first backfill put 221 files / 9.7 MB
    of scraped journal text on the artifact branch (one opening "Copyright 1973
    by The American Ceramic Society") plus LTPP exports shipping a "Recommended
    Citation.txt". Pushing that would have republished third-party copyrighted
    material.

    The rule cannot ask "did the agent fetch this" — nothing on disk records
    that. It asks a question it can answer: a directory of nothing but data,
    with no code anywhere beneath it, is derivable either way (fetched → the
    fetch script is committed; generated → the generator is committed)."""

    def test_a_fetched_corpus_directory_is_pruned_whole(self):
        for i in range(12):
            self.write(f"bztxt/{i:03d}.txt", "Copyright 1973 by Somebody\n...")
        self.write("fetch.py", "import urllib.request\n")
        self.assertEqual(self.kept(), {"fetch.py"})

    def test_the_fetch_code_that_regenerates_it_is_still_committed(self):
        # The whole justification: dropping the data loses nothing recoverable,
        # because the thing that produced it IS in the commit.
        for i in range(6):
            self.write(f"raw/table{i}.csv", "a,b\n1,2\n")
        self.write("download.sh", "#!/bin/sh\ncurl -O ...\n")
        self.write("analyse.py", "import pandas\n")
        self.assertEqual(self.kept(), {"download.sh", "analyse.py"})

    def test_a_data_file_beside_source_survives(self):
        # A mixed working directory is where the agent actually works. This is
        # also the rule's honest limit: a fetched file here is indistinguishable
        # from an analysis output, and is kept.
        self.write("fit.py", "x = 1\n")
        self.write("fit_results.json", "{}")
        self.write("summary.csv", "a,b\n")
        self.write("notes.md", "# notes\n")
        self.assertEqual(self.kept(), {"fit.py", "fit_results.json",
                                       "summary.csv", "notes.md"})

    def test_a_data_directory_nested_under_source_is_still_pruned(self):
        # The rule is about a directory's whole SUBTREE, not its parent's.
        self.write("run.py", "x = 1\n")
        for i in range(5):
            self.write(f"out/dump{i}.json", "{}")
        self.assertEqual(self.kept(), {"run.py"})

    def test_the_highest_all_data_directory_is_the_one_named(self):
        for state in ("al", "ak", "az"):
            for i in range(3):
                self.write(f"raw/{state}/t{i}.csv", "a,b\n")
        self.write("load.py", "x = 1\n")
        # `raw` is named, not each of raw/al, raw/ak, raw/az beneath it.
        drops = snap.data_drop_roots(
            [Path(f"raw/{s}/t{i}.csv") for s in ("al", "ak", "az")
             for i in range(3)] + [Path("load.py")])
        self.assertEqual(list(drops), [Path("raw")])
        self.assertEqual(self.kept(), {"load.py"})

    def test_markdown_notes_are_never_treated_as_data(self):
        # The one shape that could be caught wrongly is a notes directory. .md
        # and .rst are source-side, so the usual case is safe by construction.
        for name in ("plan.md", "findings.md", "log.md", "todo.rst"):
            self.write(f"notes/{name}", "# a note\n")
        self.assertEqual(self.kept(), {f"notes/{n}" for n in
                                       ("plan.md", "findings.md", "log.md",
                                        "todo.rst")})

    def test_a_single_data_file_in_a_directory_is_not_a_drop(self):
        self.write("data/one.csv", "a,b\n")
        self.assertEqual(self.kept(), {"data/one.csv"})

    def test_every_pruned_file_still_carries_its_reason(self):
        for i in range(5):
            self.write(f"bztxt/{i}.txt", "scraped")
        self.write("scrape.py", "import urllib.request\n")
        reason = self.skip_reason("bztxt/0.txt")
        self.assertIn("data drop", reason)
        self.assertIn("re-fetchable or regenerable", reason)
        self.assertIn("bztxt", reason)

    def test_a_deliverable_is_exempt_because_it_was_curated(self):
        deliverable = self.ws / snap.DELIVERABLE_DIRNAME
        (deliverable / "evidence").mkdir(parents=True)
        for i in range(8):
            (deliverable / "evidence" / f"row{i}.csv").write_text("a,b\n")
        kept, _ = snap.select(deliverable)
        self.assertEqual(len(kept), 8)

    def test_the_rule_can_be_forced_either_way(self):
        for i in range(5):
            self.write(f"raw/t{i}.csv", "a,b\n")
        self.assertEqual(snap.select(self.ws, prune_data_drops=True)[0], [])
        self.assertEqual(len(snap.select(self.ws, prune_data_drops=False)[0]), 5)

    def test_a_whole_workspace_of_only_data_is_pruned(self):
        for i in range(5):
            self.write(f"t{i}.csv", "a,b\n")
        self.assertEqual(self.kept(), set())
        self.assertIn("the workspace root", self.skip_reason("t0.csv"))


class TestItIsSelectionOnly(unittest.TestCase):
    def test_a_missing_workspace_is_an_empty_snapshot_not_a_failure(self):
        kept, skipped = snap.select(Path("/nonexistent/workspace"))
        self.assertEqual((kept, skipped), ([], []))

    def test_the_module_does_not_touch_git(self):
        # THE LINE THIS TASK STOPPED AT. Adding a commit here would implement a
        # scheme the owner has not ruled on; if that ruling arrives, it belongs
        # in a new module and this assertion should be deleted deliberately.
        source = Path(snap.__file__).read_text()
        for forbidden in ("subprocess", "os.system", "popen", "update-ref",
                          "commit-tree", "hash-object", "GitPython", "pygit2"):
            self.assertNotIn(forbidden, source, forbidden)
        # It writes nothing at all, in fact — no open-for-write, no mkdir.
        for forbidden in ("write_text", "write_bytes", "mkdir", '"w"', "'w'"):
            self.assertNotIn(forbidden, source, forbidden)

    def test_both_workspace_shapes_are_discovered(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "runs" / "r1" / "workspace").mkdir(parents=True)
            (root / "studies" / "s1" / "director_workspace").mkdir(parents=True)
            (root / "runs" / "r2").mkdir(parents=True)  # no workspace
            found = {p.name for p in snap.workspaces(root)}
            self.assertEqual(found, {"workspace", "director_workspace"})


if __name__ == "__main__":
    unittest.main()
