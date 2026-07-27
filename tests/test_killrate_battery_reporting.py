"""
test_killrate_battery_reporting — the battery must not lose its record, and must
not report success when it failed.

Neither harness/killrate_battery.py nor harness/survival_counter.py had ANY test
before this file, which is how both of these survived: a battery is a
multi-hour live-model run, so nobody exercises it casually, and its reporting
path had no offline coverage at all.

Two defects, both in the part that runs AFTER hours of real work:

  1. run_battery returned 0 unconditionally — including when slots aborted
     through the relaunch cap (no data point) and including when the banner
     printed "*** CRITICAL: the battery wrote a production ledger ***". Anything
     gating on the exit status read a failed, invariant-violating battery as a
     pass. It was untestable in place, which is part of why it went unnoticed;
     the decision is now a pure function over the report.

  2. the machine report was written at the very END, after every print — and the
     banner formatted kill rates with f"{r:.2f}", while survival_counter
     legitimately leaves a rate None when initial_survivor_count is missing or 0.
     One None raised TypeError and the battery ended with nothing on disk.

Offline: pure functions over report dicts. No model calls, no containers.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.killrate_battery import _fmt_rates, battery_failures  # noqa: E402


def _report(*, fidelity=0, override=0, unresolved=None):
    return {
        "ledger_activity": {"fidelity_entries": fidelity,
                            "override_entries": override},
        "per_domain": {"same": {"unresolved_slots": list(unresolved or [])}},
    }


class TestTheExitCodeMeansSomething:
    def test_a_clean_battery_has_no_failures(self):
        assert battery_failures(_report()) == []

    def test_writing_a_production_ledger_is_a_failure(self):
        """The banner already calls this CRITICAL, then exited 0 anyway."""
        failures = battery_failures(_report(fidelity=1))
        assert len(failures) == 1
        assert "production ledger" in failures[0]

    def test_an_override_ledger_entry_is_also_a_failure(self):
        assert battery_failures(_report(override=2))

    def test_an_unresolved_slot_is_a_failure(self):
        """A slot aborted through the relaunch cap produced NO data point — the
        battery did not measure what it was asked to, however clean the rest of
        the output looks."""
        failures = battery_failures(_report(unresolved=["same3"]))
        assert len(failures) == 1
        assert "no data point" in failures[0]
        assert "same3" in failures[0]

    def test_both_conditions_are_reported_not_just_the_first(self):
        failures = battery_failures(_report(fidelity=1, unresolved=["same3"]))
        assert len(failures) == 2

    def test_a_malformed_report_does_not_crash_the_decision(self):
        """This runs after hours of work; it may not raise on a shape it did not
        expect, or it destroys the thing it is reporting on."""
        for bad in ({}, {"ledger_activity": None}, {"per_domain": None},
                    {"per_domain": {"same": {}}}):
            assert battery_failures(bad) == []


class TestANullKillRateDoesNotDestroyTheReport:
    def test_a_none_rate_renders_as_not_available(self):
        """None means "no denominator" (initial_survivor_count missing or 0),
        which is not 0.00 — rendering it as a number would be a lie, and
        f"{None:.2f}" is a TypeError that used to take the banner down."""
        assert _fmt_rates([0.5, None, 0.778]) == "[0.50, n/a, 0.78]"

    def test_all_none_is_fine(self):
        assert _fmt_rates([None, None]) == "[n/a, n/a]"

    def test_ordinary_rates_are_unchanged(self):
        assert _fmt_rates([0.25, 0.6667]) == "[0.25, 0.67]"

    def test_an_empty_distribution_is_fine(self):
        assert _fmt_rates([]) == "[]"
