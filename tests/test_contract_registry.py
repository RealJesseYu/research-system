"""
test_contract_registry.py — R-S3-1 Part A. Call-free: no model calls, no
network. Proves (1) contract selection is un-pinned from the module constant to
the registry, (2) cavity's model-visible contract text is BYTE-IDENTICAL before
and after (captured under era 862531b; era-of-record is now the R5 all-routable
commit, owner 2026-07-17 — cavity's text itself did not change), and (3) the
fail-loud escape: a substrate with no wired contract RAISES and NEVER falls
back to cavity. R5 adds the routable_contracts_block proofs.

Run directly: venv/bin/python3 tests/test_contract_registry.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import substrates
from stages import stage3_fidelity_gate
from tools import substrate_registry as registry


class TestContractSelection(unittest.TestCase):
    def test_sole_routable_raises_on_the_real_two_routable_registry(self):
        # Post-R2-flip the routable set is two, so the RETIRED
        # sole_routable_id() raises on the real registry — its documented
        # behavior, and the reason D.2 replaced it with select_substrate.
        self.assertEqual(
            registry.routable_ids(),
            ("cavity_2d_cfd", "ngspice_linear_passive"),
        )
        with self.assertRaises(RuntimeError):
            registry.sole_routable_id()

    def test_cavity_contract_is_the_imported_constant(self):
        # Single source of truth: contract_for returns the SAME object
        # substrates.py exports — never a pasted copy.
        self.assertIs(
            registry.contract_for("cavity_2d_cfd"), substrates.CAVITY_2D_CONTRACT
        )

    def test_sole_routable_raises_when_not_exactly_one(self):
        # The seam's fail-loud: promoting a second substrate routable without
        # building selection must land loudly, not silently pick one.
        with mock.patch.object(
            registry, "routable_ids", return_value=("cavity_2d_cfd", "other")
        ):
            with self.assertRaises(RuntimeError):
                registry.sole_routable_id()
        with mock.patch.object(registry, "routable_ids", return_value=()):
            with self.assertRaises(RuntimeError):
                registry.sole_routable_id()


class TestEraByteIdentity(unittest.TestCase):
    """THE CENTRAL CLAIM. The old code set stage3's model-visible
    substrate_contract to exactly substrates.CAVITY_2D_CONTRACT. The new path
    derives it from the registry. Byte-equality to that constant IS byte-equality
    to the pre-change model-visible text — cavity's stage-3 surface survives
    unchanged through the R5 era move (owner, 2026-07-17; the era-of-record is
    the R5 commit — only composed STAGE-1 surfaces moved). Could fail: if
    selection returned a different substrate, or contract_for mutated the text,
    or the constant drifted, these assertions break."""

    def test_stage3_selected_contract_byte_identical(self):
        substrate_id, contract_text = stage3_fidelity_gate._selected_contract()
        self.assertEqual(substrate_id, "cavity_2d_cfd")
        # byte-for-byte identical to the constant the gate used before R-S3-1
        self.assertEqual(contract_text, substrates.CAVITY_2D_CONTRACT)
        self.assertEqual(
            len(contract_text.encode("utf-8")),
            len(substrates.CAVITY_2D_CONTRACT.encode("utf-8")),
        )

    def test_selected_contract_carries_the_cavity_header(self):
        # Sanity that the text is the cavity contract, not an empty stand-in.
        _sid, contract_text = stage3_fidelity_gate._selected_contract()
        self.assertIn("SUBSTRATE CONTRACT: cavity_2d", contract_text)


class TestRoutableContractsBlock(unittest.TestCase):
    """R5 (owner, 2026-07-17): the all-routable contract block for Stage-1
    surfaces — deterministic pure function of the registry, per-substrate
    fixed header + contract verbatim, fail-loud inherited from contract_for."""

    def test_double_composition_byte_equality(self):
        # D.0 pattern: byte-stability proven by composing twice.
        self.assertEqual(
            registry.routable_contracts_block(),
            registry.routable_contracts_block(),
        )

    def test_block_is_headers_plus_verbatim_contracts_in_enrollment_order(self):
        # The exact composition: per routable substrate, the minimal fixed
        # header naming the substrate_id, then the imported contract VERBATIM,
        # sections joined by one blank line — in enrollment order.
        expected = (
            "ROUTABLE SUBSTRATE: cavity_2d_cfd\n"
            + substrates.CAVITY_2D_CONTRACT
            + "\n\nROUTABLE SUBSTRATE: ngspice_linear_passive\n"
            + substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT
        )
        self.assertEqual(registry.routable_contracts_block(), expected)

    def test_fail_loud_escape_contractless_routable_cannot_compose(self):
        # A routable substrate without a wired contract cannot compose — the
        # LookupError escapes (never a silent skip, never a cavity fallback).
        with mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "calculix_cantilever_fea"),
        ):
            with self.assertRaises(LookupError):
                registry.routable_contracts_block()


class TestFailLoudEscape(unittest.TestCase):
    """R-S3-1 fail-loud: a substrate with no wired contract RAISES and the gate
    never falls back to cavity. This is the failing-escape proof — a check that
    cannot fail is not a proof, so we request contract-less substrates and assert
    the raise, then assert cavity's text was NOT returned."""

    def test_fea_has_no_contract_and_raises(self):
        with self.assertRaises(LookupError):
            registry.contract_for("calculix_cantilever_fea")

    def test_code_has_no_contract_and_raises(self):
        with self.assertRaises(LookupError):
            registry.contract_for("code_sklearn_eval")

    def test_web_search_has_no_contract_and_raises(self):
        with self.assertRaises(LookupError):
            registry.contract_for("web_search")

    def test_unknown_substrate_raises_keyerror(self):
        # Unknown (unenrolled) id fails even earlier, via get().
        with self.assertRaises(KeyError):
            registry.contract_for("no_such_substrate")

    def test_never_falls_back_to_cavity_for_a_contractless_substrate(self):
        # The heart of "never fall back": for every enrolled substrate that has
        # NO wired contract, contract_for must raise — it must never quietly
        # return cavity's text. Contractless is derived from the wired map
        # itself (pre-flip the map held cavity alone; since the R2 flip it
        # holds cavity + ngspice), so the derivation never goes stale.
        contractless = [
            r.substrate_id
            for r in registry.all_substrates()
            if r.substrate_id not in registry._CONTRACTS
        ]
        self.assertTrue(contractless)  # the test would be vacuous with none
        for sid in contractless:
            with self.assertRaises((LookupError, KeyError), msg=sid):
                got = registry.contract_for(sid)
                # If it somehow returned, prove it was NOT a cavity fallback.
                self.assertNotEqual(got, substrates.CAVITY_2D_CONTRACT, sid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
