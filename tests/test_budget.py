"""Tests for pi_agent/budget.py — the recursive move budget.

The load-bearing properties (docs/free_director_plan.md, R-FD-2):
  1. CONSERVATION — the sum of moves across a whole tree of allocate()s never
     exceeds the root total; allocate transfers, it does not copy.
  2. TERMINATION — a tree can make only finitely many moves; depth is capped and
     every op strictly shrinks some pool.
  3. Honest edges — over-spend / over-allocate / depth-cap raise loudly, and the
     can_*() queries give the graceful 'no' before acting.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pi_agent.budget import (  # noqa: E402
    EST_COST_PER_MOVE_USD,
    MAX_DEPTH,
    Budget,
    BudgetError,
)


# ---- construction ---------------------------------------------------------


def test_root_starts_with_full_pool_at_depth_zero():
    b = Budget(10)
    assert b.remaining() == 10
    assert b.depth == 0
    assert b.max_depth == MAX_DEPTH


def test_negative_or_nonint_moves_raise():
    with pytest.raises(BudgetError):
        Budget(-1)
    with pytest.raises(BudgetError):
        Budget(3.5)  # type: ignore[arg-type]


def test_from_cost_cap_floors_division():
    # 47 USD / 5 USD-per-move -> 9 moves (floored; never implies more spend).
    b = Budget.from_cost_cap(47.0)
    assert b.remaining() == 9
    assert b.depth == 0


def test_est_cost_per_move_env_override():
    from pi_agent.budget import _est_cost_per_move_default

    old = os.environ.get("RESEARCH_EST_COST_PER_MOVE_USD")
    try:
        os.environ["RESEARCH_EST_COST_PER_MOVE_USD"] = "20"
        assert _est_cost_per_move_default() == 20.0
        os.environ["RESEARCH_EST_COST_PER_MOVE_USD"] = "not-a-number"
        assert _est_cost_per_move_default() == 5.0   # bad value ignored
        os.environ["RESEARCH_EST_COST_PER_MOVE_USD"] = "-3"
        assert _est_cost_per_move_default() == 5.0   # non-positive ignored
    finally:
        if old is None:
            os.environ.pop("RESEARCH_EST_COST_PER_MOVE_USD", None)
        else:
            os.environ["RESEARCH_EST_COST_PER_MOVE_USD"] = old


def test_from_cost_cap_too_small_yields_zero_moves_not_crash():
    b = Budget.from_cost_cap(EST_COST_PER_MOVE_USD / 2)
    assert b.remaining() == 0


def test_from_cost_cap_rejects_bad_inputs():
    with pytest.raises(BudgetError):
        Budget.from_cost_cap(-1.0)
    with pytest.raises(BudgetError):
        Budget.from_cost_cap(10.0, est_cost_per_move_usd=0)


# ---- spending -------------------------------------------------------------


def test_spend_shrinks_pool():
    b = Budget(5)
    b.spend(2)
    assert b.remaining() == 3
    b.spend()  # default 1
    assert b.remaining() == 2


def test_spend_beyond_pool_raises_and_leaves_pool_untouched():
    b = Budget(2)
    with pytest.raises(BudgetError):
        b.spend(3)
    assert b.remaining() == 2  # failed spend must not partially consume


def test_can_spend_matches_spend():
    b = Budget(2)
    assert b.can_spend(2)
    assert not b.can_spend(3)
    assert not b.can_spend(-1)


# ---- allocation & conservation -------------------------------------------


def test_allocate_transfers_out_of_parent_pool():
    parent = Budget(10)
    child = parent.allocate(4)
    assert parent.remaining() == 6   # 4 left the parent
    assert child.remaining() == 4    # ...and became the child's whole pool
    assert child.depth == parent.depth + 1


def test_parent_cannot_respend_allocated_moves():
    parent = Budget(10)
    parent.allocate(8)
    assert parent.remaining() == 2
    with pytest.raises(BudgetError):
        parent.spend(3)  # only 2 left; the 8 are gone to the child


def test_allocate_beyond_pool_raises():
    parent = Budget(3)
    with pytest.raises(BudgetError):
        parent.allocate(4)
    assert parent.remaining() == 3


def test_conservation_across_a_whole_tree():
    """The sum of every node's (spent + remaining) equals the root total, no
    matter how the tree is carved. This is the anti-runaway guarantee."""
    ROOT = 100
    root = Budget(ROOT)
    nodes = [root]

    # Build an uneven tree: root spends some, spawns two children; each child
    # spends and one spawns a grandchild.
    root.spend(3)
    c1 = root.allocate(40)
    c2 = root.allocate(20)
    c1.spend(5)
    g1 = c1.allocate(10)
    g1.spend(4)
    c2.spend(20)
    nodes += [c1, c2, g1]

    total_spent = sum(n.report()["spent_here"] for n in nodes)
    total_remaining = sum(n.report()["remaining"] for n in nodes)
    assert total_spent + total_remaining == ROOT


def test_report_fields_sum_to_node_total():
    b = Budget(10)
    b.spend(2)
    b.allocate(3)
    r = b.report()
    assert r["spent_here"] == 2
    assert r["allocated_to_children"] == 3
    assert r["remaining"] == 5
    assert r["total_at_node"] == 10


# ---- termination / depth backstop ----------------------------------------


def test_depth_cap_blocks_allocation_even_with_budget():
    # A node at the depth cap has budget but cannot delegate deeper.
    b = Budget(100, depth=MAX_DEPTH)
    assert not b.can_allocate(1)
    with pytest.raises(BudgetError):
        b.allocate(1)
    # ...but it may still spend its own pool on direct work.
    assert b.can_spend(1)
    b.spend(1)
    assert b.remaining() == 99


def test_can_allocate_respects_both_pool_and_depth():
    b = Budget(5, depth=MAX_DEPTH - 1)
    assert b.can_allocate(5)          # depth ok, pool ok
    assert not b.can_allocate(6)      # pool too small
    child = b.allocate(5)
    assert child.depth == MAX_DEPTH
    assert not child.can_allocate(1)  # child is now at the cap


def test_tree_makes_finitely_many_moves():
    """Directly exercise termination: greedily allocate/spend until the whole
    tree is exhausted, and assert the move count is bounded by the root total."""
    ROOT = 30
    made = 0

    def drain(b: Budget):
        nonlocal made
        # Spend one, then try to push the rest into a child; recurse. Every step
        # strictly shrinks a pool, so this must bottom out.
        while b.remaining() > 0:
            if b.can_allocate(b.remaining() - 1) and b.remaining() > 1:
                b.spend(1)
                made += 1
                child = b.allocate(b.remaining())
                drain(child)
            else:
                b.spend(1)
                made += 1

    drain(Budget(ROOT))
    assert made == ROOT  # every move accounted for, none conjured
