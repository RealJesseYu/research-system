"""
ledgers.py — the two decision ledgers (Step 16.6 chunk 2): append-only JSONL
files beside journal.jsonl that make the system's decision data stop
evaporating.

- fidelity_ledger.jsonl: one entry per fidelity-gate verdict, with a
  reserved `outcome` slot (null until a real-world result later fills it —
  that join is the point of Step 21, so run_id + timestamp are on every
  entry from the first).
- override_ledger.jsonl: one entry per HUMAN gate resolution — system's own
  decision vs the human's, and whether the human overrode. Auto mode writes
  nothing here: no human decided, so there is nothing to record.

Same discipline as journal.py: append-only (no update, no delete), one JSON
object per line so a crash mid-run can never corrupt earlier entries. Like
cost_meter.py this is a LEAF module — it imports nothing project-local, so
any layer (stages, supervisor, harness) can import it without inverting the
layer order. Writers are purely observational hooks at their producers:
recording never changes what a gate returns or how control flows.

Rationales are summarized AT THE SOURCE (the caller passes the gate's own
one-sentence rationale, never a transcript); RATIONALE_CAP is a defensive
backstop, not the summarization mechanism.

A writer must be safe to call without a run_id (bare/placeholder calls):
any falsy run_id is written as JSON null rather than crashing.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

FIDELITY_LEDGER_PATH = Path(__file__).parent / "fidelity_ledger.jsonl"
OVERRIDE_LEDGER_PATH = Path(__file__).parent / "override_ledger.jsonl"

# Defensive backstop only — callers pass an already-short rationale.
RATIONALE_CAP = 300


def _normalize_run_id(run_id: Any) -> Optional[str]:
    """A missing/falsy run_id becomes None (JSON null) — never a crash."""
    if not run_id:
        return None
    return str(run_id)


def _append(path: Path, entry: dict) -> dict:
    """Append one entry as a single JSONL line, creating the file if absent.

    Returns the entry actually written (timestamp filled in).
    """
    entry = dict(entry)
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def fidelity_append(
    run_id: Any,
    verdict: str,
    substrate: Optional[str],
    rationale: str,
) -> dict:
    """Record one fidelity-gate verdict (trust / refine / defer — the gate's
    exact vocabulary, passed through verbatim).

    `substrate` is the substrate the experiment was judged against, or None
    if the producer site had none available. `outcome` is reserved: always
    written null now; a later real-world result fills it (Step 21).
    """
    text = str(rationale).strip()
    if len(text) > RATIONALE_CAP:
        text = text[:RATIONALE_CAP].rstrip() + "…"
    return _append(
        FIDELITY_LEDGER_PATH,
        {
            "run_id": _normalize_run_id(run_id),
            "verdict": verdict,
            "substrate": substrate,
            "rationale": text,
            "outcome": None,
        },
    )


def override_append(
    run_id: Any,
    gate: int,
    system_decision: Any,
    human_decision: str,
    did_override: bool,
) -> dict:
    """Record one HUMAN gate resolution (gate 1, 2, or 5): the system's own
    decision/recommendation at that gate, the human's decision, and whether
    the human's choice differed. Called only when a human actually decided —
    auto mode never reaches this writer.
    """
    return _append(
        OVERRIDE_LEDGER_PATH,
        {
            "run_id": _normalize_run_id(run_id),
            "gate": gate,
            "system_decision": system_decision,
            "human_decision": human_decision,
            "did_override": bool(did_override),
        },
    )


def count_entries(path: Path) -> int:
    """Count entries (non-empty lines) in a ledger file; 0 if absent.

    Deterministic read-side for the harness's ledger-activity delta — it
    never parses or returns entry contents.
    """
    if not path.exists():
        return 0
    with open(path) as f:
        return sum(1 for line in f if line.strip())
