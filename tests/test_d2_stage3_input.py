"""
test_d2_stage3_input.py — D.2 Step-0 capture (era 862531b).

ZERO live model calls: before D.2 retires stage 3's sole_routable_id() call
to signature-based selection, the stage-3 composed model-visible surface —
NOT pinned by any rwin1/d0/d1 fixture (test_contract_registry pins only the
contract TEXT equality, never the composed pair) — gets fixtures of its own,
captured from today's composition:

  stage3_fidelity_gate.run(): the exact model-visible pair
  (system_prompt, json.dumps(stage_input)) — the only two strings
  call_stage_model hands the transport — driven on a canned post-stage-2
  cavity baton (tests/fixtures/d2/canned_stage3_input.json, built from
  specs/handcrafted_baseline_payload.json MINUS its hand-authored verdict:
  the pre-stage-3 shape) == tests/fixtures/d2/stage3_system_prompt.txt /
  stage3_user_turn.txt. The stage_input includes the contract injection
  (stage3_fidelity_gate.py run(): the substrate_contract key), so these
  fixtures pin the selection surface D.2's surgery must leave byte-identical.

call_stage_model is intercepted at stage 3's import site; the capture
raises, so no model is called, no transcript is written, and nothing after
the call (echo check, verdict.json, fidelity ledger) runs. run() performs
no disk write before the call, so no cwd sandbox is needed.

The canned spec is the handcrafted baseline (buildable-only parameters,
validate_spec == []) deliberately: it is servable by the cavity builder, so
the same fixture remains capturable after D.2's serve-ability selection.

Run directly: venv/bin/python3 tests/test_d2_stage3_input.py
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from schemas import validate_payload_post_stage2
from stages import stage3_fidelity_gate as s3

FIX = Path(__file__).resolve().parent / "fixtures" / "d2"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class _Captured(Exception):
    """Raised by the capture stub so run() stops right after assembly."""


def assemble_stage3_model_input() -> tuple[str, str]:
    """Drive the real stage-3 assembly on the canned post-stage-2 baton;
    return the exact model-visible pair (system_prompt, user_turn)."""
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


class Stage3InputByteIdentity(unittest.TestCase):
    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage3_model_input()
        self.assertEqual(user_turn, _fixture("stage3_user_turn.txt"))

    def test_system_prompt_byte_identical_to_fixture(self):
        system_prompt, _ = assemble_stage3_model_input()
        self.assertEqual(system_prompt, _fixture("stage3_system_prompt.txt"))
        # the captured prompt IS the module constant, never a pasted copy
        self.assertIs(system_prompt, s3.SYSTEM_PROMPT)

    def test_assembly_is_deterministic_on_fixed_input(self):
        self.assertEqual(
            assemble_stage3_model_input(), assemble_stage3_model_input()
        )

    def test_canned_input_is_canonical_post_stage2_shape(self):
        baton = Baton.from_json((FIX / "canned_stage3_input.json").read_text())
        self.assertEqual(validate_payload_post_stage2(baton.payload), [])

    def test_contract_entered_the_user_turn(self):
        # the substrate_contract key carries the cavity contract text — the
        # exact surface D.2's selection surgery must leave byte-identical
        _, user_turn = assemble_stage3_model_input()
        parsed = json.loads(user_turn)
        self.assertIn("SUBSTRATE CONTRACT: cavity_2d", parsed["substrate_contract"])
        self.assertEqual(parsed["run_id"], "d2-canned-cavity")


if __name__ == "__main__":
    unittest.main()
