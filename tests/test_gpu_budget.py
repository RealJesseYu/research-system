"""The GPU spend gate — the first place in this project where a dollar ceiling
means anything.

Every other budget here counts model calls on a subscription: `cost_meter.py`
says so outright, and `pi_agent/budget.py` counts moves, converting a cost-cap
through an estimate while noting real spend enforcement is "a later task".
Rented GPU time is billed to a card by the second, so it gets a real gate.

Offline and hermetic — every test uses a temp ledger, so the project's own
`memory/gpu_spend.jsonl` is never touched by the suite.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import gpu_budget  # noqa: E402
from tools import run_remote_job as remote  # noqa: E402


class TempLedger:
    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self.path = Path(self._dir.name) / "gpu_spend.jsonl"
        return self.path

    def __exit__(self, *exc):
        self._dir.cleanup()


class TestEstimates(unittest.TestCase):

    def test_cost_is_rate_times_time(self):
        self.assertAlmostEqual(gpu_budget.estimate_usd("T4", 3600), 0.80, places=6)
        self.assertAlmostEqual(gpu_budget.estimate_usd("T4", 1800), 0.40, places=6)

    def test_no_gpu_bills_the_cpu_rate(self):
        self.assertAlmostEqual(gpu_budget.estimate_usd(None, 3600), 0.20, places=6)

    def test_an_unknown_gpu_bills_the_most_expensive_rate(self):
        # The failure to avoid is a cap that silently under-counts, so an
        # unrecognised name must never be cheap.
        self.assertEqual(gpu_budget.rate_for("B200"),
                         max(gpu_budget.RATES_USD_PER_HOUR.values()))

    def test_junk_durations_do_not_raise(self):
        for bad in (None, "soon", -5):
            self.assertGreaterEqual(gpu_budget.estimate_usd("T4", bad), 0.0)


class TestTheCeiling(unittest.TestCase):

    def test_default_is_the_owner_set_hundred(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(gpu_budget.BUDGET_ENV, None)
            self.assertEqual(gpu_budget.budget_usd(), 100.0)

    def test_the_env_channel_delegates_a_slice(self):
        with mock.patch.dict(os.environ, {gpu_budget.BUDGET_ENV: "12.50"}):
            self.assertEqual(gpu_budget.budget_usd(), 12.50)

    def test_a_budget_that_parses_to_nothing_is_not_unlimited(self):
        # The ALLOWED_SUBSTRATES lesson: a constraint that silently permits
        # everything is the failure the setting exists to prevent.
        for junk in ("", "lots", "0", "-3"):
            with mock.patch.dict(os.environ, {gpu_budget.BUDGET_ENV: junk}):
                self.assertEqual(gpu_budget.budget_usd(), 100.0, junk)


class TestLedgerAccounting(unittest.TestCase):

    def test_spend_accumulates_across_records(self):
        with TempLedger() as led:
            gpu_budget.record("T4", 3600, path=led)
            gpu_budget.record("T4", 1800, path=led)
            self.assertAlmostEqual(gpu_budget.spent_usd(led), 1.20, places=6)

    def test_a_missing_ledger_is_zero_not_a_crash(self):
        self.assertEqual(gpu_budget.spent_usd("/no/such/ledger.jsonl"), 0.0)

    def test_a_corrupt_line_is_skipped_not_fatal(self):
        with TempLedger() as led:
            gpu_budget.record("T4", 3600, path=led)
            with open(led, "a") as f:
                f.write("{not json\n\n")
            gpu_budget.record("T4", 3600, path=led)
            self.assertAlmostEqual(gpu_budget.spent_usd(led), 1.60, places=6)

    def test_a_record_says_it_is_an_estimate_not_a_bill(self):
        with TempLedger() as led:
            rec = gpu_budget.record("A100", 60, path=led)
            self.assertIn("not a bill", rec["note"])
            self.assertEqual(json.loads(led.read_text().strip())["gpu"], "A100")


class TestTheGate(unittest.TestCase):

    def test_a_job_within_budget_passes(self):
        with TempLedger() as led:
            ok, _ = gpu_budget.check_affordable("T4", 900, path=led)
            self.assertTrue(ok)

    def test_the_gate_judges_the_WORST_case_not_the_likely_one(self):
        # An H100 for the full hour is $4.50. With $2 left it must refuse, even
        # though the job would probably finish in a minute.
        with TempLedger() as led, \
             mock.patch.dict(os.environ, {gpu_budget.BUDGET_ENV: "2.00"}):
            ok, why = gpu_budget.check_affordable("H100", 3600, path=led)
        self.assertFalse(ok)
        self.assertIn("could cost up to $4.50", why)
        self.assertIn("nothing was billed", why)

    def test_spend_already_recorded_reduces_what_is_affordable(self):
        with TempLedger() as led, \
             mock.patch.dict(os.environ, {gpu_budget.BUDGET_ENV: "1.00"}):
            self.assertTrue(gpu_budget.check_affordable("T4", 3600, path=led)[0])
            gpu_budget.record("T4", 3600, path=led)          # $0.80 gone
            self.assertFalse(gpu_budget.check_affordable("T4", 3600, path=led)[0])


class TestTheWrapperEnforcesIt(unittest.TestCase):

    def test_an_unaffordable_job_is_never_dispatched(self):
        called = []

        def dispatch(clean):
            called.append(clean)
            return {"returncode": 0, "metrics": {}, "artifacts": {},
                    "stdout": "", "stderr": ""}

        with mock.patch.dict(os.environ, {gpu_budget.BUDGET_ENV: "0.01"}):
            out = remote.run_remote_job(
                {"code": "x", "gpu": "H100", "timeout_s": 3600}, dispatch=dispatch)
        self.assertFalse(out["valid"])
        self.assertIn("GPU budget", out["diagnostics"])
        self.assertEqual(called, [])        # the money was never at risk

    def test_a_completed_job_records_actual_spend_and_reports_what_is_left(self):
        with TempLedger() as led:
            with mock.patch.object(gpu_budget, "LEDGER_PATH", led):
                out = remote.run_remote_job(
                    {"code": "x", "gpu": "T4"},
                    dispatch=lambda c: {"returncode": 0, "metrics": {},
                                        "artifacts": {}, "stdout": "", "stderr": ""})
                self.assertTrue(out["valid"])
                self.assertIn("spent", out["diagnostics"])
                self.assertIn("allowance left", out["diagnostics"])
                self.assertGreater(len(led.read_text().strip().splitlines()), 0)

    def test_a_failed_job_is_still_billed(self):
        # It consumed the machine it crashed on. Not recording that is how a
        # ledger drifts below reality.
        with TempLedger() as led:
            with mock.patch.object(gpu_budget, "LEDGER_PATH", led):
                remote.run_remote_job(
                    {"code": "x", "gpu": "T4"},
                    dispatch=lambda c: {"returncode": 1, "metrics": {},
                                        "artifacts": {}, "stdout": "", "stderr": "boom"})
                self.assertEqual(len(led.read_text().strip().splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
