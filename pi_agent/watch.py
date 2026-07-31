"""pi_agent/watch.py — the live view comes up with the study and goes away with it.

Until this existed, `python -m pi_agent` printed a ceiling line and then went
quiet for hours, and the human had to remember to open a second terminal and run
`python -m liveview` by hand — run_comparison.sh line 6 was literally a comment
reminding them to. Nobody should have to remember that.

SUBPROCESS ONLY. THIS MODULE NEVER IMPORTS liveview, AND NEITHER MAY ANYTHING
ELSE IN THE RUN PATH. Verified 2026-07-31: pi_agent/, stages/ and tools/ name
liveview only in comments. That isolation is load-bearing, not incidental — the
live view was rewritten three separate times in one night WHILE a study was
running, safely, precisely because the running system cannot reach it. An import
would end that permanently in exchange for a convenience feature. So the entire
wire is `python -m liveview --web` in a child process, and nothing more.

THE WEB VIEW, NOT THE TERMINAL ONE. The run already owns stdout; two processes
writing one terminal is worse than no view at all. The child serves a page and
opens a browser, and its own output is captured to a temp file rather than
inherited, so the run's output is exactly what it was before.

Everything here follows the rule the cost meter and the artifact commit follow:
an accounting or display step may NEVER affect a run. Anything that goes wrong —
port taken, no browser, no interpreter — prints one line and the study carries on.
"""

from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

ENV_FLAG = "RESEARCH_LIVE_VIEW"
DEFAULT_PORT = 8765
PORT_TRIES = 12  # 8765..8776 — enough for a dozen overlapping studies
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_ON = {"1", "true", "yes", "on"}
_OFF = {"0", "false", "no", "off"}


def watch_enabled(no_watch: bool = False, stream=None) -> bool:
    """Whether to bring the view up.

    ON BY DEFAULT ONLY WHEN A HUMAN IS WATCHING — i.e. when stdout is a TTY. A
    cron launch, CI, the test suite and any piped invocation therefore behave
    byte-identically to before this file existed; nothing spawns, nothing prints.

    Two explicit escapes, because a scripted launch must be able to decide
    without editing a command line: `--no-watch` (the `no_watch` argument, which
    always wins) and RESEARCH_LIVE_VIEW, which forces the view either on (`1`)
    or off (`0`) regardless of the TTY.
    """
    if no_watch:
        return False
    raw = (os.environ.get(ENV_FLAG) or "").strip().lower()
    if raw in _OFF:
        return False
    if raw in _ON:
        return True
    stream = sys.stdout if stream is None else stream
    try:
        return bool(stream.isatty())
    except Exception:  # noqa: BLE001 — a stream with no isatty is not a human
        return False


def free_port(start: int = DEFAULT_PORT, tries: int = PORT_TRIES) -> int | None:
    """The first port at or above `start` that nothing is listening on, or None.

    Two studies overlap often enough (one finishing while the next launches) that
    a collision on liveview's default 8765 is ordinary, not exceptional. The
    caller PICKS A FREE PORT AND SAYS WHICH, loudly — a silently-moved port is a
    view nobody finds.

    SO_REUSEADDR is set on the probe to match ThreadingHTTPServer, so a port
    merely in TIME_WAIT reads as free here exactly as it will for the child.
    """
    for port in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    return None


class LiveView:
    """A handle on the child process. A disabled or failed view is a real object
    with `proc is None`, so every caller can `.stop()` unconditionally and no
    caller has to branch on whether the view came up."""

    def __init__(self, proc=None, port: int | None = None, log_path: str | None = None):
        self.proc = proc
        self.port = port
        self.log_path = log_path
        self._stopped = proc is None

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:
        """Take the view down. Idempotent, and never raises.

        An orphaned server holding 8765 makes the NEXT launch pick a different
        port (or fail to find one), which turns a convenience into a recurring
        papercut — so this runs on every ending, including an exception or
        Ctrl-C, via the atexit registration in start_live_view().
        """
        if self._stopped:
            return
        self._stopped = True
        proc = self.proc
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001 — shutting a display down may not raise
            pass
        try:
            if self.log_path:
                os.unlink(self.log_path)
        except Exception:  # noqa: BLE001
            pass


def _tail(path: str | None, limit: int = 200) -> str:
    """The last thing the child said, for the one line we print when it dies."""
    try:
        lines = [ln.strip() for ln in Path(path).read_text().splitlines() if ln.strip()]
        return lines[-1][:limit] if lines else ""
    except Exception:  # noqa: BLE001
        return ""


def start_live_view(
    *,
    no_watch: bool = False,
    study_id: str | None = None,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    grace: float = 0.8,
    stream=None,
) -> LiveView:
    """Spawn `python -m liveview --web` beside the study. Never raises.

    `study_id` is passed through only for a resume, where the id is known before
    the study starts. For a fresh study it is deliberately omitted: liveview
    defaults to "the newest study still running", and the study directory does
    not exist for a second or two after launch. Its page handles that window
    itself — with no study on disk the reader returns {"study_id": null,
    "error": "no studies found"}, the server answers 200, and the page re-polls
    every 4s and latches on the moment the study appears. So the child is
    started immediately and simply waits, rather than the caller sleeping.

    No liveview default is changed here. This adds a caller; the view stays
    read-only, and its only writes remain stdout and an HTTP body.
    """
    out = sys.stdout if stream is None else stream

    def say(msg: str) -> None:
        try:
            print(msg, file=out)
        except Exception:  # noqa: BLE001
            pass

    if not watch_enabled(no_watch, stream=out):
        return LiveView()

    try:
        chosen = free_port(port)
        if chosen is None:
            say(f"live view not started: ports {port}-{port + PORT_TRIES - 1} are "
                f"all in use (another study is probably being watched); the "
                f"study is unaffected")
            return LiveView()

        cmd = [sys.executable, "-m", "liveview", "--web", "--port", str(chosen)]
        if study_id:
            cmd += ["--study", study_id]
        if not open_browser:
            cmd.append("--no-browser")

        # The child's stdout/stderr go to a temp file, not to this terminal: the
        # run owns the terminal. The file is read only if the child dies early,
        # so the one line we print then says WHY, and is removed on stop().
        fd, log_path = tempfile.mkstemp(prefix="liveview-", suffix=".log")
        proc = subprocess.Popen(
            cmd, cwd=str(PROJECT_ROOT), stdin=subprocess.DEVNULL,
            stdout=fd, stderr=subprocess.STDOUT,
        )
        os.close(fd)

        # Did it survive its own startup? wait() returns only if it exited.
        try:
            code = proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            code = None
        if code is not None:
            detail = _tail(log_path)
            say(f"live view did not start (exit {code}"
                f"{': ' + detail if detail else ''}); the study is unaffected")
            try:
                os.unlink(log_path)
            except Exception:  # noqa: BLE001
                pass
            return LiveView()

        view = LiveView(proc, chosen, log_path)
        # Name every port that was skipped, not just the default: on this
        # machine 8765 AND 8766 are held by unrelated services, so "8765 was
        # busy" beside a URL on 8767 reads like an off-by-one.
        skipped = ("port " if chosen == port + 1 else "ports ") + (
            str(port) if chosen == port + 1 else f"{port}-{chosen - 1}")
        moved = f"  ({skipped} busy)" if chosen != port else ""
        say(f"live view: http://127.0.0.1:{chosen}/{moved} — read-only, closes "
            f"when the study ends (--no-watch, or {ENV_FLAG}=0, to skip it)")
        atexit.register(view.stop)
        return view
    except Exception as e:  # noqa: BLE001 — a display step may not end a run
        say(f"live view did not start ({type(e).__name__}: {e}); "
            f"the study is unaffected")
        return LiveView()
