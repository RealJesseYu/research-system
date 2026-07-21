"""pi_agent — the PI (principal-investigator) control layer.

NOT to be confused with tools/pi_gate.py, which is the Buckingham-π
dimensional-analysis report. "PI" here is the researcher that will sit on top
of the pipeline and drive it: digest a goal, form hypotheses, pick a move, read
what came back, decide the next move, and stop when the study's budget is spent.

This package is being built in pieces:
  - dispatch.py (this chunk) — the WIRING that lets a controller touch the
    tools: a run that is callable and returns a structured result, plus one
    uniform way to invoke each move type (single / campaign / chain).
  - study state, and the decision loop itself, follow in later chunks.

Nothing here is the researcher yet. This is the hands, not the mind.
"""

from pi_agent.dispatch import (
    Move,
    MoveResult,
    MoveType,
    RunResult,
    build_run_env,
    dispatch_run,
    invoke_move,
    read_run_result,
)

__all__ = [
    "Move",
    "MoveResult",
    "MoveType",
    "RunResult",
    "build_run_env",
    "dispatch_run",
    "invoke_move",
    "read_run_result",
]
