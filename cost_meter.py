"""cost_meter.py — the ONE shared per-run cost meter (Step 16.6 chunk 1).

There is no dollar cost per run (auth is subscription); cost is measured in
MODEL CALLS and WALL-TIME. This module is the call-count half of that
instrument. RECORDED RULING (Step 16.6 chunk 1): the system has TWO doors to
the model — model_call._ask_once and retrieval/web_search._search_once (the
Step-17 web-search exception, frozen by its own ruling) — and BOTH report
into this one meter, tagged by source, rather than being refactored into one
door. The two per-process transcript counters are untouched; this meter is
additive and separate from them.

Purely observational: recording never changes what either door returns to
its callers. This module imports nothing project-local (a leaf), so both the
project root and retrieval/ can import it without inverting any layer order.

In-process and per-run: reset() at the start of a harness run, read() at the
end. Token counts are accumulated VERBATIM from the SDK's
ResultMessage.usage dict — only top-level integer fields are summed, nested
structures and non-integers are ignored; nothing is invented or estimated.
If the SDK provided no usage, only the call is counted.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

# Every counter below is a read-modify-write on a shared dict, and reflection
# now runs its review chain through a ThreadPoolExecutor — so concurrent
# recorders silently lose increments without this. The lock is held only for
# the arithmetic; no I/O and no model call happens inside it.
_LOCK = threading.Lock()

# The two doors, named so read() always reports both (a zero is information:
# it says that door genuinely did not fire this run).
KNOWN_SOURCES = ("model_call", "web_search")

_calls: dict[str, int] = {}
_attempts: dict[str, int] = {}
_tokens: dict[str, dict[str, int]] = {}

# 2026-07-28 (roadmap item C): the SDK's OWN correctly-priced figure. The token
# sums above add four differently-priced quantities (input, output, cache
# creation, cache read) at face value — a cache read is ~10% the price of an
# input token — so "N tokens" was never a cost. ResultMessage.total_cost_usd IS
# the cost and num_turns is the intra-call depth signal; both were previously
# dropped on the floor. Accumulated per source, with a calls-with-value counter
# per bucket so a reader can tell "unmeasured" (count 0) from "measured zero" —
# they are different facts, and dollars must never read as 0 for a run whose
# SDK simply did not report them.
_usd: dict[str, float] = {}
_usd_calls: dict[str, int] = {}
_turns: dict[str, int] = {}
_turns_calls: dict[str, int] = {}

# Step 18.7 chunk 1: per-STAGE attribution, model_call door only. The door
# counters above are per-door and cannot see stage_name; call_stage_model
# can, and reports every COMPLETED call and every schema/validator REJECT
# here. web_search calls carry no stage_name and stay door-only, by design.
_stage_calls: dict[str, int] = {}
_stage_rejects: dict[str, int] = {}

# Step 17-fix-A: warn-only instrumentation SIGNALS, keyed by tag. A signal
# is an observation worth counting (e.g. a Generation hypothesis stating a
# number its cited snippets do not contain) that is NOT a reject — it never
# triggers a re-ask and must never contaminate the per-stage reject
# counters or any reject_rate, so it lives in its own bucket and is
# reported separately.
_signals: dict[str, int] = {}


def reset() -> None:
    """Zero the meter. Called at the start of each harness run."""
    _calls.clear()
    _attempts.clear()
    _tokens.clear()
    _usd.clear()
    _usd_calls.clear()
    _turns.clear()
    _turns_calls.clear()
    _stage_calls.clear()
    _stage_rejects.clear()
    _signals.clear()


def record_attempt(source: str) -> None:
    """Record one SDK attempt from `source`, BEFORE the call fires.

    Step 16.6 chunk 2 (cost-per-run honesty): record_call counts COMPLETED
    calls only, so a transport attempt that raises mid-stream (the Step-16
    retry path) fired a real call the meter missed. Each door records an
    attempt immediately before invoking the SDK, so a mid-stream failure
    still leaves a trace; attempts >= calls, and the gap is exactly the
    calls that fired but never completed.
    """
    with _LOCK:
        _attempts[source] = _attempts.get(source, 0) + 1


def record_call(
    source: str,
    usage: Optional[Any] = None,
    cost_usd: Optional[Any] = None,
    num_turns: Optional[Any] = None,
) -> None:
    """Record one completed SDK call from `source` (+ its usage dict, if any).

    Called by each door exactly once per completed SDK invocation, AFTER the
    response stream has been consumed. Never raises usefully upward — but it
    is also so simple it has no failure mode beyond a programming error.

    `cost_usd` / `num_turns` (roadmap item C, 2026-07-28) are ResultMessage's
    total_cost_usd and num_turns — the SDK's own correctly-priced cost and the
    call's agentic-loop depth. Both are optional and type-guarded here rather
    than at the door, so a missing/odd-shaped value from any SDK version is
    silently not recorded (observation-only discipline: recording may never
    sink a call). A value that is absent simply leaves the calls-with-value
    counter untouched — read() reporting distinguishes that from a real zero.
    """
    with _LOCK:
        _calls[source] = _calls.get(source, 0) + 1
        if isinstance(usage, dict):
            bucket = _tokens.setdefault(source, {})
            for key, value in usage.items():
                # bool is an int subclass; exclude it so a stray flag never
                # masquerades as a token count.
                if isinstance(value, int) and not isinstance(value, bool):
                    bucket[key] = bucket.get(key, 0) + value
        if isinstance(cost_usd, (int, float)) and not isinstance(cost_usd, bool):
            _usd[source] = _usd.get(source, 0.0) + float(cost_usd)
            _usd_calls[source] = _usd_calls.get(source, 0) + 1
        if isinstance(num_turns, int) and not isinstance(num_turns, bool):
            _turns[source] = _turns.get(source, 0) + num_turns
            _turns_calls[source] = _turns_calls.get(source, 0) + 1


def record_stage_call(stage_name: str) -> None:
    """Attribute one COMPLETED model_call-door call to `stage_name`.

    Step 18.7 chunk 1: fired by call_stage_model immediately after the
    transport returns a completed reply — the one point where both the
    completion and the stage are known. Gives reject-RATE a denominator
    (rejects/calls per stage), not just a raw reject count.
    """
    with _LOCK:
        _stage_calls[stage_name] = _stage_calls.get(stage_name, 0) + 1


def record_reject(stage_name: str) -> None:
    """Record one REJECT for `stage_name`: a completed call whose output
    failed schema or extra_validator and is being re-asked.

    Step 18.7 chunk 1: fired by call_stage_model at the re-ask point,
    alongside the durable RE-ASK line. Distinct from a TRANSPORT attempt
    that raised mid-stream (those never reach validation and are already
    visible as the attempts-minus-calls gap); a reject is a new completed
    call, invisible in that gap — which is exactly why this counter exists.
    """
    with _LOCK:
        _stage_rejects[stage_name] = _stage_rejects.get(stage_name, 0) + 1


def record_signal(tag: str) -> None:
    """Record one warn-only instrumentation signal under `tag`.

    Step 17-fix-A: fired by a validator (or any observer) that noticed
    something worth counting WITHOUT rejecting the reply — the reply is
    accepted as-is and no re-ask fires. Deliberately a separate bucket from
    record_reject so signals can never inflate rejects or reject_rate.
    """
    with _LOCK:
        _signals[tag] = _signals.get(tag, 0) + 1


def _stage_stats(calls: int, rejects: int) -> dict:
    return {
        "calls": calls,
        "rejects": rejects,
        "reject_rate": round(rejects / calls, 3) if calls else 0.0,
    }


def read() -> dict:
    """Snapshot the meter: per-door call counts + combined total, per-door
    ATTEMPT counts (recorded before each SDK call fires) + combined total,
    per-door token-field sums + a combined per-field total, and per-STAGE
    {calls, rejects, reject_rate} + a "total" row (Step 18.7 chunk 1; a
    stage with zero calls this run simply does not appear), and per-tag
    warn-only SIGNAL counts (Step 17-fix-A; empty dict when none fired),
    plus per-door USD cost and TURN sums with calls-with-value coverage
    counters (item C, 2026-07-28 — coverage 0 means unknown, not zero).

    Returns a plain dict copy — callers can diff two snapshots for a
    per-case delta without touching the live counters.
    """
    calls = {source: _calls.get(source, 0) for source in KNOWN_SOURCES}
    for source, count in _calls.items():  # future doors show up rather than vanish
        calls.setdefault(source, count)
    for source in _attempts:  # an attempted-but-never-completed door still shows
        calls.setdefault(source, 0)
    calls_report = dict(calls)
    calls_report["total"] = sum(calls.values())

    attempts = {source: _attempts.get(source, 0) for source in calls}
    attempts_report = dict(attempts)
    attempts_report["total"] = sum(attempts.values())

    tokens_report: dict[str, dict[str, int]] = {
        source: dict(_tokens.get(source, {})) for source in calls
    }
    combined: dict[str, int] = {}
    for source in calls:
        for field, value in tokens_report[source].items():
            combined[field] = combined.get(field, 0) + value
    tokens_report["total"] = combined

    # Real dollars and turns (item C). calls_with_usd / calls_with_turns are
    # the coverage counters: 0 there means NOTHING reported a value this run,
    # so a reader must treat the totals as unknown, never as a measured zero.
    usd_report: dict[str, Any] = {source: round(_usd.get(source, 0.0), 6)
                                  for source in calls}
    usd_report["total"] = round(sum(_usd.get(source, 0.0) for source in calls), 6)
    usd_report["calls_with_usd"] = sum(_usd_calls.get(source, 0) for source in calls)

    turns_report: dict[str, Any] = {source: _turns.get(source, 0) for source in calls}
    turns_report["total"] = sum(_turns.get(source, 0) for source in calls)
    turns_report["calls_with_turns"] = sum(_turns_calls.get(source, 0)
                                           for source in calls)

    stages_report: dict[str, dict] = {
        stage: _stage_stats(_stage_calls.get(stage, 0), _stage_rejects.get(stage, 0))
        for stage in sorted(set(_stage_calls) | set(_stage_rejects))
    }
    stages_report["total"] = _stage_stats(
        sum(_stage_calls.values()), sum(_stage_rejects.values())
    )

    return {
        "model_calls": calls_report,
        "attempts": attempts_report,
        "tokens": tokens_report,
        "usd": usd_report,
        "turns": turns_report,
        "stages": stages_report,
        "signals": dict(_signals),
    }
