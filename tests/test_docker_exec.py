"""
test_docker_exec — the exec bound that keeps a timed-out job from becoming a
WRONG NUMBER.

WHY THIS MATTERS MORE THAN A LEAK. Every wrapper driving a long-lived container
retried once on timeout, and the retry DELETES the job's output file and re-runs
into the SAME job directory. A `subprocess.run(..., timeout=N)` on `docker exec`
kills only the local client, so the previous attempt was still running — and
still writing there. The retry could read the ghost's output and report it as a
clean success, on the success path, with nothing in the summary hinting at it.

MEASURED, not assumed (2026-07-27, rdkit-prod): with the client killed mid-run,
the matching process count inside the container was unchanged. The leak is real.
Two other things measured the same session, both of which broke a first draft of
this module:
  - the substrate containers have NO ps, NO pkill and NO pgrep, so a reap
    written with pkill is dead code that always fails quietly;
  - the reap's own /proc/<pid>/cmdline contains the marker (it is an argument),
    so the first version matched itself, killed itself, and reported failure
    while having actually worked.

These tests are offline — they pin the command CONSTRUCTION and the result
classification, which is where a regression would hide. The live two-layer proof
is recorded in the commit; the wrappers' own suites cover the real containers.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.docker_exec import (CLIENT_GRACE_S,  # noqa: E402
                              TIMEOUT_EXIT_STATUS, _REAP_SCRIPT, bounded_exec,
                              exec_bounded)


class TestTheWorkIsBoundedInsideTheContainer(unittest.TestCase):
    def test_bounded_exec_inserts_timeout_before_the_command(self):
        argv = bounded_exec("colima", "rdkit-prod", ["python", "d.py"], 600)
        self.assertEqual(
            argv,
            ["docker", "--context", "colima", "exec", "rdkit-prod",
             "timeout", "600", "python", "d.py"])

    def test_the_bound_precedes_the_command_not_docker(self):
        """`timeout` must run INSIDE the container. Placing it before `docker`
        would bound the client again — the bug, reintroduced."""
        argv = bounded_exec("colima", "c", ["bash", "-c", "x"], 30)
        self.assertLess(argv.index("exec"), argv.index("timeout"))
        self.assertEqual(argv[0], "docker")

    def test_every_element_is_a_string(self):
        """argv reaches subprocess directly; an int would raise there instead."""
        for part in bounded_exec("colima", "c", ["python", 3, Path("/j/d.py")], 10):
            self.assertIsInstance(part, str)


class TestResultClassification(unittest.TestCase):
    def _run(self, **kw):
        with mock.patch("subprocess.run", **kw) as m:
            return exec_bounded("colima", "c", ["python", "d.py"],
                                timeout_s=60, kill_marker="/work/j1"), m

    def test_a_container_side_kill_is_reported_as_timed_out(self):
        done = subprocess.CompletedProcess([], TIMEOUT_EXIT_STATUS, "", "")
        res, _ = self._run(return_value=done)
        self.assertTrue(res.timed_out)
        self.assertTrue(res.killed_inside)

    def test_an_ordinary_failure_is_not_a_timeout(self):
        done = subprocess.CompletedProcess([], 1, "", "boom")
        res, _ = self._run(return_value=done)
        self.assertFalse(res.timed_out)
        self.assertEqual(res.returncode, 1)

    def test_success_passes_output_through(self):
        done = subprocess.CompletedProcess([], 0, "42", "")
        res, _ = self._run(return_value=done)
        self.assertFalse(res.timed_out)
        self.assertEqual(res.stdout, "42")

    def test_the_client_waits_longer_than_the_container(self):
        """If the client fired first we would be back to guessing what the
        container is still doing."""
        done = subprocess.CompletedProcess([], 0, "", "")
        _, m = self._run(return_value=done)
        self.assertEqual(m.call_args.kwargs["timeout"], 60 + CLIENT_GRACE_S)

    def test_a_client_timeout_is_distinguished_from_a_container_kill(self):
        """Both are timed_out, but only one leaves us uncertain — a caller
        writing a diagnostic needs to tell them apart."""
        with mock.patch("subprocess.run") as m:
            m.side_effect = [
                subprocess.TimeoutExpired(cmd="docker", timeout=75),
                subprocess.CompletedProcess([], 0, "1", ""),   # the reap
            ]
            res = exec_bounded("colima", "c", ["python", "d.py"],
                               timeout_s=60, kill_marker="/work/j1")
        self.assertTrue(res.timed_out)
        self.assertFalse(res.killed_inside)
        self.assertIn("docker client timed out", res.stderr)


class TestTheReap(unittest.TestCase):
    def test_it_does_not_use_pkill(self):
        """The containers have no pkill/pgrep/ps — a reap written with them is
        dead code that always fails quietly, which is the shape of the bugs this
        module exists to fix."""
        for absent in ("pkill", "pgrep", "ps "):
            self.assertNotIn(absent, _REAP_SCRIPT)

    def test_it_skips_itself_its_parent_and_init(self):
        """The marker is an ARGUMENT, so the script's own cmdline contains it: a
        version without these guards matched and killed itself, then reported
        failure while having worked. Killing PID 1 would take out every other
        job in the shared container."""
        self.assertIn('"$p" = "$self"', _REAP_SCRIPT)
        self.assertIn('"$p" = "$parent"', _REAP_SCRIPT)
        self.assertIn('"$p" = 1', _REAP_SCRIPT)

    def test_it_matches_fixed_strings_not_patterns(self):
        """A job dir path holds regex metacharacters; -F keeps them literal."""
        self.assertIn("grep -qF", _REAP_SCRIPT)

    def test_no_reap_is_attempted_without_a_marker(self):
        """A broad or empty marker could match another job's work."""
        with mock.patch("subprocess.run") as m:
            m.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=75)
            res = exec_bounded("colima", "c", ["python", "d.py"],
                               timeout_s=60, kill_marker="")
        self.assertEqual(m.call_count, 1)          # the exec only, no reap
        self.assertIn("not attempted", res.stderr)

    def test_the_marker_is_passed_as_an_argument_never_interpolated(self):
        """Shell-interpolating a path into the script would be an injection seam
        in a module whose whole job is running commands."""
        with mock.patch("subprocess.run") as m:
            m.side_effect = [
                subprocess.TimeoutExpired(cmd="docker", timeout=75),
                subprocess.CompletedProcess([], 0, "1", ""),
            ]
            exec_bounded("colima", "c", ["python", "d.py"],
                         timeout_s=60, kill_marker="/work/j; rm -rf /")
        reap_argv = m.call_args_list[1].args[0]
        self.assertEqual(reap_argv[-1], "/work/j; rm -rf /")
        self.assertNotIn("rm -rf", " ".join(reap_argv[:-1]))


if __name__ == "__main__":
    unittest.main()
