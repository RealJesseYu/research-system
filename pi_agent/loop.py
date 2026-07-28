"""pi_agent/loop.py — investigate(): the research cycle, top to bottom.

This is where the mind drives the hands. investigate() takes a goal (and its
constraints and budget), opens a study, and then repeats the researcher's cycle:
read the arc so far, decide the next move, run it, record what came back — until
the PI judges the investigation done or the budget of experiments is spent. The
result is the study and its arc: the accumulated investigation a paper would
later be written from.

THE CYCLE, PRECISELY.
    create the study (carrying goal + constraint + mode)
    loop:
        if the move budget is spent            -> stop (move_budget_spent)
        decide (an Opus call over the arc)     -> the next move, or stop
        if the decision is stop                -> stop (pi_judged_complete)
        run the move under the study           -> recorded in the arc
    write the study report

THE HARD CEILING IS MOVES. max_moves is the guaranteed bound — the owner's
"budget of experiments" — and it holds no matter what the decider wants, because
an open-ended loop of powerful agents must not be able to run away. It is checked
BEFORE each decision, so the loop can never start a move it has no budget for.

WHY NOT A TOKEN CEILING TOO. Each move is a subprocess run (pi_agent.dispatch),
and a subprocess has its own cost meter — the supervisor writes no per-run cost
to disk, so this process cannot see what a run spent. A spend-denominated ceiling
that actually bounds the runs would need per-run cost reporting that does not
exist yet; inventing one here would be a number that does not bind. So the report
meters what it honestly can — this process's own decider spend, diffed from the
shared cost meter — and names per-run spend as not-yet-captured. The hard ceiling
is moves; a true token cap is the next piece, and it needs that plumbing first.

FAIL-GRACEFUL AT THE TOP, LOUD BELOW. A move that halts or fails verification is
NOT a loop error — it is a result the decider reads and responds to on the next
turn (that is the whole point). But if the DECIDER itself fails (the model door
raises after its bounded re-asks), the study ends honestly with the reason
recorded and the arc preserved, rather than crashing or fabricating a decision.
The loud halts inside each run are untouched: they happen in the subprocess and
surface as that move's outcome.

No measurement is ever touched here. This layer chooses runs and reads their
outcomes; the sealed execution path and sealed judges are unreachable from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pi_agent.dispatch import Move, MoveType
from pi_agent.study import (
    STUDIES_ROOT,
    create_study,
    study_findings,
)

# A conservative default so a misconfigured call cannot loop far. The caller
# sets this deliberately per investigation.
DEFAULT_MAX_MOVES = 6

_DECISION_TO_MOVE_TYPE = {
    "run_single": MoveType.SINGLE,
    "run_campaign": MoveType.CAMPAIGN,
}


def _cost_snapshot() -> dict:
    """This process's model spend right now: {calls, tokens}. Best-effort — the
    meter is a shared module global, so this is diffed against a start snapshot
    to attribute the loop's own (decider) spend. Never raises."""
    try:
        import cost_meter

        snap = cost_meter.read()
        calls = snap.get("model_calls", {}).get("total", 0)
        tokens = sum(v for v in snap.get("tokens", {}).get("total", {}).values() if isinstance(v, int))
        return {"calls": calls, "tokens": tokens}
    except Exception:  # noqa: BLE001
        return {"calls": 0, "tokens": 0}


def _move_from_decision(decision: dict, study: Any) -> Move:
    """Build the dispatchable Move from a validated decision. The decider only
    emits run_single / run_campaign; a stop never reaches here.

    When the PI named an instrument, the move is narrowed to it (a one-element
    allow-set) — run_study_move enforces that this is within the study's outer
    bound, and the run's gate-1 chooser is then forced to that instrument. A
    null instrument leaves the move unconstrained beyond the study, so the run
    chooses for itself from the permitted set."""
    mtype = _DECISION_TO_MOVE_TYPE[decision["decision"]]
    instrument = decision.get("instrument")
    return Move(
        type=mtype,
        domain=decision["next_domain"],
        mode=study.mode,
        allowed_substrates=[instrument] if instrument else None,
    )


def investigate(
    goal: str,
    *,
    allowed_substrates: Optional[list] = None,
    mode: str = "auto",
    max_moves: int = DEFAULT_MAX_MOVES,
    ceiling: Optional[dict] = None,
    study_id: Optional[str] = None,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = Path("runs"),
    decide: Callable = None,
    run_move: Callable = None,
    run_fan: Callable = None,
) -> dict:
    """Run one investigation to completion and return its report.

    `decide` (default pi_agent.decider.decide) makes each move choice — a real
    Opus call over the arc. `run_move` (default pi_agent.study.run_study_move)
    dispatches a chosen move and records it. Both are injected so the whole loop
    is exercisable offline with fakes, and the real path is proven with only the
    model transport faked.

    Returns a report dict (also written to studies/<id>/report.json):
    {study_id, goal, allowed_substrates, mode, moves_run, termination, arc,
     process_spend, spend_note}.
    """
    if decide is None:
        from pi_agent.decider import decide as decide
    if run_move is None:
        from pi_agent.study import run_study_move as run_move
    if run_fan is None:
        from pi_agent.study import run_study_fan as run_fan

    study = create_study(
        goal,
        allowed_substrates=allowed_substrates,
        mode=mode,
        study_id=study_id,
        studies_root=studies_root,
    )
    spend_start = _cost_snapshot()

    termination = None
    while True:
        arc = study_findings(study)
        moves_used = len(arc)

        if moves_used >= max_moves:
            termination = {
                "reason": "move_budget_spent",
                "detail": f"{moves_used}/{max_moves} moves run — the experiment budget is spent",
            }
            break

        budget = {
            "moves_used": moves_used,
            "max_moves": max_moves,
            "moves_remaining": max_moves - moves_used,
        }

        try:
            decision = decide(study, arc, budget)
        except Exception as e:  # noqa: BLE001 — see FAIL-GRACEFUL in the docstring
            termination = {
                "reason": "decider_failed",
                "detail": f"the PI decider could not produce a decision: {type(e).__name__}: {e}",
            }
            break

        if decision.get("decision") == "stop":
            termination = {
                "reason": "pi_judged_complete",
                "detail": decision.get("stop_reason"),
            }
            break

        if decision.get("decision") == "run_fan":
            # BROAD cycle: several competing sub-questions tested in parallel,
            # each its own run, all recorded before the next decision reads them.
            # Capped to the remaining move budget so a fan can never overrun the
            # hard ceiling — a fan of N spends N of the budget.
            remaining = max_moves - moves_used
            domains = [
                d for d in (decision.get("fan_domains") or [])
                if isinstance(d, str) and d.strip()
            ][:remaining]
            fan_moves = [
                Move(type=MoveType.SINGLE, domain=d, mode=study.mode)
                for d in domains
            ]
            run_fan(
                study, fan_moves,
                findings=[decision.get("rationale")] * len(fan_moves),
                runs_root=runs_root,
            )
            continue

        move = _move_from_decision(decision, study)
        # The finding recorded with the move is the PI's going-in reasoning; the
        # decider's reading of the RESULT is captured in the next decision record
        # (and the next turn re-reads the whole arc). A move that halts or fails
        # is recorded like any other — the next decision responds to it.
        run_move(study, move, finding=decision.get("rationale"), runs_root=runs_root)

    spend_end = _cost_snapshot()
    report = _build_report(study, termination, spend_start, spend_end, ceiling)
    try:
        (study.dir / "report.json").write_text(json.dumps(report, indent=2))
    except Exception:  # noqa: BLE001 — the report value is returned regardless
        pass
    return report


def _build_report(
    study: Any,
    termination: dict,
    spend_start: dict,
    spend_end: dict,
    ceiling: Optional[dict] = None,
) -> dict:
    """Assemble the investigation's report. Pure over its inputs. `ceiling` is the
    provenance of the human-set bound (R-FD-2: max_moves vs a cost-cap-derived
    ceiling); recorded verbatim so a reader sees exactly what was set."""
    arc = study_findings(study)
    runs_spend = _sum_runs_spend(arc)
    # RENAMED from decider_spend (2026-07-28, roadmap item 1): the meter is
    # process-global, so this delta is everything THIS process spent during the
    # investigation, not only the PI's decisions. For this enum loop the two
    # coincide (moves are subprocesses and nothing else calls a model in
    # process), but the honest name is the process one.
    process_spend = {
        "calls": spend_end["calls"] - spend_start["calls"],
        "tokens": spend_end["tokens"] - spend_start["tokens"],
    }
    return {
        "study_id": study.study_id,
        "goal": study.goal,
        "allowed_substrates": study.allowed_substrates,
        "mode": study.mode,
        "moves_run": len(arc),
        "ceiling": ceiling,
        "termination": termination,
        "arc": arc,
        "process_spend": process_spend,
        "runs_spend": runs_spend,
        "total_spend": {
            "calls": process_spend["calls"] + runs_spend["calls"],
            "tokens": process_spend["tokens"] + runs_spend["tokens"],
        },
        "spend_note": (
            "process_spend is THIS process's model spend over the investigation "
            "(for this loop, the PI's decisions — renamed from decider_spend "
            "2026-07-28). runs_spend is summed from each move's persisted "
            "per-run cost. moves_with_cost/moves_run shows coverage — a move "
            "whose run left no record contributes no cost and is not counted. "
            "The hard budget is still max_moves; real cost-cap enforcement can "
            "now read runs_spend against the ceiling."
        ),
    }


def _sum_runs_spend(arc: list) -> dict:
    """Total model spend across the arc's moves, from each move's persisted
    per-run cost. Pure and defensive: a move with no cost (a run that left no
    record) simply contributes nothing and is not counted toward coverage."""
    calls = tokens = covered = 0
    for entry in arc:
        cost = entry.get("cost") if isinstance(entry, dict) else None
        if isinstance(cost, dict):
            c = cost.get("calls")
            t = cost.get("tokens")
            if isinstance(c, int) or isinstance(t, int):
                covered += 1
            calls += c if isinstance(c, int) else 0
            tokens += t if isinstance(t, int) else 0
    return {
        "calls": calls,
        "tokens": tokens,
        "moves_with_cost": covered,
        "moves_run": len(arc),
    }
