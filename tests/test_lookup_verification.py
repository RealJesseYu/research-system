"""The two network lookups that already worked, now able to produce KEPT numbers.

`alphafold_db` and `bio_db_lookup` were un-deferred on network grounds in July
2026 and have been returning real values ever since — a mean pLDDT, a round-trip
resolution. With no run-entry constructor wired, the verification wall could not
READ a re-run, so every value they produced was stuck as an unverified caveat.
One line each fixed that.

Offline: the wrapper is patched, so what is under test is the WALL and the
GOVERNANCE, not the network. Live evidence is in
docs/memo_defer_reexamination.md.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages import verification  # noqa: E402
from tools import run_alphafold_db as afdb  # noqa: E402
from tools import run_bio_db_lookup as biodb  # noqa: E402
from tools import substrate_dispatch as dispatch  # noqa: E402
from tools import substrate_registry as registry  # noqa: E402

LOOKUPS = ("alphafold_db", "bio_db_lookup")

AFDB_ART = {"kind": "substrate", "substrate_id": "alphafold_db",
            "typed_input": {"uniprot_accession": "P0DP23",
                            "quantity": "mean_pLDDT"},
            "quantity": "mean_pLDDT"}


def _fake(module, name, value=None, valid=True, diagnostics="ok"):
    def wrapper(spec, **kw):
        return {"valid": valid, "qoi": value, "diagnostics": diagnostics,
                "runtime_s": 0.01}
    return mock.patch.object(module, name, side_effect=wrapper)


class TestTheLookupsCanNowBeVerified(unittest.TestCase):

    def test_a_reader_is_wired_for_both(self):
        for sid in LOOKUPS:
            self.assertIsNotNone(dispatch.run_entry_constructor_for(sid), sid)

    def test_a_looked_up_value_reproduces(self):
        with _fake(afdb, "run_alphafold_db", 85.25):
            v = verification.verify_claim({"value": 85.25, "artifact": AFDB_ART})
        self.assertTrue(v["verified"])
        self.assertEqual(v["reason"], "reproduced")

    def test_a_wrong_value_is_caught(self):
        with _fake(afdb, "run_alphafold_db", 85.25):
            v = verification.verify_claim({"value": 99.9, "artifact": AFDB_ART})
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "mismatch")

    def test_a_not_found_record_never_becomes_a_number(self):
        # The failure this class of tool must never commit: an absent record
        # read as a value. valid=False carries diagnostics, never a qoi.
        with _fake(biodb, "run_bio_db_lookup", None, valid=False,
                   diagnostics="not_found: pdb record 9ZZZ did not resolve"):
            v = verification.verify_claim({"value": 1.0, "artifact": {
                "kind": "substrate", "substrate_id": "bio_db_lookup",
                "typed_input": {"database": "pdb", "record_id": "9ZZZ",
                                "quantity": "round_trip_id"},
                "quantity": "round_trip_id"}})
        self.assertFalse(v["verified"])
        self.assertEqual(v["reason"], "rerun_failed")
        self.assertIn("not_found", v["detail"])

    def test_the_artifact_is_what_gets_re_called(self):
        seen = {}

        def wrapper(spec, **kw):
            seen.update(spec)
            return {"valid": True, "qoi": 85.25, "diagnostics": "", "runtime_s": 0}

        with mock.patch.object(afdb, "run_alphafold_db", side_effect=wrapper):
            verification.verify_claim({"value": 85.25, "artifact": AFDB_ART})
        self.assertEqual(seen["uniprot_accession"], "P0DP23")


class TestWiringAReaderGrantsNoRoutingAuthority(unittest.TestCase):
    """Same discipline as R-MCP-3: a reader lets the wall verify a number the
    tool already produced. It is not a promotion, and must not become one."""

    def test_both_rows_stay_unrouted(self):
        for sid in LOOKUPS:
            self.assertFalse(registry.get(sid).routable, sid)
            self.assertNotIn(sid, registry.routable_ids(), sid)

    def test_execution_dispatch_still_refuses_them_by_name(self):
        for sid in LOOKUPS:
            with self.assertRaises(LookupError, msg=sid):
                dispatch.adapter_for(sid)
            with self.assertRaises(LookupError, msg=sid):
                dispatch.qoi_translation_for(sid)
            with self.assertRaises(LookupError, msg=sid):
                registry.contract_for(sid)

    def test_the_lookup_class_trust_claim_is_still_on_the_record(self):
        # Reproduction attests PROVENANCE, never correctness (R-MCP-5). Both
        # rows carry the permanent never-trust-alone statement; wiring a reader
        # does not soften it.
        for sid in LOOKUPS:
            self.assertIn("never-trust-alone", registry.get(sid).notes.lower(), sid)


if __name__ == "__main__":
    unittest.main()
