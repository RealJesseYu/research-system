"""
test_b1_operation_set.py — Packet B Phase 1 shared-surface machinery
(commit 2, pre-flip): the operation-set regime shape, the symbolic-result
vocabulary shape, the ngspice alien_keys extension, and the run-entry
qoi_expression widening.

ZERO model calls. Everything here runs on CONSTRUCTED records — the sympy
production instances (SYMPY_REGIME, the _VOCABS entry) are wired at the
flip commit, never before (the built-unregistered precedent). What is
proven here:

  - OperationSetRegime: shape tag, frozen, no-default `operations`
    (a record cannot be constructed without its operation set — the
    R-23.5-5a discipline), alien_keys naming BOTH other shapes' keys;
  - the operation-set checker's semantics, tested DIRECTLY on a
    constructed record: a valid {operation, notes} block passes; a
    Reynolds-shaped block and an analysis_type-shaped block each REJECT
    with a named per-substrate reason; missing/unknown operation rejects;
  - REVERSE direction (Phase-1.0 ruling item 2): AnalysisTypeRegime's
    alien_keys gained "operation" ADDITIVELY — a CAS-shaped regime block
    in an ngspice-class spec now rejects BY NAME, and the pre-existing
    Reynolds rejection strings are byte-identical (pinned exact by
    tests/test_r2355_regime.py, which must stay green beside this file);
  - SymbolicResultVocab: shape tag, frozen, no-default regime member,
    alien_keys covering BOTH machine-key grammars; a prose-only qoi
    passes; a qoi carrying either grammar's machine keys rejects by name;
  - schemas run-entry widening (Phase-1.0 ruling item 4, additive D.5
    pattern): qoi_expression validates as a non-empty string; the answer
    slot is exactly-one-of-three; every pre-existing entry shape is
    accepted byte-identically (the zero-byte-delta gate: the cavity and
    ngspice constructors are untouched and never emit the new keys —
    asserted directly on canned summaries).

Run directly: venv/bin/python3 tests/test_b1_operation_set.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import schemas
from stages import stage2_spec
from tools import substrate_dispatch
from tools.qoi_vocab import (
    ANALYSIS_TYPE,
    OPERATION_SET,
    SYMBOLIC_RESULT,
    AnalysisTypeRegime,
    NGSPICE_REGIME,
    OperationSetRegime,
    SymbolicResultVocab,
)

# A constructed operation set for the pre-flip machinery tests. The
# production record derives from tools/run_scipy.py's OPERATIONS at the
# flip; using a constructed tuple here keeps commit 2 free of any sympy
# wiring while proving the shape's semantics.
_OPS = ("integrate_definite", "diff", "solve")
_REGIME = OperationSetRegime(operations=_OPS)
_VOCAB = SymbolicResultVocab(regime=_REGIME)


def _regime_errors(regime):
    errors: list[str] = []
    stage2_spec._validate_regime(regime, _VOCAB, errors)
    return errors


def _qoi_errors(qoi):
    errors: list[str] = []
    stage2_spec._validate_qoi(qoi, _VOCAB, errors)
    return errors


class TestOperationSetRegimeRecord(unittest.TestCase):
    def test_shape_tag(self):
        self.assertEqual(OperationSetRegime.shape, OPERATION_SET)
        self.assertEqual(_REGIME.shape, "operation_set")

    def test_operations_has_no_default(self):
        # R-23.5-5a discipline: the record cannot be constructed without
        # its operation set — proven by failing.
        with self.assertRaises(TypeError):
            OperationSetRegime()

    def test_record_is_frozen(self):
        with self.assertRaises(Exception):
            _REGIME.operations = ()

    def test_alien_keys_name_both_other_shapes(self):
        self.assertEqual(
            OperationSetRegime.alien_keys,
            ("reynolds_min", "reynolds_max", "analysis_type"),
        )


class TestOperationSetChecker(unittest.TestCase):
    def test_valid_block_passes(self):
        self.assertEqual(
            _regime_errors({"operation": "diff", "notes": "one derivative"}),
            [],
        )

    def test_reynolds_shaped_block_rejects_with_named_reason(self):
        errors = _regime_errors(
            {"reynolds_min": 100, "reynolds_max": 200, "notes": "n"}
        )
        named = [e for e in errors if "not part of this substrate's regime" in e]
        self.assertEqual(len(named), 2)  # one per alien key present
        for e in named:
            self.assertIn("not a Reynolds band and not a circuit analysis", e)
            self.assertIn("declare 'operation'", e)
        # and the missing required key is still reported
        self.assertTrue(any("regime is missing 'operation'" in e for e in errors))

    def test_analysis_type_shaped_block_rejects_with_named_reason(self):
        errors = _regime_errors({"analysis_type": "op", "notes": "n"})
        self.assertTrue(
            any(
                "regime field 'analysis_type' is not part of this substrate's "
                "regime vocabulary" in e
                for e in errors
            )
        )

    def test_missing_notes_rejects(self):
        errors = _regime_errors({"operation": "solve"})
        self.assertIn("regime is missing 'notes'.", errors)

    def test_unknown_operation_rejects(self):
        errors = _regime_errors({"operation": "minimize", "notes": "n"})
        self.assertTrue(
            any("regime operation must be one of:" in e and "'minimize'" in e
                for e in errors)
        )

    def test_non_dict_rejects(self):
        self.assertEqual(
            _regime_errors("diff"),
            ["regime must be an object with operation and notes."],
        )


class TestReverseDirectionNgspice(unittest.TestCase):
    """Phase-1.0 ruling item 2: 'operation' joined AnalysisTypeRegime's
    alien_keys additively."""

    def test_alien_keys_extended_additively(self):
        # the pre-existing keys keep their positions; "operation" appends
        self.assertEqual(
            AnalysisTypeRegime.alien_keys,
            ("reynolds_min", "reynolds_max", "operation"),
        )

    def test_cas_shaped_block_in_ngspice_spec_rejects_by_name(self):
        errors: list[str] = []
        stage2_spec._validate_regime_analysis_type(
            {"operation": "diff", "notes": "n"}, NGSPICE_REGIME, errors
        )
        self.assertTrue(
            any(
                "regime field 'operation' is not part of this substrate's "
                "regime vocabulary" in e
                for e in errors
            )
        )
        # the missing analysis_type complaint still fires beside it
        self.assertTrue(
            any("regime is missing 'analysis_type'" in e for e in errors)
        )

    def test_reynolds_rejection_string_byte_identical(self):
        # the pre-extension rejection text for a Reynolds input, byte-equal
        # (the exact-string pins live in tests/test_r2355_regime.py; this
        # asserts the same rendering survives the additive extension).
        errors: list[str] = []
        stage2_spec._validate_regime_analysis_type(
            {"reynolds_min": 100, "reynolds_max": 200, "notes": "n"},
            NGSPICE_REGIME,
            errors,
        )
        allowed = ", ".join(NGSPICE_REGIME.analysis_types)
        for key in ("reynolds_min", "reynolds_max"):
            self.assertIn(
                f"regime field '{key}' is not part of this substrate's regime "
                f"vocabulary — this instrument's regime is not a Reynolds band; "
                f"declare 'analysis_type' (one of: {allowed}) and 'notes'.",
                errors,
            )


class TestSymbolicResultVocabRecord(unittest.TestCase):
    def test_shape_tag(self):
        self.assertEqual(SymbolicResultVocab.shape, SYMBOLIC_RESULT)

    def test_regime_has_no_default(self):
        with self.assertRaises(TypeError):
            SymbolicResultVocab()

    def test_record_is_frozen(self):
        with self.assertRaises(Exception):
            _VOCAB.regime = None

    def test_alien_keys_cover_both_grammars(self):
        self.assertEqual(
            SymbolicResultVocab.alien_keys,
            ("field", "operation", "component", "mask",
             "kind", "target", "reduction"),
        )


class TestSymbolicResultQoi(unittest.TestCase):
    PROSE = {
        "name": "definite integral value",
        "units": "dimensionless",
        "definition": "the exact value of the integral as typed",
        "how_extracted": "the wrapper's verified symbolic result",
    }

    def test_prose_only_qoi_passes(self):
        self.assertEqual(_qoi_errors(dict(self.PROSE)), [])

    def test_field_reduction_machine_keys_reject_by_name(self):
        qoi = dict(self.PROSE, field="U", operation="volAverage")
        errors = _qoi_errors(qoi)
        self.assertTrue(
            any("'field'" in e and "different substrate class's QoI grammar" in e
                for e in errors)
        )
        self.assertTrue(any("'operation'" in e for e in errors))

    def test_named_quantity_machine_keys_reject_by_name(self):
        qoi = dict(self.PROSE, kind="node_voltage", target="out", reduction="op_value")
        errors = _qoi_errors(qoi)
        for key in ("'kind'", "'target'", "'reduction'"):
            self.assertTrue(any(key in e for e in errors), key)

    def test_list_qoi_still_rejected_by_common_path(self):
        errors = _qoi_errors([dict(self.PROSE)])
        self.assertTrue(any("never a list" in e for e in errors))


class TestRunEntryQoiExpression(unittest.TestCase):
    """schemas widening (Phase-1.0 ruling item 4): additive, one-of-three."""

    def entry_errors(self, entry):
        errors: list[str] = []
        schemas._check_execution_run_entry(entry, "runs[0]", errors)
        return errors

    def test_expression_entry_validates(self):
        self.assertEqual(
            self.entry_errors(
                {"converged": True, "wall_clock_s": 1.2,
                 "qoi_expression": "pi/2", "state": "solved_verified"}
            ),
            [],
        )

    def test_pre_existing_shapes_accepted_unchanged(self):
        # the locked Step-15 shapes, byte-identical acceptance
        self.assertEqual(
            self.entry_errors(
                {"converged": True, "wall_clock_s": 3.0, "qoi_value": 0.42}
            ),
            [],
        )
        self.assertEqual(
            self.entry_errors(
                {"converged": False, "wall_clock_s": 3.0, "qoi_error": "boom"}
            ),
            [],
        )

    def test_exactly_one_of_three_none_present(self):
        errors = self.entry_errors({"converged": True, "wall_clock_s": 1.0})
        self.assertTrue(
            any("exactly one of qoi_value, qoi_error, or qoi_expression" in e
                and "none of them" in e for e in errors)
        )

    def test_exactly_one_of_three_two_present(self):
        errors = self.entry_errors(
            {"converged": True, "wall_clock_s": 1.0,
             "qoi_value": 1.0, "qoi_expression": "pi"}
        )
        self.assertTrue(
            any("exactly one of qoi_value, qoi_error, or qoi_expression" in e
                for e in errors)
        )

    def test_empty_expression_rejects(self):
        errors = self.entry_errors(
            {"converged": True, "wall_clock_s": 1.0, "qoi_expression": "  "}
        )
        self.assertTrue(
            any("qoi_expression must be a non-empty string" in e for e in errors)
        )

    def test_unknown_key_still_rejected(self):
        errors = self.entry_errors(
            {"converged": True, "wall_clock_s": 1.0, "qoi_value": 1.0,
             "verdict": "trust"}
        )
        self.assertTrue(any("'verdict' is not allowed" in e for e in errors))


class TestZeroByteDeltaExistingConstructors(unittest.TestCase):
    """The ruling's gate: zero byte deltas in any cavity/ngspice run entry.
    Both constructors are untouched this commit and never emit the new
    keys — asserted on canned summaries against exact expected dicts."""

    def test_cavity_entry_exact_bytes(self):
        summary = {
            "converged": True,
            "runtime": {"wall_clock_s": 7.5},
            "qoi": {"name": "volAverage(mag(U))", "value": 0.4168179},
        }
        entry = substrate_dispatch._cavity_run_entry(summary, None)
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 7.5, "qoi_value": 0.4168179},
        )
        self.assertNotIn("qoi_expression", entry)
        self.assertNotIn("state", entry)

    def test_ngspice_entry_exact_bytes(self):
        summary = {
            "valid": True, "qoi": 6.6667, "diagnostics": "op solve ok",
            "runtime_s": 0.41,
        }
        entry = substrate_dispatch.ngspice_run_entry(summary)
        self.assertEqual(
            entry,
            {"converged": True, "wall_clock_s": 0.41, "qoi_value": 6.6667},
        )
        self.assertNotIn("qoi_expression", entry)
        self.assertNotIn("state", entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
