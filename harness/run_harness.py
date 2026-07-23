"""harness/run_harness.py — the killrate + paperlint front door (Step 16.6).

Originally the measurement-rails harness over the Step-6 fidelity-gate case set
(the fast/heavy fidelity battery, plus the triage and calibration batteries).
Those batteries scored the deterministic six-stage pipeline; that pipeline and
its stages were DELETED 2026-07-23 (the free-agent purge — see
docs/handoff_free_agent_purge.md), so the fidelity/triage/calibration modes went
with them. What remains is the two modes that never touched those stages:

- --mode killrate   — the Stage-1 ideation kill-rate battery
                      (harness/killrate_battery.py + survival_counter.py).
- --mode paperlint  — lint one run's stage-6 paper output (harness/paper_lint.py).

format_reject_line / format_signals_line stay here because killrate_battery
imports them (the shared cost-report formatters).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def format_reject_line(stages: dict) -> str:
    """The per-run REJECT line (Step 18.7 chunk 1): per-stage
    {calls, rejects, reject_rate} plus the total row, from cost_meter's
    "stages" section. A stage with zero calls this run does not appear
    (the meter only holds stages that fired); web_search calls carry no
    stage_name and are deliberately absent — door-only, as always."""
    per_stage = " ".join(
        f"{stage}: calls={v['calls']} rejects={v['rejects']} rate={v['reject_rate']}"
        for stage, v in stages.items()
        if stage != "total"
    )
    total = stages["total"]
    return (
        "REJECTS (schema/validator re-asks): "
        + (per_stage + " | " if per_stage else "(no stage-attributed calls) ")
        + f"TOTAL calls={total['calls']} rejects={total['rejects']} rate={total['reject_rate']}"
    )


def format_signals_line(signals: dict) -> str:
    """The per-run SIGNALS line (Step 17-fix-A): warn-only instrumentation
    counts from cost_meter's "signals" section — observations recorded by a
    validator WITHOUT rejecting the reply. Deliberately separate from the
    REJECTS line: a signal never triggers a re-ask and never enters any
    reject_rate."""
    body = " ".join(f"{tag}={count}" for tag, count in sorted(signals.items()))
    return "SIGNALS (warn-only, never re-asked): " + (body if body else "(none)")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="killrate + paperlint harness (Step 16.6; fidelity/triage/"
        "calibration batteries purged with the free-agent purge)."
    )
    parser.add_argument(
        "--mode",
        choices=["killrate", "paperlint"],
        required=True,
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="killrate mode: ideation repeats per domain (default: the "
        "proving size, 2 x 2 domains = 4 runs).",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=None,
        help="killrate mode only: ideation rounds per run threaded to "
        "stage1_ideation.run (default 1 — baseline-comparable single pass)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="killrate mode only: print the run plan and expected cost "
        "without firing ideation",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="killrate mode only: file the battery report JSON is written "
        "to (default harness/killrate_last_run.json)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="paperlint mode only: the run whose stage6 output to lint",
    )
    args = parser.parse_args()

    if args.mode == "paperlint":
        # Step 22: lint one run's stage-6 output (paper.md + the validation
        # sidecar vs the on-disk stage-3 verdict). Lazy import per the
        # killrate pattern; deterministic, ZERO model calls.
        from harness import paper_lint

        if (args.repeats is not None or args.dry_run or args.rounds is not None
                or args.report_path is not None):
            parser.error(
                "--dry-run/--rounds/--report-path/--repeats apply only to "
                "--mode killrate"
            )
        if args.run_id is None:
            parser.error("--mode paperlint requires --run-id")
        failures = paper_lint.lint_paper(args.run_id)
        for failure in failures:
            print(
                f"PAPERLINT FAIL [{failure['code']}] "
                f"target={failure['target']}: {failure['message']}"
            )
        if failures:
            print(
                f"PAPERLINT: FAIL — {len(failures)} failure(s) "
                f"for run {args.run_id}"
            )
            return 1
        print(f"PAPERLINT: PASS — run {args.run_id} (0 failures)")
        return 0

    if args.run_id is not None:
        parser.error("--run-id applies only to --mode paperlint")

    # --mode killrate: the HEAVY kill-rate battery — Stage-1 ideation runs
    # scored by harness/survival_counter.py. Lazy import per the paperlint
    # pattern.
    from harness import killrate_battery

    repeats = args.repeats if args.repeats is not None else killrate_battery.DEFAULT_REPEATS
    rounds = args.rounds if args.rounds is not None else 1
    if args.dry_run:
        killrate_battery.print_dry_run(repeats, rounds, report_path=args.report_path)
        return 0
    return killrate_battery.run_battery(repeats, rounds, report_path=args.report_path)


if __name__ == "__main__":
    sys.exit(main())
