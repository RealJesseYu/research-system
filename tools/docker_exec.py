"""tools/docker_exec.py — bound a `docker exec` WHERE THE WORK RUNS.

THE BUG THIS EXISTS FOR. Every substrate wrapper that drives a long-lived
container does `subprocess.run(["docker", "exec", CONTAINER, ...], timeout=N)`.
A subprocess timeout kills the LOCAL DOCKER CLIENT. The process inside the
container never learns the client is gone and keeps running — keeps burning CPU,
and keeps writing to its job directory.

That is not merely a leak. Every one of these wrappers retries once on a
timeout, and the retry DELETES the job's output file and re-runs into the SAME
job directory. So the timed-out solver is still writing there while the retry
reads: the retry can pick up the ghost's output and report it as a clean
success. A wrong number, on the success path, with nothing in the summary
suggesting anything went wrong.

`tools/run_scipy.py` avoids this by giving each job its OWN ephemeral container
and `docker kill`-ing it by name (measured, and documented there: "killing only
the client leaves the container running"). The wrappers here cannot do that —
they exec into a SHARED prod container, so killing it would take out unrelated
work.

THE FIX, in two layers, because one is not enough:

  1. `timeout <n> <cmd>` INSIDE the container. The work is bounded where it
     runs, so it dies whether or not any client is still listening. This is the
     load-bearing half: it holds even if this process is killed outright.
  2. A best-effort `pkill -f <marker>` after a client-side timeout, to reap
     anything layer 1 could not (a process that ignores SIGTERM). Scoped to the
     job directory string so it can only ever match this job's own processes —
     never another job's, and never the container's own services.

The container-side budget is deliberately SHORTER than the client's, so layer 1
fires first and the wrapper sees an ordinary non-zero exit it can classify,
rather than a client timeout it has to guess about.

Pure stdlib. No model call. Every wrapper keeps its own container name, image
and diagnostics — only the exec bounding is shared, because eight copies of a
timeout policy is eight chances for one of them to drift back.
"""

from __future__ import annotations

import subprocess

#: How much longer the CLIENT waits than the container-side `timeout`. Enough
#: slack that a container-side kill is what fires on a genuine overrun, leaving
#: the client timeout as a true last resort (docker itself wedged, daemon gone).
CLIENT_GRACE_S = 15

#: Exit status `timeout` uses when it had to kill the command. Distinguishing
#: this from an ordinary failure is what lets a caller report "exceeded its
#: budget" instead of "the tool failed".
TIMEOUT_EXIT_STATUS = 124


def bounded_exec(docker_context: str, container: str, argv: list,
                 timeout_s: int) -> list:
    """The full `docker exec` argv with the work bounded INSIDE the container.

    The minimal form of the fix, for wrappers that already have their own
    TimeoutExpired handling and return contracts worth leaving alone: it inserts
    `timeout <n>` ahead of the command so the work dies where it runs, and the
    caller keeps its subprocess timeout as a last resort (raise it to
    timeout_s + CLIENT_GRACE_S so the container-side kill is what normally
    fires). A non-zero exit of TIMEOUT_EXIT_STATUS then means "exceeded its
    budget", which every caller here already classifies as transient — and now
    does so with the previous attempt genuinely dead rather than still writing
    into the job directory the retry is about to reuse.
    """
    return ["docker", "--context", docker_context, "exec", container,
            "timeout", str(int(timeout_s)), *[str(a) for a in argv]]


class ExecResult:
    """(returncode, stdout, stderr, timed_out, killed_inside).

    `timed_out` is true for EITHER layer firing, so existing callers that only
    ask "did this run out of time" keep working. `killed_inside` distinguishes
    the healthy case (layer 1, the container killed its own work) from the
    alarming one (the client gave up and we do not know what the container is
    still doing) — worth telling apart in a diagnostic.
    """

    __slots__ = ("returncode", "stdout", "stderr", "timed_out", "killed_inside")

    def __init__(self, returncode, stdout, stderr, timed_out, killed_inside):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out
        self.killed_inside = killed_inside


def exec_bounded(
    docker_context: str,
    container: str,
    argv: list,
    *,
    timeout_s: int,
    kill_marker: str = "",
) -> ExecResult:
    """`docker exec` argv in `container`, bounded INSIDE the container.

    `argv` is the command as a list (never a shell string — nothing here is
    interpolated into a shell). `timeout_s` is the budget for the work itself;
    the client waits timeout_s + CLIENT_GRACE_S.

    `kill_marker` is a string unique to this job — the job directory path is the
    natural choice — used to reap survivors with `pkill -f` if the client
    timeout fires anyway. Empty disables the reap; the marker must be specific,
    because a broad one would kill another job's work.
    """
    cmd = ["docker", "--context", docker_context, "exec", container,
           "timeout", str(int(timeout_s)), *[str(a) for a in argv]]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=int(timeout_s) + CLIENT_GRACE_S)
    except subprocess.TimeoutExpired as e:
        # Layer 1 did not save us: the container-side timeout should have fired
        # first, so this means docker itself is wedged or the daemon is gone.
        # Reap by marker so a survivor cannot write into a retry's job dir.
        reaped = _reap(docker_context, container, kill_marker)
        return ExecResult(
            returncode=-1,
            stdout=_text(e.stdout),
            stderr=(_text(e.stderr) +
                    f"\n[docker client timed out after {int(timeout_s) + CLIENT_GRACE_S}s; "
                    f"container-side reap {'succeeded' if reaped else 'not attempted/failed'}]"),
            timed_out=True,
            killed_inside=False,
        )
    return ExecResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
        timed_out=proc.returncode == TIMEOUT_EXIT_STATUS,
        killed_inside=proc.returncode == TIMEOUT_EXIT_STATUS,
    )


def _text(value) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


# Reap by scanning /proc, NOT with pkill. Measured 2026-07-27: the substrate
# containers carry no ps, no pkill and no pgrep (`command -v` -> MISSING for all
# three; a pkill call exits 127). A reap written with pkill would be dead code
# that always "fails" quietly — the same shape as the bugs this audit is fixing.
# /proc is present and `kill` is a shell builtin, so the scan below is what
# actually works: read each /proc/<pid>/cmdline, translate NULs to spaces, and
# kill the pids whose command line contains the marker.
#
# `--` before the marker and no shell metacharacters in it: the marker is a job
# directory path this module's callers construct, never user text.
# SKIPPING $$ IS NOT DEFENSIVE, IT IS REQUIRED. The marker is passed to this
# script as an argument, so the script's OWN /proc/<pid>/cmdline contains it —
# the first version matched itself, killed itself, and therefore reported
# failure while having actually worked. Its parent (the sh that docker exec
# spawns) is skipped for the same reason.
_REAP_SCRIPT = (
    "n=0; self=$$; parent=$PPID; "
    "for d in /proc/[0-9]*; do "
    "  p=${d#/proc/}; "
    "  [ \"$p\" = 1 ] && continue; "                       # never container init
    "  [ \"$p\" = \"$self\" ] && continue; "               # never ourselves
    "  [ \"$p\" = \"$parent\" ] && continue; "
    "  tr '\\0' ' ' < \"$d/cmdline\" 2>/dev/null | grep -qF -- \"$1\" || continue; "
    "  kill -9 \"$p\" 2>/dev/null && n=$((n+1)); "
    "done; "
    "echo \"$n\""
)


def _reap(docker_context: str, container: str, marker: str) -> bool:
    """Best-effort kill of container processes whose command line holds `marker`.

    True when at least one process was killed. Never raises: this runs on an
    already-bad path, and a failure to reap must not replace the real diagnostic.
    PID 1 is skipped explicitly — killing a shared prod container's init would
    take out every other job in it, which is the opposite of the point.
    """
    if not marker:
        return False
    try:
        proc = subprocess.run(
            ["docker", "--context", docker_context, "exec", container,
             "sh", "-c", _REAP_SCRIPT, "reap", marker],
            capture_output=True, text=True, timeout=30)
        return proc.returncode == 0 and (proc.stdout or "0").strip() not in ("", "0")
    except Exception:  # noqa: BLE001 — best effort by construction
        return False
