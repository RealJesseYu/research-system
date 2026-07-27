"""runbooks.py — the operating knowledge an agent should not have to re-buy.

THE PROBLEM. Every capability lane in this project is a DOOR: a shelf profile, a
connector, a rented GPU. The agent is told the doors exist. What it is not told
is what is on the other side — that Chai-1's 5.7 GB embedding download breaks and
there is a flag to skip it, that Boltz-2 currently dies on a kernel version skew,
that a pip console script needs its venv on PATH, that ESMFold folds ubiquitin in
109 seconds for four cents. That knowledge was bought once, with real money and
real debugging, and it lived only in memos the agent never reads. Without it,
every run rediscovers the same failures on its own budget.

THE SHAPE, borrowed openly from Claude Science. A runbook is a markdown file with
YAML frontmatter: a `description` short enough to select on, and a body of
operating detail — the exact invocation, what comes back, the known failure modes,
what it costs. No code. The agent reads one only when it reaches for that tool.

WHAT WE ADD THAT THEY DO NOT HAVE, and it is the whole difference: a
**RECORDING THE RESULT** section. Claude Science's runbooks stop at "how to run
it" because nothing there re-runs a result. Here a number has to survive the
verification wall, and *how* it survives differs per tool — a local shelf result
is an artifact directly, a remote result is an input whose findings must be
recomputed locally. A runbook that omitted that would teach the agent to produce
numbers it cannot keep.

HOW IT REACHES THE AGENT. `runbook_catalog()` composes a short INDEX — names and
one-line descriptions only — into the experimenter's prompt. The bodies stay on
disk and are read on demand. That keeps a prompt that would otherwise grow
without bound to a dozen lines, and it means adding a runbook needs no code
change at all: drop a file in `runbooks/`.

HONESTY RULE FOR A RUNBOOK: it records what was OBSERVED, including tools that do
NOT work. A runbook saying "Boltz-2 fails here, this far in, for this reason" is
worth more than its absence — absence invites the agent to spend an hour and a
dollar finding out for itself.
"""

from __future__ import annotations

import re
from pathlib import Path

RUNBOOK_DIR = Path(__file__).resolve().parent.parent / "runbooks"

# Frontmatter keys a runbook may declare. `status` is this project's addition:
# an agent deciding whether to reach for a tool wants to know it is known-broken
# before it spends anything.
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _parse_frontmatter(text: str) -> dict:
    """Pull the YAML-ish frontmatter into a dict. Deliberately a tiny parser and
    not a YAML dependency: the fields are flat strings, and a runbook that does
    not parse should degrade to 'no metadata' rather than break prompt assembly.
    Never raises."""
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def all_runbooks(path=None) -> list:
    """Every runbook as {name, description, status, path}, sorted by name.
    Never raises: an unreadable directory or file yields fewer entries, never an
    exception — a broken runbook must not take down a run."""
    directory = Path(path) if path else RUNBOOK_DIR
    found = []
    try:
        files = sorted(directory.glob("*.md"))
    except OSError:
        return []
    for f in files:
        try:
            meta = _parse_frontmatter(f.read_text())
        except OSError:
            continue
        found.append({
            "name": meta.get("name") or f.stem,
            "description": meta.get("description", ""),
            "status": meta.get("status", ""),
            "path": str(f),
        })
    return found


def runbook_catalog(path=None) -> str:
    """The model-visible INDEX — names, one-liners, and where to read the rest.
    Empty string when no runbooks exist, so a tree without them composes an
    identical prompt."""
    books = all_runbooks(path)
    if not books:
        return ""
    lines = [
        "RUNBOOKS — operating notes for specific tools, written from runs that "
        "actually happened. Each one holds the exact invocation, what comes "
        "back, the failure modes already hit, and how to record a result so it "
        "survives verification. READ THE FILE before using that tool; it will "
        "save you the failures someone already paid for. They live in "
        "runbooks/ and are plain markdown — open one with Read.",
    ]
    for b in books:
        status = f"  [{b['status']}]" if b["status"] else ""
        lines.append(f"- {b['name']}{status} — {b['description']}")
    return "\n".join(lines)


def load_runbook(name: str, path=None) -> str | None:
    """One runbook's full text by name, or None. For a caller that wants to
    inline a body rather than have the agent read the file itself."""
    for b in all_runbooks(path):
        if b["name"] == name:
            try:
                return Path(b["path"]).read_text()
            except OSError:
                return None
    return None
