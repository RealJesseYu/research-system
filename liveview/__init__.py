"""liveview — a READ-ONLY window onto a study that is running right now.

THE PROBLEM THIS SOLVES. An investigation runs unattended for hours. Everything it
does is already written to disk as it happens — the arc, the director's reasoning,
per-claim verification verdicts, per-run logs, the workspace the agent builds — but
the only thing a human sees is the terminal, which is a flat wall of lines from the
director AND from every child subprocess mixed together. From that wall you cannot
tell what phase the study is in, what the director just decided and why, how much of
what it found actually reproduced, what it has spent, or — the one that matters most
— whether a traceback scrolling past is a fatal error or a failure the system already
recorded and routed around. A child subprocess printing its own traceback once
convinced the owner a perfectly healthy run had died.

WHAT THIS IS. A separate reader, not instrumentation. It opens the files the running
system already writes, assembles them into one picture, and shows it. Nothing here is
imported by the running system, and nothing here writes into studies/ or runs/ — so a
view can be opened, closed, and reopened mid-run without the run ever knowing.

  liveview.reader  — disk -> one JSON-able snapshot (pure, tolerant of half-written
                     files, recursive across sub-studies)
  liveview.render  — snapshot -> terminal text
  liveview.tui     — the terminal live view (redraw loop)
  liveview.web     — the local web view (stdlib http.server, 127.0.0.1 only)
  liveview.__main__— `python -m liveview`

READ-ONLY IS A HARD RULE HERE, not an aspiration: every file is opened for reading,
directory walks are depth- and count-bounded so a watcher cannot slow the run it is
watching, and a half-written line is skipped rather than treated as corruption.
"""

from liveview.reader import (  # noqa: F401
    latest_study,
    list_studies,
    snapshot,
)

__all__ = ["snapshot", "list_studies", "latest_study"]
