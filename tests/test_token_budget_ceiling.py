"""test_token_budget_ceiling.py — tokens bind, moves account (2026-07-30).

MEASURED FAILURE. Arm C (study-20260730T034915Z) was launched with 150M tokens and
--max-moves 15 and stopped at move 16 with ~37M tokens (~$48) unspent, its last
turns visibly rushing. The silent case is worse: DEFAULT_MAX_MOVES = 6, so
`--token-budget 150000000` with no --max-moves quietly bought SIX moves.

What must NOT change, and is asserted here: max_moves still exists and is still
enforced. It is the divisible unit spawn_sub_investigation allocates a child from
(budget_moves is a required decider field) and the MOVE_COST unit every capability
spends against. This demotes it from "the thing that decides how much work a token
budget buys" to a backstop.

Run directly: venv/bin/python3 tests/test_token_budget_ceiling.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.__main__ as cli  # noqa: E402
from pi_agent.loop import DEFAULT_MAX_MOVES  # noqa: E402


class TestDerivation(unittest.TestCase):
    def test_the_arm_c_budget_no_longer_buys_six_moves(self):
        moves, tokens, prov = cli._resolve_ceiling(None, None, 150_000_000)
        self.assertEqual(tokens, 150_000_000)
        self.assertEqual(moves, 75)          # 150M / 2M, generously
        self.assertGreater(moves, 15)        # what actually cut arm C off
        self.assertEqual(prov["kind"], "token_budget")
        self.assertEqual(prov["expected_binding_ceiling"], "tokens")

    def test_the_derived_ceiling_overshoots_the_measured_cost_per_move(self):
        """The point of the derivation: it must NOT be a cost estimate. Arm C's
        measured mean was 113.2M/16 = ~7.08M tokens per move, so a ceiling
        derived at 2M/move always allows more moves than the tokens can buy —
        which is exactly what makes the token meter the thing that stops it."""
        measured_mean = 113_200_000 / 16
        self.assertLess(cli.GENEROUS_TOKENS_PER_MOVE, measured_mean)
        tokens = 150_000_000
        affordable_at_measured_rate = tokens / measured_mean   # ~21
        self.assertGreater(cli._derive_moves_from_tokens(tokens),
                           affordable_at_measured_rate)

    def test_never_derives_fewer_than_the_standing_default(self):
        self.assertEqual(cli._derive_moves_from_tokens(1), DEFAULT_MAX_MOVES)
        self.assertEqual(cli._derive_moves_from_tokens(0), DEFAULT_MAX_MOVES)

    def test_a_runaway_backstop_still_exists_and_is_recorded(self):
        moves, _t, prov = cli._resolve_ceiling(None, None, 10_000_000_000)
        self.assertEqual(moves, cli.MAX_DERIVED_MOVES)
        self.assertEqual(prov["max_derived_moves"], cli.MAX_DERIVED_MOVES)


class TestMovesAreDemotedNotDeleted(unittest.TestCase):
    def test_an_explicit_max_moves_still_wins(self):
        moves, tokens, prov = cli._resolve_ceiling(15, None, 150_000_000)
        self.assertEqual(moves, 15)
        self.assertEqual(tokens, 150_000_000)
        self.assertEqual(prov["kind"], "max_moves")
        # and the report says which one is expected to stop the run
        self.assertIn("may cut the run short", prov["expected_binding_ceiling"])

    def test_no_flags_at_all_is_unchanged(self):
        moves, tokens, prov = cli._resolve_ceiling(None, None, None)
        self.assertEqual(moves, DEFAULT_MAX_MOVES)
        self.assertIsNone(tokens)
        self.assertEqual(prov, {"kind": "default", "max_moves": DEFAULT_MAX_MOVES})

    def test_move_ceiling_is_always_an_int_the_budget_can_take(self):
        from pi_agent.budget import Budget

        for tb in (None, 1, 5_000_000, 150_000_000, 10**12):
            moves, tokens, _p = cli._resolve_ceiling(None, None, tb)
            b = Budget(moves, tokens=tokens)
            self.assertEqual(b.remaining(), moves)
            self.assertEqual(b.tokens_remaining(), tokens)

    def test_a_derived_ceiling_is_still_divisible_for_a_child(self):
        """spawn_sub_investigation allocates budget_moves from this pool — the
        reason max_moves may not be deleted."""
        from pi_agent.budget import Budget

        moves, tokens, _p = cli._resolve_ceiling(None, None, 150_000_000)
        b = Budget(moves, tokens=tokens)
        child = b.allocate(4)
        self.assertEqual(child.remaining(), 4)
        self.assertEqual(b.remaining(), moves - 4)


class TestCostCap(unittest.TestCase):
    def test_cost_cap_converts_to_tokens_at_the_measured_rate(self):
        moves, tokens, prov = cli._resolve_ceiling(None, 150.0, None)
        self.assertEqual(tokens, int(150.0 / cli.USD_PER_MTOK * 1_000_000))
        self.assertEqual(moves, cli._derive_moves_from_tokens(tokens))
        self.assertEqual(prov["expected_binding_ceiling"], "tokens")

    def test_an_explicit_token_budget_can_only_tighten_a_cost_cap(self):
        _m, tokens, _p = cli._resolve_ceiling(None, 150.0, 20_000_000)
        self.assertEqual(tokens, 20_000_000)

    def test_cost_cap_with_max_moves_is_still_an_error(self):
        with self.assertRaises(SystemExit):
            cli._resolve_ceiling(3, 50.0, None)


if __name__ == "__main__":
    unittest.main()
