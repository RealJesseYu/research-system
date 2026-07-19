"""test_run_bio_db_lookup.py — 4-API bio DB lookup wrapper (D.2 -> D.4-network
un-defer). Proven here OFFLINE + DETERMINISTIC (http_get injected): the input
gate incl. per-namespace id form, the resolved round-trip, the per-namespace
not-found shapes (incl. the HTTP-200 PubChem/UniProt traps), and the
network/partial-defer jail — never a fabricated record. Live-endpoint proof
(all four APIs + partial defer) is a separate one-off (see the D.4-network
handoff)."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_bio_db_lookup import (DATABASE_ALLOWLIST, QOI_FIELDS,
    BioDBLookupInputError, BioDBLookupNetworkError, _validate_input, _resolved,
    probe_endpoints, run_bio_db_lookup as run)


def _fake_get(status, body):
    def get(url, timeout=20.0):
        return status, body
    return get


def _raising_get(url, timeout=20.0):
    raise BioDBLookupNetworkError("URLError: test")


def _spec(db, rid):
    return {"database": db, "record_id": rid, "quantity": "round_trip_id"}


class InputGate(unittest.TestCase):
    def test_clean_passes_each_db(self):
        for db, rid in [("pdb", "1ABC"), ("pubchem", "2244"), ("uniprot", "P0DP23"), ("chembl", "CHEMBL25")]:
            self.assertEqual(_validate_input(_spec(db, rid))["database"], db)
    def test_bad_database_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input(_spec("kegg", "1ABC"))
    def test_malformed_id_per_namespace_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input(_spec("pdb", "notapdbid"))
        with self.assertRaises(BioDBLookupInputError):
            _validate_input(_spec("pubchem", "abc"))
        with self.assertRaises(BioDBLookupInputError):
            _validate_input(_spec("chembl", "25"))
    def test_empty_id_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input(_spec("uniprot", "  "))
    def test_bad_quantity_rejected(self):
        with self.assertRaises(BioDBLookupInputError):
            _validate_input({"database": "uniprot", "record_id": "P0DP23", "quantity": "record"})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("round_trip_id",))
        self.assertEqual(DATABASE_ALLOWLIST, ("pdb", "pubchem", "uniprot", "chembl"))


class ResolutionLogic(unittest.TestCase):
    """The per-namespace _resolved oracle — the subtle HTTP-200 traps."""
    def test_pdb_chembl_200_is_resolved(self):
        self.assertTrue(_resolved("pdb", 200, "{}"))
        self.assertTrue(_resolved("chembl", 200, "{}"))
    def test_pdb_chembl_404_not_resolved(self):
        self.assertFalse(_resolved("pdb", 404, "{}"))
        self.assertFalse(_resolved("chembl", 404, ""))
    def test_pubchem_200_needs_formula(self):
        good = '{"PropertyTable":{"Properties":[{"CID":2244,"MolecularFormula":"C9H8O4"}]}}'
        empty = '{"PropertyTable":{"Properties":[{"CID":999999999}]}}'
        self.assertTrue(_resolved("pubchem", 200, good))
        self.assertFalse(_resolved("pubchem", 200, empty))
    def test_uniprot_200_inactive_not_resolved(self):
        self.assertTrue(_resolved("uniprot", 200, '{"entryType":"UniProtKB reviewed (Swiss-Prot)"}'))
        self.assertFalse(_resolved("uniprot", 200, '{"entryType":"Inactive"}'))


class NetworkOutcomes(unittest.TestCase):
    def test_resolved_returns_one_and_never_trust_alone(self):
        r = run(_spec("pdb", "4HHB"), http_get=_fake_get(200, "{}"))
        self.assertTrue(r["valid"]); self.assertEqual(r["qoi"], 1.0)
        self.assertIn("NEVER-TRUSTED-ALONE", r["diagnostics"])
    def test_pubchem_200_empty_is_not_found_not_network(self):
        empty = '{"PropertyTable":{"Properties":[{"CID":999999999}]}}'
        r = run(_spec("pubchem", "999999999"), http_get=_fake_get(200, empty))
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"])
        self.assertIn("not_found", r["diagnostics"])
        self.assertNotIn("setup_error", r["diagnostics"])
    def test_uniprot_inactive_is_not_found(self):
        r = run(_spec("uniprot", "X0X0X0"), http_get=_fake_get(200, '{"entryType":"Inactive"}'))
        self.assertFalse(r["valid"]); self.assertIn("not_found", r["diagnostics"])
    def test_404_is_not_found(self):
        r = run(_spec("chembl", "CHEMBL999999999"), http_get=_fake_get(404, ""))
        self.assertFalse(r["valid"]); self.assertIn("not_found", r["diagnostics"])
    def test_unreachable_is_setup_error_partial_defer(self):
        r = run(_spec("uniprot", "P0DP23"), http_get=_raising_get)
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"])
        self.assertIn("setup_error", r["diagnostics"])
        self.assertIn("PARTIAL defer", r["diagnostics"])
        self.assertNotIn("not_found", r["diagnostics"])
    def test_5xx_and_429_are_setup_error(self):
        for status in (500, 503, 429):
            r = run(_spec("pdb", "4HHB"), http_get=_fake_get(status, ""))
            self.assertFalse(r["valid"]); self.assertIn("setup_error", r["diagnostics"])
    def test_bad_input_refused_before_network(self):
        r = run(_spec("kegg", "x"), http_get=_raising_get)
        self.assertIn("input rejected", r["diagnostics"])


class PartialDeferAndProbe(unittest.TestCase):
    def test_one_endpoint_down_defers_only_that_database(self):
        # uniprot down, pdb up — the partial-defer distinction
        down = {"uniprot": _raising_get}
        good = _fake_get(200, "{}")
        def routed(url, timeout=20.0):
            return (down["uniprot"](url) if "uniprot" in url else good(url))
        r_up = run(_spec("pdb", "4HHB"), http_get=routed)
        r_down = run(_spec("uniprot", "P0DP23"), http_get=routed)
        self.assertTrue(r_up["valid"])
        self.assertFalse(r_down["valid"]); self.assertIn("PARTIAL defer", r_down["diagnostics"])
    def test_probe_reports_fully_live_when_all_resolve(self):
        rep = probe_endpoints(http_get=_fake_get(200, '{"entryType":"reviewed","PropertyTable":{"Properties":[{"CID":1,"MolecularFormula":"X"}]}}'))
        self.assertTrue(rep["fully_live"])
        for db in DATABASE_ALLOWLIST:
            self.assertTrue(rep[db]["resolved"], db)
    def test_probe_reports_partial_when_one_unreachable(self):
        def routed(url, timeout=20.0):
            if "uniprot" in url:
                raise BioDBLookupNetworkError("URLError: test")
            return 200, '{"PropertyTable":{"Properties":[{"CID":1,"MolecularFormula":"X"}]}}'
        rep = probe_endpoints(http_get=routed)
        self.assertFalse(rep["fully_live"])
        self.assertFalse(rep["uniprot"]["reachable"])
        self.assertTrue(rep["pdb"]["resolved"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
