"""test_run_alphafold_db.py — AFDB lookup wrapper (D.2 -> D.4-network un-defer).
Proven here OFFLINE + DETERMINISTIC (http_get is injected): the input gate, the
real success shape, and the two network outcomes (honest not-found vs
could-not-run setup_error) — never a fabricated pLDDT. Live-endpoint proof is a
separate one-off (see the D.4-network handoff)."""
from __future__ import annotations
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tools.run_alphafold_db import (QOI_FIELDS, AlphaFoldDBInputError,
    AlphaFoldDBNetworkError, _validate_input, run_alphafold_db as run)

_GOOD = {"uniprot_accession": "P0DP23", "quantity": "mean_pLDDT"}


def _fake_get(status, body):
    def get(url, timeout=20.0):
        return status, body
    return get


def _raising_get(url, timeout=20.0):
    raise AlphaFoldDBNetworkError("AFDB endpoint unreachable (URLError: test)")


class InputGate(unittest.TestCase):
    def test_clean_passes(self):
        self.assertEqual(_validate_input(_GOOD)["uniprot_accession"], "P0DP23")
    def test_lowercase_accession_normalised(self):
        self.assertEqual(_validate_input({"uniprot_accession": "p0dp23", "quantity": "mean_pLDDT"})["uniprot_accession"], "P0DP23")
    def test_sequence_not_accession_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"uniprot_accession": "MKTAYIAKQR", "quantity": "mean_pLDDT"})
    def test_old_protein_sequence_field_rejected(self):
        # the retired input shape must not silently work
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"protein_sequence": "MKTAY", "quantity": "mean_pLDDT"})
    def test_bad_quantity_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"uniprot_accession": "P0DP23", "quantity": "plddt"})
    def test_missing_and_extra_rejected(self):
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"uniprot_accession": "P0DP23"})
        with self.assertRaises(AlphaFoldDBInputError):
            _validate_input({"uniprot_accession": "P0DP23", "quantity": "mean_pLDDT", "x": 1})
    def test_vocab(self):
        self.assertEqual(QOI_FIELDS, ("mean_pLDDT",))


class NetworkOutcomes(unittest.TestCase):
    def test_success_returns_real_plddt_and_never_trust_alone(self):
        body = '[{"globalMetricValue": 85.25, "uniprotAccession": "P0DP23"}]'
        r = run(_GOOD, http_get=_fake_get(200, body))
        self.assertTrue(r["valid"]); self.assertEqual(r["qoi"], 85.25)
        self.assertIn("NEVER-TRUSTED-ALONE", r["diagnostics"])
    def test_not_found_is_distinct_from_network_failure(self):
        r = run(_GOOD, http_get=_fake_get(404, '{"error":"not found"}'))
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"])
        self.assertIn("not_found", r["diagnostics"])
        self.assertNotIn("setup_error", r["diagnostics"])
    def test_malformed_400_is_not_found_not_network(self):
        r = run(_GOOD, http_get=_fake_get(400, '{"error":"Invalid identifier"}'))
        self.assertFalse(r["valid"]); self.assertIn("not_found", r["diagnostics"])
    def test_5xx_is_setup_error_not_not_found(self):
        r = run(_GOOD, http_get=_fake_get(503, "unavailable"))
        self.assertFalse(r["valid"]); self.assertIn("setup_error", r["diagnostics"])
    def test_unreachable_endpoint_is_setup_error(self):
        r = run(_GOOD, http_get=_raising_get)
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"])
        self.assertIn("setup_error", r["diagnostics"])
        self.assertNotIn("not_found", r["diagnostics"])
    def test_200_but_no_metric_is_not_found_never_fabricated(self):
        r = run(_GOOD, http_get=_fake_get(200, "[]"))
        self.assertFalse(r["valid"]); self.assertIsNone(r["qoi"])
        self.assertIn("not_found", r["diagnostics"])
    def test_bad_input_refused_before_network(self):
        # a raising http_get would blow up if reached; input jail must short-circuit
        r = run({"uniprot_accession": "12345", "quantity": "mean_pLDDT"}, http_get=_raising_get)
        self.assertIn("input rejected", r["diagnostics"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
