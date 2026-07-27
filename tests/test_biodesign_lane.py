"""The bio-design lane: ProteinMPNN as a sandbox shelf, and the defer it corrects.

Offline. The live proofs — 4 designs on the 1UBQ backbone in ~2.9 s, mean native
recovery 0.5526, bit-identical across repeats at a fixed seed, and a design
result reproducing through the verification wall — are recorded in
docs/memo_biodesign_lane.md.

What is asserted here is the wiring and, importantly, the GOVERNANCE: correcting
a defer's stated reason must not quietly promote the row. The capability is live
as a shelf; the registry row stays unrouted, and these tests fail if that ever
silently changes.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import substrate_dispatch as dispatch  # noqa: E402
from tools import substrate_registry as registry  # noqa: E402
from tools.run_python_experiment import (  # noqa: E402
    ATOMISTIC_IMAGE,
    BIODESIGN_IMAGE,
    IMAGE,
    PROFILES,
    _docker_run_flags,
    _validate_input,
)

ENV_DIR = ROOT / "tools" / "biodesign_env"
FIXTURE = ROOT / "tests" / "fixtures" / "1ubq_backbone.pdb"


class TestBiodesignProfiles(unittest.TestCase):

    def test_both_geometries_are_offered_against_the_shelf(self):
        for name in ("biodesign", "biodesign-heavy"):
            self.assertIn(name, PROFILES, name)
            self.assertEqual(PROFILES[name]["image"], BIODESIGN_IMAGE, name)

    def test_every_shelf_is_a_distinct_image(self):
        self.assertEqual(len({IMAGE, ATOMISTIC_IMAGE, BIODESIGN_IMAGE}), 3)

    def test_profile_is_shelf_times_geometry(self):
        for shelf, base in (("biodesign", "default"), ("biodesign-heavy", "heavy")):
            for key in ("default_timeout_s", "max_timeout_s", "memory_mb", "cpus"):
                self.assertEqual(PROFILES[shelf][key], PROFILES[base][key],
                                 f"{shelf}.{key} drifted from {base}")

    def test_the_shelf_kept_the_jail(self):
        for name in ("biodesign", "biodesign-heavy"):
            flags = _docker_run_flags(PROFILES[name])
            self.assertIn("--network=none", flags, name)
            self.assertIn("--read-only", flags, name)

    def test_the_profile_validates(self):
        clean = _validate_input({"code": "metrics['x']=1", "quantity": "x",
                                 "profile": "biodesign"})
        self.assertEqual(clean["profile"], "biodesign")


class TestWeightsAreProvisionedNotDownloaded(unittest.TestCase):
    """The half of the original defer that was RIGHT: weights must be present
    before the run, because the sandbox has no network."""

    def test_upstream_is_pinned_to_a_commit_not_a_branch(self):
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("PROTEINMPNN_COMMIT=8907e667", dockerfile)
        self.assertIn("git checkout", dockerfile)

    def test_the_build_records_a_weight_checksum_manifest(self):
        # "mismatched weights = confident garbage" is the specific failure the
        # row's un-defer clause names; a recorded manifest is how a run can say
        # exactly which parameters produced its numbers.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("sha256sum", dockerfile)
        self.assertIn("WEIGHTS.sha256", dockerfile)

    def test_cpu_torch_is_explicit(self):
        # The default index would pull a CUDA build that cannot load here, and a
        # silent fallback is how a "GPU required" myth starts in the first place.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("download.pytorch.org/whl/cpu", dockerfile)

    def test_the_build_asserts_runner_and_weights_exist(self):
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("protein_mpnn_run.py", dockerfile)
        self.assertIn("v_48_020.pt", dockerfile)


class TestKnownAnswerFixture(unittest.TestCase):

    def test_the_backbone_fixture_is_present_and_is_a_backbone(self):
        self.assertTrue(FIXTURE.is_file())
        lines = [l for l in FIXTURE.read_text().splitlines() if l.startswith("ATOM")]
        self.assertEqual(len(lines), 304)          # 76 residues x N/CA/C/O
        atoms = {l[12:16].strip() for l in lines}
        self.assertEqual(atoms, {"N", "CA", "C", "O"})


class TestCorrectingADeferDidNotPromoteIt(unittest.TestCase):
    """The governance property. A truth-edit fixes what a note CLAIMS; it must
    not hand the row authority it has not earned."""

    def test_the_row_is_still_unrouted(self):
        record = registry.get("proteinmpnn")
        self.assertFalse(record.routable)
        self.assertNotIn("proteinmpnn", registry.routable_ids())
        self.assertNotIn("proteinmpnn", registry.permitted_ids())

    def test_the_runtime_maps_are_still_unwired(self):
        for lookup in (dispatch.adapter_for, dispatch.qoi_translation_for,
                       dispatch.run_entry_constructor_for):
            with self.assertRaises(LookupError):
                lookup("proteinmpnn")
        with self.assertRaises(LookupError):
            registry.contract_for("proteinmpnn")

    def test_the_note_records_the_correction_and_where_capability_lives(self):
        notes = registry.get("proteinmpnn").notes
        self.assertIn("TRUTH-EDIT", notes)
        self.assertIn("GPU PREMISE ABOVE IS WRONG", notes)
        self.assertIn("biodesign", notes)          # names where it actually runs
        self.assertIn("routable=False", notes)     # and that nothing was promoted

    def test_the_interpretation_limit_survives_the_correction(self):
        # Reproducibility was never the open question for this tool.
        self.assertIn("does NOT mean the design folds or functions",
                      registry.get("proteinmpnn").notes)


if __name__ == "__main__":
    unittest.main()
