"""pi_agent/free_director.py — free_investigate(): the free director's research
cycle, with a divided budget and an open action space.

This is pi_agent/loop.py's investigate() freed. investigate() runs a flat arc of
four-verb moves under an integer max_moves. free_investigate() runs the same
read→decide→act→record cycle, but the decision comes from the OPEN action space
(pi_agent/free_decider.py) and the ceiling is a Budget (pi_agent/budget.py) that
DIVIDES down a tree — so a spawn_sub_investigation can carve a child a slice that
provably cannot overrun the whole. Built ALONGSIDE investigate() (R-FD-1); the enum
loop is untouched and stays the default until this path is live-validated.

THE CYCLE.
    create the study
    loop:
        if the budget is spent            -> stop (budget_spent)
        if the decision cap is hit        -> stop (decision_cap)  [no-op backstop]
        decide an action (a FULL model turn over the arc + budget) -> or stop
        execute it, spending/allocating budget, and record it in the arc
    write the report

TWO INDEPENDENT TERMINATION BACKSTOPS. The budget bounds real work (every
run_experiment spends a move; a spawn allocates moves to a child). But a director
that only ever picks a not-yet-wired capability spends nothing, so a decision cap —
generous, derived from the budget — bounds total loop turns as a second guarantee,
exactly as budget.max_depth backstops recursion. Neither can be exceeded.

CAPABILITY WIRING. run_experiment, call_integration, and stop are handled in the
loop (call_integration dispatches a joint-verification experiment that assembles the
arc's verified parts — Phase 5). Other non-experiment actions route to
`execute_capability` (default pi_agent.capabilities.execute): call_ideation /
call_validation / call_data_analysis (Phase 3), spawn_sub_investigation, read_memory
and write_memory (Phase 4 / R-FD-5) are ALL LIVE. spawn recurses into a child
free_investigate on a carved budget slice, and only the child's VERIFIED findings
bubble up (the measurement boundary holds at every depth). Nothing is ever faked or
silently dropped.

No measurement is touched here. This layer chooses actions and reads their recorded
outcomes; the sealed execution path and sealed judges are unreachable from it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional

from pi_agent.budget import Budget
from pi_agent.dispatch import Move, MoveResult, MoveType
from pi_agent.loop import _cost_snapshot, _sum_runs_spend  # identical cost accounting
from pi_agent.study import STUDIES_ROOT, create_study, record_move, study_findings


def _move_from_action(action: dict, study: Any) -> Move:
    """Build the dispatchable Move from a run_experiment action. A campaign flag
    selects the iterated sweep; a named instrument narrows the run to it (else the
    run chooses from the study's permitted set)."""
    instrument = action.get("instrument")
    mtype = MoveType.CAMPAIGN if action.get("campaign") else MoveType.SINGLE
    return Move(
        type=mtype,
        domain=action["domain"],
        mode=study.mode,
        allowed_substrates=[instrument] if instrument else None,
    )


def _record_capability(study: Any, action_name: str, seq: int, result: dict, finding: str) -> None:
    """Record a non-experiment action to the arc via the same record_move path the
    runs use, so the next decision reads it uniformly. Wrapped as a MoveResult
    whose move_type is the action and whose raw carries the capability result (no
    findings, no cost — nothing measured)."""
    record_move(
        study,
        MoveResult(
            move_type=action_name,
            run_id=f"{study.study_id}-cap{seq}",
            succeeded=bool(result.get("succeeded")),
            outcome=result.get("outcome"),
            raw=result,
        ),
        finding=finding,
    )


def _integration_context(study: Any) -> dict:
    """What an integration check has to compose: the VERIFIED scalar findings across
    the arc (parts) AND the reproduced reusable FILE artifacts (files), including
    those bubbled up from sub-investigations. A part that did not reproduce is not
    something to build an assembly on, so only verified ones count (the measurement
    boundary: an integration composes re-run numbers and re-runnable file
    producers, never narration or stored bytes)."""
    parts, files, seen = [], [], set()
    for entry in study_findings(study):
        for f in entry.get("results", []) or []:
            if isinstance(f, dict) and f.get("verified"):
                parts.append({"label": f.get("label"), "value": f.get("value"),
                              "from": entry.get("run_id")})
        for ra in entry.get("reusable_artifacts", []) or []:
            if isinstance(ra, dict) and ra.get("name") and ra["name"] not in seen:
                seen.add(ra["name"])
                files.append({"name": ra["name"], "producer": ra.get("producer")})
    return {"parts": parts, "files": files}


def _integration_domain(goal: str, detail: Optional[str], context: dict) -> str:
    """Frame the integration experiment. The verified parts and the reproducible
    file PRODUCERS travel in the question so the run's experimenter authors a probe
    that ASSEMBLES them — inlining each producer to regenerate the file (never a
    stored copy) — and the wall verifies the joint number, which stands only if the
    parts are actually compatible together, not merely each valid alone."""
    crit = f" Joint criterion: {detail}." if detail else ""
    parts = "; ".join(f"{p['label']}={p['value']}" for p in context["parts"])
    lines = [
        f"Integration check for the goal: {goal}.{crit}",
        f"Independently-verified subsystem results: {parts}." if parts else "",
    ]
    if context["files"]:
        producers = json.dumps([
            {"name": f["name"], "producer": f["producer"]} for f in context["files"]
        ])
        lines.append(
            "Reusable FILES from the sub-investigations, each as a re-runnable "
            "producer you should INLINE as a step (regenerate the file, never assume "
            f"a stored copy): {producers}."
        )
    lines.append(
        "Author a probe that ASSEMBLES these parts (and files) and measures whether "
        "they compose into a working whole — a joint quantity that stands only if "
        "the parts are compatible together, not merely each valid alone. Report the "
        "joint measurement and whether the assembly meets the goal."
    )
    return " ".join(line for line in lines if line)


def _decision_cap(budget: Budget, override: Optional[int]) -> int:
    """The backstop on total loop turns. Generous vs the budget so real work is
    never starved, but finite so a director looping on unwired capabilities cannot
    spin forever. Derived from the budget's initial total."""
    if override is not None:
        return override
    total = budget.report()["total_at_node"]
    return total * 3 + 10


def free_investigate(
    goal: str,
    *,
    budget: Budget,
    allowed_substrates: Optional[list] = None,
    mode: str = "auto",
    ceiling: Optional[dict] = None,
    study_id: Optional[str] = None,
    parent_study_id: Optional[str] = None,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = Path("runs"),
    max_decisions: Optional[int] = None,
    decide_action: Callable = None,
    run_move: Callable = None,
    execute_capability: Callable = None,
) -> dict:
    """Run one free-director investigation to completion and return its report.

    `budget` is the Budget (Phase 1) — the hard, divisible ceiling. `decide_action`
    (default pi_agent.free_decider.decide_action) is the open-action-space model
    brain; `run_move` (default pi_agent.study.run_study_move) dispatches and records
    an experiment; `execute_capability` (default _unwired_capability) runs the
    non-experiment actions — all injected so the whole loop is exercisable offline
    with fakes and the real path is proven with only the model transport faked.

    Returns a report dict (also written to studies/<id>/report.json).
    """
    if decide_action is None:
        from pi_agent.free_decider import decide_action as decide_action
    if run_move is None:
        from pi_agent.study import run_study_move as run_move
    if execute_capability is None:
        from pi_agent.capabilities import execute as execute_capability

    study = create_study(
        goal,
        allowed_substrates=allowed_substrates,
        mode=mode,
        study_id=study_id,
        studies_root=studies_root,
        parent_study_id=parent_study_id,
    )
    spend_start = _cost_snapshot()
    cap = _decision_cap(budget, max_decisions)

    termination = None
    decisions = 0
    while True:
        arc = study_findings(study)

        if budget.remaining() <= 0:
            termination = {
                "reason": "budget_spent",
                "detail": f"the move budget is spent ({budget.report()})",
            }
            break
        if decisions >= cap:
            termination = {
                "reason": "decision_cap",
                "detail": f"the decision backstop of {cap} turns was reached — "
                "the director made no further progress (likely looping on an "
                "unwired capability).",
            }
            break

        decisions += 1
        try:
            action = decide_action(study, arc, budget.report())
        except Exception as e:  # noqa: BLE001 — a decider failure ends honestly
            termination = {
                "reason": "director_failed",
                "detail": f"the free director could not produce a decision: {type(e).__name__}: {e}",
            }
            break

        name = action.get("action")
        finding = action.get("reasoning")

        if name == "stop":
            termination = {
                "reason": "director_judged_complete",
                "detail": action.get("stop_reason"),
            }
            break

        if name == "run_experiment":
            # Guard: never start a move the budget cannot cover. If the director
            # asked for one it cannot afford, record the honest refusal and let it
            # choose again (it may still spawn/stop within a spent budget only via
            # the top-of-loop budget check next turn).
            if not budget.can_spend(1):
                _record_capability(
                    study, "run_experiment", decisions,
                    {"succeeded": False, "outcome": "insufficient_budget",
                     "detail": "no moves remain to run an experiment."},
                    finding,
                )
                continue
            budget.spend(1)
            run_move(study, _move_from_action(action, study), finding=finding, runs_root=runs_root)
            continue

        if name == "call_integration":
            # Joint verification (Phase 5): dispatch a real experiment that
            # ASSEMBLES the verified parts and measures whether they compose. The
            # parts each already re-ran (per-number verification); an integration
            # check catches what re-running each part cannot — "each locally
            # optimal, the assembly incompatible." It IS an experiment (verified by
            # the wall), so it goes through run_move and spends a move.
            context = _integration_context(study)
            if not context["parts"] and not context["files"]:
                _record_capability(
                    study, "call_integration", decisions,
                    {"succeeded": False, "outcome": "integration_nothing_to_compose",
                     "detail": "no verified findings or reusable files yet to "
                     "integrate — run experiments or sub-investigations first."},
                    finding,
                )
                continue
            if not budget.can_spend(1):
                _record_capability(
                    study, "call_integration", decisions,
                    {"succeeded": False, "outcome": "insufficient_budget",
                     "detail": "no moves remain to run an integration check."},
                    finding,
                )
                continue
            budget.spend(1)
            domain = _integration_domain(study.goal, action.get("detail"), context)
            instrument = action.get("instrument")
            run_move(
                study,
                Move(type=MoveType.SINGLE, domain=domain, mode=study.mode,
                     allowed_substrates=[instrument] if instrument else study.allowed_substrates),
                finding=finding or "integration check", runs_root=runs_root,
            )
            continue

        # call_ideation / call_validation / call_data_analysis (Phase 3, live) and
        # spawn_sub_investigation + memory (Phase 4, not-yet-wired): routed to the
        # capability executor, which spends its own budget and returns a recorded
        # result. seq (the decision count) gives each capability run a unique id.
        result = execute_capability(name, action, study, budget, decisions)
        _record_capability(study, name, decisions, result, finding)

    spend_end = _cost_snapshot()
    report = _build_report(study, budget, termination, decisions, ceiling, spend_start, spend_end)
    try:
        (study.dir / "report.json").write_text(json.dumps(report, indent=2))
    except Exception:  # noqa: BLE001 — the report value is returned regardless
        pass
    return report


def _build_report(
    study: Any,
    budget: Budget,
    termination: dict,
    decisions: int,
    ceiling: Optional[dict],
    spend_start: dict,
    spend_end: dict,
) -> dict:
    """Assemble the free investigation's report. Pure over its inputs. Counts
    experiment moves separately from total arc entries (capability actions appear
    in the arc too), and carries the final budget state so a reader sees exactly
    what was spent and allocated across the tree."""
    arc = study_findings(study)
    experiment_moves = [e for e in arc if e.get("move_type") in ("single", "campaign")]
    runs_spend = _sum_runs_spend(arc)
    decider_spend = {
        "calls": spend_end["calls"] - spend_start["calls"],
        "tokens": spend_end["tokens"] - spend_start["tokens"],
    }
    return {
        "study_id": study.study_id,
        "goal": study.goal,
        "director": "free",
        "allowed_substrates": study.allowed_substrates,
        "mode": study.mode,
        "moves_run": len(experiment_moves),
        "decisions_made": decisions,
        "ceiling": ceiling,
        "budget_final": budget.report(),
        "termination": termination,
        "arc": arc,
        "decider_spend": decider_spend,
        "runs_spend": runs_spend,
        "total_spend": {
            "calls": decider_spend["calls"] + runs_spend["calls"],
            "tokens": decider_spend["tokens"] + runs_spend["tokens"],
        },
        "spend_note": (
            "moves_run counts only experiment moves; the arc also holds capability "
            "actions. decider_spend is this process's own; runs_spend sums each "
            "experiment's persisted per-run cost. The hard ceiling is the budget "
            "(divisible across the tree); decision_cap is the no-op backstop."
        ),
    }
