"""python -m pi_agent — run the autonomous director on a goal and walk away.

Step ④.2a (docs/plan_step4_free_the_entrance.md). The free-deciding director
(pi_agent.loop.investigate) was already built and tested but had no runnable
entry — you had to call it from Python. This CLI makes a goal a command: the PI
opens a study and drives an arc of experiments under a hard --max-moves ceiling,
each move a full pipeline run, then writes studies/<id>/report.json. Every number
of record still comes from an instrument + verification inside each run — the
director never produces a measurement (that boundary lives below this layer).

Run-venue rule (absolute): launch from a plain Terminal under caffeinate, never a
builder-session background task. Example:

    caffeinate -i venv/bin/python3 -m pi_agent \\
        --goal "predict small-molecule physicochemical properties from structure" \\
        --max-moves 6
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pi_agent.budget import EST_COST_PER_MOVE_USD, Budget  # noqa: E402
from pi_agent.loop import DEFAULT_MAX_MOVES, investigate  # noqa: E402


def _resolve_ceiling(max_moves: int | None, cost_cap: float | None) -> tuple[int, dict]:
    """Turn the human's ceiling input into the enforced move bound + a provenance
    record (R-FD-2). The human sets EITHER --max-moves OR --cost-cap; moves stay
    the always-enforced unit, and a cost cap is CONVERTED to a move ceiling here
    at the boundary via the same estimate the budget object uses, so the loop
    below stays honestly moves-denominated. The provenance goes into report.json
    so a reader can see exactly which ceiling was set and how it was derived."""
    if max_moves is not None and cost_cap is not None:
        raise SystemExit(
            "error: set EITHER --max-moves OR --cost-cap, not both (a cost cap "
            "derives its own move ceiling)."
        )
    if cost_cap is not None:
        derived = Budget.from_cost_cap(cost_cap).remaining()
        if derived < 1:
            raise SystemExit(
                f"error: --cost-cap {cost_cap} is too small for even one move at "
                f"the current estimate (${EST_COST_PER_MOVE_USD:.2f}/move)."
            )
        return derived, {
            "kind": "cost_cap",
            "cost_cap_usd": cost_cap,
            "est_cost_per_move_usd": EST_COST_PER_MOVE_USD,
            "derived_max_moves": derived,
            "note": (
                "derived ceiling: --cost-cap floored by the per-move estimate. "
                "Moves are enforced; real spend enforcement waits on per-run cost "
                "reporting."
            ),
        }
    if max_moves is not None:
        return max_moves, {"kind": "max_moves", "max_moves": max_moves}
    return DEFAULT_MAX_MOVES, {"kind": "default", "max_moves": DEFAULT_MAX_MOVES}


def main(argv: list | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pi_agent",
        description="Run the autonomous PI director on a goal: it decides an arc "
        "of experiments under a hard move ceiling and writes a study report.",
    )
    parser.add_argument(
        "--goal",
        required=True,
        help="the research goal the director holds for the whole investigation",
    )
    parser.add_argument(
        "--mode",
        choices=["human", "auto"],
        default="auto",
        help="'auto' (default): the director and each run self-resolve gates — "
        "the 'walk away' mode. 'human': each dispatched run stops at its gates.",
    )
    parser.add_argument(
        "--max-moves",
        type=int,
        default=None,
        help=f"hard ceiling on experiments the director may run (default "
        f"{DEFAULT_MAX_MOVES}); it holds no matter what the decider wants. "
        f"Mutually exclusive with --cost-cap.",
    )
    parser.add_argument(
        "--cost-cap",
        type=float,
        default=None,
        help="a spend ceiling in USD instead of a move count; the director "
        "derives the move ceiling from it (R-FD-2). Mutually exclusive with "
        "--max-moves.",
    )
    parser.add_argument(
        "--allowed-substrates",
        default=None,
        help="comma-separated substrate_ids to restrict this study to; omit for "
        "no restriction (the runs pick from the full permitted set).",
    )
    parser.add_argument(
        "--director",
        choices=["enum", "free"],
        default="enum",
        help="'enum' (default): the four-verb decider. 'free': the open-action-"
        "space director with a divisible budget (docs/free_director_plan.md) — "
        "built alongside; validate it live before it becomes the default.",
    )
    parser.add_argument(
        "--token-budget",
        type=int,
        default=None,
        help="TOKEN ceiling for the whole investigation (free director only). "
        "This is the real constraint: measured live, a 2-move study cost 55M "
        "tokens and a 4-move one cost 15.9M, because one experimenter call runs "
        "an agentic loop of up to 200 turns. The director sees tokens_remaining "
        "every turn and scales depth, decomposition and ideation depth to it. "
        "--max-moves still applies as a structural backstop. Rough guide: a "
        "substantive multi-phase study has cost 20-55M tokens.",
    )
    parser.add_argument(
        "--paper",
        action="store_true",
        help="after the investigation, write the WHOLE STUDY up as a paper "
        "(+figures) from its wall-verified findings into studies/<id>/paper.md. "
        "Works with either director. Off by default.",
    )
    args = parser.parse_args(argv)

    allowed = (
        [s.strip() for s in args.allowed_substrates.split(",") if s.strip()]
        if args.allowed_substrates
        else None
    )

    max_moves, ceiling = _resolve_ceiling(args.max_moves, args.cost_cap)

    if args.director == "free":
        from pi_agent.free_director import free_investigate

        report = free_investigate(
            goal=args.goal,
            budget=Budget(max_moves),
            allowed_substrates=allowed,
            mode=args.mode,
            ceiling=ceiling,
            token_budget=args.token_budget,
        )
    else:
        report = investigate(
            goal=args.goal,
            allowed_substrates=allowed,
            mode=args.mode,
            max_moves=max_moves,
            ceiling=ceiling,
        )

    summary = {
        "study_id": report["study_id"],
        "goal": report["goal"],
        "moves_run": report["moves_run"],
        "termination": report["termination"],
    }
    print(json.dumps(summary, indent=2))
    print(f"study report: studies/{report['study_id']}/report.json")

    # PAPER ROUTE (opt-in). Written here, at the entry point, rather than inside
    # either director: it then covers BOTH directors with one wire, and it writes
    # up only the TOP-LEVEL study (a spawned child's arc is reported inside its
    # parent's, so a per-child paper would double-report the same work).
    # Best-effort — a failed write-up never undoes the investigation.
    if args.paper:
        from stages.study_paper import write_study_paper_by_id

        outcome = write_study_paper_by_id(report["study_id"])
        if outcome.get("paper_path"):
            print(f"paper: {outcome['paper_path']}")
            for fig in outcome.get("figures") or []:
                print(f"  figure: {fig}")
            # REFEREE (best-effort, advisory). A fresh artifact-review pass
            # checks the paper's WORDS against the code and records behind it —
            # the layer the wall (numbers) and desk screen (text-only) cannot
            # see. Findings are appended to the paper's must-validate
            # territory; they never gate, and a failed review never undoes the
            # paper. REFEREE=0 disables.
            from stages.referee import referee_study_paper_by_id

            ref = referee_study_paper_by_id(report["study_id"])
            if ref.get("report_path"):
                n = len(ref.get("findings") or [])
                print(f"referee: {ref['report_path']} ({n} finding(s), "
                      f"{ref.get('appended', 0)} appended to paper)")
            else:
                print(f"no referee review: {ref.get('error')}")
        else:
            print(f"no paper written: {outcome.get('error')}")

            # BUILD CRITIC (best-effort, advisory). A DIFFERENT lens from the
            # referee: not "do the words match the code" but "could a competent
            # person actually use this tomorrow". Found the way most good checks
            # are — a human pasted a finished study into a fresh chat and asked
            # exactly that, and got six true findings the whole apparatus had
            # missed, none of them correctness failures. Its findings are routed
            # BACK TO THE DIRECTOR for one recorded response, so the challenge and
            # the answer both reach the reader. Point it at an outside model with
            # RESEARCH_MODEL_CRITIC=fable. BUILD_CRITIC=0 disables.
            from stages.build_critic import critique_and_respond

            crit = critique_and_respond(report["study_id"])
            if crit.get("error"):
                print(f"build critique skipped: {crit['error']}")
            else:
                c = crit["critique"]
                print(f"build critique: {crit['findings']} finding(s), "
                      f"usable_today={c.get('usable_today')} "
                      f"({c.get('model')})")


if __name__ == "__main__":
    main()
