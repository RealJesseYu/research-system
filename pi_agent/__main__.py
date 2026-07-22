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

from pi_agent.loop import DEFAULT_MAX_MOVES, investigate  # noqa: E402


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
        default=DEFAULT_MAX_MOVES,
        help=f"hard ceiling on experiments the director may run (default "
        f"{DEFAULT_MAX_MOVES}); it holds no matter what the decider wants.",
    )
    parser.add_argument(
        "--allowed-substrates",
        default=None,
        help="comma-separated substrate_ids to restrict this study to; omit for "
        "no restriction (the runs pick from the full permitted set).",
    )
    args = parser.parse_args(argv)

    allowed = (
        [s.strip() for s in args.allowed_substrates.split(",") if s.strip()]
        if args.allowed_substrates
        else None
    )

    report = investigate(
        goal=args.goal,
        allowed_substrates=allowed,
        mode=args.mode,
        max_moves=args.max_moves,
    )

    summary = {
        "study_id": report["study_id"],
        "goal": report["goal"],
        "moves_run": report["moves_run"],
        "termination": report["termination"],
    }
    print(json.dumps(summary, indent=2))
    print(f"study report: studies/{report['study_id']}/report.json")


if __name__ == "__main__":
    main()
