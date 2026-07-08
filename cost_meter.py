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

from typing import Any, Optional

# The two doors, named so read() always reports both (a zero is information:
# it says that door genuinely did not fire this run).
KNOWN_SOURCES = ("model_call", "web_search")

_calls: dict[str, int] = {}
_attempts: dict[str, int] = {}
_tokens: dict[str, dict[str, int]] = {}


def reset() -> None:
    """Zero the meter. Called at the start of each harness run."""
    _calls.clear()
    _attempts.clear()
    _tokens.clear()


def record_attempt(source: str) -> None:
    """Record one SDK attempt from `source`, BEFORE the call fires.

    Step 16.6 chunk 2 (cost-per-run honesty): record_call counts COMPLETED
    calls only, so a transport attempt that raises mid-stream (the Step-16
    retry path) fired a real call the meter missed. Each door records an
    attempt immediately before invoking the SDK, so a mid-stream failure
    still leaves a trace; attempts >= calls, and the gap is exactly the
    calls that fired but never completed.
    """
    _attempts[source] = _attempts.get(source, 0) + 1


def record_call(source: str, usage: Optional[Any] = None) -> None:
    """Record one completed SDK call from `source` (+ its usage dict, if any).

    Called by each door exactly once per completed SDK invocation, AFTER the
    response stream has been consumed. Never raises usefully upward — but it
    is also so simple it has no failure mode beyond a programming error.
    """
    _calls[source] = _calls.get(source, 0) + 1
    if isinstance(usage, dict):
        bucket = _tokens.setdefault(source, {})
        for key, value in usage.items():
            # bool is an int subclass; exclude it so a stray flag never
            # masquerades as a token count.
            if isinstance(value, int) and not isinstance(value, bool):
                bucket[key] = bucket.get(key, 0) + value


def read() -> dict:
    """Snapshot the meter: per-door call counts + combined total, per-door
    ATTEMPT counts (recorded before each SDK call fires) + combined total,
    and per-door token-field sums + a combined per-field total.

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

    return {
        "model_calls": calls_report,
        "attempts": attempts_report,
        "tokens": tokens_report,
    }
