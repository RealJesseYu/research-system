"""test_cost_and_code_cap.py — addendum items 7 and 8 (2026-07-30).

ITEM 7. MAX_CODE_BYTES = 100_000 refused legitimate reproducers. In
study-20260730T034915Z move 5 a real NHANES analysis over six CDC public-use files
lost ALL 19 of its claims to "the sandbox refused the artifact: 'code' exceeds
100000 bytes". Its verify.py is 336,090 bytes of which 326,454 are one gzip+base64
literal holding a 13,591-row cohort — about 10 kB of actual code. And m11, the
move that reproduced 12/12 by writing one producer per scalar, wrote files of
57-62 kB EACH: the working pattern was already at 60% of the cap.

ITEM 8. Cost is under-reported. That study's report.json shows
`moves_with_usd: 12` against `moves: 16`, so its $143.97 is a FLOOR. The cause is
_cost_snapshot returning {calls, tokens} only, so every IN-PROCESS capability row
reached the arc with tokens and no dollars — including the call_ideation move, 38
calls and 6,860,767 tokens, priced at nothing.

Run directly: venv/bin/python3 tests/test_cost_and_code_cap.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.capabilities as C  # noqa: E402
from tools import run_python_experiment as RPE  # noqa: E402


class TestCodeCap(unittest.TestCase):
    def test_the_cap_clears_the_artifact_that_was_refused(self):
        self.assertGreater(RPE.MAX_CODE_BYTES, 336_090)

    def test_it_clears_a_per_scalar_producer_with_room(self):
        """m11's producers are 57-62 kB each and that is the pattern the brief
        now asks for, so the cap must not sit anywhere near it."""
        self.assertGreater(RPE.MAX_CODE_BYTES, 10 * 62_000)

    def test_it_is_still_a_cap_and_still_under_the_file_artifact_limit(self):
        self.assertLessEqual(RPE.MAX_CODE_BYTES, RPE.MAX_ARTIFACT_BYTES)

    def test_over_the_cap_is_still_refused_and_now_says_what_to_do(self):
        spec = {"code": "x" * (RPE.MAX_CODE_BYTES + 1), "quantity": "q"}
        with self.assertRaises(RPE.PythonExperimentInputError) as cm:
            RPE._validate_code_execution(spec) if hasattr(
                RPE, "_validate_code_execution") else RPE.run_python_experiment(spec)
        msg = str(cm.exception)
        self.assertIn("over the", msg)
        self.assertIn("split the reproducer", msg)


class _Meter:
    """A fake process meter: hands out successive snapshots."""

    def __init__(self, snaps):
        self.snaps = list(snaps)

    def __call__(self):
        return self.snaps.pop(0) if len(self.snaps) > 1 else self.snaps[0]


def _snap(calls=0, tokens=0, usd=0.0, cwu=0, turns=0, cwt=0):
    return {"calls": calls, "tokens": tokens, "usd": usd, "calls_with_usd": cwu,
            "turns": turns, "calls_with_turns": cwt}


class TestCapabilityDollars(unittest.TestCase):
    def _with_cost(self, before, after, name="call_ideation"):
        real = C._cost_snapshot
        C._cost_snapshot = lambda: after
        try:
            return C._with_cost(name, {"succeeded": True}, before)
        finally:
            C._cost_snapshot = real

    def test_an_ideation_call_now_reports_dollars(self):
        r = self._with_cost(_snap(), _snap(calls=38, tokens=6_860_767,
                                           usd=8.9, cwu=38, turns=120, cwt=38))
        self.assertEqual(r["cost"]["calls"], 38)
        self.assertEqual(r["cost"]["tokens"], 6_860_767)
        self.assertAlmostEqual(r["cost"]["usd"], 8.9)
        self.assertEqual(r["cost"]["calls_with_usd"], 38)
        self.assertEqual(r["cost"]["turns"], 120)

    def test_unpriced_calls_leave_the_key_ABSENT_not_zero(self):
        """A recorded $0.00 would read as 'this was free'. 'No call reported a
        price' has to stay unknown — the same rule record_run_outcome follows."""
        r = self._with_cost(_snap(), _snap(calls=3, tokens=1_000))
        self.assertEqual(r["cost"]["tokens"], 1_000)
        self.assertNotIn("usd", r["cost"])
        self.assertNotIn("calls_with_usd", r["cost"])

    def test_the_diff_is_against_the_start_snapshot(self):
        r = self._with_cost(_snap(calls=10, tokens=500, usd=2.0, cwu=10),
                            _snap(calls=14, tokens=900, usd=5.5, cwu=14))
        self.assertEqual(r["cost"]["calls"], 4)
        self.assertEqual(r["cost"]["tokens"], 400)
        self.assertAlmostEqual(r["cost"]["usd"], 3.5)
        self.assertEqual(r["cost"]["calls_with_usd"], 4)

    def test_a_broken_meter_still_cannot_sink_a_result(self):
        real = C._cost_snapshot

        def boom():
            raise RuntimeError("meter down")
        C._cost_snapshot = boom
        try:
            r = C._with_cost("call_ideation", {"succeeded": True}, _snap())
        finally:
            C._cost_snapshot = real
        self.assertTrue(r["succeeded"])

    def test_snapshot_carries_the_new_keys_and_never_raises(self):
        from pi_agent.loop import _cost_snapshot
        s = _cost_snapshot()
        for k in ("calls", "tokens", "usd", "calls_with_usd", "turns",
                  "calls_with_turns"):
            self.assertIn(k, s)


class TestTheAggregatorCountsIt(unittest.TestCase):
    def test_a_capability_row_with_usd_raises_moves_with_usd(self):
        from pi_agent.cost_report import _own_arc_spend
        entries = [
            {"cost": {"calls": 1, "tokens": 10, "usd": 1.0, "calls_with_usd": 1}},
            {"cost": {"calls": 38, "tokens": 6_860_767, "usd": 8.9,
                      "calls_with_usd": 38}},
        ]
        s = _own_arc_spend(entries)
        self.assertEqual(s["moves_with_usd"], 2)
        self.assertAlmostEqual(s["usd"], 9.9)


if __name__ == "__main__":
    unittest.main()
