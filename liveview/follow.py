"""follow.py — print each thing ONCE, when it happens.

WHY THIS REPLACED THE DASHBOARD AS THE DEFAULT. The repainting view redrew the
whole picture every tick. A first attempt to paint only on change compared the
RENDERED STRING — which carries a live clock in its header, so it differed every
tick and repainted every time anyway. The owner watched the same screen scroll
past for minutes and learned nothing from it.

The deeper problem was the shape, not the bug. A study is mostly quiet: an
experiment runs for many minutes and nothing changes. What a watcher wants is not
a dashboard that redraws — it is a LOG OF WHAT HAPPENED, each event printed once,
in order, with enough substance to follow the reasoning:

    the director decided X, because Y
    ideation returned these hypotheses
    a run finished: 8 of 9 verified
    BLOCKED: needs this from you

So this tracks what it has already printed and emits only what is new. It never
clears the screen and never repeats itself. Change is detected from the STUDY'S
OWN STATE — decision sequence numbers, arc length, health — never from rendered
text, so a clock in a header can no longer defeat it.

Read-only, like the rest of liveview: it touches nothing the run owns.
"""

from __future__ import annotations

import sys
import time
from typing import Optional

from liveview.reader import (RUNS_ROOT, STUDIES_ROOT, TERMINAL_HEALTH_STATES,
                             full_snapshot)

BOLD, DIM, GREEN, YELLOW, BLUE, RESET = (
    "\033[1m", "\033[2m", "\033[32m", "\033[33m", "\033[34m", "\033[0m")


def _c(text: str, code: str, color: bool) -> str:
    return f"{code}{text}{RESET}" if color else text


def _wrap(text: str, width: int, indent: str) -> list:
    words, lines, cur = str(text).split(), [], indent
    for w in words:
        if len(cur) + len(w) + 1 > width and cur.strip():
            lines.append(cur)
            cur = indent + w
        else:
            cur = (cur + " " + w) if cur.strip() else indent + w
    if cur.strip():
        lines.append(cur)
    return lines


class Follower:
    """Holds what has been printed. Pure over the snapshots it is fed, so the
    whole thing is testable without a running study."""

    def __init__(self, *, color: bool = True, width: int = 100):
        self.color = color
        self.width = width
        # KEYED BY (study_id, seq), NOT BARE seq. active_node() switches the
        # active study to the deepest RUNNING child, and every study numbers its
        # own decisions and moves from 1 — so a bare-seq set made a
        # sub-investigation's first N events look "already seen" and dropped
        # them silently. Recursion is a live, load-bearing feature, so that threw
        # away the start of every sub-study (all of it, for a short one).
        self._decisions_seen: set = set()
        self._arc_seen: set = set()
        self._blockers_seen: set = set()
        self._health = None
        # Which study the printed events currently belong to. The header used to
        # print once for the whole session, so after a switch every line was
        # attributed to the wrong study.
        self._open_study = None

    def _c(self, t, code):
        return _c(t, code, self.color)

    def events(self, snap: dict) -> list:
        """The lines to print for this snapshot — only what has not been printed
        before. Empty list when nothing happened, which is most ticks."""
        out: list = []
        active = snap.get("active") or {}
        if not active.get("exists"):
            return out

        study_id = active.get("study_id")
        if study_id != self._open_study:
            # A switch is worth announcing: "the parent is waiting on a child"
            # reads very differently from "the parent stopped".
            if self._open_study is not None:
                out.append(self._c(f"--- now following sub-study {study_id} "
                                   f"(parent {self._open_study} is waiting) ---", DIM))
            self._open_study = study_id
            out.append("")
            out.append(self._c(f"STUDY {active.get('study_id')}", BOLD)
                       + self._c(f"  ({active.get('mode')} mode)", DIM))
            out.extend(_wrap(active.get("goal") or "", self.width, "  "))
            out.append("")

        # --- the director's turns, in its own words --------------------------
        for d in active.get("decisions") or []:
            if d.get("incomplete"):
                continue                      # caught mid-write; it will reappear
            seq = d.get("seq")
            key = (study_id, seq)
            if key in self._decisions_seen:
                continue
            self._decisions_seen.add(key)
            head = f"[decision {seq}] {d.get('action')}"
            if d.get("instrument"):
                head += f" · {d['instrument']}"
            out.append(self._c(head, BLUE))
            if d.get("reading"):
                out.extend(_wrap("read: " + d["reading"], self.width, "    "))
            if d.get("reasoning"):
                out.extend(_wrap("why:  " + d["reasoning"], self.width, "    "))
            if d.get("domain"):
                out.extend(_wrap("ask:  " + d["domain"], self.width, "    ")[:4])
            if d.get("stop_reason"):
                out.extend(_wrap("stop: " + d["stop_reason"], self.width, "    "))
            out.append("")

        # --- what each move actually produced --------------------------------
        for a in active.get("arc") or []:
            seq = a.get("seq")
            key = (study_id, seq)
            if key in self._arc_seen:
                continue
            self._arc_seen.add(key)
            mark = "ok " if a.get("succeeded") else "FAILED"
            # A fan member reports move_type "single"; its position in the fan is
            # the only thing that tells one member from another in a log.
            kind = (f"fan {a.get('fan_index')}/{a.get('fan_width')}"
                    if a.get("fan_width") else str(a.get("move_type")))
            line = f"[move {seq}] {kind} — {mark}"
            if a.get("results_total"):
                line += (f" · {a.get('results_verified')}/{a.get('results_total')} "
                         "verified")
            out.append(self._c(line, GREEN if a.get("succeeded") else YELLOW))
            # The question this move was given. In the event log it is printed per
            # move rather than per decision, because one fan decision covers N moves.
            if a.get("domain"):
                out.extend(_wrap("ask:  " + a["domain"], self.width, "    ")[:4])
            for stmt in (a.get("hypotheses") or [])[:8]:
                out.extend(_wrap("· " + stmt, self.width, "    "))
            if a.get("error"):
                out.extend(_wrap("error: " + str(a["error"]), self.width, "    "))
            out.append("")

        # --- anything a human can unblock, said once and loudly --------------
        for a in active.get("arc") or []:
            for b in a.get("blocked_on") or []:
                key = str(b.get("need"))
                if key in self._blockers_seen:
                    continue
                self._blockers_seen.add(key)
                out.append(self._c("BLOCKED — a human can unlock this:", YELLOW))
                out.extend(_wrap(f"needs: {b.get('need')}", self.width, "    "))
                out.extend(_wrap(f"you can: {b.get('human_action')}", self.width,
                                 "    "))
                out.append("")

        # --- the run ending ---------------------------------------------------
        health = (snap.get("health") or {}).get("state")
        if health != self._health:
            self._health = health
            if health in TERMINAL_HEALTH_STATES:
                out.append(self._c(str((snap.get("health") or {}).get("headline")),
                                   BOLD))
                detail = (snap.get("health") or {}).get("detail")
                if detail:
                    out.extend(_wrap(detail, self.width, "  "))
                out.append("")
        return out


def follow(study_id: Optional[str] = None, *, interval: float = 4.0,
           color: bool = True, out=sys.stdout, studies_root=STUDIES_ROOT,
           runs_root=RUNS_ROOT, max_iterations: Optional[int] = None) -> int:
    """Tail a study, printing each event once. Never clears, never repeats."""
    f = Follower(color=color)
    seen_end = False
    i = 0
    try:
        while True:
            i += 1
            try:
                snap = full_snapshot(study_id, studies_root=studies_root,
                                     runs_root=runs_root)
                for line in f.events(snap):
                    out.write(line + "\n")
                out.flush()
                state = (snap.get("health") or {}).get("state")
                seen_end = state in TERMINAL_HEALTH_STATES
            except Exception as e:  # noqa: BLE001 — a watcher never dies loudly
                out.write(f"(could not read this tick: {type(e).__name__}: {e})\n")
                out.flush()
            if seen_end or (max_iterations and i >= max_iterations):
                return 0
            time.sleep(interval)
    except KeyboardInterrupt:
        return 0
