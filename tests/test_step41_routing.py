"""
test_step41_routing.py — D.1b: Step 41 hierarchical within-family routing.

Call-free: no model calls, no network. Proves tools/substrate_selection's
L0/L1a/L1b/L2 pipeline (docs/memo_step41_routing.md), with EVERY narrowing and
EVERY loud stop proven BY FIRING (a check that cannot fail is not a proof):

  Live near-neighbour pair (the real cantilevers, acceptance test #3):
    * a spec declaring fenicsx's extra param routes to fenicsx at L0;
    * a shared-seven spec that BOTH cantilevers serve, share a regime shape,
      and admit the same QoI is a true near-neighbour tie -> R-B-1 LOUD STOP
      naming both, order-independent — never a coin flip.

  L1a (regime-shape) fires, BOTH directions, on a constructed signature
  collision (ngspice's signature patched to cavity's, so both serve a
  cavity-param spec but their regime grammars differ):
    * a reynolds-regime spec narrows to the reynolds-band substrate;
    * an analysis-regime spec narrows to the analysis-type substrate;
    * a regime grammar no server admits stops loudly AT L1a.

  L1b (QoI-vocab) fires, BOTH directions, on two same-signature same-regime
  fixed-summary substrates whose QoI name sets differ:
    * a spec asking a quantity only one admits routes to that one;
    * a quantity no server admits stops loudly AT L1b.

  Regression: a spec that declares no regime/qoi narrows nothing (L1a/L1b are
  transparent) — the minimal-spec R-B-1 behavior is unchanged.

Constructed registries follow tests/test_substrate_selection.py's precedent
(mock-patched routable set + signature/vocab maps); every vocabulary is the
real record or one built from a real record's shape, never a copied literal.

Run directly: venv/bin/python3 tests/test_step41_routing.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools import qoi_vocab
from tools import run_fea, run_fenicsx, run_ngspice
from tools import substrate_registry as registry
from tools import substrate_selection as selection
from tools.qoi_vocab import (
    FixedSummaryVocab,
    StaticSmallDeflectionRegime,
    vocab_for,
)

FEA_SIG = frozenset(run_fea._REQUIRED_FIELDS)          # the shared seven
FX_SIG = frozenset(run_fenicsx._REQUIRED_FIELDS)        # seven + element_degree
NGSPICE_ANALYSIS = next(iter(run_ngspice._ANALYSIS_FIELDS))  # a real analysis type


def _spec(params, regime=None, qoi=None) -> dict:
    s: dict = {"parameters": [{"name": n} for n in params]}
    if regime is not None:
        s["regime"] = regime
    if qoi is not None:
        s["qoi"] = qoi
    return s


def _prose_qoi(**extra) -> dict:
    """A QoI with the four prose fields and no machine keys — admissible under
    every vocab shape, so it never interferes with an L1a-only narrowing.
    `extra` adds a machine key (e.g. quantity=...) for L1b tests."""
    return {
        "name": "q",
        "units": "u",
        "definition": "d",
        "how_extracted": "e",
        **extra,
    }


class TestLiveCantileverNearNeighbours(unittest.TestCase):
    """The real calculix/fenicsx pair — acceptance test #3, no patching."""

    def test_element_degree_spec_resolves_to_fenicsx_at_L0(self):
        # fenicsx's extra param puts the spec outside calculix's signature, so
        # serve-ability alone (L0) resolves it — no tie.
        self.assertEqual(
            selection.select_substrate(_spec(sorted(FX_SIG))),
            "fenicsx_cantilever_elastic",
        )

    def test_shared_seven_true_tie_stops_loudly_at_L2(self):
        # both serve, both static regime, both admit tip_displacement -> a true
        # near-neighbour tie: R-B-1 loud stop, never a coin flip.
        spec = _spec(
            sorted(FEA_SIG),
            regime={"notes": "inside the card's ruled bounds"},
            qoi=_prose_qoi(quantity="tip_displacement"),
        )
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(spec)
        msg = str(ctx.exception)
        self.assertIn("ambiguous (R-B-1", msg)
        self.assertIn("calculix_cantilever_fea@", msg)
        self.assertIn("fenicsx_cantilever_elastic@", msg)
        self.assertIn("stopping before routing", msg)

    def test_the_tie_stop_is_order_independent(self):
        spec = _spec(
            sorted(FEA_SIG),
            regime={"notes": "inside bounds"},
            qoi=_prose_qoi(quantity="tip_displacement"),
        )
        for order in (
            ("calculix_cantilever_fea", "fenicsx_cantilever_elastic"),
            ("fenicsx_cantilever_elastic", "calculix_cantilever_fea"),
        ):
            with mock.patch.object(
                registry, "routable_ids", return_value=order
            ):
                with self.assertRaises(LookupError) as ctx:
                    selection.select_substrate(spec)
                self.assertIn("ambiguous (R-B-1", str(ctx.exception))


def _cavity_ngspice_signature_collision():
    """A constructed two-routable registry where ngspice SHARES cavity's
    signature (patched) — so a cavity-param spec serves BOTH at L0, and only
    their differing regime grammars (real vocab records) can separate them."""
    return (
        mock.patch.object(
            registry,
            "routable_ids",
            return_value=("cavity_2d_cfd", "ngspice_linear_passive"),
        ),
        mock.patch.dict(
            selection._SIGNATURES,
            {"ngspice_linear_passive": selection._SIGNATURES["cavity_2d_cfd"]},
        ),
    )


class TestL1aRegimeShapeNarrows(unittest.TestCase):
    CAVITY_PARAM = "lid_velocity"  # in cavity's (and the patched ngspice) sig

    def test_reynolds_regime_narrows_to_the_reynolds_substrate(self):
        p = self._cavity_and_ngspice_both_serve()
        spec = _spec(
            [self.CAVITY_PARAM],
            regime={"reynolds_min": 1, "reynolds_max": 100, "notes": "n"},
            qoi=_prose_qoi(),
        )
        with p[0], p[1]:
            self.assertEqual(selection.select_substrate(spec), "cavity_2d_cfd")

    def test_analysis_regime_narrows_to_the_analysis_substrate(self):
        p = self._cavity_and_ngspice_both_serve()
        spec = _spec(
            [self.CAVITY_PARAM],
            regime={"analysis_type": NGSPICE_ANALYSIS, "notes": "n"},
            qoi=_prose_qoi(),
        )
        with p[0], p[1]:
            self.assertEqual(
                selection.select_substrate(spec), "ngspice_linear_passive"
            )

    def test_regime_grammar_no_server_admits_stops_at_L1a(self):
        # an operation-set regime block: cavity (reynolds) and ngspice
        # (analysis) both reject it -> L1a empties -> loud stop AT L1a.
        p = self._cavity_and_ngspice_both_serve()
        spec = _spec(
            [self.CAVITY_PARAM],
            regime={"operation": "differentiate", "notes": "n"},
            qoi=_prose_qoi(),
        )
        with p[0], p[1]:
            with self.assertRaises(LookupError) as ctx:
                selection.select_substrate(spec)
        msg = str(ctx.exception)
        self.assertIn("stops at L1a", msg)
        self.assertIn("regime-shape", msg)
        self.assertIn("stopping before routing", msg)

    def _cavity_and_ngspice_both_serve(self):
        return _cavity_ngspice_signature_collision()


def _two_fixed_summary_different_names():
    """Two same-signature, same-regime-shape fixed-summary substrates whose
    QoI name sets differ: calculix keeps its real vocab; fenicsx is given
    calculix's signature (so both serve the shared seven) and a constructed
    fixed-summary vocab with a DISJOINT name set — so only the requested
    quantity can separate them (L1b)."""
    fenicsx_vocab = FixedSummaryVocab(
        names=("fenicsx_only_quantity",),
        regime=StaticSmallDeflectionRegime(),
    )
    return (
        mock.patch.object(
            registry,
            "routable_ids",
            return_value=(
                "calculix_cantilever_fea",
                "fenicsx_cantilever_elastic",
            ),
        ),
        mock.patch.dict(
            selection._SIGNATURES,
            {
                "fenicsx_cantilever_elastic": selection._SIGNATURES[
                    "calculix_cantilever_fea"
                ]
            },
        ),
        mock.patch.dict(
            qoi_vocab._VOCABS,
            {"fenicsx_cantilever_elastic": fenicsx_vocab},
        ),
    )


class TestL1bQoiVocabNarrows(unittest.TestCase):
    def setUp(self):
        # a real calculix quantity name, from its own wired vocab
        self.calculix_qty = vocab_for("calculix_cantilever_fea").names[0]

    def _spec_asking(self, quantity: str) -> dict:
        return _spec(
            sorted(FEA_SIG),
            regime={"notes": "inside bounds"},
            qoi=_prose_qoi(quantity=quantity),
        )

    def test_calculix_quantity_narrows_to_calculix(self):
        p = _two_fixed_summary_different_names()
        with p[0], p[1], p[2]:
            self.assertEqual(
                selection.select_substrate(self._spec_asking(self.calculix_qty)),
                "calculix_cantilever_fea",
            )

    def test_fenicsx_only_quantity_narrows_to_fenicsx(self):
        p = _two_fixed_summary_different_names()
        with p[0], p[1], p[2]:
            self.assertEqual(
                selection.select_substrate(
                    self._spec_asking("fenicsx_only_quantity")
                ),
                "fenicsx_cantilever_elastic",
            )

    def test_quantity_no_server_admits_stops_at_L1b(self):
        p = _two_fixed_summary_different_names()
        with p[0], p[1], p[2]:
            with self.assertRaises(LookupError) as ctx:
                selection.select_substrate(
                    self._spec_asking("no_such_quantity_anywhere")
                )
        msg = str(ctx.exception)
        self.assertIn("stops at L1b", msg)
        self.assertIn("QoI-vocab", msg)
        self.assertIn("stopping before routing", msg)


class TestNarrowingIsTransparentWithoutRegimeOrQoi(unittest.TestCase):
    def test_minimal_spec_still_reaches_rb1_unchanged(self):
        # no regime, no qoi -> L1a/L1b narrow nothing; the shared-seven spec
        # is still a tie at L2 (proves L1a/L1b did not spuriously drop anyone).
        with self.assertRaises(LookupError) as ctx:
            selection.select_substrate(_spec(sorted(FEA_SIG)))
        self.assertIn("ambiguous (R-B-1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
