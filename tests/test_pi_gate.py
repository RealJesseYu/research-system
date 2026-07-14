"""
test_pi_gate.py — standalone test of tools/pi_gate.py.

Zero model calls: pi_report is pure Python. Covers the four checks against
hand-computed values, the "not checkable" honesty path, the pass path, and the
v1-never-kills contract (enforce exists but is only reachable by an explicit
call, wired nowhere).

Run directly: python3 tests/test_pi_gate.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.pi_gate import pi_enforce_verdict, pi_report, pi_verdict


def base_spec() -> dict:
    """A clean lid-driven-cavity sweep: U=1,3,5; L=1; nu=0.005 -> Re 200/600/1000,
    Co at the top = 5*0.002/(1/80) = 0.80.
    """
    return {
        "hypothesis_id": "h1",
        "parameters": [
            {"name": "lid_velocity", "role": "sweep", "units": "m/s", "min": 1.0, "max": 5.0},
            {"name": "cavity_length", "role": "fixed", "units": "m", "value": 1.0},
            {"name": "kinematic_viscosity", "role": "fixed", "units": "m^2/s", "value": 0.005},
            {"name": "mesh_resolution", "role": "fixed", "units": "cells per side", "value": 80},
            {"name": "time_step", "role": "fixed", "units": "s", "value": 0.002},
        ],
        "mini_experiment": {
            "runs": [
                {"lid_velocity": 1.0, "cavity_length": 1.0, "kinematic_viscosity": 0.005,
                 "mesh_resolution": 80, "time_step": 0.002},
                {"lid_velocity": 3.0, "cavity_length": 1.0, "kinematic_viscosity": 0.005,
                 "mesh_resolution": 80, "time_step": 0.002},
                {"lid_velocity": 5.0, "cavity_length": 1.0, "kinematic_viscosity": 0.005,
                 "mesh_resolution": 80, "time_step": 0.002},
            ],
        },
    }


class ReynoldsMath(unittest.TestCase):
    def test_computed_re_matches_hand_values(self):
        r = pi_report(base_spec())
        got = [p["computed_re"] for p in r["points"]]
        self.assertEqual(got, [200.0, 600.0, 1000.0])

    def test_declared_vs_computed_consistency_flag(self):
        spec = base_spec()
        # declare a derived Re that disagrees at the middle point
        spec["parameters"].append(
            {"name": "reynolds_number", "role": "derived", "units": "dimensionless",
             "derived_from": "U*L/nu"}
        )
        spec["mini_experiment"]["runs"][1]["reynolds_number"] = 999  # wrong (true 600)
        spec["mini_experiment"]["runs"][0]["reynolds_number"] = 200
        spec["mini_experiment"]["runs"][2]["reynolds_number"] = 1000
        r = pi_report(spec)
        self.assertEqual(r["verdict"], "flag")
        self.assertTrue(any("point 2" in x and "disagrees" in x for x in r["reasons"]))

    def test_not_checkable_when_inputs_absent(self):
        # only a declared Re, no U/L/nu -> computed n/a, uses declared, honest note
        spec = {
            "parameters": [
                {"name": "reynolds_number", "role": "sweep", "units": "dimensionless",
                 "min": 100, "max": 300},
            ],
            "mini_experiment": {"runs": [{"reynolds_number": 100}, {"reynolds_number": 300}]},
        }
        r = pi_report(spec)
        self.assertIsNone(r["points"][0]["computed_re"])
        self.assertEqual(r["points"][0]["declared_re"], 100)
        self.assertFalse(r["checkable"]["coherence"])


class DuplicateRe(unittest.TestCase):
    def test_same_re_flagged(self):
        spec = base_spec()
        # collapse all three points to U=2 -> identical Re
        for run in spec["mini_experiment"]["runs"]:
            run["lid_velocity"] = 2.0
        r = pi_report(spec)
        self.assertEqual(r["verdict"], "flag")
        dups = [x for x in r["reasons"] if "share Re" in x]
        self.assertEqual(len(dups), 3)  # pairs (1,2)(1,3)(2,3)

    def test_distinct_re_not_flagged_as_dup(self):
        r = pi_report(base_spec())
        self.assertFalse(any("share Re" in x for x in r["reasons"]))


class Courant(unittest.TestCase):
    def test_high_courant_warns(self):
        r = pi_report(base_spec())
        # top point Co = 0.80 > 0.5 -> exactly one Courant reason
        cour = [x for x in r["reasons"] if "Courant" in x]
        self.assertEqual(len(cour), 1)
        self.assertAlmostEqual(r["points"][2]["courant"], 0.8, places=6)

    def test_low_courant_no_warn(self):
        spec = base_spec()
        # shrink dt so every Co < 0.5
        for run in spec["mini_experiment"]["runs"]:
            run["time_step"] = 0.0005
        r = pi_report(spec)
        self.assertFalse(any("Courant" in x for x in r["reasons"]))


class Coherence(unittest.TestCase):
    def test_incoherent_units_flagged(self):
        spec = base_spec()
        # give viscosity velocity-units -> U*L/nu no longer dimensionless
        for p in spec["parameters"]:
            if p["name"] == "kinematic_viscosity":
                p["units"] = "m/s"
        r = pi_report(spec)
        self.assertTrue(any("incoherence" in x for x in r["reasons"]))

    def test_coherent_units_no_flag(self):
        r = pi_report(base_spec())
        self.assertFalse(any("incoherence" in x for x in r["reasons"]))
        self.assertTrue(r["checkable"]["coherence"])


class NeverKills(unittest.TestCase):
    def test_verdict_is_advisory_only(self):
        # pi_verdict/pi_report never raise and only ever say pass|flag
        self.assertIn(pi_verdict(None)["verdict"], ("pass", "flag"))
        self.assertIn(pi_verdict({})["verdict"], ("pass", "flag"))
        self.assertEqual(pi_report(base_spec())["verdict"], "flag")

    def test_enforce_is_separate_explicit_call(self):
        allowed, reasons = pi_enforce_verdict(base_spec())
        self.assertIsInstance(allowed, bool)
        self.assertIsInstance(reasons, list)
        # base_spec flags (Courant), so enforce would disallow — proving it is a
        # DISTINCT, opt-in gate, deliberately not wired into any pipeline path.
        self.assertFalse(allowed)


class RealSpecOnDisk(unittest.TestCase):
    def test_real_spec_reynolds_matches_declared(self):
        path = Path(__file__).resolve().parent.parent / "runs/20260712T194452Z/stage2/spec.json"
        if not path.exists():
            self.skipTest("real spec not on disk")
        spec = json.loads(path.read_text())
        r = pi_report(spec)
        # this spec declares reynolds_number per point; computed must match
        for pt in r["points"]:
            if pt["computed_re"] is not None and pt["declared_re"] is not None:
                self.assertAlmostEqual(pt["computed_re"], pt["declared_re"], places=3)


if __name__ == "__main__":
    unittest.main()
