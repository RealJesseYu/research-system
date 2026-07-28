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

    def test_a_small_result_file_and_a_figure_are_kept(self):
        self.write("fit.json", "{}")
        self.write("fig1.png", "notreallyapng")
        self.assertEqual(self.kept(), {"fit.json", "fig1.png"})


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
