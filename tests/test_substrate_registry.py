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
    def test_all_six_substrates_enrolled(self):
        ids = [r.substrate_id for r in registry.all_substrates()]
        self.assertEqual(
            ids,
            [
                "cavity_2d_cfd",
                "calculix_cantilever_fea",
                "code_sklearn_eval",
                "fenicsx_cantilever_elastic",
                "sympy_symbolic_exact",
                "web_search",
            ],
        )

    def test_cavity_is_provisional_and_the_sole_routable(self):
        cfd = registry.get("cavity_2d_cfd")
        self.assertEqual(cfd.maturity, registry.PROVISIONAL)
        self.assertTrue(cfd.routable)
        self.assertEqual(cfd.wrapper, "tools/run_cfd.py")
        # provisional is non-mature -> a trust decision on it is human-required
        self.assertFalse(registry.is_mature("cavity_2d_cfd"))
        # the SOLE routable substrate today
        self.assertEqual(registry.routable_ids(), ("cavity_2d_cfd",))

    def test_fea_and_code_are_calibrating_and_unroutable(self):
        for sid in ("calculix_cantilever_fea", "code_sklearn_eval"):
            rec = registry.get(sid)
            self.assertEqual(rec.maturity, registry.CALIBRATING, sid)
            self.assertFalse(rec.routable, sid)
            self.assertFalse(registry.is_mature(sid), sid)

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
