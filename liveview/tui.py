"""liveview/tui.py — the terminal live view: read the disk, draw, wait, repeat.

No curses, deliberately. The view is redrawn as plain lines with an ANSI clear, so it
works over ssh, inside tmux, in a pipe (`--once`), and in a terminal that is not a
real tty. Ctrl-C leaves the terminal exactly as it was found.

Nothing here writes to the study it is watching. If the reader hiccups on a file that
was mid-write, the loop draws the previous picture plus a note rather than dying —
a watcher crashing is annoying; a watcher that makes you doubt a healthy run is worse.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

from liveview.reader import RUNS_ROOT, STUDIES_ROOT, full_snapshot
from liveview.render import GREY, RESET, render

CLEAR = "\033[2J\033[H"       # clear screen, cursor home
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"


def _width(default: int = 100) -> int:
    try:
        return max(60, min(160, shutil.get_terminal_size((default, 40)).columns))
    except Exception:  # noqa: BLE001
        return default


def watch(
    study_id: Optional[str] = None,
    *,
    interval: float = 4.0,
    once: bool = False,
    color: Optional[bool] = None,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = RUNS_ROOT,
    out=None,
    max_iterations: Optional[int] = None,
) -> int:
    """Watch one study until interrupted. Returns a process exit code: 0 while the
    picture is healthy or the study finished on its own terms, 1 if the study ended
    badly or looks to have vanished — so `liveview --once` is usable in a script.

    `max_iterations` bounds the loop (tests, and `--once`)."""
    out = out or sys.stdout
    if color is None:
        color = out.isatty() and os.environ.get("NO_COLOR") is None
    iterations = 0
    code = 0
    last_painted = None
    if not once and color:
        out.write(HIDE_CURSOR)
    try:
        while True:
            iterations += 1
            try:
                snap = full_snapshot(
                    study_id, studies_root=studies_root, runs_root=runs_root
                )
                lines = render(snap, width=_width(), color=color)
                code = 1 if (snap.get("health") or {}).get("state") in (
                    "ended-badly", "vanished") else 0
            except Exception as e:  # noqa: BLE001 — a watcher must never die loudly
                lines = [f"the view could not read the study this tick "
                         f"({type(e).__name__}: {e}) — retrying"]
            # ONLY REPAINT WHEN SOMETHING CHANGED. The loop used to redraw the
            # identical picture every tick, which on a terminal that does not
            # honour the ANSI clear (or any scrollback, pipe or tmux pane) reads
            # as the view spamming the same output forever. A study is mostly
            # quiet — an experiment runs for minutes — so the honest behaviour is
            # to paint on change and otherwise say nothing. --once is unaffected.
            painted = "\n".join(lines)
            if not once and painted == last_painted:
                time.sleep(interval)
                continue
            last_painted = painted
            if not once:
                out.write(CLEAR)
            out.write(painted + "\n")
            if not once:
                hint = (f"{GREY}   watching every {interval:g}s · Ctrl-C to stop · "
                        f"read-only, this view never touches the run{RESET}"
                        if color else
                        f"   watching every {interval:g}s · Ctrl-C to stop")
                out.write(hint + "\n")
            out.flush()
            if once or (max_iterations and iterations >= max_iterations):
                return code
            time.sleep(interval)
    except KeyboardInterrupt:
        return code
    finally:
        if not once and color:
            out.write(SHOW_CURSOR)
            out.flush()
