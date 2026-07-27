"""The engineering lane: geometry, thermofluids, dynamics, RF and digital logic.

Offline. The live known-answer proofs (CadQuery volume to machine precision,
CoolProp's enthalpy of vaporisation against steam tables, MuJoCo free-fall
against 0.5gt^2, scikit-rf reflection against (ZL-Z0)/(ZL+Z0), and an
iverilog-compiled adder) are recorded in docs/memo_engineering_lane.md.

Asserted here: the wiring, the shelf's contents, and the honest fence — this
lane adds digital logic and deliberately does NOT pretend to add nonlinear
analog, which remains Route-A regime work on the ngspice substrate.
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import substrate_registry as registry  # noqa: E402
from tools.run_python_experiment import (  # noqa: E402
    ATOMISTIC_IMAGE,
    BIODESIGN_IMAGE,
    ENGINEERING_IMAGE,
    IMAGE,
    PROFILES,
    _docker_run_flags,
    _validate_input,
)

ENV_DIR = ROOT / "tools" / "engineering_env"

EXPECTED_SHELF = {
    "numpy", "scipy",
    "cadquery", "cadquery-ocp", "build123d",   # geometry
    "coolprop",                                 # thermofluid properties
    "mujoco",                                   # multibody dynamics
    "scikit-rf",                                # RF networks
}


class TestEngineeringProfiles(unittest.TestCase):

    def test_both_geometries_are_offered_against_the_shelf(self):
        for name in ("engineering", "engineering-heavy"):
            self.assertIn(name, PROFILES, name)
            self.assertEqual(PROFILES[name]["image"], ENGINEERING_IMAGE, name)

    def test_every_shelf_is_a_distinct_image(self):
        self.assertEqual(
            len({IMAGE, ATOMISTIC_IMAGE, BIODESIGN_IMAGE, ENGINEERING_IMAGE}), 4)

    def test_profile_is_shelf_times_geometry(self):
        for shelf, base in (("engineering", "default"),
                            ("engineering-heavy", "heavy")):
            for key in ("default_timeout_s", "max_timeout_s", "memory_mb", "cpus"):
                self.assertEqual(PROFILES[shelf][key], PROFILES[base][key],
                                 f"{shelf}.{key} drifted from {base}")

    def test_the_shelf_kept_the_jail(self):
        for name in ("engineering", "engineering-heavy"):
            flags = _docker_run_flags(PROFILES[name])
            self.assertIn("--network=none", flags, name)
            self.assertIn("--read-only", flags, name)

    def test_the_profile_validates(self):
        clean = _validate_input({"code": "metrics['x']=1", "quantity": "x",
                                 "profile": "engineering"})
        self.assertEqual(clean["profile"], "engineering")


class TestEngineeringImageDefinition(unittest.TestCase):

    def test_every_package_is_pinned(self):
        reqs = (ENV_DIR / "requirements.txt").read_text().splitlines()
        pkgs = [l.strip() for l in reqs if l.strip() and not l.startswith("#")]
        self.assertTrue(pkgs)
        for line in pkgs:
            self.assertRegex(line, r"^[A-Za-z0-9_.\-]+==[0-9]",
                             f"unpinned requirement: {line!r}")

    def test_the_shelf_is_what_the_lane_promises(self):
        reqs = (ENV_DIR / "requirements.txt").read_text()
        names = {m.group(1).lower()
                 for m in re.finditer(r"^([A-Za-z0-9_.\-]+)==", reqs, re.M)}
        self.assertEqual(names, EXPECTED_SHELF)

    def test_digital_logic_tools_are_system_installed(self):
        # The circuitry half. Not pip packages — apt tools, so they are asserted
        # in the Dockerfile rather than the manifest.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("iverilog", dockerfile)
        self.assertIn("verilator", dockerfile)

    def test_opencascade_system_libraries_are_present(self):
        # CadQuery imports fail without these even headless; a missing libGL is
        # the classic way this image breaks on a rebuild.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        for lib in ("libgl1", "libglu1-mesa", "libx11-6"):
            self.assertIn(lib, dockerfile, lib)

    def test_the_build_exercises_each_library_not_just_imports_it(self):
        # A geometry kernel that imports but cannot build a solid, or a property
        # library with no fluid data, is the failure worth catching at build.
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("Volume()", dockerfile)      # cadquery actually builds
        self.assertIn("PropsSI", dockerfile)       # coolprop actually queries
        self.assertIn("mj_step", dockerfile)       # mujoco actually steps
        self.assertIn("IVERILOG_OK=42", dockerfile)  # the toolchain actually runs

    def test_threads_are_pinned(self):
        self.assertIn("OMP_NUM_THREADS=1", (ENV_DIR / "Dockerfile").read_text())


class TestTheFenceIsHonest(unittest.TestCase):
    """This lane adds DIGITAL logic. It must not read as having added nonlinear
    analog, which is genuinely out of reach and is Route-A work."""

    def test_the_dockerfile_states_what_it_does_not_add(self):
        dockerfile = (ENV_DIR / "Dockerfile").read_text()
        self.assertIn("NONLINEAR ANALOG", dockerfile)

    def test_the_passive_spice_substrate_is_untouched_by_this_lane(self):
        # ngspice stays exactly as it was: routable, still fenced to linear
        # passive networks. Nothing here widened its envelope.
        record = registry.get("ngspice_linear_passive")
        self.assertTrue(record.routable)
        self.assertIn("linear passive",
                      registry.contract_for("ngspice_linear_passive").lower())


if __name__ == "__main__":
    unittest.main()
