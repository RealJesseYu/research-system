"""
test_ngspice_stage3_birth.py — the R2-flip BIRTH FIXTURE (owner, 2026-07-17).

ZERO live model calls. ngspice's contract became model-visible at stage 3
for ngspice-routed specs at the R2 promotion flip — a NEW model-visible
surface, not an era move of an existing one, so its era record starts at
birth (the lesson of five closed gap-class instances): the composed
(system_prompt, user_turn) pair — the only two strings call_stage_model
hands the transport — is captured d2-style on a canned ngspice-servable
baton (tests/fixtures/ngspice_birth/canned_stage3_input.json, HAND-AUTHORED:
stage 2 still authors against the cavity pin until the D.1.1 selection
point lands with Step-35) and pinned byte-identical here:

  tests/fixtures/ngspice_birth/stage3_system_prompt.txt
  tests/fixtures/ngspice_birth/stage3_user_turn.txt

The capture runs on the REAL post-flip registry: selection resolves
ngspice_linear_passive from the spec's declared parameter names, and the
injected substrate_contract IS substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT
(the graduated constant), never a pasted copy. The capture stub raises so
no model is called and nothing after the call runs (the d2 mechanics).

Run directly: venv/bin/python3 tests/test_ngspice_stage3_birth.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import substrates
from baton import Baton
from stages import stage3_fidelity_gate as s3
from tools import substrate_selection as selection

FIX = Path(__file__).resolve().parent / "fixtures" / "ngspice_birth"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class _Captured(Exception):
    """Raised by the capture stub so run() stops right after assembly."""


def assemble_stage3_model_input() -> tuple[str, str]:
    """Drive the real stage-3 assembly on the canned ngspice baton against
    the REAL registry; return the exact model-visible pair."""
    baton = Baton.from_json((FIX / "canned_stage3_input.json").read_text())
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    with patch.object(s3, "call_stage_model", side_effect=_capture):
        try:
            s3.run(baton)
        except _Captured:
            pass
        else:
            raise AssertionError(
                "call_stage_model was never reached — assembly did not run"
            )

    return captured["system_prompt"], json.dumps(captured["stage_input"])


class NgspiceStage3BirthByteIdentity(unittest.TestCase):
    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage3_model_input()
        self.assertEqual(user_turn, _fixture("stage3_user_turn.txt"))

    def test_system_prompt_byte_identical_to_fixture(self):
        system_prompt, _ = assemble_stage3_model_input()
        self.assertEqual(system_prompt, _fixture("stage3_system_prompt.txt"))
        # the frozen judgment prompt is substrate-independent: the SAME
        # module constant the cavity surface uses, never a variant
        self.assertIs(system_prompt, s3.SYSTEM_PROMPT)

    def test_assembly_is_deterministic_on_fixed_input(self):
        self.assertEqual(
            assemble_stage3_model_input(), assemble_stage3_model_input()
        )

    def test_selection_resolves_ngspice_on_the_real_registry(self):
        baton = Baton.from_json((FIX / "canned_stage3_input.json").read_text())
        self.assertEqual(
            selection.select_substrate(baton.payload["experiment_spec"]),
            "ngspice_linear_passive",
        )

    def test_contract_entered_the_user_turn_and_is_the_graduated_constant(self):
        _, user_turn = assemble_stage3_model_input()
        parsed = json.loads(user_turn)
        self.assertIn(
            "SUBSTRATE CONTRACT: ngspice_linear_passive",
            parsed["substrate_contract"],
        )
        # the injected text IS the graduated substrates.py constant
        self.assertEqual(
            parsed["substrate_contract"],
            substrates.NGSPICE_LINEAR_PASSIVE_CONTRACT,
        )
        self.assertEqual(parsed["run_id"], "birth-canned-ngspice")


if __name__ == "__main__":
    unittest.main()
