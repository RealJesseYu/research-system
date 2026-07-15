"""
test_rwin1_prompts.py — the R-WIN-1 prompt-touch window (2026-07-14).

ZERO live model calls: every assertion is over the pure prompt-composition
functions and the imported contract constant. Proves hard rule (b): with all
new switches OFF, the composed prompt families are BYTE-IDENTICAL to the
fixtures captured from today's composition (tests/fixtures/rwin1/*.txt) EXCEPT
the two unconditional changes — the instrument-contract block appended to the
chooser and the full review, and the contract cost sentences — which get their
own presence/content asserts. Also proves hard rule (a): every contract block
IS the imported CAVITY_2D_CONTRACT, never a pasted copy.

Run directly: venv/bin/python3 tests/test_rwin1_prompts.py
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from substrates import CAVITY_2D_CONTRACT
from stages import gate1_chooser as gc
from stages import reflection_reviews as rr
from stages import stage1_ideation as s1
from stages import generation_strategies as gs

FIX = Path(__file__).resolve().parent / "fixtures" / "rwin1"


def _fixture(name: str) -> str:
    return (FIX / name).read_text()


# Clean env for every test: the switches must be genuinely OFF, not inherited.
_CLEAN = {
    "CRITERIA_IMPACT": "",
    "CRITERIA_ALIGNMENT": "",
    "FEASIBILITY_NUDGE": "",
}


def _clean_env():
    env = dict(os.environ)
    for k in _CLEAN:
        env.pop(k, None)
    return env


class JudgeRubricSwitches(unittest.TestCase):
    def test_off_is_byte_identical_to_fixture(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            self.assertEqual(
                s1.compose_judge_prompt(s1.RANKING_SYSTEM_PROMPT_V2),
                _fixture("ranking_judge.txt"),
            )
            self.assertEqual(
                s1.compose_judge_prompt(s1.DEBATE_JUDGE_SYSTEM_PROMPT),
                _fixture("debate_judge.txt"),
            )

    def test_impact_only(self):
        with patch.dict(os.environ, {**_clean_env(), "CRITERIA_IMPACT": "1"}, clear=True):
            out = s1.compose_judge_prompt(s1.RANKING_SYSTEM_PROMPT_V2)
        self.assertIn(s1.IMPACT_CRITERION, out)
        self.assertNotIn(s1.ALIGNMENT_CRITERION, out)
        # inserted into the judging section, before the reply spec
        self.assertLess(out.index(s1.IMPACT_CRITERION), out.index("Reply ONLY with JSON"))

    def test_alignment_only(self):
        with patch.dict(os.environ, {**_clean_env(), "CRITERIA_ALIGNMENT": "1"}, clear=True):
            out = s1.compose_judge_prompt(s1.DEBATE_JUDGE_SYSTEM_PROMPT)
        self.assertIn(s1.ALIGNMENT_CRITERION, out)
        self.assertNotIn(s1.IMPACT_CRITERION, out)

    def test_both_on(self):
        with patch.dict(
            os.environ,
            {**_clean_env(), "CRITERIA_IMPACT": "1", "CRITERIA_ALIGNMENT": "1"},
            clear=True,
        ):
            out = s1.compose_judge_prompt(s1.RANKING_SYSTEM_PROMPT_V2)
        self.assertIn(s1.IMPACT_CRITERION, out)
        self.assertIn(s1.ALIGNMENT_CRITERION, out)
        # impact precedes alignment, both before the reply spec
        self.assertLess(out.index(s1.IMPACT_CRITERION), out.index(s1.ALIGNMENT_CRITERION))
        self.assertLess(out.index(s1.ALIGNMENT_CRITERION), out.index("Reply ONLY with JSON"))


class ChooserContractGrounding(unittest.TestCase):
    def test_appends_the_imported_contract_block(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            out = gc.compose_chooser_prompt()
        base = _fixture("chooser.txt")
        # byte-identical prefix — only the unconditional block is added
        self.assertTrue(out.startswith(base))
        self.assertEqual(out, base + gc.instrument_contract_block())
        # single source of truth: body IS the imported constant, not a copy
        self.assertIn(CAVITY_2D_CONTRACT, gc.instrument_contract_block())
        self.assertIn(gc.INSTRUMENT_CONTRACT_HEADER, out)
        self.assertIn(gc.INSTRUMENT_CONTRACT_INSTRUCTION, out)


class ReflectionFullReviewGrounding(unittest.TestCase):
    def test_impact_off_is_base_plus_contract(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            out = rr.compose_full_review_prompt()
        base = _fixture("full_review.txt")
        self.assertEqual(out, base + rr.instrument_contract_block())
        self.assertNotIn(rr.IMPACT_LENS, out)
        # single source of truth
        self.assertIn(CAVITY_2D_CONTRACT, rr.instrument_contract_block())
        self.assertIn(rr.INSTRUMENT_CONTRACT_HEADER, out)
        self.assertIn(rr.INSTRUMENT_CONTRACT_INSTRUCTION, out)

    def test_impact_on_adds_lens_before_reply_spec(self):
        with patch.dict(os.environ, {**_clean_env(), "CRITERIA_IMPACT": "1"}, clear=True):
            out = rr.compose_full_review_prompt()
        self.assertIn(rr.IMPACT_LENS, out)
        self.assertLess(out.index(rr.IMPACT_LENS), out.index("Reply ONLY with JSON"))
        # contract still present and unconditional
        self.assertIn(CAVITY_2D_CONTRACT, out)


class FeasibilityNudgeSeam(unittest.TestCase):
    def test_switch_off_by_default(self):
        with patch.dict(os.environ, _clean_env(), clear=True):
            # default off -> generation inputs get no feasibility_nudge field
            self.assertFalse(gs._feasibility_nudge_on())

    def test_switch_on(self):
        with patch.dict(os.environ, {**_clean_env(), "FEASIBILITY_NUDGE": "on"}, clear=True):
            self.assertTrue(gs._feasibility_nudge_on())

    def test_block_content(self):
        # no failure memo on disk for a fresh run id -> block is header +
        # imported contract + instruction only
        block = gs.build_feasibility_nudge("rwin1-no-such-run")
        self.assertTrue(block.startswith(gs.FEASIBILITY_NUDGE_HEADER))
        self.assertIn(CAVITY_2D_CONTRACT, block)  # single source of truth
        self.assertIn(gs.FEASIBILITY_NUDGE_INSTRUCTION, block)
        self.assertNotIn("MOST RECENT FAILURE MEMO", block)

    def test_failure_memo_absent_returns_none(self):
        self.assertIsNone(gs.read_recent_failure_memo("rwin1-no-such-run"))


class ContractCostText(unittest.TestCase):
    def test_measured_range_present_stale_rate_gone(self):
        # new measured truth
        self.assertIn("2.3-4.1 ms/step", CAVITY_2D_CONTRACT)
        self.assertIn("161-175 s", CAVITY_2D_CONTRACT)
        self.assertIn("~95 s", CAVITY_2D_CONTRACT)
        self.assertIn("scales with Reynolds number", CAVITY_2D_CONTRACT)
        # the stale single-rate sentence is gone
        self.assertNotIn("run_cfd wall-clock 11.4-11.6 s", CAVITY_2D_CONTRACT)
        self.assertNotIn("two production mini-runs", CAVITY_2D_CONTRACT)


if __name__ == "__main__":
    unittest.main()
