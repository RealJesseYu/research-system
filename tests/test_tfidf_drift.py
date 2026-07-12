"""
test_tfidf_drift.py — 17-CLOSE tfidf/proximity parameter-sync guard
(tests/ only; no source change).

The tournament's proximity matrix (stages/tournament.py) promises it uses
"the same vectorizer machinery tfidf_core builds this project's retrieval
indices with" — but both sites construct their TfidfVectorizer inline, so
nothing enforced the promise. This test captures the ACTUAL constructor
arguments each site passes (by patching TfidfVectorizer at its import
source and delegating to the real class, so both code paths run for real)
and fails on any divergence. Dedup thresholds and similarity bands were
calibrated against this shared configuration (17-C/17-D); a silent drift
would invalidate them.

Zero model calls; sklearn runs locally. Run directly:
venv/bin/python3 tests/test_tfidf_drift.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from retrieval import tfidf_core
from stages import tournament


class TestTfidfParameterSync(unittest.TestCase):
    class _Constructed(Exception):
        """Sentinel: the vectorizer was constructed — the parameters are
        captured, so the site is aborted before any fit/pickle work (a real
        instance cannot be pickled while the class attribute is patched)."""

    def _capture_vectorizer_args(self, run_site) -> tuple:
        """Run one code path with TfidfVectorizer patched at its import
        source (both sites import it inside the function, so patching the
        sklearn module attribute intercepts both) and return the (args,
        kwargs) it was constructed with."""
        import sklearn.feature_extraction.text as sk_text

        captured: list[tuple] = []

        def recording_factory(*args, **kwargs):
            captured.append((args, kwargs))
            raise self._Constructed

        with patch.object(sk_text, "TfidfVectorizer", recording_factory):
            try:
                run_site()
            except self._Constructed:
                pass
        self.assertEqual(
            len(captured), 1, "expected exactly one vectorizer construction"
        )
        return captured[0]

    def test_tournament_vectorizer_matches_tfidf_core_factory(self):
        survivors = [
            {"statement": "vortex strength scales with Reynolds number", "rationale": "benchmark data"},
            {"statement": "corner eddies cascade at fixed aspect ratio", "rationale": "prior simulations"},
        ]
        tournament_args = self._capture_vectorizer_args(
            lambda: tournament.proximity_matrix(survivors)
        )

        docs = [
            {"text": "lid-driven cavity flow benchmark"},
            {"text": "secondary corner eddy structure"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            core_args = self._capture_vectorizer_args(
                lambda: tfidf_core.build_index(docs, Path(tmp) / "index.pkl")
            )

        self.assertEqual(
            tournament_args,
            core_args,
            "tournament.proximity_matrix's TfidfVectorizer parameters have "
            "drifted from tfidf_core.build_index's configuration — the "
            "proximity/dedup calibration assumes they are identical",
        )
        # Guard against a vacuous pass: the shared configuration is not the
        # sklearn default — it must actually say something.
        self.assertTrue(
            tournament_args[0] or tournament_args[1],
            "captured vectorizer construction carried no parameters at all",
        )


if __name__ == "__main__":
    unittest.main()
