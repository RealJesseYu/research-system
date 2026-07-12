"""harness/run_harness.py — measurement-rails harness (Step 16.6).

The harness is the instrument that reports the project's two cost units —
MODEL CALLS (per door, via the shared cost_meter) and WALL-TIME (via
time.perf_counter). Chunk 3 replaces chunk 1's placeholder with the real
deterministic battery over the Step-6 fidelity-gate case set
(harness/cases/cases.json, copied in-repo; answer keys included):

- FAST target (--mode fast): the merge gate. Runs the HUMAN-SELECTED
  hard-gate cases (chosen at this chunk's Part-3 stop, 2026-07-07) — ALL
  must return their exact true_label or FAST is RED — plus the
  boundary-sensitive WATCH cases, which are recorded and warned on a miss
  but NEVER turn FAST red (verdicts are model judgments; a must-pass-all
  battery would go red on model noise, not real regressions).
- HEAVY target (--mode heavy): the on-demand full battery — ALL 16 cases,
  full label scoring, not the merge gate.
- The cost-routing trap (Hagen-Poiseuille must route to analytic, not CFD)
  is REGISTERED in both targets with an explicit SKIP — it appears in the
  output as SKIPPED ("pending: analytic tier not built (Step 12)") and runs
  nothing today, so it can never be silently absent.

Cases run via harness/fidelity_case_runner.py — the DIRECT call_stage_model
path (frozen stage-3 SYSTEM_PROMPT + each case's own prompt_inputs), never
stage3_fidelity_gate.run(). CRITICAL INVARIANT: the battery writes NO
production ledger entry (memory/fidelity_ledger.jsonl or otherwise) — it is
a test, not a real experiment. The LEDGER ACTIVITY line in the cost report
doubles as the in-band check: it must read 0/0 every battery run.

The COST REPORT is printed and written to harness/last_run.json. OVERWRITE,
deliberately: the file's name means "the latest run"; runs/ stays the
project's only append-only evidence store. The report carries ATTEMPTS
alongside completed calls (attempts are recorded at each door BEFORE the
SDK call fires, so a mid-stream transport failure still leaves a trace).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cost_meter  # noqa: E402
from memory import ledgers  # noqa: E402
from harness.fidelity_case_runner import load_cases, run_case  # noqa: E402

LAST_RUN_PATH = Path(__file__).resolve().parent / "last_run.json"
TRAP_CASE_PATH = Path(__file__).resolve().parent / "cases" / "trap_hagen_poiseuille.json"

# Human-selected at this chunk's Part-3 stop (2026-07-07): clean-trust case 1
# and clean-defers 6 and 16 — zero historical misses across the spike's v1
# and v2 scored runs, wide physics margins. NOT auto-selected.
HARD_GATE_CASE_IDS = (1, 6, 16)

# Boundary-sensitive: recorded, non-blocking. 13 flipped refine->trust under
# the frozen v2 prompt (the archetypal flipper), 3 flipped trust->refine
# under v2, 4 flipped trust->refine across prompt versions v1->v2.
WATCH_CASE_IDS = (3, 4, 13)


def load_trap_case() -> dict:
    """The registered-but-skipped cost-routing trap (runs nothing today)."""
    return json.loads(TRAP_CASE_PATH.read_text())["case"]


def _trap_report_entry(trap: dict) -> dict:
    """The trap's battery entry: explicitly SKIPPED, zero cost, no call."""
    return {
        "case": trap["id"],
        "role": "cost-routing-trap",
        "status": trap["skip"]["status"],
        "reason": trap["skip"]["reason"],
    }


def run_battery_case(case: dict, role: str) -> dict:
    """One scored battery case: the runner's record plus its battery role."""
    result = run_case(case)
    return {"case": f"case_{result['case_id']}", "role": role, **result}


def _format_calls(calls: dict) -> str:
    doors = " ".join(f"{k}={v}" for k, v in calls.items() if k != "total")
    return f"{doors} total={calls['total']}"


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


def print_battery_report(report: dict) -> None:
    battery = report["battery"]
    print()
    print("=" * 22 + f" {report['mode'].upper()} BATTERY " + "=" * 22)
    for entry in report["cases"]:
        if entry["role"] == "cost-routing-trap":
            continue  # printed in its own SKIPPED section below
        verdict_line = (
            f"  case {entry['case_id']:>2} [{entry['role']}]  "
            f"true={entry['true_label']:<6} got={entry['verdict']:<6} -> "
            f"{'PASS' if entry['passed'] else ('MISS' if entry['role'] == 'watch' else 'FAIL')}"
        )
        print(verdict_line)
        if entry["role"] == "watch" and not entry["passed"]:
            print(
                f"    WATCH WARNING: case {entry['case_id']} missed "
                f"(true={entry['true_label']} got={entry['verdict']}) — "
                "recorded, does NOT affect GREEN/RED"
            )
    for skipped in battery["skipped"]:
        print(
            f"  case {skipped['case']} [{skipped['role']}]  "
            f"{skipped['status']} — {skipped['reason']}"
        )
    if report["mode"] == "fast":
        print(
            f"  hard-gate cases: {list(battery['hard_gate_case_ids'])}   "
            f"watch cases: {list(battery['watch_case_ids'])}"
        )
        print(
            f"FAST: {battery['status']} "
            f"(hard-gate {battery['hard_gate_passed']}/{battery['hard_gate_total']}"
            + (
                f"; watch misses: {battery['watch_misses']}"
                if battery["watch_misses"]
                else "; no watch misses"
            )
            + ")"
        )
    else:
        print(f"HEAVY score: {battery['score']} correct (not the merge gate)")
        if battery["misses"]:
            for miss in battery["misses"]:
                print(
                    f"    miss: case {miss['case_id']} "
                    f"true={miss['true_label']} got={miss['verdict']}"
                )
        else:
            print("    (no misses)")
    print("=" * 61)


def format_signals_line(signals: dict) -> str:
    """The per-run SIGNALS line (Step 17-fix-A): warn-only instrumentation
    counts from cost_meter's "signals" section — observations recorded by a
    validator WITHOUT rejecting the reply. Deliberately separate from the
    REJECTS line: a signal never triggers a re-ask and never enters any
    reject_rate."""
    body = " ".join(f"{tag}={count}" for tag, count in sorted(signals.items()))
    return "SIGNALS (warn-only, never re-asked): " + (body if body else "(none)")


def print_cost_report(report: dict) -> None:
    print()
    print("=" * 24 + " COST REPORT " + "=" * 24)
    print(f"mode: {report['mode']}   cases: {report['num_cases']}")
    for case in report["cases"]:
        if case["role"] == "cost-routing-trap":
            print(f"  case {case['case']}: SKIPPED — no model call, zero cost")
            continue
        print(
            f"  case {case['case']}: model_calls {_format_calls(case['model_calls'])} | "
            f"attempts {_format_calls(case['attempts'])} | "
            f"wall_time_seconds={case['wall_time_seconds']}"
        )
    totals = report["totals"]
    print(
        f"  TOTAL: model_calls {_format_calls(totals['model_calls'])} | "
        f"attempts {_format_calls(totals['attempts'])} | "
        f"wall_time_seconds={totals['wall_time_seconds']}"
    )
    print(f"    tokens: {json.dumps(totals['tokens'])}")
    print(f"  {format_reject_line(totals['stage_rejects'])}")
    print(f"  {format_signals_line(totals['signals'])}")
    activity = report["ledger_activity"]
    print(
        f"  LEDGER ACTIVITY this run: fidelity_entries={activity['fidelity_entries']} "
        f"override_entries={activity['override_entries']}"
        + (
            ""
            if activity["fidelity_entries"] == 0 and activity["override_entries"] == 0
            else "   *** CRITICAL: the battery wrote a production ledger ***"
        )
    )
    print("=" * 61)


def run_harness(mode: str) -> int:
    cases_by_id = {case["id"]: case for case in load_cases()}
    if mode == "fast":
        roster = [(case_id, "hard-gate") for case_id in HARD_GATE_CASE_IDS] + [
            (case_id, "watch") for case_id in WATCH_CASE_IDS
        ]
    else:
        roster = [(case_id, "scored") for case_id in sorted(cases_by_id)]
    trap = load_trap_case()

    cost_meter.reset()
    # Ledger-activity baseline: the battery must add NOTHING (critical
    # invariant — see module docstring); the delta below is the in-band proof.
    fidelity_before = ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH)
    override_before = ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH)

    case_reports = []
    run_start = time.perf_counter()
    for case_id, role in roster:
        case_reports.append(run_battery_case(cases_by_id[case_id], role))
    case_reports.append(_trap_report_entry(trap))
    total_wall = time.perf_counter() - run_start
    final_meter = cost_meter.read()

    scored = [entry for entry in case_reports if entry["role"] != "cost-routing-trap"]
    skipped = [
        {
            "case": entry["case"],
            "role": entry["role"],
            "status": entry["status"],
            "reason": entry["reason"],
        }
        for entry in case_reports
        if entry["role"] == "cost-routing-trap"
    ]
    if mode == "fast":
        hard_gate = [entry for entry in scored if entry["role"] == "hard-gate"]
        watch = [entry for entry in scored if entry["role"] == "watch"]
        battery = {
            "target": "fast",
            "hard_gate_case_ids": list(HARD_GATE_CASE_IDS),
            "watch_case_ids": list(WATCH_CASE_IDS),
            "hard_gate_passed": sum(1 for entry in hard_gate if entry["passed"]),
            "hard_gate_total": len(hard_gate),
            "status": "GREEN" if all(entry["passed"] for entry in hard_gate) else "RED",
            "watch_misses": [
                entry["case_id"] for entry in watch if not entry["passed"]
            ],
            "skipped": skipped,
        }
    else:
        battery = {
            "target": "heavy",
            "score": f"{sum(1 for entry in scored if entry['passed'])}/{len(scored)}",
            "misses": [
                {
                    "case_id": entry["case_id"],
                    "true_label": entry["true_label"],
                    "verdict": entry["verdict"],
                }
                for entry in scored
                if not entry["passed"]
            ],
            "skipped": skipped,
        }

    report = {
        "mode": mode,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "num_cases": len(case_reports),
        "battery": battery,
        "cases": case_reports,
        "totals": {
            "model_calls": final_meter["model_calls"],
            "attempts": final_meter["attempts"],
            "tokens": final_meter["tokens"],
            "stage_rejects": final_meter["stages"],
            "signals": final_meter["signals"],
            "wall_time_seconds": round(total_wall, 3),
        },
        "ledger_activity": {
            "fidelity_entries": ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH)
            - fidelity_before,
            "override_entries": ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH)
            - override_before,
        },
    }

    print_battery_report(report)
    print_cost_report(report)
    with open(LAST_RUN_PATH, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"report written to {LAST_RUN_PATH}")
    if mode == "fast" and battery["status"] == "RED":
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Measurement-rails harness (Step 16.6).")
    parser.add_argument(
        "--mode", choices=["fast", "heavy", "killrate", "paperlint"], required=True
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=None,
        help="killrate mode only: ideation repeats per domain "
        "(default: the proving size, 2 x 2 domains = 4 runs)",
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

        if args.repeats is not None or args.dry_run or args.rounds is not None:
            parser.error("--repeats/--dry-run/--rounds apply only to --mode killrate")
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
    if args.mode == "killrate":
        # The HEAVY kill-rate battery (chunk 4): Stage-1 ideation runs
        # scored by harness/survival_counter.py — a different instrument
        # from the fidelity-case battery, same harness front door.
        from harness import killrate_battery

        repeats = args.repeats if args.repeats is not None else killrate_battery.DEFAULT_REPEATS
        rounds = args.rounds if args.rounds is not None else 1
        if args.dry_run:
            killrate_battery.print_dry_run(repeats, rounds)
            return 0
        return killrate_battery.run_battery(repeats, rounds)
    if args.repeats is not None or args.dry_run or args.rounds is not None:
        parser.error("--repeats/--dry-run/--rounds apply only to --mode killrate")
    return run_harness(args.mode)


if __name__ == "__main__":
    sys.exit(main())
