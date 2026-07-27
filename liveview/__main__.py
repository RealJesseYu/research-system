"""python -m liveview — watch a study while it runs.

    python -m liveview                    # terminal view of the newest live study
    python -m liveview --web               # same picture in a browser, localhost only
    python -m liveview --study study-XXXX  # a specific study (finished ones too)
    python -m liveview --once              # print one snapshot and exit (scriptable)
    python -m liveview --json              # one snapshot as JSON
    python -m liveview --list              # what studies are on disk

Read-only by construction: this process opens files the running system already
writes and never writes into studies/ or runs/. Starting, stopping, or restarting
it cannot affect a run in progress.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from liveview.reader import (  # noqa: E402
    RUNS_ROOT,
    STUDIES_ROOT,
    full_snapshot,
    list_studies,
)
from liveview.tui import watch  # noqa: E402


def main(argv: list | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m liveview",
        description="A read-only live view of a study that is running: current phase, "
        "the arc so far, the director's latest reasoning, verified-vs-total, spend, "
        "and which failures are fatal (almost none are).",
    )
    p.add_argument("--study", help="study id (default: the newest one still running)")
    p.add_argument("--web", action="store_true", help="serve the browser view instead")
    p.add_argument("--port", type=int, default=8765, help="web view port (default 8765)")
    p.add_argument("--no-browser", action="store_true", help="do not open a browser")
    p.add_argument("--interval", type=float, default=4.0, help="refresh seconds (default 4)")
    p.add_argument("--once", action="store_true", help="print one snapshot and exit")
    p.add_argument("--json", action="store_true", help="print one snapshot as JSON and exit")
    p.add_argument("--list", action="store_true", help="list studies on disk and exit")
    p.add_argument("--no-color", action="store_true", help="plain text, no ANSI colour")
    p.add_argument("--studies-root", default=str(STUDIES_ROOT))
    p.add_argument("--runs-root", default=str(RUNS_ROOT))
    args = p.parse_args(argv)

    studies_root, runs_root = Path(args.studies_root), Path(args.runs_root)

    if args.list:
        for s in list_studies(studies_root):
            mark = "finished" if s["finished"] else "RUNNING "
            child = f"  (sub-study of {s['parent_study_id']})" if s.get("parent_study_id") else ""
            print(f"{mark}  {s['study_id']}{child}")
            if s.get("goal"):
                print(f"            {s['goal'][:110]}")
        return 0

    if args.json:
        print(json.dumps(
            full_snapshot(args.study, studies_root=studies_root, runs_root=runs_root),
            indent=2, default=str))
        return 0

    if args.web:
        from liveview.web import serve

        serve(port=args.port, studies_root=studies_root, runs_root=runs_root,
              open_browser=not args.no_browser)
        return 0

    return watch(
        args.study,
        interval=args.interval,
        once=args.once,
        color=False if args.no_color else None,
        studies_root=studies_root,
        runs_root=runs_root,
    )


if __name__ == "__main__":
    raise SystemExit(main())
