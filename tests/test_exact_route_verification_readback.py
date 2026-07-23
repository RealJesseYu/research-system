"""test_exact_route_verification_readback.py — the 2026-07-22 live-run fix.

The director (pi_agent) reads a run's verified findings from
runs/<id>/verification.json. The static pipeline writes it; the exact route did
NOT, so a live director run saw every routed move as "publishable, but no
measurements" and its arc could not compound (decide2/decide3 literally said
"returned no actual descriptor measurements"). experiment_report.build_verification
now maps a routed investigation into that exact shape and write_report emits it.

Proves:
  * build_verification maps verified and unverified probes correctly (verified ->
    reproduced number; unverified surfaced as `original`, never dropped);
  * the director's OWN read path (pi_agent.dispatch.read_run_result, a pure fn)
    now returns publishable + findings for a routed run — the evidence channel
    the arc depends on.

Call-free: zero model calls, zero docker.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent.dispatch import read_run_result  # noqa: E402
from stages.experiment_report import build_verification  # noqa: E402


def _result(publishable, measurements):
    return {
        "publishable": publishable,
        "investigation": {
            "iterations": len(measurements),
            "verified": sum(1 for m in measurements if m.get("verified")),
            "measurements": measurements,
        },
    }


class TestBuildVerification(unittest.TestCase):
    def test_verified_and_unverified_probes_map_correctly(self):
        result = _result(False, [
            {"iteration": 0, "verified": True, "value": 0.42, "rel_error": 0.0,
             "recipe": {"combine": {"quantity": "margin"}}},
            {"iteration": 1, "verified": False, "value": 1.5,
             "produce_error": "postProcess wrote no output",
             "recipe": {"combine": {"quantity": "ratio"}}},
        ])
        v = build_verification(result)
        self.assertEqual(v["verified"], 1)
        self.assertEqual(v["total"], 2)
        self.assertFalse(v["publishable"])

        good, bad = v["verdicts"]
        self.assertEqual(good["label"], "margin")
        self.assertTrue(good["verified"])
        self.assertEqual(good["reproduced"], 0.42)
        # the unverified probe is surfaced (as original), not silently dropped
        self.assertEqual(bad["label"], "ratio")
        self.assertFalse(bad["verified"])
        self.assertIsNone(bad["reproduced"])
        self.assertEqual(bad["original"], 1.5)
        self.assertIn("postProcess", bad["reason"])

    def test_label_falls_back_to_probe_index_without_a_combine_quantity(self):
        v = build_verification(_result(True, [
            {"iteration": 3, "verified": True, "value": 7, "rel_error": 0.0,
             "recipe": {}}]))
        self.assertEqual(v["verdicts"][0]["label"], "probe 3")


class TestDirectorReadsExactRouteFindings(unittest.TestCase):
    def test_read_run_result_surfaces_publishable_and_findings(self):
        result = _result(True, [
            {"iteration": 0, "verified": True, "value": 0.009116, "rel_error": 0.0,
             "recipe": {"combine": {"quantity": "margin"}}},
        ])
        with tempfile.TemporaryDirectory() as d:
            run_dir = Path(d)
            (run_dir / "verification.json").write_text(
                json.dumps(build_verification(result)))
            # a routed run's run_record extras (how_far only) — the exact case
            # that made the director blind before the fix
            record = {"extras": {
                "how_far": "completed exact-route investigation (publishable)"}}
            rr = read_run_result(run_dir, "rid", 0, record)

        # publishable now True (was None) -> MoveResult.succeeded = bool(publishable)
        self.assertTrue(rr.publishable)
        self.assertEqual(rr.verified, 1)
        self.assertEqual(rr.total, 1)
        # and the actual number reaches the director
        self.assertEqual(len(rr.findings), 1)
        self.assertEqual(rr.findings[0]["label"], "margin")
        self.assertEqual(rr.findings[0]["value"], 0.009116)
        self.assertTrue(rr.findings[0]["verified"])


if __name__ == "__main__":
    unittest.main()
