"""The atomistic lane: a second sandbox SHELF, reached the same way as the first.

Offline. The live proofs (PySCF, ASE, OpenMM, pymatgen actually computing inside
the image, and an atomistic result reproducing through the verification wall)
are recorded in docs/memo_atomistic_lane.md; what is asserted here is the wiring
that must not drift — that a profile is (shelf x geometry), that the new shelf is
a genuinely different image, and that adding it took nothing away from the jail.

Note the division of labour with tests/test_heavy_profile.py: its invariant tests
loop over EVERY profile, so the jail and geometry-only checks already cover these
two the moment they are added. That is the design working — a new shelf cannot
quietly become an exception.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.run_python_experiment import (  # noqa: E402
    ATOMISTIC_IMAGE,
    IMAGE,
    PROFILES,
    _docker_run_flags,
    _validate_input,
)

ENV_DIR = ROOT / "tools" / "atomistic_env"

# The shelf this lane exists to provide. One tool per layer of theory, plus the
# hub that makes them compose. A package leaving this list is a capability
# leaving the system, so the manifest is pinned here too.
EXPECTED_SHELF = {"ase", "pymatgen", "pyscf", "openmm", "rdkit", "numpy", "scipy"}


class TestAtomisticProfiles(unittest.TestCase):

    def test_both_geometries_are_offered_against_the_new_shelf(self):
        for name in ("atomistic", "atomistic-heavy"):
            self.assertIn(name, PROFILES, name)
            self.assertEqual(PROFILES[name]["image"], ATOMISTIC_IMAGE, name)

    def test_the_shelf_is_a_different_image_from_the_code_lane(self):
        # If these ever collided, an atomistic experiment would run against the
        # sklearn shelf and fail on import rather than on physics.
        self.assertNotEqual(ATOMISTIC_IMAGE, IMAGE)

    def test_profile_is_shelf_times_geometry(self):
        # atomistic mirrors default's geometry; atomistic-heavy mirrors heavy's.
        # Only the image differs — that factorization is the whole point, and it
        # is what keeps one lane's resource decisions from drifting from the
        # other's.
        for shelf, base in (("atomistic", "default"), ("atomistic-heavy", "heavy")):
            for key in ("default_timeout_s", "max_timeout_s", "memory_mb", "cpus"):
                self.assertEqual(PROFILES[shelf][key], PROFILES[base][key],
                                 f"{shelf}.{key} drifted from {base}")

    def test_the_new_lane_kept_the_jail(self):
        # Covered generically by test_heavy_profile's all-profiles loop; asserted
        # explicitly here because it is the one property a new shelf could
        # plausibly be tempted to relax (a network install at runtime).
        for name in ("atomistic", "atomistic-heavy"):
            flags = _docker_run_flags(PROFILES[name])
            self.assertIn("--network=none", flags, name)
            self.assertIn("--read-only", flags, name)
            self.assertIn("--rm", flags, name)

    def test_an_atomistic_profile_validates(self):
        clean = _validate_input({"code": "metrics['x']=1", "quantity": "x",
                                 "profile": "atomistic"})
        self.assertEqual(clean["profile"], "atomistic")
        self.assertEqual(clean["timeout_s"], PROFILES["default"]["default_timeout_s"])

    def test_a_misspelled_shelf_is_refused_naming_the_real_ones(self):
        from tools.run_python_experiment import PythonExperimentInputError
        with self.assertRaises(PythonExperimentInputError) as ctx:
            _validate_input({"code": "metrics['x']=1", "quantity": "x",
                             "profile": "atomistics"})
        self.assertIn("atomistic", str(ctx.exception))


class TestAtomisticImageDefinition(unittest.TestCase):

    def test_the_env_directory_is_the_house_shape(self):
        self.assertTrue((ENV_DIR / "Dockerfile").is_file())
        self.assertTrue((ENV_DIR / "requirements.txt").is_file())

    def test_every_package_is_pinned(self):
        # Same discipline as code_env: a job's result must be a function of the
        # spec alone, never of a dependency that drifted since the build.
        reqs = (ENV_DIR / "requirements.txt").read_text().splitlines()
        pkgs = [l.strip() for l in reqs if l.strip() and not l.startswith("#")]
        self.assertTrue(pkgs, "the manifest is empty")
        for line in pkgs:
            self.assertRegex(line, r"^[A-Za-z0-9_.\-]+==[0-9]",
                             f"unpinned requirement: {line!r}")

    def test_the_shelf_is_what_the_lane_promises(self):
        reqs = (ENV_DIR / "requirements.txt").read_text()
        names = {m.group(1).lower()
                 for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==", reqs, re.M)}
        self.assertEqual(names, EXPECTED_SHELF)

    def test_the_build_self_checks_every_library(self):
        # The build imports the whole shelf and exercises OpenMM's platform
        # registration, so a broken wheel fails the BUILD rather than the first
        # experiment that reaches for it.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        for lib in ("ase", "pymatgen", "pyscf", "rdkit"):
            self.assertIn(lib, dockerfile, f"{lib} is not smoke-checked at build")
        self.assertIn("Platform", dockerfile)

    def test_threads_are_pinned_so_wall_clock_is_not_host_dependent(self):
        # A library that spawns a thread per core makes a run's timing (and
        # sometimes its floating-point reduction order) depend on the host —
        # which verification would then report as irreproducibility.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("OMP_NUM_THREADS=1", dockerfile)


if __name__ == "__main__":
    unittest.main()
