"""test_run_bio_db_lookup.py — 4-API bio DB lookup wrapper (D.2, DEFERRED).
Proven now: input gate incl. per-database id form + honest DEFERRED, never a
fabricated record."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_bio_db_lookup import (DATABASE_ALLOWLIST, QOI_FIELDS,
    BioDBLookupInputError, _validate_input, endpoint_available,
    run_bio_db_lookup as run)


class InputGate(unittest.TestCase):
    def test_clean_passes_each_db(self):
        for db, rid in [("pdb", "1ABC"), ("pubchem", "2244"), ("uniprot", "P0DP23"), ("chembl", "CHEMBL25")]:
            self.assertEqual(_validate_input({"database": db, "record_id": rid, "quantity": "round_trip_id"})["database"], db)
    def test_bad_database_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "kegg", "record_id": "1ABC", "quantity": "round_trip_id"})
    def test_malformed_id_per_namespace_rejected(self):
        # a real jail: wrong id form for the chosen database
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "pdb", "record_id": "notapdbid", "quantity": "round_trip_id"})
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "pubchem", "record_id": "abc", "quantity": "round_trip_id"})
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "chembl", "record_id": "25", "quantity": "round_trip_id"})
    def test_empty_id_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "uniprot", "record_id": "  ", "quantity": "round_trip_id"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "uniprot", "record_id": "P0DP23", "quantity": "record"})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("round_trip_id",))
        self.assertEqual(DATABASE_ALLOWLIST, ("pdb", "pubchem", "uniprot", "chembl"))


class DeferredState(unittest.TestCase):
    def test_per_database_deferral_mentions_all_four_and_never_trust_alone(self):
        r = endpoint_available("pdb")
        self.assertIsNotNone(r)
        self.assertIn("ALL FOUR", r)
        self.assertIn("NEVER-TRUSTED-ALONE", r)
    def test_valid_input_returns_deferred(self):
        r = run({"database": "uniprot", "record_id": "P0DP23", "quantity": "round_trip_id"})
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"]); self.assertIn("DEFERRED", r["diagnostics"])
    def test_bad_input_refused_first(self):
        self.assertIn("input rejected", run({"database": "kegg", "record_id": "x", "quantity": "round_trip_id"})["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
