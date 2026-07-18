"""
test_d1a_stage5_contract.py — D.1a: the stage-5 substrate-contract handoff.

ZERO live model calls. Drives the REAL stage-5 assembly path on the canned
cavity baton (with substrate_id swapped) and proves:

  * a NON-anchor substrate threads its OWN contract_for(...) text as the
    optional seventh key "substrate_contract" — grounding, not a bare defer;
  * the declared frozen ANCHOR (cavity) is excluded BY PROPERTY, not by name —
    no seventh key (its byte-identity is pinned separately by
    tests/test_d0_stage5_input.py, kept GREEN and unchanged);
  * the relaxed tripwire STILL FIRES (proven by firing) on a genuinely-wrong
    extra key and on a missing core key — it is opened by exactly one named key;
  * the registry anchor property: cavity True, every other substrate False, an
    unknown id raises KeyError (fail-loud, never silently non-anchor).

Run directly: venv/bin/python3 tests/test_d1a_stage5_contract.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from stages import stage5_thought_layer as s5
from tools import substrate_registry as registry

FIX = Path(__file__).resolve().parent / "fixtures" / "d0"


class _Captured(Exception):
    """Raised by the capture stub so assembly stops right after the tripwire."""


def _assemble_prompt_inputs(substrate_id: str) -> dict:
    """Drive the real stage-5 assembly on the canned baton with substrate_id
    swapped; return the exact prompt_inputs handed to the model call. Raises
    out right after assembly — no model is called, nothing is written outside
    the temp cwd."""
    raw = json.loads((FIX / "canned_stage_input.json").read_text())
    raw["payload"]["substrate_id"] = substrate_id
    baton = Baton.from_json(json.dumps(raw))
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="d1a_stage5_")
    try:
        stage4_dir = Path(tmp) / "runs" / baton.run_id / "stage4"
        stage4_dir.mkdir(parents=True)
        shutil.copyfile(
            FIX / "canned_stage4_results.json", stage4_dir / "results.json"
        )
        os.chdir(tmp)
        with patch.object(s5, "call_stage_model", side_effect=_capture):
            try:
                s5.run(baton)
            except _Captured:
                pass
            else:
                raise AssertionError(
                    "call_stage_model was never reached — assembly did not run"
                )
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    return captured["stage_input"]


def _valid_core_inputs() -> dict:
    """A minimal, JSON-serializable dict carrying exactly the six core keys —
    enough to pass the tripwire's presence checks."""
    return {k: (k if k != "stage4_summaries" else []) for k in s5.PROMPT_INPUT_KEYS}


class RegistryAnchorProperty(unittest.TestCase):
    def test_cavity_is_the_anchor(self):
        self.assertTrue(registry.is_frozen_anchor("cavity_2d_cfd"))

    def test_every_other_routable_is_not_an_anchor(self):
        for sid in registry.routable_ids():
            if sid == "cavity_2d_cfd":
                continue
            self.assertFalse(
                registry.is_frozen_anchor(sid), f"{sid} must not be an anchor"
            )

    def test_unknown_id_raises_not_silently_non_anchor(self):
        with self.assertRaises(KeyError):
            registry.is_frozen_anchor("no_such_substrate")


class Stage5ContractThreading(unittest.TestCase):
    def test_non_anchor_threads_its_own_contract(self):
        inputs = _assemble_prompt_inputs("ngspice_linear_passive")
        self.assertIn(s5.CONTRACT_KEY, inputs)
        self.assertEqual(
            inputs[s5.CONTRACT_KEY],
            registry.contract_for("ngspice_linear_passive"),
        )
        # the six core keys are all still present alongside the seventh
        for key in s5.PROMPT_INPUT_KEYS:
            self.assertIn(key, inputs)
        self.assertEqual(
            sorted(inputs), sorted((*s5.PROMPT_INPUT_KEYS, s5.CONTRACT_KEY))
        )

    def test_anchor_is_excluded_by_property(self):
        inputs = _assemble_prompt_inputs("cavity_2d_cfd")
        self.assertNotIn(s5.CONTRACT_KEY, inputs)
        self.assertEqual(sorted(inputs), sorted(s5.PROMPT_INPUT_KEYS))


class Stage5TripwireStillFires(unittest.TestCase):
    def test_optional_contract_is_allowed_through(self):
        inputs = _valid_core_inputs()
        inputs[s5.CONTRACT_KEY] = "SOME CONTRACT TEXT"
        # patched model call proves the tripwire PASSED (control reached it)
        with patch.object(s5, "call_stage_model", side_effect=_Captured):
            with self.assertRaises(_Captured):
                s5.run_thought_model(inputs)

    def test_extra_key_fires_the_tripwire(self):
        inputs = _valid_core_inputs()
        inputs["bogus_seventh"] = 1
        with self.assertRaises(RuntimeError) as ctx:
            s5.run_thought_model(inputs)
        self.assertIn("ANSWER KEY LEAK", str(ctx.exception))

    def test_missing_core_key_fires_the_tripwire(self):
        inputs = _valid_core_inputs()
        del inputs["experiment_spec"]
        with self.assertRaises(RuntimeError) as ctx:
            s5.run_thought_model(inputs)
        self.assertIn("ANSWER KEY LEAK", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
