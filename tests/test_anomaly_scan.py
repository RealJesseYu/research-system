"""
test_anomaly_scan.py — Phase-1 Lane-1: read-only scanner smoke.
Deterministic, ZERO model calls. A fixture runs/ tree with a planted outlier,
a repeated-across-runs QoI value, a truncated json, and an empty file is built
in a TemporaryDirectory; the scanner must find each.

Run directly: venv/bin/python3 tests/test_anomaly_scan.py
"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import anomaly_scan


def _run(qoi_name, qoi_value, wall):
    return {"status": "executed", "runs": [
        {"run_index": 1, "case": "c1", "summary": {
            "converged": True, "final_time": 20.0, "end_time": 20.0,
            "residuals": {"Ux": 1e-9, "Uy": 1e-9, "p": 1e-8},
            "key_result": {"max_Courant": 0.30, "continuity_global": 1e-19},
            "runtime": {"wall_clock_s": wall, "solver_execution_time_s": wall - 1},
            "qoi": {"name": qoi_name, "value": qoi_value, "time": 20.0},
        }},
    ]}


class ScannerSmoke(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runs = root / "runs"
        self.harness = root / "harness"
        self.runs.mkdir()
        self.harness.mkdir()

        # four normal wall times + one planted OUTLIER (500s)
        walls = {"R1": 10.0, "R2": 11.0, "R3": 10.5, "R4": 12.0, "ROUT": 500.0}
        for rid, wall in walls.items():
            (self.runs / rid / "stage4").mkdir(parents=True)
            (self.runs / rid / "stage4" / "results.json").write_text(
                json.dumps(_run("volAverage(mag(U))", 0.4, wall)))

        # a REPEATED QoI value across two DISTINCT runs
        for rid in ("RREP1", "RREP2"):
            (self.runs / rid / "stage4").mkdir(parents=True)
            (self.runs / rid / "stage4" / "results.json").write_text(
                json.dumps(_run("cellMin(U)[0]", -0.123456, 9.0)))

        # a TRUNCATED json file
        (self.runs / "RTRUNC" / "stage4").mkdir(parents=True)
        (self.runs / "RTRUNC" / "stage4" / "results.json").write_text('{"status": "executed", "runs": [')

        # an EMPTY results.json
        (self.runs / "REMPTY" / "stage4").mkdir(parents=True)
        (self.runs / "REMPTY" / "stage4" / "results.json").write_text("")

        self.findings = anomaly_scan.run_scan(self.runs, self.harness)

    def tearDown(self):
        self.tmp.cleanup()

    def test_planted_outlier_found(self):
        wall_outliers = self.findings["outliers"].get("wall_clock_s", [])
        labels = [o["label"] for o in wall_outliers]
        values = [o["value"] for o in wall_outliers]
        self.assertTrue(any(v == 500.0 for v in values), f"500s outlier not flagged: {wall_outliers}")

    def test_repeated_value_across_distinct_runs(self):
        rep = self.findings["repeated_values"].get("qoi:cellMin(U)[0]", [])
        self.assertTrue(rep, "repeated QoI value not detected")
        entry = rep[0]
        self.assertEqual(entry["n_runs"], 2)
        self.assertEqual(sorted(entry["run_ids"]), ["RREP1", "RREP2"])

    def test_truncated_and_empty_flagged(self):
        issues = " ".join(s["issue"] + " " + s["file"] for s in self.findings["structural"])
        self.assertIn("RTRUNC", issues)
        self.assertIn("truncated", issues.lower() + issues)  # message contains 'truncated'
        self.assertIn("REMPTY", issues)
        self.assertIn("empty", issues.lower())

    def test_no_predicted_wall_time_field(self):
        # fixtures write no predicted field -> gaps must be empty
        self.assertEqual(self.findings["wall_time_gaps"], [])

    def test_report_renders(self):
        text = anomaly_scan.format_report(self.findings)
        self.assertIn("# Anomaly scan v0", text)
        self.assertIn("(a) Outliers", text)
        self.assertIn("(d) Structural", text)


class IqrUnit(unittest.TestCase):
    def test_iqr_needs_four_points(self):
        self.assertEqual(anomaly_scan._iqr_outliers([("a", 1.0), ("b", 2.0), ("c", 100.0)]), [])

    def test_iqr_flags_clear_outlier(self):
        vals = [("a", 1.0), ("b", 1.1), ("c", 0.9), ("d", 1.05), ("e", 50.0)]
        out = anomaly_scan._iqr_outliers(vals)
        self.assertEqual([o["label"] for o in out], ["e"])

    def test_zero_spread_no_outlier(self):
        vals = [("a", 5.0), ("b", 5.0), ("c", 5.0), ("d", 5.0)]
        self.assertEqual(anomaly_scan._iqr_outliers(vals), [])


if __name__ == "__main__":
    unittest.main()
