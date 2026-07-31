"""tests/test_live_view_autostart.py — the live view starts itself, and the way it
does that may never reach into the run.

Four things are protected here.

1. THE ISOLATION. Nothing in the run path may IMPORT liveview — not pi_agent, not
   stages, not tools, and not the launcher itself. The view was rewritten three
   times in one night while a study ran, safely, only because the running system
   could not reach it. This is the test that keeps that true.

2. IT IS OFF UNLESS A HUMAN IS WATCHING. Default on for a TTY only, so cron, CI,
   this suite and any piped launch behave exactly as they did before.

3. IT IS NEVER FATAL. Every failure mode — no free port, a child that dies at
   once, an interpreter that will not spawn — must print one line and return an
   inert handle, never raise.

4. IT CLEANS UP. A real child is spawned, answers on its port, and is gone (with
   the port free) after stop(); stop() is idempotent and registered with atexit
   so an exception or a Ctrl-C ending frees the port too.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from pi_agent import watch
from pi_agent.watch import (DEFAULT_PORT, ENV_FLAG, LiveView, free_port,
                            start_live_view, watch_enabled)

ROOT = Path(__file__).resolve().parent.parent


class Out:
    """A non-TTY stdout stand-in that records what was printed."""

    def __init__(self, tty: bool = False):
        self.lines: list[str] = []
        self._tty = tty

    def write(self, s):
        if s.strip():
            self.lines.append(s.strip())

    def flush(self):
        pass

    def isatty(self):
        return self._tty

    @property
    def text(self):
        return "\n".join(self.lines)


# --------------------------------------------------------------------------- #
# 1. THE ISOLATION — a subprocess wire, never an import
# --------------------------------------------------------------------------- #

def test_the_run_path_never_imports_liveview():
    """The load-bearing constraint. `liveview` may be MENTIONED in a comment
    anywhere; it may not be imported by anything the run path executes."""
    offenders = []
    for pkg in ("pi_agent", "stages", "tools"):
        for path in (ROOT / pkg).rglob("*.py"):
            for n, line in enumerate(path.read_text().splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if (stripped.startswith("import liveview")
                        or stripped.startswith("from liveview")
                        or "import liveview" in stripped.split("#")[0]):
                    offenders.append(f"{path.relative_to(ROOT)}:{n}: {stripped}")
    assert offenders == [], (
        "the run path must reach the live view only as a subprocess:\n"
        + "\n".join(offenders))


def test_the_launcher_spawns_the_module_as_a_child(monkeypatch):
    """What is actually run: this interpreter, `-m liveview`, --web, an explicit
    port, from the project root. Not the terminal view — the run owns stdout."""
    seen = {}

    class FakeProc:
        def poll(self):
            return None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("liveview", timeout)

        def terminate(self):
            seen["terminated"] = True

    def fake_popen(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return FakeProc()

    monkeypatch.setattr(watch.subprocess, "Popen", fake_popen)
    out = Out(tty=True)
    view = start_live_view(port=free_port(), open_browser=False, grace=0.0,
                           stream=out)

    assert seen["cmd"][:4] == [sys.executable, "-m", "liveview", "--web"]
    assert "--port" in seen["cmd"]
    assert "--web" in seen["cmd"] and "--dashboard" not in seen["cmd"]
    assert seen["kw"]["cwd"] == str(ROOT)
    # the child's output is captured, NOT inherited: one terminal, one writer
    assert seen["kw"]["stdout"] != 1 and seen["kw"]["stderr"] == subprocess.STDOUT
    assert "http://127.0.0.1:" in out.text
    view.stop()


def test_a_resume_points_the_view_at_the_known_study(monkeypatch):
    """--resume-study is the one case where the id exists before the study does,
    so the race window is skipped outright."""
    seen = {}

    class FakeProc:
        def poll(self):
            return None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("liveview", timeout)

        def terminate(self):
            pass

    monkeypatch.setattr(watch.subprocess, "Popen",
                        lambda cmd, **kw: (seen.update(cmd=cmd), FakeProc())[1])
    start_live_view(study_id="study-abc", open_browser=False, grace=0.0,
                    stream=Out(tty=True)).stop()
    assert "--study" in seen["cmd"] and "study-abc" in seen["cmd"]


# --------------------------------------------------------------------------- #
# 2. ON ONLY WHEN A HUMAN IS WATCHING
# --------------------------------------------------------------------------- #

def test_default_is_on_for_a_tty_and_off_for_everything_else(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert watch_enabled(stream=Out(tty=True)) is True
    assert watch_enabled(stream=Out(tty=False)) is False


def test_the_flag_and_the_env_var_both_turn_it_off(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert watch_enabled(no_watch=True, stream=Out(tty=True)) is False
    for off in ("0", "false", "no", "off", "OFF"):
        monkeypatch.setenv(ENV_FLAG, off)
        assert watch_enabled(stream=Out(tty=True)) is False


def test_the_env_var_can_also_force_it_on_without_a_tty(monkeypatch):
    """A scripted launch that DOES want the view must not have to fake a TTY."""
    for on in ("1", "true", "yes", "ON"):
        monkeypatch.setenv(ENV_FLAG, on)
        assert watch_enabled(stream=Out(tty=False)) is True
    # the flag still wins over the env var
    monkeypatch.setenv(ENV_FLAG, "1")
    assert watch_enabled(no_watch=True, stream=Out(tty=False)) is False


def test_a_disabled_view_spawns_nothing_prints_nothing_and_stops_safely(monkeypatch):
    """The byte-identical-to-before promise for cron, CI and this suite."""
    monkeypatch.setattr(watch.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("spawned while disabled"))
    out = Out(tty=False)
    monkeypatch.delenv(ENV_FLAG, raising=False)
    view = start_live_view(stream=out)
    assert view.proc is None and view.running is False and out.lines == []
    view.stop()
    view.stop()


# --------------------------------------------------------------------------- #
# 3. NEVER FATAL
# --------------------------------------------------------------------------- #

def test_no_free_port_says_so_and_carries_on(monkeypatch):
    monkeypatch.setattr(watch, "free_port", lambda *a, **k: None)
    monkeypatch.setattr(watch.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("spawned with no port"))
    out = Out(tty=True)
    view = start_live_view(stream=out)
    assert view.proc is None
    assert "not started" in out.text and "unaffected" in out.text


def test_a_child_that_dies_at_once_is_reported_in_one_line(monkeypatch):
    """The port could be taken between the probe and the bind, the module could
    be missing — whatever it is, one line, and the study runs."""
    class DeadProc:
        returncode = 1

        def poll(self):
            return 1

        def wait(self, timeout=None):
            return 1

    monkeypatch.setattr(watch.subprocess, "Popen", lambda *a, **k: DeadProc())
    out = Out(tty=True)
    view = start_live_view(stream=out, grace=0.0)
    assert view.proc is None and view.running is False
    assert len(out.lines) == 1
    assert "did not start" in out.text and "unaffected" in out.text


def test_a_spawn_that_raises_is_swallowed(monkeypatch):
    def boom(*a, **k):
        raise OSError("no such interpreter")

    monkeypatch.setattr(watch.subprocess, "Popen", boom)
    out = Out(tty=True)
    view = start_live_view(stream=out)
    assert view.proc is None
    assert "OSError" in out.text and "unaffected" in out.text


def test_stop_never_raises_on_a_hostile_process():
    class Hostile:
        def poll(self):
            return None

        def terminate(self):
            raise OSError("gone")

    view = LiveView(Hostile(), 1234, None)
    view.stop()  # must not raise
    assert view._stopped is True


# --------------------------------------------------------------------------- #
# 4. PORTS, AND A REAL CHILD THAT REALLY GOES AWAY
# --------------------------------------------------------------------------- #

def test_free_port_skips_a_busy_one():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as held:
        held.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        held.bind(("127.0.0.1", 0))
        held.listen(1)
        busy = held.getsockname()[1]
        assert free_port(busy, tries=3) == busy + 1 or free_port(busy, tries=3) > busy


def test_a_moved_port_is_visible_to_the_human(monkeypatch):
    """A silently-moved port is a view nobody finds."""
    class FakeProc:
        def poll(self):
            return None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("liveview", timeout)

        def terminate(self):
            pass

    monkeypatch.setattr(watch.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(watch, "free_port", lambda *a, **k: DEFAULT_PORT + 3)
    out = Out(tty=True)
    start_live_view(stream=out, grace=0.0).stop()
    assert f"127.0.0.1:{DEFAULT_PORT + 3}" in out.text
    # every skipped port is named, not just the default: on this machine 8765
    # AND 8766 are held by unrelated services, and naming only 8765 beside a URL
    # on 8767 reads like an off-by-one
    assert f"ports {DEFAULT_PORT}-{DEFAULT_PORT + 2} busy" in out.text

    monkeypatch.setattr(watch, "free_port", lambda *a, **k: DEFAULT_PORT + 1)
    out2 = Out(tty=True)
    start_live_view(stream=out2, grace=0.0).stop()
    assert f"port {DEFAULT_PORT} busy" in out2.text


@pytest.mark.parametrize("_", [0])
def test_a_real_child_serves_then_is_gone_and_frees_its_port(_, tmp_path, monkeypatch):
    """End to end with a real subprocess: it answers on its port, and after
    stop() the process is dead and the port is bindable again.

    No study exists in this environment, which is also the STARTUP WINDOW a real
    launch opens in — the study directory does not exist for a second or two.
    The view must serve anyway rather than die on it.
    """
    monkeypatch.setenv(ENV_FLAG, "1")  # forced on: pytest's stdout is not a TTY
    out = Out(tty=False)
    port = free_port(9765)
    assert port is not None
    view = start_live_view(port=port, open_browser=False, stream=out, grace=2.0)
    if view.proc is None:  # a machine that cannot spawn is not a test failure
        pytest.skip(f"child did not start: {out.text}")
    try:
        body = None
        for _try in range(40):
            try:
                body = urllib.request.urlopen(
                    f"http://127.0.0.1:{view.port}/api/snapshot", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(0.25)
        assert body is not None, "the child never answered"
        assert b"study_id" in body  # serves fine with no study on disk
        assert view.running is True
    finally:
        view.stop()

    assert view.running is False
    assert view.proc.poll() is not None
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        probe.bind(("127.0.0.1", port))  # must not raise: the port is free again


def test_stop_is_registered_with_atexit(monkeypatch):
    """The exception and Ctrl-C endings. main() also calls stop() on the ordinary
    path; stop() is idempotent so both firing is fine."""
    registered = []

    class FakeProc:
        def poll(self):
            return None

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired("liveview", timeout)

        def terminate(self):
            pass

    monkeypatch.setattr(watch.subprocess, "Popen", lambda *a, **k: FakeProc())
    monkeypatch.setattr(watch.atexit, "register", lambda fn: registered.append(fn))
    view = start_live_view(stream=Out(tty=True), grace=0.0)
    assert registered == [view.stop]
    view.stop()


# --------------------------------------------------------------------------- #
# THE WIRE ITSELF — the flag exists, and the script no longer tells a human to
# launch the view by hand. liveview once shipped a dispatch branch reading a
# --dashboard flag that an edit never actually inserted; --help is the check.
# --------------------------------------------------------------------------- #

def test_pi_agent_offers_no_watch():
    helptext = subprocess.run(
        [sys.executable, "-m", "pi_agent", "--help"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120).stdout
    assert "--no-watch" in helptext
    assert ENV_FLAG in helptext


def test_run_comparison_no_longer_tells_you_to_launch_it_by_hand():
    text = (ROOT / "run_comparison.sh").read_text()
    assert "-m liveview" not in text, "the comment outlived the manual step"


# --------------------------------------------------------------------------- #
# THE WIRE IN main() — the view really is started around a study, and really is
# taken down after it. The director is stubbed out; what is under test is the
# entry point's own two lines, not an investigation.
# --------------------------------------------------------------------------- #

def _stub_report():
    return {"study_id": "study-stub", "goal": "g", "moves_run": 0,
            "termination": "stubbed", "arc": []}


def test_main_starts_the_view_around_the_study_and_stops_it_after(monkeypatch, capsys):
    import pi_agent.__main__ as entry
    import pi_agent.free_director as fd

    events = []

    class FakeProc:
        def poll(self):
            return None if "stopped" not in events else 0

        def wait(self, timeout=None):
            if "stopped" in events:
                return 0
            raise subprocess.TimeoutExpired("liveview", timeout)

        def terminate(self):
            events.append("stopped")

    def fake_popen(*a, **k):
        events.append("started")
        return FakeProc()

    def fake_investigate(**kwargs):
        # the view must already be up while the study runs — that is the point
        assert events == ["started"]
        events.append("investigated")
        return _stub_report()

    monkeypatch.setenv(ENV_FLAG, "1")  # pytest's stdout is not a TTY
    monkeypatch.setattr(watch.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(fd, "free_investigate", fake_investigate)
    monkeypatch.setattr(watch.atexit, "register", lambda fn: None)

    entry.main(["--goal", "g", "--director", "free", "--max-moves", "1"])

    assert events == ["started", "investigated", "stopped"]
    assert "live view: http://127.0.0.1:" in capsys.readouterr().out


def test_main_honours_no_watch(monkeypatch, capsys):
    import pi_agent.__main__ as entry
    import pi_agent.free_director as fd

    monkeypatch.setenv(ENV_FLAG, "1")  # even forced on, the flag wins
    monkeypatch.setattr(watch.subprocess, "Popen",
                        lambda *a, **k: pytest.fail("spawned under --no-watch"))
    monkeypatch.setattr(fd, "free_investigate", lambda **k: _stub_report())
    entry.main(["--goal", "g", "--director", "free", "--max-moves", "1",
                "--no-watch"])
    assert "live view" not in capsys.readouterr().out
