"""gpu_budget.py — the one place real dollars are counted.

WHY THIS IS DIFFERENT FROM EVERY OTHER BUDGET HERE. `cost_meter.py` opens with
"there is no dollar cost per run (auth is subscription); cost is measured in
MODEL CALLS and WALL-TIME", and `pi_agent/budget.py` counts MOVES, converting a
`--cost-cap` into a move ceiling through an estimate while noting that "real
mid-run cost enforcement waits on per-run cost reporting (a later Phase-1 task)".

Both were right for a system whose only spend was model calls on a subscription.
The remote lane (`tools/run_remote_job.py`) changed that: rented GPU time is
billed by the second to the owner's card. This is the first place the system can
actually cost money, so it is the first place a dollar ceiling means anything —
and it is enforced here, at the door, rather than estimated at the root.

THE ACCOUNTING, and why it is deliberately pessimistic in one direction:

  * BEFORE dispatch, a job is checked against its WORST CASE — the full timeout
    at the GPU's rate — because that is the most it can possibly cost and the
    check has to happen before the money is spent. A job that might fit but
    might not is refused.
  * AFTER it returns, the ACTUAL seconds are recorded. The ledger therefore
    tells the truth about what was spent, while the gate refuses on what could
    have been. Reserving worst-case and recording actual is the only combination
    that neither overspends nor lies.

THE LEDGER IS A FILE, not an in-process counter, and that is load-bearing: a
campaign dispatches runs as SUBPROCESSES, so an in-process total would reset
every run and a "cap" would bound nothing. `memory/gpu_spend.jsonl` is
append-only, in the house idiom of `memory/override_ledger.jsonl`.

RATES ARE ESTIMATES AND ARE DELIBERATELY HIGH. They are rounded up from Modal's
published per-second pricing; an over-estimate refuses earlier and can never
overshoot the cap, the same discipline `EST_COST_PER_MOVE_USD` already follows.
They are not a billing record — the provider's invoice is the truth, and an
operator who cares about the exact figure should read it there.

DELEGATION. The ceiling is read from `RESEARCH_GPU_BUDGET_USD`, the same
environment channel every other run-scoped constraint uses (`ALLOWED_SUBSTRATES`,
`RESEARCH_CAMPAIGN`, `CAMPAIGN_MAX_ITERS`). A director hands a child run a
SLICE of its allowance by setting that variable on the subprocess — the
`pi_agent/budget.py` allocate() idea, in dollars, across a process boundary.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Append-only, one record per dispatched job. Lives beside the other ledgers.
LEDGER_PATH = _PROJECT_ROOT / "memory" / "gpu_spend.jsonl"

# The ceiling, in USD. Owner-set 2026-07-27: $100 standing allowance.
BUDGET_ENV = "RESEARCH_GPU_BUDGET_USD"
DEFAULT_BUDGET_USD = 100.0

# USD per hour, ROUNDED UP from Modal's published rates. High on purpose (see
# the module docstring). "cpu" covers a remote job that asked for no GPU.
RATES_USD_PER_HOUR = {
    "cpu": 0.20,
    "T4": 0.80,
    "L4": 1.00,
    "A10G": 1.40,
    "A100": 2.50,
    "A100-80GB": 3.00,
    "H100": 4.50,
}


def rate_for(gpu) -> float:
    """USD/hour for a GPU name, or for CPU when gpu is None. An UNKNOWN name
    bills at the most expensive rate rather than a default cheap one: the
    failure to avoid is a cap that silently under-counts."""
    if gpu is None:
        return RATES_USD_PER_HOUR["cpu"]
    return RATES_USD_PER_HOUR.get(gpu, max(RATES_USD_PER_HOUR.values()))


def estimate_usd(gpu, seconds: float) -> float:
    """What `seconds` on `gpu` costs, at the pessimistic rate. Pure."""
    try:
        secs = max(0.0, float(seconds))
    except (TypeError, ValueError):
        secs = 0.0
    return rate_for(gpu) * secs / 3600.0


def budget_usd() -> float:
    """The ceiling for this process. Unset, malformed, or non-positive falls
    back to the default — a budget that parses to nothing must not read as
    unlimited, which is the mistake `ALLOWED_SUBSTRATES` already refuses to
    make. Set it to a large number if you genuinely want a large allowance."""
    raw = os.environ.get(BUDGET_ENV)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_BUDGET_USD
    return value if value > 0 else DEFAULT_BUDGET_USD


def spent_usd(path=None) -> float:
    """Total recorded spend. Never raises: a missing or corrupt ledger reads as
    the spend it can prove, and a malformed LINE is skipped rather than taking
    down the run — but note the direction, since unreadable history reads as
    UNDER-spent, so the ledger is append-only and never rewritten."""
    p = Path(path) if path else LEDGER_PATH
    total = 0.0
    try:
        text = p.read_text()
    except OSError:
        return 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
            total += float(rec.get("usd") or 0.0)
        except (ValueError, TypeError):
            continue
    return total


def remaining_usd(path=None) -> float:
    return max(0.0, budget_usd() - spent_usd(path))


def check_affordable(gpu, seconds: float, path=None) -> tuple:
    """(ok, reason). Judged on the WORST CASE — the full timeout at this GPU's
    rate — because the check must happen before the money is spent."""
    worst = estimate_usd(gpu, seconds)
    left = remaining_usd(path)
    if worst <= left:
        return True, ""
    return False, (
        f"this job could cost up to ${worst:.2f} ({gpu or 'cpu'} for "
        f"{int(seconds)}s at ${rate_for(gpu):.2f}/hr) but only ${left:.2f} of "
        f"the ${budget_usd():.2f} GPU allowance remains "
        f"(${spent_usd(path):.2f} already recorded). Raise {BUDGET_ENV} or "
        f"shorten the job; nothing was dispatched and nothing was billed."
    )


def record(gpu, seconds: float, *, run_id=None, path=None) -> dict:
    """Append one ACTUAL-spend record and return it. Never raises: failing to
    write the ledger must not destroy a result that has already been paid for,
    so a write failure is swallowed and the record still comes back to the
    caller for its own evidence."""
    rec = {
        "ts": time.time(),
        "gpu": gpu or "cpu",
        "seconds": round(float(seconds or 0.0), 3),
        "usd": round(estimate_usd(gpu, seconds), 6),
        "rate_usd_per_hour": rate_for(gpu),
        "run_id": run_id,
        "note": "estimated from a rounded-up published rate, not a bill",
    }
    p = Path(path) if path else LEDGER_PATH
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return rec


def report(path=None) -> dict:
    """A small summary for a run's evidence or a director's next decision."""
    return {"budget_usd": budget_usd(), "spent_usd": round(spent_usd(path), 4),
            "remaining_usd": round(remaining_usd(path), 4),
            "ledger": str(Path(path) if path else LEDGER_PATH)}
