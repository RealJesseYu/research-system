"""liveview/render.py — a snapshot, drawn as text a human can read at a glance.

Pure: snapshot dict in, list of lines out. No I/O, no clock beyond what the snapshot
carries, so the terminal view and any other consumer draw the same picture and the
whole thing is testable without a running study.

The ordering is deliberate and answers, top to bottom, the questions a watcher
actually has: is it alive, what is it doing right now, what did the director just
decide and why, what has it found, what has it spent, and what went wrong (and did
any of it matter).
"""

from __future__ import annotations

import textwrap
import time
from typing import Optional

from liveview.reader import STATE_WORD

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
GREY = "\033[90m"

_STATE_COLOR = {
    "running": GREEN,
    "finished": CYAN,
    "ended-badly": RED,
    "vanished": RED,
    "unknown": YELLOW,
}

_SEVERITY_COLOR = {"fatal": RED, "recorded": YELLOW, "watch": BLUE}
_SEVERITY_LABEL = {"fatal": "FATAL", "recorded": "recorded", "watch": "watch"}


class _Painter:
    """Colors, unless the caller asked for none (a pipe, a file, a test)."""

    def __init__(self, color: bool = True):
        self.color = color

    def __call__(self, text: str, *codes: str) -> str:
        if not self.color or not codes:
            return text
        return "".join(codes) + text + RESET


def _age(seconds: Optional[float]) -> str:
    """A duration a human reads without arithmetic."""
    if seconds is None:
        return "?"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def _tokens(n: Optional[int]) -> str:
    n = n or 0
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def _wrap(text: str, width: int, indent: str = "") -> list:
    if not text:
        return []
    out = []
    for para in str(text).splitlines():
        if not para.strip():
            continue
        out.extend(
            textwrap.wrap(
                para.strip(), width=max(20, width - len(indent)),
                initial_indent=indent, subsequent_indent=indent,
            )
        )
    return out


def _clip(text: Optional[str], n: int) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def render(snap: dict, *, width: int = 100, color: bool = True,
           reasoning_lines: int = 8, log_lines: int = 6,
           show_events: int = 8) -> list:
    """Draw the whole view. Returns a list of lines (no trailing newlines)."""
    c = _Painter(color)
    W = max(60, width)
    L: list = []

    if not snap.get("root"):
        return [c(snap.get("error", "no study to show"), RED)]

    root = snap["root"]
    active = snap.get("active") or root
    h = snap.get("health") or {}
    tot = snap.get("totals") or {}

    # --- header: alive or not, and what this study is ---------------------- #
    state_color = _STATE_COLOR.get(h.get("state"), YELLOW)
    stamp = time.strftime("%H:%M:%SZ", time.gmtime(snap.get("at") or time.time()))
    L.append(c("═" * W, GREY))
    headline = f" {h.get('headline', '')}"
    pad = " " * max(1, W - len(headline) - len(stamp))
    L.append(c(headline, BOLD, state_color) + pad + c(stamp, GREY))
    if h.get("detail"):
        L.extend(c(x, GREY) for x in _wrap(h["detail"], W, "   "))
    ident = f" {root.get('study_id')}  ·  {root.get('mode') or '?'} mode"
    budget = root.get("budget") or {}
    if budget:
        ident += (f"  ·  budget {budget.get('remaining')} of "
                  f"{budget.get('total_at_node')} moves left")
    if tot.get("studies", 1) > 1:
        ident += f"  ·  {tot['studies']} studies (incl. sub-investigations)"
    L.append(c(ident, DIM))
    L.extend(c(x, GREY) for x in _wrap("GOAL  " + (root.get("goal") or "?"), W, " "))
    L.append(c("═" * W, GREY))

    # --- now: the live phase, at the deepest node that is moving ----------- #
    L.append("")
    phase = active.get("phase") or "?"
    where = ""
    if active.get("study_id") != root.get("study_id"):
        where = c(f"   (in sub-investigation {active['study_id']})", GREY)
    L.append(c(" NOW  ", BOLD) + c(phase, BOLD, state_color) + where)

    flight = active.get("in_flight") or {}
    run = flight.get("run") or {}
    if run:
        bits = [f"run {run.get('run_id')}"]
        if run.get("elapsed") is not None:
            bits.append(f"running {_age(run['elapsed'])}")
        if run.get("last_write_age") is not None:
            bits.append(f"last wrote {_age(run['last_write_age'])} ago")
        bits.append(f"workspace {run.get('workspace_files', 0)} file(s)")
        bits.append(f"log {run.get('log_bytes', 0)}B")
        L.append(c("      " + "  ·  ".join(bits), GREY))
        for line in (run.get("log_tail") or [])[-log_lines:]:
            L.append(c("      │ ", GREY) + c(_clip(line, W - 10), DIM))
    elif flight.get("action") == "deciding":
        L.append(c("      the director is thinking — no move is running right now", GREY))
    if active.get("state") == "running" and active.get("quiet_seconds") is not None:
        L.append(c(f"      nothing on disk has changed for "
                   f"{_age(active['quiet_seconds'])}", GREY))

    # --- the director's latest reasoning, in its own words ----------------- #
    # The newest decision file can be caught mid-flush; the last COMPLETE turn is
    # the last one whose words can be trusted, so that is what gets shown.
    decisions = [d for d in (active.get("decisions") or []) if not d.get("incomplete")]
    if decisions:
        d = decisions[-1]
        timing = d.get("timing") or {}
        L.append("")
        L.append(c(f" DIRECTOR'S LATEST TURN  (decision {d.get('seq')}"
                   f"{', ' + str(timing.get('model')) if timing.get('model') else ''}"
                   f"{', %.1fs' % timing['duration_seconds'] if timing.get('duration_seconds') else ''})",
                   BOLD))
        if d.get("reading"):
            L.append(c("   WHAT IT READ", CYAN))
            L.extend(_wrap(d["reading"], W, "     ")[:reasoning_lines])
        L.append(c("   WHAT IT CHOSE", CYAN) + "  "
                 + c(str(d.get("action")), BOLD)
                 + (f" on {d.get('instrument')}" if d.get("instrument") else "")
                 + (" [campaign]" if d.get("campaign") else ""))
        if d.get("reasoning"):
            L.append(c("   WHY", CYAN))
            L.extend(_wrap(d["reasoning"], W, "     ")[:reasoning_lines])
        if d.get("stop_reason"):
            L.append(c("   STOP REASON", CYAN))
            L.extend(_wrap(d["stop_reason"], W, "     ")[:reasoning_lines])

    # --- the arc so far ----------------------------------------------------- #
    L.append("")
    L.append(c(f" THE ARC SO FAR  ({tot.get('moves', 0)} move(s) across "
               f"{tot.get('studies', 1)} study/studies)", BOLD))
    L.extend(_arc_lines(root, c, W))

    # --- what stood, and what it cost -------------------------------------- #
    verified, claims = tot.get("verified", 0), tot.get("claims", 0)
    rate = f"{verified}/{claims}"
    ver_color = GREEN if claims and verified == claims else (
        YELLOW if verified else RED)
    L.append("")
    reported = root.get("spend_reported") or {}
    L.append(" " + c("VERIFIED ", BOLD) + c(rate, ver_color)
             + c(" claims reproduced", GREY)
             + c("   ·   SPEND ", BOLD)
             + f"{tot.get('calls', 0)} call(s), {_tokens(tot.get('tokens'))} tokens "
             + c("in runs across the tree", GREY)
             + (c(f" · this study's report: {reported.get('calls')} calls, "
                  f"{_tokens(reported.get('tokens'))} (its own runs + its director)", GREY)
                if reported else "")
             + (c(f"   ·   {tot.get('moves', 0)} moves", GREY)))

    # --- failures, and whether any of them matter -------------------------- #
    events = snap.get("events") or []
    counts = h.get("counts") or {}
    L.append("")
    L.append(" " + c("FAILURES  ", BOLD)
             + c(f"{counts.get('fatal', 0)} fatal", RED if counts.get("fatal") else GREY)
             + c("  ·  ", GREY)
             + c(f"{counts.get('recorded', 0)} recorded",
                 YELLOW if counts.get("recorded") else GREY)
             + c("  ·  ", GREY)
             + c(f"{counts.get('watch', 0)} to watch",
                 BLUE if counts.get("watch") else GREY))
    for e in events[:show_events]:
        sev = e.get("severity", "recorded")
        L.append("   " + c(f"[{_SEVERITY_LABEL.get(sev, sev)}]",
                           _SEVERITY_COLOR.get(sev, YELLOW))
                 + " " + _clip(e.get("title"), W - 16)
                 + (c(f"  ({e['study_id']})", GREY)
                    if e.get("study_id") and e["study_id"] != root.get("study_id") else ""))
        if e.get("detail"):
            L.extend(c(x, GREY) for x in _wrap(_clip(e["detail"], 300), W, "        "))
        L.extend(c(x, DIM) for x in _wrap("→ " + (e.get("means") or ""), W, "        "))
    if len(events) > show_events:
        L.append(c(f"   … and {len(events) - show_events} more", GREY))
    L.append("")
    L.extend(
        c(x, DIM)
        for x in _wrap(
            "A RECORDED failure is data: it is written to the arc, the director reads "
            "it on its next turn, and the study continues. A traceback printed by a "
            "child process is one of these. Only a FATAL line means the investigation "
            "itself ended.",
            W, "   ",
        )
    )
    return L


# The MARK is presentational and lives here; the WORD is semantic and lives in
# reader.STATE_WORD, so no two surfaces can disagree about whether a move failed.
_STATE_MARK = {"stood": ("✓", GREEN), "ran": ("◐", BLUE), "did_not_run": ("✗", RED)}
_LABEL_W = 9


def _field(c: _Painter, W: int, indent: str, label: str, text, *,
           limit: Optional[int] = None) -> list:
    """One labelled field, WRAPPED to the width with a hanging indent.

    Wrapped rather than clipped because clipping is what made the old arc
    unreadable: a domain string, a blocker's human_action and a finding all had
    their load-bearing half past the cut, and `…` does not tell you what you lost.
    `limit` bounds a very long field in LINES and marks that it was cut, so one
    verbose move can still never push the rest of the arc off the screen.
    """
    if not text:
        return []
    hang = indent + "  " + " " * _LABEL_W
    lines = _wrap(str(text), W, hang)
    if not lines:
        return []
    if limit and len(lines) > limit:
        lines = lines[:limit]
        lines[-1] = lines[-1] + " …"
    # Overwrite the first line's hanging indent with the label, so the label column
    # and the text column line up no matter how deeply a sub-study is nested.
    lines[0] = (indent + "  " + c(f"{label:<{_LABEL_W - 1}}", DIM) + " "
                + lines[0][len(hang):])
    return lines


def _arc_lines(node: dict, c: _Painter, W: int, indent: str = "  ") -> list:
    """The arc as a labelled block per move, sub-investigations nested under the move
    that spawned them, so the shape of the investigation is visible."""
    out: list = []
    children = {ch.get("study_id"): ch for ch in node.get("children") or []}
    for a in node.get("arc") or []:
        state = a.get("state") or ("stood" if a.get("succeeded") else "ran")
        mark_ch, mark_col = _STATE_MARK.get(state, ("·", GREY))
        counts = ""
        if a.get("results_total"):
            good = a["results_verified"] == a["results_total"]
            counts = c(f"{a['results_verified']}/{a['results_total']} verified",
                       GREEN if good else YELLOW)
        elif a.get("child_termination"):
            counts = c(str(a["child_termination"]), GREY)
        # A fan member's move_type is the bare string "single", so name it by its
        # place in the fan instead — the label is otherwise identical N times over.
        kind = str(a.get("move_type"))
        if a.get("fan_width"):
            kind = f"fan {a.get('fan_index')}/{a.get('fan_width')}"
        # The STATE IN WORDS on the head line. A bare ✗ next to "21/21 verified" is
        # the thing that made a watcher ask why every move had failed.
        out.append(f"{indent}{c(mark_ch, mark_col)} {a.get('seq')}. "
                   f"{c(kind, BOLD)}  {c(STATE_WORD[state], mark_col)}"
                   + ("  ·  " + counts if counts else ""))
        # One labelled, WRAPPED field per thing worth knowing. Wrapped, not clipped:
        # every one of these fields had its interesting half past the cut before.
        out += _field(c, W, indent, "asked", a.get("domain"), limit=4)
        out += _field(c, W, indent, "outcome",
                      a.get("outcome_plain") or a.get("outcome"), limit=2)
        # The parent fan's reasoning is copied onto every member; print it once.
        if a.get("finding") and not a.get("finding_repeats_fan"):
            out += _field(c, W, indent, "why", a.get("finding"), limit=4)
        # WHAT an ideation call actually proposed. Without this a watcher sees
        # "call_ideation ✓ done" and nothing about the ideas — the most
        # interesting thing that happens in an ideation turn.
        for i, stmt in enumerate((a.get("hypotheses") or [])[:6]):
            out += _field(c, W, indent, "idea" if i == 0 else "", stmt, limit=3)
        # Anything a human could unblock, surfaced where they will see it.
        for b in (a.get("blocked_on") or []):
            out += _field(c, W, indent, "BLOCKED",
                          f"{b.get('need')} — YOU CAN: {b.get('human_action')}",
                          limit=6)
        # T0.1: a number this move established that contradicts one the study
        # already held. Same surface as BLOCKED, because it is the same kind of
        # thing — something a watcher wants to know NOW rather than in §5.2 of
        # the write-up, which is where the measured instance of this surfaced.
        for q in (a.get("quantity_conflicts") or []):
            out += _field(c, W, indent, "CONFLICT",
                          f"{q.get('quantity')} — {q.get('detail')}", limit=6)
        child = children.get(a.get("child_study_id"))
        if child:
            out.extend(_arc_lines(child, c, W, indent + "     "))
    flight = node.get("in_flight") or {}
    if node.get("state") == "running" and flight.get("action") not in (None, "deciding"):
        out.append(f"{indent}{c('▸', BLUE)} {len(node.get('arc') or []) + 1}. "
                   + c(f"{flight.get('action')} — running now", BLUE))
        child = children.get(flight.get("child_study_id"))
        if child:
            out.extend(_arc_lines(child, c, W, indent + "     "))
    if not out:
        out.append(c(f"{indent}(no moves recorded yet)", GREY))
    return out
