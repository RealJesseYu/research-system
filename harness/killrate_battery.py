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

Comparability: every run must retrieve the SAME memory block the diag4a
runs saw. Each run's stage1/retrieved_memory.json md5 is checked against
EXPECTED_MEMORY_MD5 (373c886b, verified identical across all nine diag4a
dirs); a differing run is flagged non_comparable and EXCLUDED from the
per-domain distributions — reported separately, never silently averaged in.

Model pins: the battery uses whatever the current stage pins are, and
RECORDS them in the results file, so a post-18.7 run can never be silently
compared against a today's-pins run.

CRITICAL INVARIANT (same as the fidelity battery): ideation runs never
reach stage 3 or a human gate, so NO production ledger entry is written —
the report's ledger-activity delta is the in-band proof, and must read 0/0.

Results overwrite harness/killrate_last_run.json (the filename means "the
latest run"); the per-run evidence stays in runs/<id>/ as always.
"""

from __future__ import annotations

import hashlib
import json
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

# The EXACT diag4a inputs, verbatim from the rescued driver
# (harness/diag4a_reference/diag4a_driver.py).
SAME_DOMAIN = "mean-flow structure and vortex strength in laminar lid-driven cavity flows"
ALT_DOMAIN = (
    "secondary corner eddies and their dependence on Reynolds number in "
    "two-dimensional laminar lid-driven cavity flow"
)
DOMAINS = {"same": SAME_DOMAIN, "alt": ALT_DOMAIN}

# md5 (first 8 hex chars) of stage1/retrieved_memory.json in every diag4a
# run dir — the comparability pin for the memory block.
EXPECTED_MEMORY_MD5 = "373c886b"

DEFAULT_REPEATS = 2          # PROVING size: 2 repeats x 2 domains = 4 runs
MAX_RELAUNCHES = 2           # extra attempts after an ABORTED run, per slot
INTER_RUN_SLEEP_S = 180      # the driver's arXiv-courtesy spacing

# Observed single-run cost, for the dry-run estimate only (provenance: the
# chunk-3 reflect6smoke run counted 40 model_call + 9 web_search calls; the
# four completed diag4a runs took 3285-4134 s wall each).
EST_MODEL_CALLS_PER_RUN = "≈40-50 model_call + ≈9 web_search"
EST_WALL_PER_RUN = "≈55-70 min"


def current_model_pins() -> dict:
    """The stage pins the battery would run under, read from the live
    modules — recorded in every results file for cross-run comparability."""
    import model_call
    from retrieval import web_search
    from stages import generation_strategies, reflection_reviews, stage1_ideation

    return {
        "stage1_ideation.SONNET_MODEL": stage1_ideation.SONNET_MODEL,
        "stage1_ideation.OPUS_MODEL": stage1_ideation.OPUS_MODEL,
        "generation_strategies.SONNET_MODEL": generation_strategies.SONNET_MODEL,
        "reflection_reviews.SONNET_MODEL": reflection_reviews.SONNET_MODEL,
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
    }


def _delta(after: dict, before: dict) -> dict:
    return {
        section: {
            k: after[section].get(k, 0) - before[section].get(k, 0)
            for k in set(after[section]) | set(before[section])
        }
        for section in ("model_calls", "attempts")
    }


def _launch_one(slot: str, domain: str) -> dict:
    """One ideation attempt: baton built exactly as the diag4a driver builds
    it (mirroring supervisor.main()), stages.stage1_ideation.run(baton)
    unchanged, baton_after_stage_1.json written on success. Returns the
    attempt record; classification comes from the survival counter."""
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
        out = stage1_ideation.run(baton)
        (run_dir / "baton_after_stage_1.json").write_text(out.to_json())
    except Exception as exc:  # classified from disk below, never re-raised
        exception_text = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
    wall_s = round(time.perf_counter() - t0, 1)

    counted = survival_counter.count_run(run_dir)
    memory_md5 = _memory_md5(run_dir)
    comparable = memory_md5 == EXPECTED_MEMORY_MD5
    record = {
        "run_id": run_id,
        "slot": slot,
        "wall_s": wall_s,
        "exception": exception_text,
        "memory_md5": memory_md5,
        "comparable": comparable,
        "cost_delta": _delta(_meter_totals(), meter_before),
        **{k: counted[k] for k in (
            "status", "k", "k_reason",
            "initial_survivor_count", "deep_verify_discards",
            "deep_verify_kill_rate", "abort_reason",
        )},
    }
    if exception_text and counted["status"] == survival_counter.STATUS_SCORED and counted["k"]:
        # e.g. a ranking-step raise AFTER survivors.json was written: k is
        # known, the failure happened downstream of the number we measure.
        record["note"] = "exception_after_scoring — k read from disk is valid"
    return record


def print_dry_run(repeats: int) -> None:
    """The launchability proof: the full run plan and expected cost, with
    NO ideation fired and nothing written."""
    plan = build_run_plan(repeats)
    print()
    print("=" * 18 + " KILL-RATE BATTERY — DRY RUN (no ideation fired) " + "=" * 18)
    print(f"repeats per domain: {repeats}   total runs: {len(plan)}")
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
    print(f"expected cost (estimate from diag4a/reflect6smoke observations): "
          f"{EST_MODEL_CALLS_PER_RUN} calls per run, {EST_WALL_PER_RUN} wall per run")
    print(f"  -> for {len(plan)} runs: ≈{40 * len(plan)}-{50 * len(plan)} model_call + "
          f"≈{9 * len(plan)} web_search calls, "
          f"≈{len(plan) * 55 / 60:.1f}-{len(plan) * 70 / 60:.1f} h + sleeps")
    print("ledger invariant: ideation never reaches stage 3 or a human gate — "
          "fidelity/override ledgers must show a 0/0 delta")
    print(f"results would be written to {KILLRATE_LAST_RUN_PATH}")
    print("=" * 85)


def run_battery(repeats: int) -> int:
    """The live battery. NOT run in chunk 4 — the proving batch is the
    human's to launch in a plain Terminal later."""
    plan = build_run_plan(repeats)
    pins = current_model_pins()

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
            record = _launch_one(entry["slot"], entry["domain"])
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
        "repeats": repeats,
        "domains": DOMAINS,
        "model_pins": pins,
        "expected_memory_md5": EXPECTED_MEMORY_MD5,
        "slots": slots,
        "per_domain": per_domain,
        "totals": {
            "model_calls": meter["model_calls"],
            "attempts": meter["attempts"],
            "tokens": meter["tokens"],
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
    activity = report["ledger_activity"]
    print(f"LEDGER ACTIVITY this battery: fidelity_entries={activity['fidelity_entries']} "
          f"override_entries={activity['override_entries']}"
          + ("" if activity["fidelity_entries"] == 0 and activity["override_entries"] == 0
             else "   *** CRITICAL: the battery wrote a production ledger ***"))
    print("=" * 70)

    with open(KILLRATE_LAST_RUN_PATH, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"report written to {KILLRATE_LAST_RUN_PATH}")
    return 0
