"""
test_run_homology_search.py — the BLAST+HMMER bundle wrapper (BIO Wave D.2, T2).

  * PURE tests (no container): input jails.
  * LIVE tests (homology-search-prod): a real known hit's e-value; the
    DB-INTEGRITY gate proven by triggering — a clean 0-hits run (valid, qoi=None)
    is distinguished from a search that could not run (valid=False), the
    sequence-search analog of cobrapy's status gate; determinism.

Run directly: venv/bin/python3 tests/test_run_homology_search.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import run_homology_search
from tools.run_homology_search import (
    DATABASE_ALLOWLIST, QOI_FIELDS, TOOLS, HomologySearchInputError,
    _validate_input, run_homology_search as run,
)

_LIVE = run_homology_search.preflight() is None
_KNOWN = ("MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEK"
          "AVQVKVKALPDAQFEVVHSLAKWKR")


class PureInputJails(unittest.TestCase):
    def test_clean_input_passes(self):
        out = _validate_input({"database": "demo_prot", "query": _KNOWN,
                               "tool": "blast", "quantity": "e_value"})
        self.assertEqual(out["database"], "demo_prot")
        self.assertEqual(out["tool"], "blast")

    def test_database_off_allowlist_rejected(self):
        with self.assertRaises(HomologySearchInputError) as e:
            _validate_input({"database": "nr", "query": _KNOWN,
                             "tool": "blast", "quantity": "e_value"})
        self.assertIn("allowlist", str(e.exception))

    def test_non_protein_query_rejected(self):
        with self.assertRaises(HomologySearchInputError):
            _validate_input({"database": "demo_prot", "query": "12345",
                             "tool": "blast", "quantity": "e_value"})

    def test_unknown_tool_rejected(self):
        with self.assertRaises(HomologySearchInputError):
            _validate_input({"database": "demo_prot", "query": _KNOWN,
                             "tool": "diamond", "quantity": "e_value"})

    def test_bad_quantity_rejected(self):
        with self.assertRaises(HomologySearchInputError):
            _validate_input({"database": "demo_prot", "query": _KNOWN,
                             "tool": "blast", "quantity": "score"})

    def test_hmmer_query_must_be_a_baked_profile_name(self):
        # for tool=hmmer, query is a PROFILE name, not a sequence.
        with self.assertRaises(HomologySearchInputError) as e:
            _validate_input({"database": "demo_prot", "query": _KNOWN,
                             "tool": "hmmer", "quantity": "e_value"})
        self.assertIn("profile", str(e.exception).lower())

    def test_vocabularies(self):
        self.assertEqual(QOI_FIELDS, ("e_value",))
        self.assertEqual(TOOLS, ("blast", "hmmer"))
        self.assertIn("demo_prot", DATABASE_ALLOWLIST)


@unittest.skipUnless(_LIVE, "homology-search-prod not running — live checks skipped")
class LiveBlast(unittest.TestCase):
    def test_known_hit_evalue(self):
        r = run({"database": "demo_prot", "query": _KNOWN, "tool": "blast",
                 "quantity": "e_value"})
        self.assertTrue(r["valid"])
        self.assertIsNotNone(r["qoi"])
        self.assertLess(r["qoi"], 1e-10)  # a strong, significant hit

    def test_zero_hits_is_valid_no_homolog_not_an_error(self):
        # search RAN cleanly, found nothing: valid=True, qoi=None (a real result).
        r = run({"database": "demo_prot", "query": "W" * 30, "tool": "blast",
                 "quantity": "e_value"})
        self.assertTrue(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("0 significant hits", r["diagnostics"])

    def test_db_integrity_gate_distinguishes_error_from_no_hits(self):
        # THE gate, triggered: a broken/missing DB -> search could NOT run ->
        # valid=False, distinct from the clean 0-hits case above.
        r = run({"database": "_broken_selftest", "query": _KNOWN, "tool": "blast",
                 "quantity": "e_value"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("could not run", r["diagnostics"].lower())

    def test_determinism_identical_repeat(self):
        a = run({"database": "demo_prot", "query": _KNOWN, "tool": "blast",
                 "quantity": "e_value"})
        b = run({"database": "demo_prot", "query": _KNOWN, "tool": "blast",
                 "quantity": "e_value"})
        self.assertEqual(a["qoi"], b["qoi"])


@unittest.skipUnless(_LIVE, "homology-search-prod not running — HMMER checks skipped")
class LiveHmmer(unittest.TestCase):
    def test_hmmer_known_hit_evalue(self):
        r = run({"database": "demo_prot", "query": "demo_hmm", "tool": "hmmer",
                 "quantity": "e_value"})
        self.assertTrue(r["valid"])
        self.assertIsNotNone(r["qoi"])
        self.assertLess(r["qoi"], 1e-10)

    def test_profile_integrity_gate_distinguishes_malformed_hmm_from_no_hits(self):
        # HMMER's EXTRA integrity surface: a malformed/empty PROFILE -> search
        # could NOT run -> valid=False, distinct from a clean 0-hits. Proven by
        # triggering (the analog of BLAST's broken-DB-vs-0-hits, on the profile).
        r = run({"database": "demo_prot", "query": "_broken_profile",
                 "tool": "hmmer", "quantity": "e_value"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])
        self.assertIn("could not run", r["diagnostics"].lower())

    def test_target_integrity_gate_distinguishes_bad_target_from_no_hits(self):
        r = run({"database": "_broken_selftest", "query": "demo_hmm",
                 "tool": "hmmer", "quantity": "e_value"})
        self.assertFalse(r["valid"])
        self.assertIsNone(r["qoi"])

    def test_hmmer_determinism(self):
        a = run({"database": "demo_prot", "query": "demo_hmm", "tool": "hmmer",
                 "quantity": "e_value"})
        b = run({"database": "demo_prot", "query": "demo_hmm", "tool": "hmmer",
                 "quantity": "e_value"})
        self.assertEqual(a["qoi"], b["qoi"])

    def test_blast_path_unperturbed_by_the_hmmer_addition(self):
        # (owner check a): extending the tool dispatch must not move BLAST.
        r = run({"database": "demo_prot", "query": _KNOWN, "tool": "blast",
                 "quantity": "e_value"})
        self.assertTrue(r["valid"])
        self.assertAlmostEqual(r["qoi"], 4.36e-58, delta=1e-60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
