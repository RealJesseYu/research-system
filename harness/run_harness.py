"""harness/run_harness.py — the killrate + paperlint front door (Step 16.6).

Originally the measurement-rails harness over the Step-6 fidelity-gate case set
(the fast/heavy fidelity battery, plus the triage and calibration batteries).
Those batteries scored the deterministic six-stage pipeline; that pipeline and
its stages were DELETED 2026-07-23 (the free-agent purge — see
docs/handoff_free_agent_purge.md), so the fidelity/triage/calibration modes went
with them. What remains is the two modes that never touched those stages:

- --mode killrate   — the Stage-1 ideation kill-rate battery
                      (harness/killrate_battery.py + survival_counter.py).
- --mode paperlint  — lint a deliverable's SHAPE. Two targets:
                      --study-id <id>  the LIVE route: studies/<id>/paper.md +
                        report.md against the deliverable standard — the opening
                        "Bottom line" block (what was accomplished / what it is
                        worth / what you can do with it now / what is not
                        established), a table of contents over six sections, the
                        section skeleton for its declared kind, and the mandatory
                        "What a human must still validate" (harness/study_lint.py).
                      --run-id <id>    the RETIRED six-stage layout
                        (harness/paper_lint.py), kept for old runs on disk.

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


def _declared_document_kind(study_dir: Path) -> str:
    """The skeleton this study's paper is held to. The writer DECLARES its kind
    and the study report records it; when that record is absent (an older study,
    or one written before the declaration existed) the kind is inferred from the
    paper's own headings rather than assumed. Never raises."""
    import json

    from harness.study_lint import DOCUMENT_KINDS, infer_document_kind

    for name in ("paper_meta.json", "report.json", "study.json"):
        try:
            data = json.loads((study_dir / name).read_text())
        except (OSError, ValueError):
            continue
        kind = data.get("document_kind") if isinstance(data, dict) else None
        if kind in DOCUMENT_KINDS:
            return kind
    try:
        return infer_document_kind((study_dir / "paper.md").read_text())
    except (OSError, UnicodeDecodeError):
        return "research"


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
    parser.add_argument(
        "--study-id",
        default=None,
        help="paperlint mode only: the STUDY whose paper.md + report.md to lint "
        "(the live free route; harness/study_lint.py)",
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
        # STUDY MODE — the live route. The run-id branch below lints the RETIRED
        # six-stage layout; this one lints what a director-run study actually
        # writes today, studies/<id>/paper.md + report.md, against the
        # deliverable-shape standard (opening block, navigation, skeleton,
        # must-validate). Deterministic, ZERO model calls, same failure shape.
        if args.study_id is not None:
            if args.run_id is not None:
                parser.error("--mode paperlint takes --run-id OR --study-id, "
                             "not both")
            from harness.study_lint import lint_study_dir

            study_dir = Path("studies") / str(args.study_id)
            if not study_dir.is_dir():
                print(f"PAPERLINT: NOT APPLICABLE — no study directory at "
                      f"{study_dir}.")
                return 0
            kind = _declared_document_kind(study_dir)
            failures = lint_study_dir(study_dir, kind)
            for failure in failures:
                print(f"PAPERLINT FAIL [{failure['code']}] "
                      f"target={failure['target']}: {failure['message']}")
            if failures:
                print(f"PAPERLINT: FAIL — {len(failures)} failure(s) for study "
                      f"{args.study_id} (linted as document_kind={kind!r})")
                return 1
            print(f"PAPERLINT: PASS — study {args.study_id}, 0 failures "
                  f"(document_kind={kind!r})")
            return 0

        if args.run_id is None:
            parser.error("--mode paperlint requires --run-id or --study-id")

        # THIS MODE LINTS THE RETIRED STAGE-6 LAYOUT. lint_paper reads
        # runs/<id>/stage6/paper.md plus stage6/paper_validation.json and
        # stage3/verdict.json — the six-stage relay's artifacts. The live route
        # (stages/free_paper.py, stages/study_paper.py) writes runs/<id>/paper.md
        # and produces none of that stage evidence, and pi_agent/dispatch.py
        # already migrated its own read to the new path; this mode did not.
        #
        # Pointed at a current run it would therefore report a pile of
        # missing-artifact failures that say "your paper is broken" when the truth
        # is "this lint does not cover this route". Say which it is, loudly,
        # instead of emitting misleading failures.
        _run_dir = Path("runs") / str(args.run_id)
        if not (_run_dir / "stage6").is_dir():
            print(
                f"PAPERLINT: NOT APPLICABLE — run {args.run_id} has no stage6/ "
                "directory, so it was not produced by the six-stage relay this "
                "lint checks."
            )
            if (_run_dir / "paper.md").is_file():
                print(
                    f"  This run's paper is at {_run_dir / 'paper.md'} (the free "
                    "route). It is NOT covered by any lint: the free writers use "
                    'the heading "What a human must still validate" and emit no '
                    "validation sidecar, both of which this module predates."
                )
            elif not _run_dir.is_dir():
                print(f"  No run directory at {_run_dir} either.")
            return 0

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
