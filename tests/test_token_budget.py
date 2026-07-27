"""test_token_budget.py — the director's ceiling is tokens, not moves.

WHY. Measured across a day of real studies: a 2-move study cost 55M tokens while
a 4-move one cost 15.9M. One `call_stage_model` to the experimenter is a single
"move" and runs an agentic loop of up to 200 turns, so a move count is close to
noise as a cost signal. --max-moves was bounding the wrong quantity.

The move pool stays — it is the STRUCTURAL guarantee (termination, and the
divisible slice a spawn carves for its child). The token budget is what the
director actually reasons about: it sees tokens_remaining every turn and decides
how many phases to run, whether to decompose, and whether to call ideation quick
or full.

Offline; no model calls.

Run directly: venv/bin/python3 tests/test_token_budget.py
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pi_agent.free_director as FD  # noqa: E402
from pi_agent.budget import Budget  # noqa: E402
from pi_agent.free_director import free_investigate  # noqa: E402


def _act(action, **over):
    base = {"ack": "s", "reading": "r", "reasoning": "because", "action": action,
            "domain": "q", "instrument": None, "campaign": False,
            "budget_moves": None, "detail": "d", "depth": None, "stop_reason": None}
    base.update(over)
    return base


class TokenBudgetTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class TestTheBudgetViewShownToTheDirector(unittest.TestCase):
    def test_without_a_token_budget_the_view_is_the_move_pool_as_before(self):
        v = FD._budget_view(Budget(6), 0, None)
        self.assertEqual(v["remaining"], 6)
        self.assertNotIn("token_budget", v)
        self.assertNotIn("tokens_remaining", v)

    def test_with_one_the_director_sees_what_it_has_left(self):
        v = FD._budget_view(Budget(6), 12_000_000, 50_000_000)
        self.assertEqual(v["tokens_spent"], 12_000_000)
        self.assertEqual(v["tokens_remaining"], 38_000_000)
        self.assertEqual(v["fraction_of_token_budget_used"], 0.24)
        self.assertIn("REAL ceiling", v["note"])

    def test_overspend_reports_zero_remaining_not_a_negative(self):
        v = FD._budget_view(Budget(6), 60_000_000, 50_000_000)
        self.assertEqual(v["tokens_remaining"], 0)

    def test_the_move_pool_is_still_reported(self):
        """It remains the structural guarantee: termination, and the slice a
        spawn carves for a child."""
        v = FD._budget_view(Budget(6), 1, 10)
        for k in ("depth", "max_depth", "remaining", "spent_here",
                  "allocated_to_children", "total_at_node"):
            self.assertIn(k, v)


class TestTheLoopStopsOnTokens(TokenBudgetTestCase):
    def test_an_exhausted_token_budget_ends_the_arc_honestly(self):
        def decide(study, arc, budget):     # would run forever if not stopped
            return _act("run_experiment")

        FD._tokens_spent = lambda arc, start: 99_000_000   # pretend we overspent
        try:
            report = free_investigate(
                "g", budget=Budget(6), studies_root=self.root, study_id="s",
                decide_action=decide, run_move=lambda *a, **k: None,
                token_budget=50_000_000)
        finally:
            import importlib
            importlib.reload(FD)
        self.assertEqual(report["termination"]["reason"], "token_budget_spent")
        self.assertIn("structural backstop", report["termination"]["detail"])
        self.assertEqual(report["moves_run"], 0)   # stopped before spending a move


class TestNoTokenBudgetIsUnchanged(TokenBudgetTestCase):
    def test_omitting_it_behaves_exactly_as_before(self):
        report = free_investigate(
            "g", budget=Budget(6), studies_root=self.root, study_id="s",
            decide_action=lambda *a: _act("stop", stop_reason="done"),
            run_move=lambda *a, **k: None)
        self.assertEqual(report["termination"]["reason"], "director_judged_complete")


class TestThePromptTeachesSpending(unittest.TestCase):
    def test_the_director_is_told_tokens_are_the_ceiling(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("YOUR BUDGET IS TOKENS", p)
        self.assertIn("tokens_remaining", p)

    def test_it_is_told_moves_are_a_poor_cost_signal(self):
        """The measured fact that motivated the whole change."""
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("a two-move study has cost more than a four-move one", p)

    def test_it_is_told_to_land_the_arc_rather_than_run_dry(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("land the investigation cleanly before you run out", p)

    def test_depth_and_decomposition_are_named_as_purchases(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("Depth and thoroughness are things you buy", p)


class TestBreadthIsBought(unittest.TestCase):
    """Revised #15. Scaling the pool with a fixed env knob was the wrong shape
    once the director spends a token budget it can see: breadth should be
    something it BUYS, like ideation depth — a large pool when the ideas are the
    deliverable and it can afford the reviews, a small one when it just needs a
    direction to test."""

    def setUp(self):
        import stages.generation_strategies as g
        g.set_pool_size(None)

    def tearDown(self):
        import stages.generation_strategies as g
        g.set_pool_size(None)

    def test_no_request_leaves_the_module_defaults(self):
        import stages.generation_strategies as g
        self.assertEqual(g.pool_size("literature"), g.LITERATURE_HYPOTHESIS_COUNT)

    def test_a_requested_total_scales_the_three_strategies(self):
        import stages.generation_strategies as g
        g.set_pool_size(90)
        total = (g.pool_size("literature") + g.pool_size("assumptions")
                 + g.pool_size("expansion"))
        self.assertAlmostEqual(total, 90, delta=2)   # rounding across three splits

    def test_a_small_request_still_leaves_every_strategy_alive(self):
        """A strategy rounded to zero would silently drop a whole generation
        angle from the pool."""
        import stages.generation_strategies as g
        g.set_pool_size(3)
        for k in ("literature", "assumptions", "expansion"):
            self.assertGreaterEqual(g.pool_size(k), 1)

    def test_an_absurd_request_is_clamped_not_obeyed(self):
        """A director asking for a thousand would stall the run in review."""
        import stages.generation_strategies as g
        g.set_pool_size(100000)
        total = (g.pool_size("literature") + g.pool_size("assumptions")
                 + g.pool_size("expansion"))
        self.assertLessEqual(total, g.MAX_POOL + 2)

    def test_junk_is_ignored_rather_than_raising(self):
        import stages.generation_strategies as g
        for junk in ("many", None, 3.7, [10]):
            g.set_pool_size(junk)          # must not raise
        g.set_pool_size(None)
        self.assertEqual(g.pool_size("literature"), g.LITERATURE_HYPOTHESIS_COUNT)

    def test_the_validator_accepts_pool_size_only_on_ideation(self):
        from pi_agent import free_decider
        base = {"ack": "s", "reading": "r", "reasoning": "why",
                "action": "call_ideation", "domain": None, "instrument": None,
                "campaign": False, "budget_moves": None, "detail": "ideas",
                "depth": None, "pool_size": 60, "stop_reason": None}
        v = free_decider.make_action_validator("s", 1, ("rdkit",))
        self.assertEqual(v(base), [])
        wrong = dict(base, action="run_experiment", domain="q", detail=None)
        self.assertTrue(any("pool_size must be null" in e for e in v(wrong)))
        bad = dict(base, pool_size=0)
        self.assertTrue(any("positive integer" in e for e in v(bad)))

    def test_the_prompt_frames_breadth_as_a_purchase(self):
        from pi_agent.free_decider import SYSTEM_PROMPT as p
        self.assertIn("breadth is something you buy out of your token budget", p)
        self.assertIn("cost scales with the pool", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
