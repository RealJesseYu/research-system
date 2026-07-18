"""
test_r2355_regime.py — R-23.5-5 Phase-2 machinery tests: per-substrate
regime semantics in the vocabulary records, and the R-23.5-5a rider.

ZERO model calls. What is proven here:
  - the cavity record's regime semantics are ReynoldsBandRegime, and the
    delegated checker is byte-equal to the pre-change behavior (the exact
    strings are pinned by tests/test_r2355_captures.py; here the dispatch
    path is shown to produce them);
  - AnalysisTypeRegime is DERIVED from the wrapper's typed input —
    analysis_types == tuple(run_ngspice._ANALYSIS_FIELDS), the wrapper's
    own analysis-type table, never a pasted list;
  - the named-analysis checker's semantics, tested DIRECTLY on a
    constructed vocab (production enrollment of NGSPICE_REGIME FLIPPED at
    Phase 3 with the placeholder-fixture supersession — see
    TestProductionRecordEscapes for the enrolled-record proofs): a valid
    {analysis_type, notes} block passes; a Reynolds-shaped block REJECTS
    with a named per-substrate reason; an unknown analysis_type rejects;
    a regime-less spec still rejects via the required-field check;
  - an unknown regime-vocabulary shape raises (broken invariant, not a
    model error);
  - R-23.5-5a escapes, proven by failing: no vocab -> TypeError; explicit
    None -> TypeError; a vocab record cannot even be CONSTRUCTED without
    regime semantics.

Run directly: venv/bin/python3 tests/test_r2355_regime.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.stage2_spec import validate_spec
from tools import run_ngspice
from tools.qoi_vocab import (
    ANALYSIS_TYPE,
    NGSPICE_REGIME,
    AnalysisTypeRegime,
    NamedQuantityVocab,
    ReynoldsBandRegime,
    vocab_for,
)

FIX = Path(__file__).resolve().parent / "fixtures"

CAVITY_VOCAB = vocab_for("cavity_2d_cfd")

# A named-quantity vocab carrying the ngspice regime semantics, constructed
# HERE for direct checker tests (written pre-flip; since Phase 3 the
# production record carries the same NGSPICE_REGIME — proven below).
NGSPICE_VOCAB_WITH_REGIME = NamedQuantityVocab(
    kinds=run_ngspice._QOI_KINDS,
    target_re=run_ngspice._NAME_RE,
    reductions=run_ngspice._REDUCTIONS,
    regime=NGSPICE_REGIME,
)


def _circuit_spec() -> dict:
    """The c235 circuit spec (placeholder regime at Phase 2; honest
    named-analysis regime since the Phase-3c supersession — this loader
    tracks the fixture)."""
    return json.loads((FIX / "c235" / "ngspice_full_spec.json").read_text())


def _cavity_spec() -> dict:
    spec = json.loads((FIX / "r2355" / "reply_bad_regime.json").read_text())["spec"]
    spec["regime"]["reynolds_min"] = 100  # heal the capture's deliberate break
    return spec


class TestCavityRegimeDelegation(unittest.TestCase):
    def test_cavity_record_carries_reynolds_band_semantics(self):
        self.assertIsInstance(CAVITY_VOCAB.regime, ReynoldsBandRegime)

    def test_valid_cavity_regime_passes_through_dispatch(self):
        self.assertEqual(validate_spec(_cavity_spec(), "hand-baseline", CAVITY_VOCAB), [])

    def test_ordering_violation_string_unchanged_through_dispatch(self):
        spec = _cavity_spec()
        spec["regime"]["reynolds_min"] = 300
        self.assertEqual(
            validate_spec(spec, "hand-baseline", CAVITY_VOCAB),
            [
                "regime must satisfy 0 < reynolds_min <= reynolds_max; "
                "got reynolds_min=300 and reynolds_max=200."
            ],
        )


class TestAnalysisTypeRegimeDerivation(unittest.TestCase):
    def test_derived_from_the_wrapper_typed_input(self):
        # each field cited: _ANALYSIS_FIELDS is run_ngspice's own
        # analysis-type table; the record is a structural view of its keys
        self.assertEqual(
            NGSPICE_REGIME.analysis_types, tuple(run_ngspice._ANALYSIS_FIELDS)
        )
        self.assertEqual(NGSPICE_REGIME.shape, ANALYSIS_TYPE)

    def test_wrapper_order_preserved(self):
        self.assertEqual(NGSPICE_REGIME.analysis_types, ("op", "dc", "ac", "tran"))


class TestNamedAnalysisChecker(unittest.TestCase):
    """Direct semantics tests on the constructed vocab (pre-flip)."""

    def _spec_with_regime(self, regime) -> dict:
        spec = _circuit_spec()
        spec["regime"] = regime
        return spec

    def _regime_errors(self, regime) -> list[str]:
        errors = validate_spec(
            self._spec_with_regime(regime), "hand-ngspice", NGSPICE_VOCAB_WITH_REGIME
        )
        return [e for e in errors if e.startswith("regime")]

    def test_valid_named_analysis_regime_passes(self):
        self.assertEqual(
            self._regime_errors(
                {"analysis_type": "op", "notes": "linear passive DC operating point"}
            ),
            [],
        )

    def test_reynolds_shaped_block_rejects_with_named_reason(self):
        errors = self._regime_errors(
            {"reynolds_min": 1, "reynolds_max": 1, "notes": "placeholder"}
        )
        self.assertEqual(
            errors,
            [
                "regime field 'reynolds_min' is not part of this substrate's "
                "regime vocabulary — this instrument's regime is not a Reynolds "
                "band; declare 'analysis_type' (one of: op, dc, ac, tran) and "
                "'notes'.",
                "regime field 'reynolds_max' is not part of this substrate's "
                "regime vocabulary — this instrument's regime is not a Reynolds "
                "band; declare 'analysis_type' (one of: op, dc, ac, tran) and "
                "'notes'.",
                "regime is missing 'analysis_type' — this substrate's regime is "
                "declared as one of its analysis types: op, dc, ac, tran.",
            ],
        )

    def test_unknown_analysis_type_rejects(self):
        self.assertEqual(
            self._regime_errors({"analysis_type": "noise", "notes": "n"}),
            [
                "regime analysis_type must be one of: op, dc, ac, tran; "
                "got 'noise'."
            ],
        )

    def test_not_an_object_rejects(self):
        self.assertEqual(
            self._regime_errors("op"),
            ["regime must be an object with analysis_type and notes."],
        )

    def test_missing_notes_rejects(self):
        self.assertEqual(
            self._regime_errors({"analysis_type": "op"}),
            ["regime is missing 'notes'."],
        )

    def test_regime_less_spec_still_rejects(self):
        spec = _circuit_spec()
        del spec["regime"]
        self.assertIn(
            "required field 'regime' is missing — add it.",
            validate_spec(spec, "hand-ngspice", NGSPICE_VOCAB_WITH_REGIME),
        )


class TestUnknownShapeRaises(unittest.TestCase):
    def test_unknown_regime_shape_is_a_broken_invariant(self):
        class _AlienRegime:
            shape = "spectral_band"

        alien = NamedQuantityVocab(
            kinds=run_ngspice._QOI_KINDS,
            target_re=run_ngspice._NAME_RE,
            reductions=run_ngspice._REDUCTIONS,
            regime=_AlienRegime(),
        )
        with self.assertRaises(ValueError):
            validate_spec(_circuit_spec(), "hand-ngspice", alien)


class TestProductionRecordEscapes(unittest.TestCase):
    """3e NEW escapes, proven on the ENROLLED production record (post-flip)."""

    def test_production_ngspice_record_carries_the_wrapper_derived_regime(self):
        self.assertIs(vocab_for("ngspice_linear_passive").regime, NGSPICE_REGIME)

    def test_honest_circuit_spec_validates_under_the_production_record(self):
        self.assertEqual(
            validate_spec(
                _circuit_spec(), "hand-ngspice", vocab_for("ngspice_linear_passive")
            ),
            [],
        )

    def test_reynolds_shaped_regime_rejects_under_the_production_record(self):
        spec = _circuit_spec()
        spec["regime"] = {"reynolds_min": 1, "reynolds_max": 1, "notes": "placeholder"}
        errors = validate_spec(
            spec, "hand-ngspice", vocab_for("ngspice_linear_passive")
        )
        self.assertTrue(
            any("not a Reynolds band" in e for e in errors), errors
        )

    def test_regime_less_spec_rejects_under_the_production_record(self):
        spec = _circuit_spec()
        del spec["regime"]
        self.assertIn(
            "required field 'regime' is missing — add it.",
            validate_spec(
                spec, "hand-ngspice", vocab_for("ngspice_linear_passive")
            ),
        )

    def test_unknown_substrate_at_the_vocab_lookup_raises(self):
        with self.assertRaises(KeyError):
            vocab_for("no_such_substrate")


class TestRider5aEscapes(unittest.TestCase):
    """Escapes proven by FAILING (R-23.5-5a)."""

    def test_absent_vocab_raises(self):
        with self.assertRaises(TypeError):
            validate_spec(_cavity_spec(), "hand-baseline")

    def test_explicit_none_vocab_raises(self):
        with self.assertRaises(TypeError):
            validate_spec(_cavity_spec(), "hand-baseline", None)

    def test_vocab_record_requires_regime_semantics(self):
        # a record without regime semantics cannot exist
        with self.assertRaises(TypeError):
            NamedQuantityVocab(
                kinds=run_ngspice._QOI_KINDS,
                target_re=run_ngspice._NAME_RE,
                reductions=run_ngspice._REDUCTIONS,
            )

    def test_dataclass_regime_is_a_new_field_not_a_default(self):
        # AnalysisTypeRegime itself refuses construction without its
        # wrapper-derived member
        with self.assertRaises(TypeError):
            AnalysisTypeRegime()


if __name__ == "__main__":
    unittest.main()
