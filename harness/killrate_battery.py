"""harness/killrate_battery.py — the HEAVY kill-rate battery (Step 16.6
chunk 4): the deep-verification survival-rate instrument, run on demand.

Launched via run_harness.py --mode killrate. For each of the TWO diag4a
domains it runs Stage-1 ideation (stages.stage1_ideation.run(baton), the
baton mirroring supervisor.main() exactly as the rescued diag4a driver —
harness/diag4a_reference/diag4a_driver.py — builds it) N repeats each
(default N=2: the PROVING size, 2 repeats x 2 domains = 4 runs), then
reports PER-DOMAIN the distribution of k and of deep-verify kill rate
across repeats. The variance is the point — the diagnostic saw k=3,0,3 on
the same domain.

Failure handling mirrors the driver's observed batch behavior, upgraded to
relaunch: after every attempt the Part-1 survival counter reads the run dir
— disk is ground truth, not the exception message. A run the counter calls
ABORTED (no reflection_reviews.json: arXiv/transport death) is RE-LAUNCHED
up to MAX_RELAUNCHES times and is NEVER recorded as k=0; a run the counter
calls scored (including the two zero-survivor raises) is a real data point,
recorded k=0-with-reason. The driver's ~180 s inter-run sleep (arXiv
courtesy) is kept between attempts.

Comparability: every run in one battery must retrieve the SAME memory
block. Each run's stage1/retrieved_memory.json md5 is checked against
EXPECTED_MEMORY_MD5; a differing run is flagged non_comparable and EXCLUDED
from the per-domain distributions — reported separately, never silently
averaged in. Pin history: 373c886b (diag4a era, verified identical across
all nine diag4a dirs; held through 17-fix-A/B, 17-C/D/E) ended by design
when the Step-17 supervised Runs A/B/C journaled learned summaries; the
Step-18 pin below was re-derived at 18-prep (R-18P-4: over the memory
state as it stood post-Run-C, no excision).

Model pins: the battery uses whatever the current stage pins are, and
RECORDS them in the results file, so a post-18.7 run can never be silently
compared against a today's-pins run.

CRITICAL INVARIANT (same as the fidelity battery): ideation runs never
reach stage 3 or a human gate, so NO production ledger entry is written —
the report's ledger-activity delta is the in-band proof, and must read 0/0.

Results overwrite harness/killrate_last_run.json (the filename means "the
latest run") unless --report-path names another file (18-prep: parallel
batteries must not collide on the report); the per-run evidence stays in
runs/<id>/ as always.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cost_meter  # noqa: E402
from memory import ledgers  # noqa: E402
from harness import survival_counter  # noqa: E402

KILLRATE_LAST_RUN_PATH = Path(__file__).resolve().parent / "killrate_last_run.json"


def resolve_report_path(report_path: str | Path | None) -> Path:
    """Where this battery's machine report goes: the fixed default file, or
    the caller's --report-path (18-prep: parallel batteries each get their
    own report file so simultaneous launches never clobber each other)."""
    return Path(report_path) if report_path is not None else KILLRATE_LAST_RUN_PATH

# The EXACT diag4a inputs, verbatim from the rescued driver
# (harness/diag4a_reference/diag4a_driver.py).
SAME_DOMAIN = "mean-flow structure and vortex strength in laminar lid-driven cavity flows"
ALT_DOMAIN = (
    "secondary corner eddies and their dependence on Reynolds number in "
    "two-dimensional laminar lid-driven cavity flow"
)
DOMAINS = {"same": SAME_DOMAIN, "alt": ALT_DOMAIN}

# md5 (first 8 hex chars) of stage1/retrieved_memory.json — the
# comparability pin for the memory block. R-WIN-1 value, re-taken at the
# 2026-07-14 prompt-touch window over the live journal via the battery's own
# derivation (json.dumps(journal_recent_by_kind("learned_summary", 3),
# indent=2) -> md5[:8]); covers the three most recent learned summaries
# (run 20260714T152314Z, hypothesis ev1). This begins the R-WIN-1
# comparability era. Prior eras: 073ff57e (18-prep), 373c886b (diag4a).
EXPECTED_MEMORY_MD5 = "04d721c8"

DEFAULT_REPEATS = 2          # PROVING size: 2 repeats x 2 domains = 4 runs
MAX_RELAUNCHES = 2           # extra attempts after an ABORTED run, per slot
INTER_RUN_SLEEP_S = 180      # the driver's arXiv-courtesy spacing

# Observed per-ROUND cost, for the dry-run estimate only (17-CLOSE refresh;
# provenance: the 17-E overnight witness measured ≈85 total calls and ≈72 min
# wall per round). A run costs these figures times its requested rounds.
EST_CALLS_PER_ROUND = 85
EST_WALL_MIN_PER_ROUND = 72


def launch_git_head() -> tuple[str | None, str | None]:
    """git rev-parse HEAD at battery launch, recorded in the report header
    (17-CLOSE: the 17-C witness's launch commit was dictated provenance
    only — this makes it disk-recorded). Returns (head, note): note is None
    on success; any git failure returns (None, <note>) and never crashes
    the battery."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=_PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception as exc:
        return None, f"git rev-parse failed: {type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return None, (
            f"git rev-parse failed (exit {proc.returncode}): "
            f"{proc.stderr.strip() or '(no stderr)'}"
        )
    return proc.stdout.strip(), None


def current_model_pins() -> dict:
    """The stage pins the battery would run under, read from the live
    modules — recorded in every results file for cross-run comparability."""
    import model_call
    from retrieval import web_search
    from stages import (
        evolution_strategies,
        generation_strategies,
        meta_review,
        reflection_reviews,
        stage1_ideation,
    )

    return {
        "stage1_ideation.OPUS_MODEL": stage1_ideation.OPUS_MODEL,
        "generation_strategies.HAIKU_MODEL": generation_strategies.HAIKU_MODEL,
        "reflection_reviews.HAIKU_MODEL": reflection_reviews.HAIKU_MODEL,
        "reflection_reviews.DEEP_VERIFY_MODEL": reflection_reviews.DEEP_VERIFY_MODEL,
        "reflection_reviews.REVIEW6_MODEL": reflection_reviews.REVIEW6_MODEL,
        "evolution_strategies.EVOLUTION_MODEL": evolution_strategies.EVOLUTION_MODEL,
        "meta_review.META_REVIEW_MODEL": meta_review.META_REVIEW_MODEL,
        "web_search.HAIKU_MODEL": web_search.HAIKU_MODEL,
        "model_call.HAIKU_MODEL_default": model_call.HAIKU_MODEL,
    }


def build_run_plan(repeats: int) -> list[dict]:
    """The slot list: repeats per domain, tags mirroring the diagnostic's
    (same1..sameN, alt1..altN)."""
    plan = []
    for domain_key, domain in DOMAINS.items():
        for i in range(1, repeats + 1):
            plan.append({"slot": f"{domain_key}{i}", "domain_key": domain_key, "domain": domain})
    return plan


def _memory_md5(run_dir: Path) -> str | None:
    path = run_dir / "stage1" / "retrieved_memory.json"
    if not path.exists():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()[:8]


def _meter_totals() -> dict:
    m = cost_meter.read()
    return {
        "model_calls": dict(m["model_calls"]),
        "attempts": dict(m["attempts"]),
        "stages": {stage: dict(stats) for stage, stats in m["stages"].items()},
        "signals": dict(m["signals"]),
    }


def _delta(after: dict, before: dict) -> dict:
    return {
        section: {
            k: after[section].get(k, 0) - before[section].get(k, 0)
            for k in set(after[section]) | set(before[section])
        }
        for section in ("model_calls", "attempts")
    }


def _stage_reject_delta(after: dict, before: dict) -> dict:
    """Per-stage {calls, rejects, reject_rate} for ONE run (Step 18.7
    chunk 1): the difference between two cost_meter "stages" snapshots,
    with the rate computed on the delta. Stages with zero activity in the
    window do not appear; a "total" row always does."""
    out: dict[str, dict] = {}
    total_calls = total_rejects = 0
    for stage in sorted(set(after) | set(before)):
        if stage == "total":
            continue
        calls = after.get(stage, {}).get("calls", 0) - before.get(stage, {}).get("calls", 0)
        rejects = after.get(stage, {}).get("rejects", 0) - before.get(stage, {}).get("rejects", 0)
        total_calls += calls
        total_rejects += rejects
        if calls or rejects:
            out[stage] = {
                "calls": calls,
                "rejects": rejects,
                "reject_rate": round(rejects / calls, 3) if calls else 0.0,
            }
    out["total"] = {
        "calls": total_calls,
        "rejects": total_rejects,
        "reject_rate": round(total_rejects / total_calls, 3) if total_calls else 0.0,
    }
    return out


def _rounds_info(run_dir: Path) -> tuple[int | None, str | None]:
    """(rounds_completed, termination_reason) read from the run's
    stage1/rounds.json (Step 17-E). A completed round is any entry that was
    not the zero-survivor termination record; the slot-level
    termination_reason is the last entry's. (None, None) when the file is
    absent — a run that crashed before any round finished."""
    path = run_dir / "stage1" / "rounds.json"
    if not path.exists():
        return None, None
    entries = json.loads(path.read_text())
    completed = sum(
        1 for e in entries if e.get("termination_reason") != "zero_survivors_terminated"
    )
    reason = entries[-1].get("termination_reason") if entries else None
    return completed, reason


def _launch_one(slot: str, domain: str, rounds: int) -> dict:
    """One ideation attempt: baton built exactly as the diag4a driver builds
    it (mirroring supervisor.main()), stages.stage1_ideation.run(baton,
    rounds=rounds) — rounds defaults to 1 at the battery front door, so
    scored runs stay baseline-comparable single passes unless flagged —
    baton_after_stage_1.json written on success. Returns the attempt
    record; classification comes from the survival counter."""
    from baton import Baton
    from stages import stage1_ideation

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"killrate-{ts}-{slot}"
    run_dir = _PROJECT_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    baton = Baton(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode="auto",
        payload={"domain": domain},
    )
    baton.validate()

    meter_before = _meter_totals()
    t0 = time.perf_counter()
    exception_text = None
    try:
        out = stage1_ideation.run(baton, rounds=rounds)
        (run_dir / "baton_after_stage_1.json").write_text(out.to_json())
    except Exception as exc:  # classified from disk below, never re-raised
        exception_text = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    wall_s = round(time.perf_counter() - t0, 1)

    counted = survival_counter.count_run(run_dir)
    memory_md5 = _memory_md5(run_dir)
    comparable = memory_md5 == EXPECTED_MEMORY_MD5
    rounds_completed, termination_reason = _rounds_info(run_dir)
    meter_after = _meter_totals()
    record = {
        "run_id": run_id,
        "slot": slot,
        "wall_s": wall_s,
        "exception": exception_text,
        "memory_md5": memory_md5,
        "comparable": comparable,
        "cost_delta": _delta(meter_after, meter_before),
        "reject_stats": _stage_reject_delta(meter_after["stages"], meter_before["stages"]),
        # Step 17-fix-A: warn-only signal counts for THIS run (never part
        # of reject_stats — a signal is not a reject and feeds no re-ask).
        "signals": {
            tag: meter_after["signals"].get(tag, 0) - meter_before["signals"].get(tag, 0)
            for tag in set(meter_after["signals"]) | set(meter_before["signals"])
        },
        **{k: counted[k] for k in (
            "status", "k", "k_reason",
            "initial_survivor_count", "deep_verify_discards",
            "deep_verify_kill_rate", "abort_reason",
            # Step 17-E, ADDITIVE: Evolution's variant counts (from the
            # survival counter, on disk) and the controller's round facts.
            # k derivation stays byte-identical — none of these enter it.
            "variants_emitted", "variants_accepted",
            # 17-CLOSE, ADDITIVE: run-total variant counts (summed across
            # round dirs when they exist; else the canonical file).
            "variants_emitted_total", "variants_accepted_total",
        )},
        "rounds_completed": rounds_completed,
        "termination_reason": termination_reason,
    }
    if exception_text and counted["status"] == survival_counter.STATUS_SCORED and counted["k"]:
        # e.g. a ranking-step raise AFTER survivors.json was written: k is
        # known, the failure happened downstream of the number we measure.
        record["note"] = "exception_after_scoring — k read from disk is valid"
    return record


def print_dry_run(repeats: int, rounds: int = 1,
                  report_path: str | Path | None = None) -> None:
    """The launchability proof: the full run plan and expected cost, with
    NO ideation fired. Default behavior writes nothing; when --report-path
    is EXPLICITLY given, a small dry_run-stamped plan stub is written there
    (18-prep: the parallel launch smoke needs on-disk proof that N
    simultaneous invocations land on N distinct report files) — the
    default report file is never touched by a dry run."""
    plan = build_run_plan(repeats)
    resolved = resolve_report_path(report_path)
    print()
    print("=" * 18 + " KILL-RATE BATTERY — DRY RUN (no ideation fired) " + "=" * 18)
    print(f"repeats per domain: {repeats}   total runs: {len(plan)}")
    print(f"rounds per run: {rounds}"
          + (" (single-pass, baseline-comparable)" if rounds == 1
             else " — MULTI-ROUND: per-run cost multiplies accordingly"))
    for domain_key, domain in DOMAINS.items():
        print(f'  domain "{domain_key}": {domain}')
    print("run plan (sequential, one Stage-1 ideation each):")
    for entry in plan:
        print(f"  slot {entry['slot']:<7} -> runs/killrate-<ts>-{entry['slot']}   domain={entry['domain_key']}")
    print(f"  inter-run sleep: {INTER_RUN_SLEEP_S} s (the driver's arXiv courtesy)")
    print(f"  relaunch cap: {MAX_RELAUNCHES} relaunches per slot on ABORTED (transport death); "
          "aborts are never recorded as k=0")
    print(f"  memory comparability pin: stage1/retrieved_memory.json md5 must be {EXPECTED_MEMORY_MD5}; "
          "a differing run is flagged non-comparable and excluded from distributions")
    print("model pins that would be recorded:")
    for name, pin in current_model_pins().items():
        print(f"  {name} = {pin}")
    print(f"expected cost (17-E measured: ≈{EST_CALLS_PER_ROUND} calls / "
          f"≈{EST_WALL_MIN_PER_ROUND} min per ROUND): "
          f"≈{EST_CALLS_PER_ROUND * rounds} calls, ≈{EST_WALL_MIN_PER_ROUND * rounds} min "
          f"per run at rounds={rounds}")
    print(f"  -> for {len(plan)} runs: ≈{EST_CALLS_PER_ROUND * rounds * len(plan)} calls, "
          f"≈{EST_WALL_MIN_PER_ROUND * rounds * len(plan) / 60:.1f} h + sleeps")
    print("ledger invariant: ideation never reaches stage 3 or a human gate — "
          "fidelity/override ledgers must show a 0/0 delta")
    print(f"results would be written to {resolved}")
    if report_path is not None:
        stub = {
            "mode": "killrate",
            "dry_run": True,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "repeats": repeats,
            "rounds": rounds,
            "report_path": str(resolved),
            "planned_slots": [entry["slot"] for entry in plan],
        }
        with open(resolved, "w") as f:
            json.dump(stub, f, indent=2)
            f.write("\n")
        print(f"dry-run plan stub written to {resolved}")
    print("=" * 85)


def run_battery(repeats: int, rounds: int = 1,
                report_path: str | Path | None = None) -> int:
    """The live battery. NOT run in chunk 4 — the proving batch is the
    human's to launch in a plain Terminal later. rounds defaults to 1
    (Step 17-E): scored runs stay baseline-comparable single passes unless
    the --rounds flag says otherwise. report_path (18-prep): where the
    machine report is written; default unchanged."""
    plan = build_run_plan(repeats)
    resolved = resolve_report_path(report_path)
    pins = current_model_pins()
    git_head, git_head_note = launch_git_head()

    cost_meter.reset()
    fidelity_before = ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH)
    override_before = ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH)

    slots = []
    battery_start = time.perf_counter()
    for idx, entry in enumerate(plan):
        attempts = []
        for attempt_no in range(1 + MAX_RELAUNCHES):
            if attempts or idx:  # the driver's spacing, between ALL launches
                print(f"[battery] sleeping {INTER_RUN_SLEEP_S} s (arXiv courtesy)", flush=True)
                time.sleep(INTER_RUN_SLEEP_S)
            print(f"[battery] slot {entry['slot']} attempt {attempt_no + 1}", flush=True)
            record = _launch_one(entry["slot"], entry["domain"], rounds)
            attempts.append(record)
            print(f"[battery] {record['run_id']}: status={record['status']} "
                  f"k={record['k']} k_reason={record['k_reason']} "
                  f"kill={record['deep_verify_kill_rate']} ({record['wall_s']} s)", flush=True)
            if record["status"] == survival_counter.STATUS_SCORED:
                break
            print(f"[battery] ABORTED ({record['abort_reason']}) — "
                  + ("relaunching" if attempt_no < MAX_RELAUNCHES else "relaunch cap reached"),
                  flush=True)
        final = attempts[-1]
        slots.append({
            "slot": entry["slot"],
            "domain_key": entry["domain_key"],
            "attempts": attempts,
            "resolved": final["status"] == survival_counter.STATUS_SCORED,
        })

    total_wall = round(time.perf_counter() - battery_start, 1)
    meter = cost_meter.read()

    per_domain: dict = {}
    for domain_key in DOMAINS:
        domain_slots = [s for s in slots if s["domain_key"] == domain_key]
        counted = [
            s["attempts"][-1] for s in domain_slots
            if s["resolved"] and s["attempts"][-1]["comparable"]
        ]
        per_domain[domain_key] = {
            "k_distribution": [r["k"] for r in counted],
            "k_reasons": {r["run_id"]: r["k_reason"] for r in counted if r["k_reason"]},
            "kill_rate_distribution": [r["deep_verify_kill_rate"] for r in counted],
            "unresolved_slots": [s["slot"] for s in domain_slots if not s["resolved"]],
            "non_comparable_runs": [
                s["attempts"][-1]["run_id"] for s in domain_slots
                if s["resolved"] and not s["attempts"][-1]["comparable"]
            ],
        }

    report = {
        "mode": "killrate",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # 17-CLOSE: the commit the battery was launched from, captured by
        # git rev-parse at launch; null (plus launch_git_head_note) when
        # git could not answer — provenance is recorded, never a crash.
        "launch_git_head": git_head,
        **({"launch_git_head_note": git_head_note} if git_head_note else {}),
        "repeats": repeats,
        "rounds": rounds,
        # 18-prep: the file this report was written to, recorded in-band so
        # a parallel launch's three reports are self-attributing.
        "report_path": str(resolved),
        "domains": DOMAINS,
        "model_pins": pins,
        "expected_memory_md5": EXPECTED_MEMORY_MD5,
        "slots": slots,
        "per_domain": per_domain,
        "totals": {
            "model_calls": meter["model_calls"],
            "attempts": meter["attempts"],
            "tokens": meter["tokens"],
            "stage_rejects": meter["stages"],
            "signals": meter["signals"],
            "wall_time_seconds": total_wall,
        },
        "ledger_activity": {
            "fidelity_entries": ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH) - fidelity_before,
            "override_entries": ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH) - override_before,
        },
    }

    print()
    print("=" * 22 + " KILL-RATE BATTERY REPORT " + "=" * 22)
    for domain_key, dist in per_domain.items():
        print(f'domain "{domain_key}": k distribution {dist["k_distribution"]}   '
              f'kill rates {[f"{r:.2f}" for r in dist["kill_rate_distribution"]]}')
        for run_id, reason in dist["k_reasons"].items():
            print(f"    {run_id}: k=0 reason {reason}")
        if dist["unresolved_slots"]:
            print(f"    UNRESOLVED (aborted through relaunch cap, no data point): {dist['unresolved_slots']}")
        if dist["non_comparable_runs"]:
            print(f"    NON-COMPARABLE (memory md5 != {EXPECTED_MEMORY_MD5}, excluded): {dist['non_comparable_runs']}")
    totals = report["totals"]
    calls = " ".join(f"{k}={v}" for k, v in totals["model_calls"].items())
    print(f"TOTAL COST: model_calls {calls} | wall_time_seconds={totals['wall_time_seconds']}")
    from harness.run_harness import format_reject_line, format_signals_line  # lazy: mirrors run_harness's lazy import of this module

    print(format_reject_line(totals["stage_rejects"]))
    print(format_signals_line(totals["signals"]))
    activity = report["ledger_activity"]
    print(f"LEDGER ACTIVITY this battery: fidelity_entries={activity['fidelity_entries']} "
          f"override_entries={activity['override_entries']}"
          + ("" if activity["fidelity_entries"] == 0 and activity["override_entries"] == 0
             else "   *** CRITICAL: the battery wrote a production ledger ***"))
    print("=" * 70)

    with open(resolved, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"report written to {resolved}")
    return 0
