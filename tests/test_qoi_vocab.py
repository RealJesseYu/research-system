"""
test_qoi_vocab.py — D.3 Steps 2-4 proofs. Call-free: no model calls, no
network, no containers. Proves:

  (1) IDENTITY CHAIN (the contract-registry precedent,
      tests/test_contract_registry.py): the production cavity record's
      members ARE tools/run_cfd.py's objects — assertIs, never a copy.
  (2) CAVITY BATTERY: a valid spec plus one spec per rejection class (bad
      operation / bad component / bad mask / bad field name) produce
      byte-identical outcomes — decision AND error string — against the
      Step-0 d3 captures (commit "D.3 step 0", recorded pre-surgery on the
      untouched tree). The expected error string is derived from each d3
      retry fixture's embedded validation_error, so the battery is pinned
      to the captures themselves, not to re-typed literals.
  (3) TWO-SHAPE PROOF on a constructed registry: a named-quantity record
      (built in THIS test from tools/run_ngspice.py's own constants — its
      single source; NOT wired in production) validates an ngspice-shaped
      QoI request and rejects field-reduction grammar; cavity's record
      rejects a named-quantity request.
  (4) FAIL-LOUD ESCAPE: a routable substrate with no wired vocabulary
      raises LookupError at lookup — never a cavity fallback; an unknown
      id raises KeyError first.

Run directly: venv/bin/python3 tests/test_qoi_vocab.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from stages.stage2_spec import validate_spec
from tools import qoi_vocab
from tools import run_cfd
from tools import run_ngspice
from tools import substrate_registry as registry
from tools.qoi_vocab import (
    FieldReductionVocab,
    NamedQuantityVocab,
    ReynoldsBandRegime,
    vocab_for,
)

D3_FIX = Path(__file__).resolve().parent / "fixtures" / "d3"

CHOSEN_ID = "hand-baseline"  # the d3 battery specs' pinned hypothesis id

# The ngspice record, constructed HERE from the wrapper's own constants —
# the tests-only wiring the D.3 design names. Promotion to production is a
# separate recorded ruling.
NGSPICE_VOCAB = NamedQuantityVocab(
    kinds=run_ngspice._QOI_KINDS,
    target_re=run_ngspice._NAME_RE,
    reductions=run_ngspice._REDUCTIONS,
    # R-23.5-5: regime semantics are a required member of every vocab
    # record. This tests-only record DELIBERATELY keeps ReynoldsBandRegime
    # (unlike the production record, which carries NGSPICE_REGIME since the
    # Phase-3 flip): its battery specs are the d3 cavity captures, whose
    # Reynolds regime blocks must validate unchanged — these tests probe
    # QoI-shape classes, not regime semantics.
    regime=ReynoldsBandRegime(),
)


def _battery_spec(cls: str) -> dict:
    """One rejection-class spec, read from the Step-0 canned reply fixture."""
    return json.loads((D3_FIX / f"reply_{cls}.json").read_text())["spec"]


def _expected_error(cls: str) -> str:
    """The pre-surgery error string for one class, derived from the Step-0
    capture: the retry surface's validation_error minus the raw-reply tail."""
    validation_error = json.loads((D3_FIX / f"retry_{cls}.txt").read_text())[
        "validation_error"
    ]
    return validation_error.split(" (raw reply: ")[0]


class TestIdentityChain(unittest.TestCase):
    def test_cavity_record_members_are_run_cfd_objects(self):
        record = vocab_for("cavity_2d_cfd")
        self.assertIsInstance(record, FieldReductionVocab)
        self.assertIs(record.operations, run_cfd.QOI_OPERATIONS)
        self.assertIs(record.components, run_cfd.QOI_COMPONENTS)
        self.assertIs(record.field_re, run_cfd._QOI_FIELD_RE)
        self.assertIs(record.mask_types, run_cfd.MASK_TYPES)


class TestCavityBattery(unittest.TestCase):
    """Byte-identical outcomes against the Step-0 captures."""

    def test_valid_spec_still_accepted(self):
        spec = json.loads((ROOT / "specs" / "handcrafted_baseline_qoi.json").read_text())
        self.assertEqual(validate_spec(spec, CHOSEN_ID, vocab_for("cavity_2d_cfd")), [])

    def _check_class(self, cls: str) -> None:
        errors = validate_spec(_battery_spec(cls), CHOSEN_ID, vocab_for("cavity_2d_cfd"))
        self.assertEqual(errors, [_expected_error(cls)])

    def test_bad_operation_byte_identical(self):
        self._check_class("bad_operation")

    def test_bad_component_byte_identical(self):
        self._check_class("bad_component")

    def test_bad_mask_byte_identical(self):
        self._check_class("bad_mask")

    def test_bad_field_byte_identical(self):
        self._check_class("bad_field")

    def test_no_default_vocab_escape_proven_by_failing(self):
        # R-23.5-5a TRUTH-EDIT (superseding the old None-defaults-to-cavity
        # equivalence test): the default is REMOVED. A call without a vocab
        # raises, and an explicit None raises — nothing resolves to cavity.
        with self.assertRaises(TypeError):
            validate_spec(_battery_spec("bad_operation"), CHOSEN_ID)
        with self.assertRaises(TypeError):
            validate_spec(_battery_spec("bad_operation"), CHOSEN_ID, None)


class TestTwoShapeProof(unittest.TestCase):
    """Each shape validates its own grammar and rejects the other's."""

    def _ngspice_shaped_spec(self) -> dict:
        spec = json.loads((ROOT / "specs" / "handcrafted_baseline_qoi.json").read_text())
        spec["qoi"] = {
            "name": "output_node_voltage",
            "units": "V",
            "definition": "The DC operating-point voltage at the output node.",
            "how_extracted": "node_voltage at 'out', reduction op_value.",
            "kind": "node_voltage",
            "target": "out",
            "reduction": "op_value",
        }
        return spec

    def test_named_record_validates_ngspice_shaped_request(self):
        errors = validate_spec(self._ngspice_shaped_spec(), CHOSEN_ID,
                               vocab=NGSPICE_VOCAB)
        self.assertEqual(errors, [])

    def test_named_record_members_are_run_ngspice_objects(self):
        self.assertIs(NGSPICE_VOCAB.kinds, run_ngspice._QOI_KINDS)
        self.assertIs(NGSPICE_VOCAB.target_re, run_ngspice._NAME_RE)
        self.assertIs(NGSPICE_VOCAB.reductions, run_ngspice._REDUCTIONS)

    def test_named_record_rejects_field_reduction_grammar(self):
        spec = json.loads((ROOT / "specs" / "handcrafted_baseline_qoi.json").read_text())
        # the handcrafted spec's qoi carries field/operation/component —
        # cavity grammar, alien to a named-quantity substrate
        errors = validate_spec(spec, CHOSEN_ID, vocab=NGSPICE_VOCAB)
        self.assertEqual(len(errors), 1)
        self.assertIn("belong to a different substrate class's QoI grammar", errors[0])
        self.assertIn("'field'", errors[0])
        self.assertIn("'operation'", errors[0])
        self.assertIn("'component'", errors[0])

    def test_cavity_record_rejects_named_quantity(self):
        errors = validate_spec(self._ngspice_shaped_spec(), CHOSEN_ID,
                               vocab=vocab_for("cavity_2d_cfd"))
        self.assertEqual(len(errors), 1)
        self.assertIn("belong to a different substrate class's QoI grammar", errors[0])
        self.assertIn("'kind'", errors[0])
        self.assertIn("'target'", errors[0])
        self.assertIn("'reduction'", errors[0])

    def test_named_record_bad_kind_and_reduction_rejected(self):
        spec = self._ngspice_shaped_spec()
        spec["qoi"]["kind"] = "branch_power"
        spec["qoi"]["reduction"] = "median"
        errors = validate_spec(spec, CHOSEN_ID, vocab=NGSPICE_VOCAB)
        self.assertEqual(len(errors), 2)
        self.assertIn("qoi kind must be one of", errors[0])
        self.assertIn("qoi reduction must be one of", errors[1])

    def test_constructed_registry_lookup_returns_named_record(self):
        # A registry with ngspice wired: vocab_for hands back the tests-only
        # record itself, keyed structurally by substrate id.
        with mock.patch.dict(
            qoi_vocab._VOCABS, {"ngspice_linear_passive": NGSPICE_VOCAB}
        ):
            self.assertIs(vocab_for("ngspice_linear_passive"), NGSPICE_VOCAB)


class TestFailLoudEscape(unittest.TestCase):
    def test_routable_substrate_without_vocab_raises_at_lookup(self):
        # A registry where a substrate has been flipped routable but no
        # vocabulary was wired: the lookup raises, never a cavity fallback.
        # Post-R2-flip ngspice IS wired, so the subject is fenicsx (enrolled,
        # unwired).
        real = registry.get("fenicsx_cantilever_elastic")
        routable_row = registry.SubstrateRecord(
            substrate_id=real.substrate_id, wrapper=real.wrapper,
            card_path=real.card_path, maturity=real.maturity,
            routable=True, cost_tier=real.cost_tier, notes=real.notes,
        )
        with mock.patch.object(registry, "get", return_value=routable_row):
            with self.assertRaises(LookupError) as ctx:
                vocab_for("fenicsx_cantilever_elastic")
        self.assertIn("no QoI vocabulary wired", str(ctx.exception))
        self.assertIn("routable=True", str(ctx.exception))

    def test_enrolled_unwired_substrate_raises_lookup_error(self):
        # fenicsx: enrolled, unwired (ngspice left this class at the R2 flip)
        with self.assertRaises(LookupError):
            vocab_for("fenicsx_cantilever_elastic")

    def test_unknown_substrate_raises_key_error_first(self):
        with self.assertRaises(KeyError):
            vocab_for("no_such_substrate")


if __name__ == "__main__":
    unittest.main()
