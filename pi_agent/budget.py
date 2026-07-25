"""pi_agent/budget.py — a finite move budget that DIVIDES down a tree of
investigations and provably terminates.

THE PROBLEM THIS SOLVES. The free director (docs/free_director_plan.md) makes the
director recursive: a director may spawn a SUB-investigation, which is itself a
director that may spawn its own. Freedom in *what* to investigate is the whole
point — but unbounded recursion under a walk-away regime is the runaway-cost and
infinite-decompose hazard. The one guarantee the loop has today is `max_moves`
(pi_agent/loop.py). This module extends that single flat ceiling into a ceiling
that holds over a whole TREE.

THE INVARIANT (why the tree is provably finite). A Budget owns a pool of moves.
There are exactly two ways to consume from the pool, and BOTH strictly shrink it;
nothing ever grows it:

  - spend(n)      — consume n moves for THIS level's own work (running a probe).
  - allocate(k)   — TRANSFER k moves out of this pool into a fresh child Budget
                    (depth + 1). The k moves leave the parent's pool and become the
                    child's whole pool; the parent can never spend them again.

Because allocate transfers rather than copies, the sum of moves across the entire
tree is conserved: it is exactly the root total, partitioned among the nodes. No
subtree can exceed the slice it was handed, and the grand total can never exceed
what the human set at the root. Termination follows from three facts together:
(1) the root total is finite; (2) every spend/allocate strictly decreases some
node's pool and nothing increases any pool; (3) depth is hard-capped at max_depth
as an independent backstop. So the number of moves the whole tree can ever make is
bounded, and the recursion cannot run forever.

THIS MODULE IS PURE. No model call, no I/O, no clock — a plain accounting object,
unit-tested. R-FD-2 (docs/free_director_plan.md): moves are the enforced unit; a
cost-cap is converted to a move ceiling at the root by from_cost_cap(), and real
mid-run cost enforcement waits on per-run cost reporting (a later Phase-1 task).
"""

from __future__ import annotations

import os

# Independent recursion backstop: even with budget to spare, the decomposition
# tree may not go deeper than this. Belt-and-suspenders beside budget exhaustion.
# Depth 0 is the root director; 5 allows root -> subsystem -> sub-component -> a
# little headroom, well past what any planned decomposition needs. Raise only on
# evidence a real study wants a deeper tree (tested-first, no gold-plating).
MAX_DEPTH = 5

# R-FD-2: when the human sets a spend cap instead of a move count, the root
# derives a move ceiling from this estimate. Deliberately conservative (an
# over-estimate spends FEWER moves — it never overshoots the cap). This is a
# derived ceiling only; real spend enforcement needs per-run cost reporting and
# is a separate task. Units are USD-per-move. The default is a placeholder;
# set RESEARCH_EST_COST_PER_MOVE_USD before launch to your measured per-move cost
# (moves are experiments + heavy tool calls) so a --cost-cap derives real moves.
# A non-numeric or non-positive env value is ignored in favour of the default.
def _est_cost_per_move_default() -> float:
    raw = os.environ.get("RESEARCH_EST_COST_PER_MOVE_USD")
    try:
        val = float(raw)
        return val if val > 0 else 5.0
    except (TypeError, ValueError):
        return 5.0


EST_COST_PER_MOVE_USD = _est_cost_per_move_default()


class BudgetError(Exception):
    """Raised on an impossible budget request — a negative amount, or an
    allocate/spend the pool cannot cover. A caller that wants a graceful 'no'
    should ask can_spend()/can_allocate() first; this is the loud path for a
    request that violated the accounting."""


class Budget:
    """A node's share of the tree's finite move pool.

    Construct the ROOT with a move total (or via from_cost_cap). Hand a child its
    slice with allocate(). Query before acting with can_spend()/can_allocate(),
    or act and let an over-request raise BudgetError.
    """

    __slots__ = ("_pool", "depth", "max_depth", "_spent", "_allocated")

    def __init__(self, moves: int, *, depth: int = 0, max_depth: int = MAX_DEPTH):
        if not isinstance(moves, int):
            raise BudgetError(f"moves must be an int, got {type(moves).__name__}")
        if moves < 0:
            raise BudgetError(f"moves must be >= 0, got {moves}")
        if depth < 0:
            raise BudgetError(f"depth must be >= 0, got {depth}")
        # _pool is the moves still available at THIS node (not yet spent here nor
        # transferred to a child). _spent and _allocated are cumulative tallies
        # kept only for honest reporting; the pool is the source of truth.
        self._pool = moves
        self.depth = depth
        self.max_depth = max_depth
        self._spent = 0
        self._allocated = 0

    # ---- construction ----------------------------------------------------

    @classmethod
    def from_cost_cap(
        cls, cost_cap_usd: float, *, est_cost_per_move_usd: float = EST_COST_PER_MOVE_USD
    ) -> "Budget":
        """Derive a root move ceiling from a human spend cap (R-FD-2). Floors the
        division so the derived ceiling never implies more spend than the cap. A
        cap too small for even one move yields a 0-move budget — an honest 'you
        gave me no room', not a crash."""
        if cost_cap_usd < 0:
            raise BudgetError(f"cost_cap_usd must be >= 0, got {cost_cap_usd}")
        if est_cost_per_move_usd <= 0:
            raise BudgetError(
                f"est_cost_per_move_usd must be > 0, got {est_cost_per_move_usd}"
            )
        return cls(int(cost_cap_usd // est_cost_per_move_usd))

    # ---- queries ---------------------------------------------------------

    def remaining(self) -> int:
        """Moves still available at this node (spendable here or allocatable to a
        child)."""
        return self._pool

    def can_spend(self, n: int = 1) -> bool:
        return isinstance(n, int) and n >= 0 and n <= self._pool

    def can_allocate(self, k: int = 1) -> bool:
        """True iff k moves can be carved into a child AND the child's depth is
        within the recursion backstop. Depth is checked here (not at spend) so a
        node that has run out of depth can still spend its own remaining pool on
        direct work — it just cannot delegate deeper."""
        if not isinstance(k, int) or k < 0 or k > self._pool:
            return False
        return self.depth + 1 <= self.max_depth

    # ---- consumption -----------------------------------------------------

    def spend(self, n: int = 1) -> None:
        """Consume n moves for this level's own work. Raises BudgetError if the
        pool cannot cover it (guard with can_spend for the graceful path)."""
        if not isinstance(n, int) or n < 0:
            raise BudgetError(f"spend amount must be a non-negative int, got {n!r}")
        if n > self._pool:
            raise BudgetError(
                f"cannot spend {n}: only {self._pool} move(s) left at depth {self.depth}"
            )
        self._pool -= n
        self._spent += n

    def allocate(self, k: int) -> "Budget":
        """Carve k moves out of this pool into a fresh child Budget at depth+1 and
        return it. The k moves LEAVE this pool (transfer, not copy), so the tree's
        total is conserved. Raises BudgetError if the pool is too small or the
        depth backstop is hit (guard with can_allocate for the graceful path)."""
        if not isinstance(k, int) or k < 0:
            raise BudgetError(f"allocate amount must be a non-negative int, got {k!r}")
        if k > self._pool:
            raise BudgetError(
                f"cannot allocate {k}: only {self._pool} move(s) left at depth {self.depth}"
            )
        if self.depth + 1 > self.max_depth:
            raise BudgetError(
                f"cannot allocate at depth {self.depth}: child would be depth "
                f"{self.depth + 1} > max_depth {self.max_depth}"
            )
        self._pool -= k
        self._allocated += k
        return Budget(k, depth=self.depth + 1, max_depth=self.max_depth)

    # ---- reporting -------------------------------------------------------

    def report(self) -> dict:
        """A structured snapshot for the arc/record — never narration, just the
        accounting. spent + allocated + remaining sums to the moves this node was
        constructed with."""
        return {
            "depth": self.depth,
            "max_depth": self.max_depth,
            "remaining": self._pool,
            "spent_here": self._spent,
            "allocated_to_children": self._allocated,
            "total_at_node": self._pool + self._spent + self._allocated,
        }

    def __repr__(self) -> str:
        return (
            f"Budget(depth={self.depth}, remaining={self._pool}, "
            f"spent={self._spent}, allocated={self._allocated})"
        )
