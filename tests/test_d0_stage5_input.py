"""
test_d0_stage5_input.py — D.0 stage-5 model-input fixture (era 862531b).

ZERO live model calls: the one hole in the era-862531b byte-identity net was
stage 5's model-visible input — the rwin1 set (chooser, debate_judge,
full_review, ranking_judge) never pinned it, and D.5 changes stage 5's
payload. This test drives the REAL assembly path — stage5_thought_layer.run()
on a canned cavity baton (tests/fixtures/d0/canned_stage_input.json) with a
canned stage-4 results file staged into a throwaway cwd — and asserts the
exact model-visible bytes are BYTE-IDENTICAL to the captured fixtures:

  thought_user_turn.txt      == json.dumps(stage_input)   (model_call.py:294)
  thought_system_prompt.txt  == SYSTEM_PROMPT

call_stage_model is intercepted at stage 5's import site, AFTER
run_thought_model's answer-key tripwire has run; the capture raises, so no
model is called and nothing is written outside the temp dir. For cavity input
the optional D.5 key stays ABSENT — same canned input, same bytes, forever.

Run directly: venv/bin/python3 tests/test_d0_stage5_input.py
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
from schemas import validate_payload_post_stage4
from stages import stage5_thought_layer as s5

FIX = Path(__file__).resolve().parent / "fixtures" / "d0"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


class _Captured(Exception):
    """Raised by the capture stub so run() stops right after assembly."""


def assemble_model_input() -> tuple[str, str]:
    """Drive the real stage-5 assembly on the canned input; return the exact
    model-visible pair (system_prompt, user_turn) — the only two strings
    call_stage_model hands the transport (model_call.py:6, :294)."""
    baton = Baton.from_json((FIX / "canned_stage_input.json").read_text())
    captured: dict = {}

    def _capture(stage_name, system_prompt, stage_input, schema, **kwargs):
        captured["system_prompt"] = system_prompt
        captured["stage_input"] = stage_input
        raise _Captured()

    old_cwd = os.getcwd()
    tmp = tempfile.mkdtemp(prefix="d0_stage5_")
    try:
        stage4_dir = Path(tmp) / "runs" / baton.run_id / "stage4"
        stage4_dir.mkdir(parents=True)
        shutil.copyfile(
            FIX / "canned_stage4_results.json", stage4_dir / "results.json"
        )
        os.chdir(tmp)  # _load_stage4_summaries reads runs/<id>/ relative to cwd
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

    return captured["system_prompt"], json.dumps(captured["stage_input"])


class Stage5InputByteIdentity(unittest.TestCase):
    def test_user_turn_byte_identical_to_fixture(self):
        _, user_turn = assemble_model_input()
        self.assertEqual(user_turn, _fixture("thought_user_turn.txt"))

    def test_system_prompt_byte_identical_to_fixture(self):
        system_prompt, _ = assemble_model_input()
        self.assertEqual(system_prompt, _fixture("thought_system_prompt.txt"))
        # the captured prompt IS the module constant, never a pasted copy
        self.assertIs(system_prompt, s5.SYSTEM_PROMPT)

    def test_assembly_is_deterministic_on_fixed_input(self):
        self.assertEqual(assemble_model_input(), assemble_model_input())

    def test_canned_input_is_canonical_cavity_shape(self):
        # the locked post-stage-4 schema rejects extra keys everywhere,
        # including inside execution run entries — the exact guard D.5 needs
        baton = Baton.from_json((FIX / "canned_stage_input.json").read_text())
        self.assertEqual(validate_payload_post_stage4(baton.payload), [])

    def test_summaries_entered_the_user_turn(self):
        # both canned wrapper summaries made it through _load_stage4_summaries
        _, user_turn = assemble_model_input()
        parsed = json.loads(user_turn)
        self.assertEqual(sorted(parsed), sorted(s5.PROMPT_INPUT_KEYS))
        self.assertEqual(
            [s["case"] for s in parsed["stage4_summaries"]],
            ["d0-canned-cavity_run1", "d0-canned-cavity_run2"],
        )


if __name__ == "__main__":
    unittest.main()
