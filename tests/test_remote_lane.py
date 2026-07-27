"""The remote lane: rented hardware for the class of tools this machine cannot run.

Fully offline — the `dispatch` seam stands in for Modal, so every outcome is
provable without an account, a token, or a bill.

The most important tests here are the NEGATIVE ones. R-REMOTE-1 says a remote
result is an input and never a claim, and that policy is enforced structurally:
there is no `remote` artifact kind, the wrapper returns no `qoi`, and nothing
imports it into the verification path. Those absences are asserted, because an
absence is exactly the kind of guarantee a later edit erodes without noticing.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import verification  # noqa: E402
from tools import run_remote_job as remote  # noqa: E402


def _ok(metrics=None, artifacts=None, returncode=0, stderr=""):
    def dispatch(clean):
        return {"returncode": returncode, "metrics": metrics or {},
                "artifacts": artifacts or {}, "stdout": "", "stderr": stderr}
    return dispatch


class TestRemoteJobOutcomes(unittest.TestCase):

    def test_a_completed_job_returns_metrics_and_files(self):
        out = remote.run_remote_job(
            {"code": "print(1)", "gpu": "A10G", "output_files": ["out.pdb"]},
            dispatch=_ok(metrics={"plddt": 85.2}, artifacts={"out.pdb": b"ATOM"}))
        self.assertTrue(out["valid"])
        self.assertEqual(out["metrics"], {"plddt": 85.2})
        self.assertEqual(out["artifacts"], {"out.pdb": b"ATOM"})
        self.assertIn("A10G", out["diagnostics"])

    def test_every_success_says_it_is_not_a_claim(self):
        out = remote.run_remote_job({"code": "x"}, dispatch=_ok(metrics={"a": 1.0}))
        self.assertIn("INPUT, NOT A CLAIM", out["diagnostics"])
        self.assertIn("verified\": false", out["diagnostics"])

    def test_a_failed_job_does_not_pass_off_its_metrics(self):
        out = remote.run_remote_job(
            {"code": "x"},
            dispatch=_ok(metrics={"plddt": 99.0}, returncode=1, stderr="CUDA OOM"))
        self.assertFalse(out["valid"])
        self.assertIn("CUDA OOM", out["diagnostics"])
        self.assertIn("not\ntrustworthy", out["diagnostics"].replace(" ", "\n"))

    def test_a_declared_output_that_never_appeared_fails_loudly(self):
        out = remote.run_remote_job(
            {"code": "x", "output_files": ["structure.pdb"]}, dispatch=_ok())
        self.assertFalse(out["valid"])
        self.assertIn("structure.pdb", out["diagnostics"])

    def test_unreachable_backend_is_a_could_not_run(self):
        def dead(clean):
            raise remote.RemoteJobUnavailable("AuthError: no token")
        out = remote.run_remote_job({"code": "x"}, dispatch=dead)
        self.assertFalse(out["valid"])
        self.assertIn("setup_error", out["diagnostics"])
        self.assertIn("modal token new", out["diagnostics"])
        self.assertIn("no result was fabricated", out["diagnostics"])

    def test_oversized_artifacts_are_dropped_not_returned(self):
        big = b"x" * (remote.MAX_ARTIFACT_BYTES + 1)
        out = remote.run_remote_job(
            {"code": "x", "output_files": ["big.bin"]},
            dispatch=_ok(artifacts={"big.bin": big}))
        self.assertFalse(out["valid"])          # declared but not delivered
        self.assertNotIn("big.bin", out["artifacts"])


class TestInputJail(unittest.TestCase):

    def test_gpu_allowlist_refuses_a_typo_before_it_becomes_a_bill(self):
        out = remote.run_remote_job({"code": "x", "gpu": "H200"}, dispatch=_ok())
        self.assertFalse(out["valid"])
        self.assertIn("allowlist", out["diagnostics"])

    def test_cpu_jobs_are_allowed_explicitly(self):
        out = remote.run_remote_job({"code": "x", "gpu": None}, dispatch=_ok())
        self.assertTrue(out["valid"])
        self.assertIn("cpu", out["diagnostics"])

    def test_timeout_is_bounded(self):
        for bad in (0, remote.MAX_TIMEOUT_S + 1, "soon"):
            out = remote.run_remote_job({"code": "x", "timeout_s": bad},
                                        dispatch=_ok())
            self.assertFalse(out["valid"], bad)

    def test_path_traversal_in_file_names_is_refused(self):
        for spec in ({"code": "x", "input_files": {"../evil": b"a"}},
                     {"code": "x", "output_files": ["/etc/passwd"]}):
            out = remote.run_remote_job(spec, dispatch=_ok())
            self.assertFalse(out["valid"])
            self.assertIn("bare filename", out["diagnostics"])

    def test_structural_input_errors(self):
        for spec, expect in (
            ({}, "missing required"),
            ({"code": "x", "nope": 1}, "unsupported field"),
            ({"code": ""}, "non-empty"),
            ({"code": "x", "pip": "torch"}, "list of strings"),
            ({"code": "x", "input_files": {"a": "not bytes"}}, "must be bytes"),
        ):
            out = remote.run_remote_job(spec, dispatch=_ok())
            self.assertFalse(out["valid"])
            self.assertIn(expect, out["diagnostics"])


class TestRemoteResultsCannotBecomeClaims(unittest.TestCase):
    """R-REMOTE-1, enforced by absence. These are the tests that matter."""

    def test_the_wrapper_returns_no_qoi(self):
        # Every other wrapper returns one because every other wrapper feeds a
        # claim. The missing field IS the policy.
        out = remote.run_remote_job({"code": "x"}, dispatch=_ok(metrics={"a": 1.0}))
        self.assertNotIn("qoi", out)

    def test_verification_has_no_remote_artifact_kind(self):
        verdict = verification.verify_claim({
            "value": 85.2,
            "artifact": {"kind": "remote", "code": "fold()", "quantity": "plddt"}})
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "unrunnable_artifact")
        self.assertIn("unknown artifact kind", verdict["detail"])

    def test_the_wrapper_is_not_reachable_from_the_verification_path(self):
        # A remote job must not be re-runnable by the wall — not because a flag
        # forbids it, but because no path exists.
        source = (ROOT / "stages" / "verification.py").read_text()
        self.assertNotIn("run_remote_job", source)
        self.assertNotIn("remote_job", source)

    def test_the_registry_does_not_enroll_a_remote_substrate(self):
        # Enrollment would give wrapper_callable a route to it, which is the
        # first half of becoming verifiable.
        from tools import substrate_registry as registry
        ids = [r.substrate_id for r in registry.all_substrates()]
        for sid in ids:
            self.assertNotEqual(registry.get(sid).wrapper, "tools/run_remote_job.py")


if __name__ == "__main__":
    unittest.main()
