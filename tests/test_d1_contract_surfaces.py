"""
test_d1_contract_surfaces.py — D.1 Step-0 captures (captured under era
862531b; era-of-record is now the R5 all-routable commit, owner 2026-07-17 —
the P7 feasibility-nudge fixture was RE-CAPTURED under R5 and carries every
routable contract; the P8 stage-2 pair is pinned un-moved).

ZERO live model calls: before the four `from substrates import
CAVITY_2D_CONTRACT` sites are retired to the registry (D.1), the two
composed model-visible surfaces NOT already byte-pinned by the rwin1 set
get fixtures of their own, captured from today's composition:

  P7 — generation_strategies.build_feasibility_nudge: the FEASIBILITY NUDGE
       block with no failure memo on disk (the live shape today — no
       producer writes memos) == tests/fixtures/d1/feasibility_nudge.txt.
  P8 — stage2_experiment_design.run(): the exact model-visible pair
       (system_prompt, json.dumps(stage_input)) — the only two strings
       call_stage_model hands the transport (model_call.py:294) — driven on
       a canned post-gate-1 cavity baton
       (tests/fixtures/d1/canned_stage2_input.json) ==
       tests/fixtures/d1/stage2_system_prompt.txt / stage2_user_turn.txt.
       The journal is blanked via the BLANK_MEMORY seam (journal.jsonl
       lives at an absolute path beside memory/journal.py, so a throwaway
       cwd alone does not isolate the read); runs/<id>/ writes land in a
       throwaway cwd, same harness pattern as tests/test_d0_stage5_input.py.

call_stage_model is intercepted at stage 2's import site; the capture
raises, so no model is called and no transcript is written.

Run directly: venv/bin/python3 tests/test_d1_contract_surfaces.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton
from schemas import validate_payload_post_gate1
from stages import generation_strategies as gs
from stages import stage2_experiment_design as s2

FIX = Path(__file__).resolve().parent / "fixtures" / "d1"

# A run id no runs/ dir has ever carried: the no-memo nudge shape is the
# live surface today (read_recent_failure_memo returns None).
NUDGE_RUN_ID = "d1-no-such-run"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class _Captured(Exception):
    """Raised by the capture stub so run() stops right after assembly."""


def assemble_stage2_model_input() -> tuple[str, str]:
    """Drive the real stage-2 assembly on the canned post-gate-1 baton;
    return the exact model-visible pair (system_prompt, user_turn)."""
    baton = Baton.from_json((FIX / "canned_stage2_input.json").read_text())
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="d1_stage2_")
    try:
        os.chdir(tmp)  # run() writes runs/<id>/stage2/ relative to cwd
        with patch.dict(os.environ, {"BLANK_MEMORY": "1"}):
            with patch.object(s2, "call_stage_model", side_effect=_capture):
                try:
                    s2.run(baton)
                except _Captured:
                    pass
                else:
                    raise AssertionError(
                        "call_stage_model was never reached — assembly did not run"
                    )
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(tmp, ignore_errors=True)

    return captured["system_prompt"], json.dumps(captured["stage_input"])


class FeasibilityNudgeByteIdentity(unittest.TestCase):
    def test_no_memo_block_byte_identical_to_fixture(self):
        self.assertEqual(
            gs.build_feasibility_nudge(NUDGE_RUN_ID),
            _fixture("feasibility_nudge.txt"),
        )

    def test_block_is_deterministic(self):
        self.assertEqual(
            gs.build_feasibility_nudge(NUDGE_RUN_ID),
            gs.build_feasibility_nudge(NUDGE_RUN_ID),
        )


class Stage2InputByteIdentity(unittest.TestCase):
    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_stage2_model_input()
        self.assertEqual(user_turn, _fixture("stage2_user_turn.txt"))

    def test_system_prompt_byte_identical_to_fixture(self):
        system_prompt, _ = assemble_stage2_model_input()
        self.assertEqual(system_prompt, _fixture("stage2_system_prompt.txt"))
        # the captured prompt IS the module constant, never a pasted copy
        self.assertIs(system_prompt, s2.SYSTEM_PROMPT)

    def test_assembly_is_deterministic_on_fixed_input(self):
        self.assertEqual(
            assemble_stage2_model_input(), assemble_stage2_model_input()
        )

    def test_canned_input_is_canonical_post_gate1_shape(self):
        baton = Baton.from_json((FIX / "canned_stage2_input.json").read_text())
        self.assertEqual(validate_payload_post_gate1(baton.payload), [])

    def test_contract_entered_the_user_turn(self):
        # the substrate_contract key carries the cavity contract text — the
        # exact surface P8's import retirement must leave byte-identical
        _, user_turn = assemble_stage2_model_input()
        parsed = json.loads(user_turn)
        self.assertIn("SUBSTRATE CONTRACT: cavity_2d", parsed["substrate_contract"])
        self.assertIsNone(parsed["prior_thought"])


if __name__ == "__main__":
    unittest.main()
