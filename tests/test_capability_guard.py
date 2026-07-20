"""
test_capability_guard — what a tooled stage may not touch (2026-07-20).

Granting stages tools re-opened three holes that allowed_tools=[] had closed by
accident. These tests are the enforcement of the closures, and they matter more
than most tests in this project: every one of them corresponds to a way an
autonomous stage could corrupt the evidence it is judged by.

The relative-path cases are not padding. The first version of the guard matched
"/memory/" and cheerfully allowed Write("memory/journal.jsonl") — the relative
form, which is how every call site in this project actually writes a path.
"""

import unittest

from capability_guard import (
    CapabilityPairingError,
    assert_profile_allowed,
    check,
)


class TestTranscriptReadBack(unittest.TestCase):
    """Hole 1: transcripts are the cross-context covert channel the whole
    six-fresh-contexts design exists to prevent."""

    def test_relative_and_absolute_both_denied(self):
        for path in (
            "runs/x/transcripts/0001_a.json",
            "/Users/jesseyu/research-system/runs/x/transcripts/0001_a.json",
            "./runs/x/transcripts/0001_a.json",
        ):
            ok, _ = check("Read", {"file_path": path})
            self.assertFalse(ok, path)

    def test_glob_and_grep_denied(self):
        self.assertFalse(check("Glob", {"pattern": "runs/*/transcripts/*.json"})[0])
        self.assertFalse(check("Grep", {"pattern": "x", "path": "runs/a/transcripts/"})[0])

    def test_shell_read_denied(self):
        self.assertFalse(check("Bash", {"command": "cat runs/a/transcripts/0001.json"})[0])


class TestAnswerKeyLeak(unittest.TestCase):
    """Hole 2: a gate that can grep its own answer key is not a gate."""

    def test_calibration_artifacts_denied(self):
        for inp in (
            {"file_path": "harness/calibration_cobrapy_20260719T052035Z.json"},
            {"pattern": "expected_class", "path": "harness/"},
            {"pattern": "acceptable_labels"},
            {"file_path": "harness/killrate_last_run.json"},
        ):
            self.assertFalse(check("Grep", inp)[0], inp)


class TestEvidenceAndMemoryMutation(unittest.TestCase):
    """Hole 3: the supervisor reads memory/. A stage that rewrites it rewrites
    what the next run believes."""

    def test_journal_and_ledger_writes_denied(self):
        for path in ("memory/journal.jsonl", "./memory/ledgers.jsonl",
                     "/Users/jesseyu/research-system/memory/journal.jsonl"):
            self.assertFalse(check("Write", {"file_path": path})[0], path)
            self.assertFalse(check("Edit", {"file_path": path})[0], path)

    def test_shell_mutation_of_evidence_denied(self):
        for cmd in ("rm -rf runs/20260720T080610Z",
                    "echo x >> memory/journal.jsonl",
                    "sed -i '' s/a/b/ memory/journal.jsonl",
                    "rm -rf cases_cobrapy/"):
            self.assertFalse(check("Bash", {"command": cmd})[0], cmd)

    def test_shell_read_of_memory_denied(self):
        """Reading the journal is a leak even though it mutates nothing."""
        self.assertFalse(check("Bash", {"command": "cat memory/journal.jsonl"})[0])


class TestCredentials(unittest.TestCase):

    def test_env_denied_for_read_and_write(self):
        self.assertFalse(check("Read", {"file_path": ".env"})[0])
        self.assertFalse(check("Bash", {"command": "cat .env"})[0])
        self.assertFalse(check("Write", {"file_path": ".env"})[0])


class TestLegitimateWorkStillAllowed(unittest.TestCase):
    """A guard that blocks the actual work is just the old cage with extra
    steps. These are the cases that must keep working."""

    def test_reading_source_and_docs(self):
        self.assertTrue(check("Read", {"file_path": "stages/stage2_experiment_design.py"})[0])
        self.assertTrue(check("Read", {"file_path": "docs/envelope_card_cobrapy.md"})[0])
        self.assertTrue(check("Grep", {"pattern": "MODEL_ALLOWLIST", "path": "tools/"})[0])

    def test_web_and_scratch_and_running_code(self):
        self.assertTrue(check("WebSearch", {"query": "iML1515 reactions"})[0])
        self.assertTrue(check("WebFetch", {"url": "https://example.com/paper"})[0])
        self.assertTrue(check("Write", {"file_path": "/tmp/scratch/fit.py"})[0])
        self.assertTrue(check("Bash", {"command": "python3 /tmp/scratch/fit.py --seed 0"})[0])

    def test_empty_input_is_allowed(self):
        self.assertTrue(check("Bash", {})[0])


class TestStageProfilePairing(unittest.TestCase):
    """capabilities= is an ordinary keyword argument. Without this table
    nothing stops a future edit handing the fidelity gate a tooled profile."""

    def test_measurement_stages_may_not_hold_tools(self):
        for stage in ("stage3_fidelity_gate", "stage4_simulation",
                      "stage5_thought_layer", "stage6_desk_review",
                      "calibration_battery"):
            for profile in ("discovery", "builder"):
                with self.assertRaises(CapabilityPairingError, msg=f"{stage}/{profile}"):
                    assert_profile_allowed(stage, profile)

    def test_sealed_is_always_allowed(self):
        for stage in ("stage3_fidelity_gate", "stage1_generation", "anything"):
            assert_profile_allowed(stage, "sealed")  # must not raise

    def test_discovery_stages_may_hold_tools(self):
        for stage in ("stage1_generation_literature", "stage2_experiment_design",
                      "stage1_reflection_full", "stage1_meta_review"):
            assert_profile_allowed(stage, "discovery")
            assert_profile_allowed(stage, "builder")


if __name__ == "__main__":
    unittest.main()
