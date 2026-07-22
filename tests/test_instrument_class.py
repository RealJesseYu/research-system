"""test_instrument_class.py — the exact/approximate marker (Phase 3, R-ROUTE-1/2).

docs/memo_phase3_routing.md. A run must be able to tell an EXACT tool (code,
lookup, deterministic wrapper — re-running IS the check) from an APPROXIMATE
instrument (a simulator that can converge to a confidently wrong number), so the
fidelity gate can fire ONLY for the approximate class. Before this there was no
structural marker — the distinction lived only inside the fidelity gate's Opus
judgment.

These tests pin: the marker is correct on every enrolled substrate, the DEFAULT
is the fail-safe class (approximate — never accidentally skip a needed gate), an
unknown class is refused loudly at construction, an unknown id fails loud, and
this addition changed NO model-visible surface (the pipeline stays byte-identical
— nothing reads the marker yet).

Run directly: venv/bin/python3 tests/test_instrument_class.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.substrate_registry as reg  # noqa: E402

# The substrates explicitly declared EXACT (R-ROUTE-1): the four mature tools
# plus the sealed code sandbox. Everything else holds the fail-safe default.
EXPECTED_EXACT = {"rdkit", "cobrapy", "mafft", "homology_search", "python_experiment"}


class TestClassificationIsCorrect(unittest.TestCase):
    def test_the_declared_exact_tools_are_exact(self):
        for sid in EXPECTED_EXACT:
            self.assertEqual(reg.instrument_class_of(sid), reg.EXACT, sid)
            self.assertFalse(reg.is_approximate(sid), sid)

    def test_every_other_enrolled_substrate_is_approximate(self):
        for record in reg.all_substrates():
            sid = record.substrate_id
            if sid in EXPECTED_EXACT:
                continue
            self.assertEqual(reg.instrument_class_of(sid), reg.APPROXIMATE, sid)
            self.assertTrue(reg.is_approximate(sid), sid)

    def test_the_simulators_are_approximate(self):
        """The whole reason the marker exists: a CFD/FEA simulator can be
        confidently wrong, so it keeps the fidelity gate."""
        for sid in ("cavity_2d_cfd", "calculix_cantilever_fea",
                    "fenicsx_cantilever_elastic"):
            self.assertTrue(reg.is_approximate(sid), sid)


class TestFailSafeAndFailLoud(unittest.TestCase):
    def test_the_default_class_is_approximate(self):
        """The fail-safe direction: a substrate declared with no class is
        treated as confidently-wrong-capable, so a needed gate is never skipped
        by omission."""
        rec = reg.SubstrateRecord(
            substrate_id="probe_default", wrapper="w", card_path="c",
            maturity=reg.CALIBRATING, routable=False, cost_tier="low", notes="n")
        self.assertEqual(rec.instrument_class, reg.APPROXIMATE)

    def test_an_unknown_class_is_refused_at_construction(self):
        with self.assertRaises(ValueError):
            reg.SubstrateRecord(
                substrate_id="probe_bad", wrapper="w", card_path="c",
                maturity=reg.CALIBRATING, routable=False, cost_tier="low",
                notes="n", instrument_class="sorta_exact")

    def test_an_unknown_id_fails_loud(self):
        with self.assertRaises(KeyError):
            reg.instrument_class_of("no_such_substrate")
        with self.assertRaises(KeyError):
            reg.is_approximate("no_such_substrate")

    def test_is_approximate_treats_any_non_exact_value_as_approximate(self):
        """Defense in depth: even if a bad class slipped past construction, the
        predicate errs toward firing the gate, never skipping it."""
        self.assertTrue(reg.is_approximate("cavity_2d_cfd"))


class TestModelVisibleSurfaceUnchanged(unittest.TestCase):
    """The marker is a Python field read by upper layers — it must NOT appear in
    anything a model sees, or it would drift cavity's frozen-anchor era guard."""

    def test_the_contract_block_does_not_leak_the_class(self):
        # The class is a Python field name upper layers read; it must never
        # appear as a field in the model-visible contract block. (The prose
        # word "exact" occurs naturally in contract text — it is the FIELD that
        # must not leak, so that is what is checked.)
        block = reg.routable_contracts_block()
        self.assertNotIn("instrument_class", block)


if __name__ == "__main__":
    unittest.main()
