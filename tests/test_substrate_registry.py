"""
test_substrate_registry.py — STEP 28 / 28.7-STUB. Call-free: no model calls,
no network. Covers the substrate maturity registry and the web-search stub's
structural provenance contract.

Run directly: venv/bin/python3 tests/test_substrate_registry.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import substrate_registry as registry
from tools import web_search_stub


class TestRegistryTable(unittest.TestCase):
    def test_all_enrolled_substrates_in_order(self):
        # BIO Wave D.2: rdkit enrolled (Option A) after ngspice, before
        # web_search (web_search stays last — outside the routable ladder).
        ids = [r.substrate_id for r in registry.all_substrates()]
        self.assertEqual(
            ids,
            [
                "cavity_2d_cfd",
                "calculix_cantilever_fea",
                "code_sklearn_eval",
                "fenicsx_cantilever_elastic",
                "sympy_symbolic_exact",
                "ngspice_linear_passive",
                "rdkit",
                "cobrapy",
                "cas_offinder",
                "homology_search",
                "mafft",
                "autodock_vina",
                "crispr_guide_scoring",
                "boltz2",
                "proteinmpnn",
                "web_search",
            ],
        )

    def test_cavity_is_provisional_and_first_routable(self):
        cfd = registry.get("cavity_2d_cfd")
        self.assertEqual(cfd.maturity, registry.PROVISIONAL)
        self.assertTrue(cfd.routable)
        self.assertEqual(cfd.wrapper, "tools/run_cfd.py")
        # provisional is non-mature -> a trust decision on it is human-required
        self.assertFalse(registry.is_mature("cavity_2d_cfd"))
        # the routable set since the Packet B Phase 2 flip (build chat
        # under the owner's standing delegation, 2026-07-17): five ids in
        # enrollment order — cavity, calculix, fenicsx, sympy, ngspice
        self.assertEqual(
            registry.routable_ids(),
            ("cavity_2d_cfd", "calculix_cantilever_fea",
             "fenicsx_cantilever_elastic", "sympy_symbolic_exact",
             "ngspice_linear_passive"),
        )

    def test_sympy_is_calibrating_routable_under_packet_b_phase1(self):
        # the flip's row: routable=True RULED (owner "start phase 1" +
        # Phase-1.0 ruling line, 2026-07-17), maturity CALIBRATING
        # unchanged, recorded in notes with the battery evidence line
        rec = registry.get("sympy_symbolic_exact")
        self.assertTrue(rec.routable)
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(registry.is_mature("sympy_symbolic_exact"))
        self.assertIn("Packet B Phase 1", rec.notes)
        self.assertIn("'start phase 1'", rec.notes)
        self.assertIn(
            "calibration_sympy_symbolic_exact_20260717T115450Z.json", rec.notes
        )

    def test_ngspice_is_calibrating_routable_under_r2_r3(self):
        # the flip's row: routable=True RULED R2, maturity CALIBRATING
        # unchanged RULED R3 (owner, 2026-07-17), recorded in notes
        rec = registry.get("ngspice_linear_passive")
        self.assertTrue(rec.routable)
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(registry.is_mature("ngspice_linear_passive"))
        self.assertIn("(owner, 2026-07-17)", rec.notes)

    def test_code_is_calibrating_and_unroutable(self):
        # calculix left this loop at the Packet B Phase 2 flip; code stays
        # the enrolled-unroutable subject (with web_search, its own class).
        rec = registry.get("code_sklearn_eval")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertFalse(registry.is_mature("code_sklearn_eval"))

    def test_rdkit_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 (Option A): rdkit enrolls calibrating/routable=False and
        # is INERT — a registry row only, with NO _CONTRACTS entry, so
        # contract_for MUST raise (the ngspice-card-8.5 invariant). Runtime
        # wiring is deferred to D.4 promotion.
        rec = registry.get("rdkit")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertFalse(registry.is_mature("rdkit"))
        self.assertEqual(rec.wrapper, "tools/run_rdkit.py")
        self.assertNotIn("rdkit", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("rdkit")

    def test_cobrapy_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 2 (Option A): same inert enrollment as rdkit.
        rec = registry.get("cobrapy")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertFalse(registry.is_mature("cobrapy"))
        self.assertEqual(rec.wrapper, "tools/run_cobrapy.py")
        self.assertNotIn("cobrapy", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("cobrapy")

    def test_cas_offinder_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 3 (Option A, DEFERRED): inert like rdkit/cobrapy.
        rec = registry.get("cas_offinder")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertEqual(rec.wrapper, "tools/run_cas_offinder.py")
        self.assertNotIn("cas_offinder", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("cas_offinder")

    def test_homology_search_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 4 (Option A, T2): the BLAST+HMMER bundle, inert.
        rec = registry.get("homology_search")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertEqual(rec.wrapper, "tools/run_homology_search.py")
        self.assertNotIn("homology_search", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("homology_search")

    def test_mafft_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 6 (Option A, T2): msa_alignment, inert.
        rec = registry.get("mafft")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertEqual(rec.wrapper, "tools/run_mafft.py")
        self.assertNotIn("mafft", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("mafft")

    def test_autodock_vina_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 7 (Option A, DEFERRED — no aarch64 build): inert.
        rec = registry.get("autodock_vina")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertEqual(rec.wrapper, "tools/run_autodock_vina.py")
        self.assertNotIn("autodock_vina", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("autodock_vina")

    def test_crispr_guide_scoring_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 increment 8 (Option A, DEFERRED — no verified scorer): inert.
        rec = registry.get("crispr_guide_scoring")
        self.assertEqual(rec.maturity, registry.CALIBRATING)
        self.assertFalse(rec.routable)
        self.assertEqual(rec.wrapper, "tools/run_crispr_guide_scoring.py")
        self.assertNotIn("crispr_guide_scoring", registry.routable_ids())
        with self.assertRaises(LookupError):
            registry.contract_for("crispr_guide_scoring")

    def test_deferred_tier_enrolled_calibrating_unroutable_and_inert(self):
        # BIO Wave D.2 the final deferred tier (Option A): all inert.
        for sid, wrapper in [
            ("boltz2", "tools/run_boltz2.py"),
            ("proteinmpnn", "tools/run_proteinmpnn.py"),
            ("retrosynthesis", "tools/run_retrosynthesis.py"),
            ("alphafold_db", "tools/run_alphafold_db.py"),
            ("bio_db_lookup", "tools/run_bio_db_lookup.py"),
        ]:
            if sid not in registry._BY_ID:
                continue  # enrolled across successive increments
            rec = registry.get(sid)
            self.assertEqual(rec.maturity, registry.CALIBRATING, sid)
            self.assertFalse(rec.routable, sid)
            self.assertEqual(rec.wrapper, wrapper, sid)
            self.assertNotIn(sid, registry.routable_ids(), sid)
            with self.assertRaises(LookupError):
                registry.contract_for(sid)

    def test_cantilevers_are_calibrating_routable_under_packet_b_phase2(self):
        # the flip's rows: routable=True RULED Packet B Phase 2 (owner
        # 'start phase 1' pair unit + R-B-1 + the Phase-2.0 ruling line,
        # build chat under the owner's standing delegation, 2026-07-17),
        # maturity CALIBRATING unchanged, battery evidence in notes.
        for sid, battery in (
            ("calculix_cantilever_fea",
             "calibration_calculix_cantilever_fea_20260716T053643Z.json"),
            ("fenicsx_cantilever_elastic",
             "calibration_fenicsx_cantilever_elastic_20260717T125837Z.json"),
        ):
            rec = registry.get(sid)
            self.assertTrue(rec.routable, sid)
            self.assertEqual(rec.maturity, registry.CALIBRATING, sid)
            self.assertFalse(registry.is_mature(sid), sid)
            self.assertIn("Packet B Phase 2", rec.notes)
            self.assertIn("R-B-1", rec.notes)
            self.assertIn("StaticSmallDeflectionRegime", rec.notes)
            self.assertIn(battery, rec.notes)

    def test_web_search_is_its_own_class_and_unroutable(self):
        web = registry.get("web_search")
        self.assertEqual(web.maturity, registry.RETRIEVAL_PROVISIONAL)
        self.assertFalse(web.routable)
        self.assertFalse(registry.is_mature("web_search"))
        # retrieval-provisional is deliberately OUTSIDE the routable ladder
        self.assertNotIn(registry.RETRIEVAL_PROVISIONAL, registry.MATURITY_LADDER)

    def test_no_substrate_is_mature_today(self):
        self.assertFalse(any(registry.is_mature(r.substrate_id) for r in registry.all_substrates()))

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError):
            registry.get("no_such_substrate")

    def test_records_are_frozen(self):
        rec = registry.get("cavity_2d_cfd")
        with self.assertRaises(Exception):
            rec.maturity = registry.MATURE  # frozen dataclass: cannot mutate a trust fact

    def test_changes_only_by_ruling_comment_present(self):
        src = (ROOT / "tools" / "substrate_registry.py").read_text()
        self.assertIn("changes only by recorded ruling", src)


class TestWebSearchStubShape(unittest.TestCase):
    def test_shape_and_provenance(self):
        out = web_search_stub.web_search_stub("lid-driven cavity", k=3)
        self.assertEqual(out["provenance"], "provisional")
        self.assertEqual(len(out["results"]), 3)
        for r in out["results"]:
            self.assertEqual(set(r.keys()), {"title", "url", "snippet"})

    def test_k_controls_count(self):
        self.assertEqual(len(web_search_stub.web_search_stub("q", k=1)["results"]), 1)
        self.assertEqual(len(web_search_stub.web_search_stub("q", k=0)["results"]), 0)

    def test_snippets_bounded_no_full_body(self):
        out = web_search_stub.web_search_stub("x" * 5000, k=2)
        for r in out["results"]:
            self.assertLessEqual(len(r["snippet"]), web_search_stub.SNIPPET_CAP)


class TestWebFindingProvenanceContract(unittest.TestCase):
    """Hard rule (c): the writer can NEVER emit a validated-class value."""

    def test_writes_provisional_by_default(self):
        captured = {}

        def fake_append(entry):
            captured.update(entry)
            return entry

        with mock.patch.object(web_search_stub, "journal_append", fake_append):
            web_search_stub.journal_web_finding(
                "run-1", "q", [{"title": "t", "url": "u", "snippet": "s"}]
            )
        self.assertEqual(captured["kind"], "web_finding")
        self.assertEqual(captured["extras"]["provenance"], "provisional")

    def test_snippets_bounded_in_journal_entry(self):
        captured = {}

        def fake_append(entry):
            captured.update(entry)
            return entry

        with mock.patch.object(web_search_stub, "journal_append", fake_append):
            web_search_stub.journal_web_finding(
                "run-1", "q", [{"title": "t", "url": "u", "snippet": "y" * 9000}]
            )
        self.assertLessEqual(
            len(captured["extras"]["results"][0]["snippet"]), web_search_stub.SNIPPET_CAP
        )

    def test_any_other_provenance_raises(self):
        # The failing test for hard rule (c): attempting a non-provisional
        # provenance is refused loudly, and NOTHING is appended.
        appended = []

        def fake_append(entry):
            appended.append(entry)
            return entry

        with mock.patch.object(web_search_stub, "journal_append", fake_append):
            for bad in ("validated", "mature", "trusted", ""):
                with self.assertRaises(ValueError):
                    web_search_stub.journal_web_finding(
                        "run-1", "q", [], provenance=bad
                    )
        self.assertEqual(appended, [], "no entry may be written on a refused provenance")


if __name__ == "__main__":
    unittest.main(verbosity=2)
