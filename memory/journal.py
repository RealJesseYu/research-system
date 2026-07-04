"""
journal.py — the experiment journal: an append-only, on-disk record of what
each run did. This is long-term memory living outside any AI's context, per
CLAUDE.md's memory invariant.

Append-only matters because a memory that can be silently rewritten isn't a
trustworthy record — if old entries could be edited or deleted, nothing here
could ever be trusted as "what actually happened," which defeats the point of
keeping a journal at all. So this module only ever adds lines to
journal.jsonl; it has no update or delete.

Storage: one JSON object per line (JSON Lines), so a partial write or a crash
mid-run can never corrupt earlier entries — each line stands alone.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOURNAL_PATH = Path(__file__).parent / "journal.jsonl"

REQUIRED_FIELDS = ("run_id", "kind", "text")


def journal_append(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one entry to the journal. Fills in `timestamp` if the caller omitted it.

    Required keys: run_id, kind, text. Optional: extras (a dict).
    Returns the entry actually written (with timestamp/extras filled in).
    """
    entry = dict(entry)
    entry.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    entry.setdefault("extras", {})
    for field in REQUIRED_FIELDS:
        if field not in entry:
            raise ValueError(f"journal entry missing required field: {field}")

    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def journal_search(
    keyword: str | None = None,
    run_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return matching journal entries, most-recent-first.

    keyword: plain substring match against `text`, case-insensitive. No TF-IDF —
    the journal is too young for that machinery to earn its keep yet.
    run_id: exact match.
    limit: cap on the number of entries returned.
    """
    if not JOURNAL_PATH.exists():
        return []

    entries = []
    with open(JOURNAL_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    entries.reverse()  # most-recent-first (file is append-only, oldest-first on disk)

    if run_id is not None:
        entries = [e for e in entries if e.get("run_id") == run_id]
    if keyword is not None:
        needle = keyword.lower()
        entries = [e for e in entries if needle in e.get("text", "").lower()]
    if limit is not None:
        entries = entries[:limit]
    return entries
