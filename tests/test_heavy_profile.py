"""
test_heavy_profile — the sandbox-profile mechanism (2026-07-26).

docs/memo_heavy_verification_lane.md: an artifact may declare a sandbox
`profile` so ONE genuinely heavy evaluation re-runs under heavier ceilings
(time / memory / cpus). The load-bearing tests here are the INVARIANT ones:
no profile may weaken the jail — every profile's docker flags must carry
--network=none and --read-only, and a profile can only hold resource-geometry
keys, so a weakening cannot even be expressed in the table. Pass-through is
tested offline by patching the wrapper; one live smoke proves the heavy lane
actually runs (skipped when the image is absent, like every substrate test).
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from stages.verification import ArtifactError, rerun_artifact, verify_claim
from tools.run_python_experiment import (
    DEFAULT_PROFILE,
    PROFILES,
    PythonExperimentInputError,
    _docker_run_flags,
    _validate_input,
    run_python_experiment,
)


def _image_available() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        out = subprocess.run(
            ["docker", "--context", "colima", "images", "-q", "code-img:latest"],
            capture_output=True, text=True, timeout=30,
        )
        return bool(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


LIVE = _image_available()
requires_image = unittest.skipUnless(LIVE, "code-img:latest not available")

# The only keys a profile may hold. Resource geometry ONLY — if someone adds
# e.g. a "network" key to a profile, this test fails before any run does.
_ALLOWED_PROFILE_KEYS = {
    "image", "default_timeout_s", "max_timeout_s", "memory_mb", "cpus"}


class TestProfileTable(unittest.TestCase):

    def test_default_profile_exists_and_matches_prior_behavior(self):
        self.assertIn(DEFAULT_PROFILE, PROFILES)
        d = PROFILES["default"]
        self.assertEqual(d["default_timeout_s"], 300)
        self.assertEqual(d["max_timeout_s"], 1800)
        self.assertEqual(d["memory_mb"], 4096)
        self.assertEqual(d["cpus"], 2)
        self.assertEqual(d["image"], "code-img:latest")

    def test_profiles_hold_resource_geometry_only(self):
        for name, profile in PROFILES.items():
            self.assertEqual(
                set(profile), _ALLOWED_PROFILE_KEYS,
                f"profile {name!r} carries keys outside the resource geometry")

    def test_every_profile_keeps_the_jail(self):
        # The invariant that makes the heavy lane safe to have at all.
        for name, profile in PROFILES.items():
            flags = _docker_run_flags(profile)
            for required in ("--rm", "--network=none", "--read-only"):
                self.assertIn(required, flags,
                              f"profile {name!r} lost {required}")
            self.assertTrue(any(f.startswith("--pids-limit=") for f in flags),
                            f"profile {name!r} lost the pids limit")

    def test_heavy_raises_ceilings_not_the_jail(self):
        h = PROFILES["heavy"]
        d = PROFILES["default"]
        self.assertGreater(h["default_timeout_s"], d["default_timeout_s"])
        self.assertGreater(h["max_timeout_s"], d["max_timeout_s"])
        self.assertGreater(h["memory_mb"], d["memory_mb"])
        flags = _docker_run_flags(h)
        self.assertIn("--memory=6144m", flags)
        self.assertIn("--memory-swap=6144m", flags)  # swap stays disabled
        self.assertIn("4", flags[flags.index("--cpus") + 1])


class TestProfileValidation(unittest.TestCase):

    def test_absent_profile_resolves_to_default(self):
        clean = _validate_input({"code": "metrics['x']=1", "quantity": "x"})
        self.assertEqual(clean["profile"], "default")
        self.assertEqual(clean["timeout_s"], 300)

    def test_unknown_profile_rejected_naming_the_valid_ones(self):
        with self.assertRaises(PythonExperimentInputError) as cm:
            run_python_experiment(
                {"code": "metrics['x']=1", "quantity": "x", "profile": "gpu"})
        msg = str(cm.exception)
        self.assertIn("gpu", msg)
        self.assertIn("heavy", msg)

    def test_heavy_widens_the_timeout_bound(self):
        # 3600 is refused by default and accepted by heavy; 3601 refused by both.
        with self.assertRaises(PythonExperimentInputError):
            _validate_input(
                {"code": "x=1", "quantity": "x", "timeout_s": 3600})
        clean = _validate_input(
            {"code": "x=1", "quantity": "x", "timeout_s": 3600,
             "profile": "heavy"})
        self.assertEqual(clean["timeout_s"], 3600)
        with self.assertRaises(PythonExperimentInputError):
            _validate_input(
                {"code": "x=1", "quantity": "x", "timeout_s": 3601,
                 "profile": "heavy"})

    def test_heavy_default_budget_is_1800(self):
        clean = _validate_input(
            {"code": "x=1", "quantity": "x", "profile": "heavy"})
        self.assertEqual(clean["timeout_s"], 1800)


class TestVerificationPassThrough(unittest.TestCase):
    """The wall must carry the artifact's declared profile into the sandbox
    spec — and must NOT invent one when the artifact is silent."""

    def _capture(self, artifact):
        captured = {}

        def fake_run(spec):
            captured.update(spec)
            return {"valid": True, "qoi": 1.0, "metrics": {"x": 1.0},
                    "diagnostics": "", "runtime_s": 0.0}

        with mock.patch(
                "tools.run_python_experiment.run_python_experiment", fake_run):
            result = rerun_artifact(artifact)
        return captured, result

    def test_code_artifact_profile_travels(self):
        captured, result = self._capture(
            {"kind": "code", "code": "metrics['x']=1.0", "quantity": "x",
             "profile": "heavy"})
        self.assertEqual(captured.get("profile"), "heavy")
        self.assertEqual(result["value"], 1.0)

    def test_code_artifact_without_profile_stays_bare(self):
        captured, _ = self._capture(
            {"kind": "code", "code": "metrics['x']=1.0", "quantity": "x"})
        self.assertNotIn("profile", captured)

    def test_workspace_file_profile_travels(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "recheck.py"
            p.write_text("metrics['x']=1.0\n")
            captured, result = self._capture(
                {"kind": "workspace_file", "path": str(p), "quantity": "x",
                 "profile": "heavy"})
        self.assertEqual(captured.get("profile"), "heavy")
        self.assertEqual(result["value"], 1.0)

    def test_unknown_profile_is_an_unrunnable_artifact_not_a_crash(self):
        # No docker involved: the wrapper rejects the profile before any run.
        claim = {"value": 1.0,
                 "artifact": {"kind": "code", "code": "metrics['x']=1.0",
                              "quantity": "x", "profile": "warp-drive"}}
        verdict = verify_claim(claim)
        self.assertFalse(verdict["verified"])
        self.assertEqual(verdict["reason"], "unrunnable_artifact")
        self.assertIn("warp-drive", verdict["detail"])

    def test_unknown_profile_raises_artifact_error_from_rerun(self):
        with self.assertRaises(ArtifactError):
            rerun_artifact({"kind": "code", "code": "metrics['x']=1.0",
                            "quantity": "x", "profile": "warp-drive"})


class TestFindingArtifactPassThrough(unittest.TestCase):

    def test_free_experimenter_carries_profile(self):
        from stages.free_experimenter import _finding_artifact
        art = _finding_artifact(
            {"file": "recheck.py", "quantity": "x", "profile": "heavy"},
            "/some/workspace")
        self.assertEqual(art["kind"], "workspace_file")
        self.assertEqual(art["profile"], "heavy")

    def test_free_experimenter_omits_absent_profile(self):
        from stages.free_experimenter import _finding_artifact
        art = _finding_artifact(
            {"file": "recheck.py", "quantity": "x"}, "/some/workspace")
        self.assertNotIn("profile", art)


class TestLiveHeavyLane(unittest.TestCase):

    @requires_image
    def test_heavy_profile_runs_and_reports(self):
        # timeout_s 2400 was impossible before (old hard max 1800): declaring
        # it AND completing proves the raised ceiling reaches a real container,
        # at the cost of an instant script — the budget is a ceiling, not a wait.
        summary = run_python_experiment({
            "code": "metrics['x'] = 2.0",
            "quantity": "x",
            "profile": "heavy",
            "timeout_s": 2400,
        })
        self.assertTrue(summary["valid"], summary["diagnostics"])
        self.assertEqual(summary["qoi"], 2.0)


if __name__ == "__main__":
    unittest.main()
