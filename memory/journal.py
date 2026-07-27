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
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

JOURNAL_PATH = Path(__file__).parent / "journal.jsonl"


def blank_memory_active() -> bool:
    """True when the run is in blank-memory mode (env BLANK_MEMORY=1, default
    off). Phase-1 Lane-2 seam: an ablation that starves every stage's retrieved
    memory. Read live each call so a test can set/unset it. This is the single
    retrieval source (all stages read memory through journal_recent_by_kind),
    so intercepting here — rather than in any stages/* composition code, which
    stays frozen — makes ALL retrieved memory blocks come back empty.
    """
    return os.environ.get("BLANK_MEMORY") == "1"

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

    # MEASURED, NOT ASSUMED (2026-07-27). An audit flagged this buffered write
    # as able to tear a line: several processes append here at once (the director
    # dispatches runs as subprocesses and sub-studies recurse), and a buffered
    # writer flushing in chunks could let another process's line land between two
    # write(2) calls of one entry.
    #
    # It does not. Tested against 8 concurrent processes x 40 entries, at 20 KB
    # and again at 400 KB per entry — above this platform's 131072-byte text
    # buffer, which is where a split would have to happen: 320 of 320 lines
    # intact, zero torn, both runs. CPython hands an oversized write straight to
    # the raw layer in a single call, and "a" mode opens with O_APPEND, so that
    # call is atomic with respect to the file offset.
    #
    # Left as-is on the strength of that measurement, per "expand only on
    # evidence" — an os.write/O_APPEND rewrite was tried and reverted because it
    # fixed nothing observable. Recorded here so the question is not re-opened
    # from first principles a third time. The real defect the audit found was on
    # the READ side below, and that one was genuine.
    with open(JOURNAL_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def _read_entries() -> tuple[list[dict[str, Any]], int]:
    """Every well-formed entry, oldest-first, plus a count of unreadable lines.

    ONE BAD LINE MUST NOT COST THE WHOLE JOURNAL. Both readers below used to do
    an unguarded json.loads per line, so a single torn or truncated line raised
    out of journal_recent_by_kind — which is the SINGLE retrieval source every
    stage's memory block reads through. One damaged line therefore broke memory
    retrieval for every subsequent run, permanently, until someone repaired the
    file by hand. (That this file already has a
    journal.jsonl.pre-correction-20260720 sibling says the damage is not
    hypothetical.)

    Skip-and-count rather than skip-and-hide: the caller reports the count, so a
    corrupt line stays visible instead of quietly shrinking what memory knows.
    """
    entries: list[dict[str, Any]] = []
    unreadable = 0
    with open(JOURNAL_PATH, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                unreadable += 1
                continue
            # A line that parses but is not an object cannot answer .get(),
            # and would raise at the filter sites instead of here.
            if isinstance(obj, dict):
                entries.append(obj)
            else:
                unreadable += 1
    return entries, unreadable


def _note_unreadable(unreadable: int) -> None:
    """Surface skipped lines once per read. Deliberately a print, matching how
    this project already reports fence-strips and re-asks: silent tolerance of a
    corrupt journal would be its own defect."""
    if unreadable:
        print(f"NOTE: journal has {unreadable} unreadable line(s), skipped — "
              f"{JOURNAL_PATH} may need repair")


def journal_recent_by_kind(kind: str, limit: int = 3) -> list[dict[str, Any]]:
    """Return the most recent entries whose `kind` matches exactly, most-recent-first.

    Deterministic read-side: a plain scan of journal.jsonl, exact string match
    on `kind`, capped at `limit`. No model involvement, no embeddings — stage
    code calls this to surface the last few observations of one kind (e.g.
    learned_summary) without any search machinery.

    Blank-memory ablation (BLANK_MEMORY=1): returns [] before any read, so
    every downstream memory block composes empty. Flag off (default): byte-
    identical to the plain scan below.
    """
    if blank_memory_active():
        return []
    if not JOURNAL_PATH.exists():
        return []

    entries, unreadable = _read_entries()
    _note_unreadable(unreadable)

    entries.reverse()  # most-recent-first (file is append-only, oldest-first on disk)
    return [e for e in entries if e.get("kind") == kind][:limit]


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

    entries, unreadable = _read_entries()
    _note_unreadable(unreadable)

    entries.reverse()  # most-recent-first (file is append-only, oldest-first on disk)

    if run_id is not None:
        entries = [e for e in entries if e.get("run_id") == run_id]
    if keyword is not None:
        needle = keyword.lower()
        entries = [e for e in entries if needle in e.get("text", "").lower()]
    if limit is not None:
        entries = entries[:limit]
    return entries
