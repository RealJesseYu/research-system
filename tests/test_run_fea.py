"""
test_run_fea.py — call-free tests for the CalculiX FEA wrapper (Step 27 DRY).

ZERO model calls, ZERO docker: the solver is either bypassed (pure functions:
deck generation, parsing, analytic formula) or replaced by a stub that
simulates ccx by writing a frozen real .dat fixture. The two fixtures were
captured from a REAL ccx-prod run:
  * fea_cantilever_converged.dat — the coarse (8x1x1) smoke case output;
  * fea_cantilever_failed.dat    — a real header truncated at an aborted run.

Run directly:  venv/bin/python3 -m pytest tests/test_run_fea.py
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

import run_fea  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CONVERGED = (FIXTURES / "fea_cantilever_converged.dat").read_text()
FAILED = (FIXTURES / "fea_cantilever_failed.dat").read_text()

BASE_SPEC = {"length": 1.0, "width": 0.05, "height": 0.05,
             "E": 210e9, "nu": 0.3, "tip_load": 1000.0, "mesh_density": 8}


class TestDeckGeneration(unittest.TestCase):
    def test_deck_generation_is_deterministic(self):
        self.assertEqual(run_fea.build_deck(BASE_SPEC), run_fea.build_deck(dict(BASE_SPEC)))

    def test_mesh_density_changes_the_deck(self):
        coarse = run_fea.build_deck({**BASE_SPEC, "mesh_density": 8})
        finer = run_fea.build_deck({**BASE_SPEC, "mesh_density": 32})
        self.assertNotEqual(coarse, finer)

    def test_deck_node_and_element_counts(self):
        # mesh_density 8 -> nx=8, ny=nz=1 (aspect scaled): 9*2*2 = 36 nodes, 8 elems.
        deck = run_fea.build_deck(BASE_SPEC)
        self.assertIn("*ELEMENT, TYPE=C3D8I", deck)
        self.assertIn("*ELASTIC", deck)
        self.assertIn("2.1e+11, 0.3", deck)              # E, nu on the *ELASTIC line
        elem_lines = [ln for ln in deck.splitlines() if len(ln.split(",")) == 9]
        self.assertEqual(len(elem_lines), 8)             # nx*ny*nz = 8*1*1

    def test_analytic_tip_deflection_formula(self):
        # delta = P L^3 / (3 E I), I = w h^3 / 12
        I = BASE_SPEC["width"] * BASE_SPEC["height"] ** 3 / 12.0
        expected = BASE_SPEC["tip_load"] * BASE_SPEC["length"] ** 3 / (3 * BASE_SPEC["E"] * I)
        self.assertAlmostEqual(run_fea.analytic_tip_deflection(BASE_SPEC), expected, places=12)

    def test_input_validation_rejects(self):
        for bad in ({k: v for k, v in BASE_SPEC.items() if k != "E"},          # missing
                    {**BASE_SPEC, "extra": 1},                                  # unsupported
                    {**BASE_SPEC, "nu": 0.7},                                   # nu out of range
                    {**BASE_SPEC, "height": -1.0},                             # non-positive
                    {**BASE_SPEC, "mesh_density": 0}):                          # md < 1
            with self.assertRaises(run_fea.FeaInputError):
                run_fea.build_deck(bad)


class TestParsers(unittest.TestCase):
    def test_converged_fixture_summarizes(self):
        qoi = run_fea.summarize_dat(CONVERGED)
        self.assertAlmostEqual(qoi["tip_displacement"], 0.003002929, places=9)
        self.assertGreater(qoi["max_von_mises"], 0.0)

    def test_converged_fixture_row_count(self):
        self.assertEqual(len(run_fea.parse_node_displacements(CONVERGED)), 36)
        self.assertTrue(run_fea.parse_element_stresses(CONVERGED))

    def test_failed_fixture_raises_not_fabricates(self):
        with self.assertRaises(ValueError):
            run_fea.summarize_dat(FAILED)

    def test_von_mises_uniaxial(self):
        # Pure uniaxial sxx=100 -> von Mises == 100.
        self.assertAlmostEqual(run_fea.von_mises(100.0, 0, 0, 0, 0, 0), 100.0, places=9)


class _StubCcx:
    """Replaces run_fea._run_ccx. Scripted per-attempt outcomes; on a 'success'
    it writes the frozen converged .dat into the case dir like real ccx would."""

    def __init__(self, outcomes, shared_host: Path):
        self.outcomes = outcomes          # list of "ok" | "transient" | "timeout"
        self.shared_host = shared_host
        self.calls = 0

    def __call__(self, job: str):
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(cmd="ccx", timeout=run_fea.TIMEOUT_SECONDS)
        if outcome == "ok":
            (self.shared_host / job).mkdir(parents=True, exist_ok=True)
            (self.shared_host / job / f"{job}.dat").write_text(CONVERGED)
            return (0, "")
        return (1, "")                    # transient: nonzero exit, no .dat written


class TestExecutionPaths(unittest.TestCase):
    def setUp(self):
        self._orig_host = run_fea.SHARED_HOST
        self._orig_runccx = run_fea._run_ccx
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        run_fea.SHARED_HOST = Path(self._tmp.name)

    def tearDown(self):
        run_fea.SHARED_HOST = self._orig_host
        run_fea._run_ccx = self._orig_runccx
        self._tmp.cleanup()

    def test_retry_once_then_succeeds(self):
        stub = _StubCcx(["transient", "ok"], run_fea.SHARED_HOST)
        run_fea._run_ccx = stub
        result = run_fea.run_fea(BASE_SPEC)
        self.assertTrue(result["valid"])
        self.assertEqual(stub.calls, 2)                  # retried exactly once
        self.assertIsNotNone(result["qoi"])

    def test_timeout_path_returns_invalid(self):
        stub = _StubCcx(["timeout", "timeout"], run_fea.SHARED_HOST)
        run_fea._run_ccx = stub
        result = run_fea.run_fea(BASE_SPEC)
        self.assertFalse(result["valid"])
        self.assertIsNone(result["qoi"])
        self.assertIn("timeout", result["diagnostics"].lower())
        self.assertEqual(stub.calls, 2)                  # tried, then retried once

    def test_return_carries_no_raw_log_text(self):
        stub = _StubCcx(["ok"], run_fea.SHARED_HOST)
        run_fea._run_ccx = stub
        result = run_fea.run_fea(BASE_SPEC)
        blob = repr(result)
        # None of the raw .dat's tell-tale lines may leak into the return.
        self.assertNotIn("displacements (vx", blob)
        self.assertNotIn("stresses (elem", blob)
        self.assertLessEqual(len(result["diagnostics"]), run_fea.MAX_DIAG_CHARS)
        # The return has exactly the documented top-level keys.
        self.assertEqual(set(result), {"valid", "qoi", "diagnostics", "runtime_s"})

    def test_bad_input_returns_invalid_without_running(self):
        stub = _StubCcx(["ok"], run_fea.SHARED_HOST)
        run_fea._run_ccx = stub
        result = run_fea.run_fea({**BASE_SPEC, "mesh_density": 0})
        self.assertFalse(result["valid"])
        self.assertEqual(stub.calls, 0)                  # never reached the solver


class TestDocsIndex(unittest.TestCase):
    def test_search_fea_docs_finds_linear_elasticity(self):
        if not run_fea.FEA_DOCS_INDEX.exists():
            self.skipTest("fea_docs index not built")
        hits = run_fea.search_fea_docs("linear elastic material", top_k=3)
        self.assertTrue(hits)
        self.assertTrue(all("CalculiX" in h["title"] for h in hits))
        self.assertTrue(all(0.0 < h["score"] <= 1.0 for h in hits))


if __name__ == "__main__":
    unittest.main()
