"""
test_multiqoi_contract_schema.py — Multi-QoI build, part B (2026-07-15, R-MB-1).

ZERO live model calls. Two guarantees:

  1. CONTRACT CONTENT — the model-visible CAVITY_2D_CONTRACT now states the
     real, tested part-A capability (a VECTOR of masked reductions + a compact
     field export) and no longer claims whole-domain-/single-shot-only
     extraction; the masked-extremum honesty sentences and their measured
     numbers are present. The block reaches its consumers by IMPORT, so the
     new sentences are asserted present in what a live consumer composes too.

  2. SPEC SCHEMA — the additive optional fields (`qois` list, per-qoi `mask`)
     are present-only (control_block precedent): every real on-disk spec still
     validates unchanged, and validation fires when the new fields are present
     and malformed — both ways.

Run directly: venv/bin/python3 tests/test_multiqoi_contract_schema.py
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from substrates import CAVITY_2D_CONTRACT
from stages.stage2_spec import validate_spec
from tools.qoi_vocab import vocab_for

# R-23.5-5a: validate_spec's vocab argument is required at every call site.
CAVITY_VOCAB = vocab_for("cavity_2d_cfd")
from stages import gate1_chooser as gc


# A real, untouched on-disk spec (a stage-2 output) to prove back-compat.
_REAL_SPEC_PATH = ROOT / "runs" / "20260703T035155Z" / "stage2" / "spec.json"


class ContractContent(unittest.TestCase):
    def test_new_capability_sentences_present(self):
        c = CAVITY_2D_CONTRACT
        # VECTOR of masked reductions
        self.assertIn("VECTOR of", c)
        self.assertIn("corner_exclusion", c)
        self.assertIn("boundary_exclusion", c)
        self.assertIn("box", c)
        self.assertIn("radius_frac", c)
        self.assertIn("distance_frac", c)
        # masked results report masked/total cell counts
        self.assertIn("cells masked", c)
        # compact field export of the final state
        self.assertIn("COMPACT FIELD EXPORT", c)
        self.assertIn("cell centres", c)

    def test_masked_extremum_honesty_sentences_present(self):
        c = CAVITY_2D_CONTRACT
        # (i) a masked extremum must state its mask type + params in the spec
        self.assertIn("MUST state its mask type", c)
        # (ii) mask-insensitivity must be demonstrated, with the measured numbers
        self.assertIn("mask-insensitive", c)
        self.assertIn("-0.270", c)
        self.assertIn("-0.141", c)
        self.assertIn("Re 100", c)

    def test_whole_domain_only_claims_gone(self):
        c = CAVITY_2D_CONTRACT
        # the old single-shot / whole-domain-only framing is amended away
        self.assertNotIn("single-shot: one QoI per run", c)
        self.assertNotIn("no field sampling beyond the volume reductions", c)

    def test_consumer_sees_new_sentences_by_import(self):
        # the block a live consumer composes carries the new capability text —
        # proves it travels by IMPORT, not by a stale pasted copy.
        with patch.dict(os.environ, {}, clear=False):
            block = gc.instrument_contract_block()
        self.assertIn(CAVITY_2D_CONTRACT, block)
        self.assertIn("VECTOR of", block)
        self.assertIn("COMPACT FIELD EXPORT", block)


class SchemaBackCompat(unittest.TestCase):
    def test_real_on_disk_spec_validates_unchanged(self):
        spec = json.loads(_REAL_SPEC_PATH.read_text())
        self.assertEqual(validate_spec(spec, spec["hypothesis_id"], CAVITY_VOCAB), [])

    def _base_spec(self):
        spec = json.loads(_REAL_SPEC_PATH.read_text())
        return spec, spec["hypothesis_id"]


class SchemaFiresWhenPresent(unittest.TestCase):
    def setUp(self):
        self.spec = json.loads(_REAL_SPEC_PATH.read_text())
        self.cid = self.spec["hypothesis_id"]

    def test_valid_qois_vector_with_mask_is_clean(self):
        spec = copy.deepcopy(self.spec)
        spec["qois"] = [
            {
                "name": "interior min p",
                "units": "m^2/s^2",
                "definition": "minimum pressure with the lid corners excluded",
                "how_extracted": "corner-masked min reduction over p",
                "field": "p",
                "operation": "min",
                "mask": {"type": "corner_exclusion", "params": {"radius_frac": 0.1}},
            }
        ]
        self.assertEqual(validate_spec(spec, self.cid, CAVITY_VOCAB), [])

    def test_malformed_qois_entry_fires(self):
        spec = copy.deepcopy(self.spec)
        spec["qois"] = [
            {"field": "1bad", "operation": "nope",
             "mask": {"type": "wedge", "params": "notdict"}}
        ]
        errs = validate_spec(spec, self.cid, CAVITY_VOCAB)
        # required-field, machine-key, and mask errors all fire, all labeled qois[0]
        self.assertTrue(any("qois[0] is missing 'name'" in e for e in errs))
        self.assertTrue(any("qois[0] field must be" in e for e in errs))
        self.assertTrue(any("qois[0] operation must be one of" in e for e in errs))
        self.assertTrue(any("qois[0] mask type must be one of" in e for e in errs))
        self.assertTrue(any("qois[0] mask must carry a 'params'" in e for e in errs))

    def test_empty_qois_list_fires(self):
        spec = copy.deepcopy(self.spec)
        spec["qois"] = []
        errs = validate_spec(spec, self.cid, CAVITY_VOCAB)
        self.assertTrue(any("qois, when present, must be a non-empty list" in e for e in errs))

    def test_single_qoi_bad_mask_fires(self):
        spec = copy.deepcopy(self.spec)
        q = dict(spec.get("qoi") or {})
        q.setdefault("name", "x")
        q.setdefault("units", "x")
        q.setdefault("definition", "x")
        q.setdefault("how_extracted", "x")
        q["mask"] = {"type": "corner_exclusion"}  # missing params
        spec["qoi"] = q
        errs = validate_spec(spec, self.cid, CAVITY_VOCAB)
        self.assertTrue(any("qoi mask must carry a 'params'" in e for e in errs))

    def test_single_qoi_good_mask_is_clean_addition(self):
        # adding only a valid mask to a valid single qoi introduces no error
        spec = copy.deepcopy(self.spec)
        q = dict(spec.get("qoi") or {})
        q.setdefault("name", "x")
        q.setdefault("units", "x")
        q.setdefault("definition", "x")
        q.setdefault("how_extracted", "x")
        baseline = validate_spec(spec, self.cid, CAVITY_VOCAB)
        q["mask"] = {"type": "box",
                     "params": {"x_min": 0.1, "x_max": 0.9, "y_min": 0.1, "y_max": 0.9}}
        spec["qoi"] = q
        self.assertEqual(validate_spec(spec, self.cid, CAVITY_VOCAB), baseline)


if __name__ == "__main__":
    unittest.main()
