"""liveview/reader.py — the disk, read as one picture. Pure, read-only, tolerant.

Everything a watcher needs is already on disk while the run happens:

    studies/<id>/study.json          the goal and constraints, written once
    studies/<id>/arc.jsonl           one line appended per completed move
    studies/<id>/decisions/decideN.json  the director's full turn: what it read,
                                     why, and what it chose — written BEFORE the
                                     chosen action runs
    studies/<id>/report.json         written once, at the very end
    runs/<run-id>/log.txt            appended line-by-line as a move runs
    runs/<run-id>/verification.json  per-claim verdicts, written when a move ends
    runs/<run-id>/workspace/         what the experimenter is actually building

The two counts that give the live phase away: a decision file is written before its
action runs, and an arc line is appended after it finishes. So

    decisions > arc  ->  the decided action is IN FLIGHT (and the decision says what)
    decisions == arc ->  the director is THINKING about the next move

which is how this module knows the phase without the running system telling it
anything. Sub-investigations are their own studies (studies/<id>-sub<N>/), so the
same reading recurses and the live phase is the deepest node still moving.

TOLERANCE IS THE POINT. Every file here can be read mid-write: arc.jsonl can end in
a partial line, a JSON file can be half-flushed. Nothing in this module raises on
that — a partial line is skipped and counted, a partial JSON file reads as None, and
the snapshot says so rather than pretending. No function here writes anything.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

STUDIES_ROOT = Path("studies")
RUNS_ROOT = Path("runs")

# How long a study with no report.json may go without ANY file changing before the
# view starts saying so. Long moves are genuinely quiet for stretches (an agent
# thinking, a solver running), so this is deliberately generous and the wording it
# drives is a question, never a verdict.
QUIET_SECONDS = 20 * 60

# Bounds on directory walks, so watching can never cost the run being watched.
_MAX_WALK_ENTRIES = 4000
_MAX_WALK_DEPTH = 3
_SKIP_DIRS = {"__pycache__", ".git", "node_modules"}

# Study ids and run ids are minted by the system from a timestamp and a counter;
# anything else is not one, and is refused before it reaches the filesystem.
_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


# --------------------------------------------------------------------------- #
# Tolerant readers. None of these raise on a file that is mid-write.
# --------------------------------------------------------------------------- #

def read_json(path: Path) -> Optional[Any]:
    """Parse a JSON file, or return None if it is missing, unreadable, or caught
    half-written. A partially flushed file is a normal state for a live run, not an
    error worth surfacing as a crash."""
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — missing, partial, or malformed all read as None
        return None


def read_jsonl(path: Path) -> tuple[list, int]:
    """Read an append-only JSONL file into (entries, skipped). The last line of a
    file being appended to right now may be incomplete; it is skipped and counted so
    the caller can say "3 moves (a 4th is being written)" instead of crashing or
    silently dropping it."""
    entries: list = []
    skipped = 0
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:  # noqa: BLE001 — a torn trailing line, mid-append
                    skipped += 1
    except Exception:  # noqa: BLE001 — no arc yet is a normal early state
        return [], 0
    return entries, skipped


def tail_lines(path: Path, limit: int = 40, max_bytes: int = 200_000) -> list:
    """The last `limit` lines of a text file, read from the end so a huge log costs
    the same as a small one. Never raises."""
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # drop the partial first line
            data = f.read()
    except Exception:  # noqa: BLE001
        return []
    text = data.decode("utf-8", errors="replace")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-limit:]


def _mtime(path: Path) -> Optional[float]:
    try:
        return os.path.getmtime(path)
    except Exception:  # noqa: BLE001
        return None


def _created(path: Path) -> Optional[float]:
    """When a run dir came into being — st_birthtime where the platform has it (macOS
    does), else the directory's own mtime, which for a run dir is close enough to say
    "this move has been going for 40 minutes"."""
    try:
        st = os.stat(path)
    except Exception:  # noqa: BLE001
        return None
    return getattr(st, "st_birthtime", None) or st.st_mtime


def newest_mtime(root: Path, *, depth: int = _MAX_WALK_DEPTH) -> Optional[float]:
    """The most recent modification time anywhere under `root`, bounded in both
    depth and number of entries examined. This is the run's heartbeat: while an
    experimenter works, files under its workspace keep changing."""
    newest = _mtime(root)
    seen = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    while stack:
        d, level = stack.pop()
        if level > depth:
            continue
        try:
            with os.scandir(d) as it:
                for entry in it:
                    seen += 1
                    if seen > _MAX_WALK_ENTRIES:
                        return newest
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in _SKIP_DIRS:
                                stack.append((Path(entry.path), level + 1))
                            continue
                        ts = entry.stat(follow_symlinks=False).st_mtime
                    except Exception:  # noqa: BLE001
                        continue
                    if newest is None or ts > newest:
                        newest = ts
        except Exception:  # noqa: BLE001 — vanished or unreadable dir
            continue
    return newest


def _safe_id(value: str) -> Optional[str]:
    """A study/run id is only ever used to build a path, so it is validated before
    it touches the filesystem — the web view accepts ids from a URL."""
    if isinstance(value, str) and value and _ID_RE.match(value) and ".." not in value:
        return value
    return None


# --------------------------------------------------------------------------- #
# Finding studies.
# --------------------------------------------------------------------------- #

def list_studies(studies_root: Path = STUDIES_ROOT) -> list:
    """Every study on disk, newest first, each with just enough to choose from:
    whether it has finished (report.json exists), whether it is a sub-study, its
    goal, and when it last changed."""
    out = []
    try:
        entries = sorted(os.scandir(studies_root), key=lambda e: e.name, reverse=True)
    except Exception:  # noqa: BLE001
        return []
    for entry in entries:
        if not entry.is_dir():
            continue
        d = Path(entry.path)
        identity = read_json(d / "study.json") or {}
        arc_mtime = _mtime(d / "arc.jsonl") or _mtime(d) or 0.0
        out.append(
            {
                "study_id": identity.get("study_id", entry.name),
                "goal": identity.get("goal"),
                "mode": identity.get("mode"),
                "parent_study_id": identity.get("parent_study_id"),
                "created_at": identity.get("created_at"),
                "finished": (d / "report.json").is_file(),
                "last_change": arc_mtime,
            }
        )
    out.sort(key=lambda s: s["last_change"], reverse=True)
    return out


def latest_study(studies_root: Path = STUDIES_ROOT) -> Optional[str]:
    """The study a watcher almost certainly means.

    First choice is a root study that is BOTH unfinished and recently active — one
    actually running now. "Unfinished" alone is not enough: a run that was killed
    months ago is unfinished forever, and picking it over the run that just completed
    is how a watcher ends up staring at a corpse (this happened the first time a live
    run finished under the view). So a stale unfinished study loses to whatever
    changed most recently, and the picker shows the rest."""
    studies = list_studies(studies_root)
    roots = [s for s in studies if not s.get("parent_study_id")] or studies
    if not roots:
        return None
    now = time.time()
    for s in roots:  # already newest-first
        if not s["finished"] and (now - (s["last_change"] or 0)) < QUIET_SECONDS:
            return s["study_id"]
    return roots[0]["study_id"]


# --------------------------------------------------------------------------- #
# Reading one study's pieces.
# --------------------------------------------------------------------------- #

def read_decisions(study_dir: Path, *, full: bool = False) -> list:
    """The director's turns, in order. Each decision file holds the whole turn: the
    input it was given, the decision it made (reading / reasoning / action / detail),
    and timing. The reading and reasoning ARE the plain-language explanation of what
    the system is doing — they are the point of this view, so they are carried
    verbatim rather than summarized. `full` additionally carries the input the
    director saw (large: the instrument menu and the whole arc)."""
    ddir = study_dir / "decisions"
    out = []
    try:
        names = [e.name for e in os.scandir(ddir) if e.name.startswith("decide")]
    except Exception:  # noqa: BLE001
        return []
    for name in names:
        m = re.match(r"decide(\d+)\.json$", name)
        if not m:
            continue
        raw = read_json(ddir / name)
        if not isinstance(raw, dict):
            # Being written right now: record the turn exists, without its content.
            out.append({"seq": int(m.group(1)), "incomplete": True})
            continue
        d = raw.get("decision") or {}
        rec = {
            "seq": raw.get("seq", int(m.group(1))),
            "action": d.get("action"),
            "instrument": d.get("instrument"),
            "campaign": d.get("campaign"),
            "domain": d.get("domain"),
            # A run_fan carries its questions HERE and leaves `domain` null; the
            # per-member questions are what _annotate_fan_members hands to the arc.
            "fan_domains": d.get("fan_domains"),
            "reading": d.get("reading"),
            "reasoning": d.get("reasoning"),
            "detail": d.get("detail"),
            "budget_moves": d.get("budget_moves"),
            "stop_reason": d.get("stop_reason"),
            "timing": raw.get("timing") or {},
            # The budget as the director itself saw it this turn. While a study is
            # running there is no report.json yet, so this is the only place the
            # live remaining-moves count exists.
            "budget_seen": (raw.get("input") or {}).get("budget"),
            "incomplete": False,
        }
        if full:
            rec["input"] = raw.get("input")
        out.append(rec)
    out.sort(key=lambda r: r["seq"])
    return out


def _verification(run_dir: Path) -> Optional[dict]:
    """A run's per-claim verdicts, trimmed to what a watcher reads: the counts, and
    each claim's label, value and — when it did not stand — the reason it did not."""
    data = read_json(run_dir / "verification.json")
    if not isinstance(data, dict):
        return None
    verdicts = []
    for v in data.get("verdicts") or []:
        if not isinstance(v, dict):
            continue
        verdicts.append(
            {
                "verified": bool(v.get("verified")),
                "label": v.get("label"),
                "reason": v.get("reason"),
                "detail": v.get("detail"),
                "original": v.get("original"),
                "reproduced": v.get("reproduced"),
                "rel_error": v.get("rel_error"),
            }
        )
    return {
        "total": data.get("total"),
        "verified": data.get("verified"),
        "failed": data.get("failed"),
        "publishable": data.get("publishable"),
        "verdicts": verdicts,
    }


def read_run(run_id: str, *, runs_root: Path = RUNS_ROOT, log_lines: int = 25) -> Optional[dict]:
    """What a single move's run dir shows right now: whether it has finished (a
    verification.json means the wall has ruled), its log tail, and how much the
    experimenter has built in its workspace. Returns None if the run dir does not
    exist yet — a move whose subprocess has not started."""
    rid = _safe_id(run_id)
    if not rid:
        return None
    run_dir = Path(runs_root) / rid
    if not run_dir.is_dir():
        return None
    workspace = run_dir / "workspace"
    ws_files = 0
    try:
        with os.scandir(workspace) as it:
            for e in it:
                if e.name not in _SKIP_DIRS:
                    ws_files += 1
    except Exception:  # noqa: BLE001
        ws_files = 0
    last = newest_mtime(run_dir)
    started = _created(run_dir)
    return {
        "run_id": rid,
        "dir": str(run_dir),
        "started_at": started,
        "elapsed": (time.time() - started) if started else None,
        "log_tail": tail_lines(run_dir / "log.txt", limit=log_lines),
        "log_bytes": (lambda p: os.path.getsize(p) if p.is_file() else 0)(run_dir / "log.txt"),
        "workspace_files": ws_files,
        "last_write": last,
        "last_write_age": (time.time() - last) if last else None,
        "verification": _verification(run_dir),
        "finished": (run_dir / "verification.json").is_file()
        or (run_dir / "free_investigation.json").is_file(),
    }


# --------------------------------------------------------------------------- #
# Failures: the distinction that matters most.
# --------------------------------------------------------------------------- #

# A recorded failure is DATA. The director reads it on its next turn and decides
# what to do — retry differently, route around it, or stop — exactly as a researcher
# does when an instrument breaks. The only thing that ends a study is the director
# itself, so only a termination says "over".
FATAL_TERMINATIONS = {"director_failed"}

#: Every state health() can return, and which of them mean the study is OVER.
#: Defined beside the producer because a consumer that guesses gets it wrong:
#: follow.py waited for "ended-well", which health() has never emitted — so a
#: study that finished normally and wrote its report never printed the FINISHED
#: headline and `python -m liveview` (follow is the default mode) polled forever.
#: A watcher silently reporting a finished study as still running is the exact
#: misreport liveview exists to prevent, so the vocabulary lives in one place and
#: consumers import it.
HEALTH_STATES = ("finished", "ended-badly", "vanished", "running", "unknown")
TERMINAL_HEALTH_STATES = frozenset({"finished", "ended-badly", "vanished"})

_OUTCOME_PLAIN = {
    "sub_investigation_barren": "a sub-investigation finished with nothing verified",
    "sub_investigation_done": "a sub-investigation returned verified results",
    "insufficient_budget": "the director asked for a move it could not afford",
    "integration_nothing_to_compose": "an integration was asked for with nothing verified to compose yet",
    "decision_failed": "the director's own call failed this turn (it retries next turn)",
    "spawn_depth_cap": "a sub-investigation was refused: recursion depth cap",
    "spawn_insufficient_budget": "a sub-investigation was refused: not enough budget to carve",
    "memory_read": "read prior lessons from memory",
    "memory_written": "wrote a lesson to memory",
    "ideation_done": "the hypothesis apparatus returned candidates",
}


def _plain_outcome(entry: dict) -> str:
    """One plain sentence for an arc entry's outcome."""
    outcome = entry.get("outcome") or ""
    if outcome in _OUTCOME_PLAIN:
        return _OUTCOME_PLAIN[outcome]
    if outcome.endswith("_failed"):
        return f"{outcome[:-len('_failed')].replace('_', ' ')} raised and was recorded"
    return outcome or "no outcome recorded"


def _is_barren(entry: dict) -> bool:
    """A move that ran fine and simply found nothing that stood. The system records
    it as not-succeeded, but it is a negative RESULT, not a malfunction, and calling
    it a failure in the view would teach a watcher to distrust honest reporting."""
    outcome = (entry.get("outcome") or "").lower()
    return "nothing publishable" in outcome or "barren" in outcome


def _barren_means(entry: dict) -> str:
    """What a not-publishable move actually is, told by its own verified count."""
    total = entry.get("results_total") or 0
    good = entry.get("results_verified") or 0
    if total and good == total:
        return (f"the move ran and ALL {good} of its claims reproduced — it reports "
                "not-publishable because it did not consider the question answered, "
                "not because anything failed. Read it.")
    if good:
        return (f"the move ran and {good} of {total} claims reproduced; it did not "
                "clear the publishable bar. A partial result, not a malfunction.")
    return ("the move ran and measured, but nothing it produced stood — a real "
            "(negative) result, not a malfunction.")


MOVE_STATES = ("stood", "ran", "did_not_run")

# The state IN WORDS, defined once here rather than per surface: the terminal, the
# event log and the web view must never disagree about whether a move failed.
STATE_WORD = {
    "stood": "stood",
    # Named at length on purpose. "FAILED" was read as a malfunction when what it
    # meant was "did not claim to have answered the whole question".
    "ran": "ran, not publishable",
    "did_not_run": "did not run",
}


def _move_state(view: dict) -> str:
    """Three states, because `succeeded` is only two and the truth is three.

    pi_agent/dispatch.py:528 sets `succeeded = bool(result.publishable)`, and the
    experimenter (stages/free_experimenter.py:74) sets `publishable` only when the
    question is ANSWERED *and* every kept finding reproduced. Both halves. So a
    scouting move — dispatched to survey one candidate, never asked to answer the
    whole goal — reports publishable false and was drawn identically to a move that
    died on dispatch. Experiment 2's move 3 verified 21 of 21 claims, became the
    target the entire study was then built on, and rendered as a failure.

    Calling that a failure teaches a watcher to distrust honest reporting, which is
    the opposite of what the arc is for.

      "stood"        publishable: question answered, findings reproduced
      "ran"          it ran and measured but did not clear that bar — a RESULT
      "did_not_run"  nothing was measured: dispatch error, crash, or an honest halt
    """
    if view.get("succeeded"):
        return "stood"
    outcome = str(view.get("outcome") or "").lower()
    if any(k in outcome for k in ("dispatch_error", "crashed", "halted",
                                  "setup_error", "skipped")):
        return "did_not_run"
    if view.get("results_total") or view.get("run_id") or _is_barren(view):
        return "ran"
    return "did_not_run"


def failure_events(node: dict) -> list:
    """Everything that went wrong in this study (and its children), each labelled
    with what it MEANS — the distinction the terminal cannot make.

      severity "fatal"    the study is over and ended badly. Only a director-level
                          termination can be this.
      severity "recorded" something failed and the system wrote it down and carried
                          on. Tracebacks in here are expected and are not a death.
      severity "watch"    nothing has failed, but something is worth a human's eye
                          (a long silence, an unusually low verification rate).
    """
    events: list = []
    sid = node.get("study_id")

    report = node.get("report") or {}
    term = (report or {}).get("termination") or {}
    if term.get("reason") in FATAL_TERMINATIONS:
        events.append(
            {
                "severity": "fatal",
                "study_id": sid,
                "title": "the study ended because the director could not decide",
                "detail": term.get("detail"),
                "means": "the arc stopped early — budget may remain unspent. This is "
                         "the one failure that actually ends an investigation.",
            }
        )

    for entry in node.get("arc") or []:
        if entry.get("succeeded") is False:
            barren = _is_barren(entry)
            events.append(
                {
                    "severity": "watch" if barren else "recorded",
                    "study_id": sid,
                    "seq": entry.get("seq"),
                    "title": f"move {entry.get('seq')} ({entry.get('move_type')}): "
                             f"{_plain_outcome(entry)}",
                    "detail": entry.get("error") or entry.get("detail"),
                    # "nothing it produced stood" was FALSE for the move that mattered
                    # most in experiment 2: 21 of 21 claims reproduced and it still
                    # reported not-publishable, because it had not answered the whole
                    # question. Say what actually happened instead of assuming barren
                    # means empty-handed.
                    "means": _barren_means(entry) if barren
                    else "recorded to the arc; the director read it and continued.",
                }
            )
        run = entry.get("run") or {}
        ver = run.get("verification") or {}
        if ver.get("failed"):
            failed = [v for v in ver.get("verdicts") or [] if not v.get("verified")]
            first = failed[0] if failed else {}
            events.append(
                {
                    "severity": "recorded",
                    "study_id": sid,
                    "seq": entry.get("seq"),
                    "title": f"move {entry.get('seq')}: {ver.get('failed')} of "
                             f"{ver.get('total')} claims did not reproduce",
                    "detail": f"{first.get('label')} — {first.get('reason')}: "
                              f"{(first.get('detail') or '')[:400]}"
                    if first
                    else None,
                    "means": "the verification wall refused these numbers. The run "
                             "still stands as evidence; its unverified claims do not.",
                }
            )

    quiet = node.get("quiet_seconds")
    if node.get("state") == "running" and quiet is not None and quiet > QUIET_SECONDS:
        events.append(
            {
                "severity": "watch",
                "study_id": sid,
                "title": f"no file has changed in {int(quiet // 60)} minutes",
                "detail": "long moves are genuinely quiet for stretches, so this is "
                          "not by itself a failure.",
                "means": "check that the director process is still alive.",
            }
        )

    for child in node.get("children") or []:
        events.extend(failure_events(child))
    return events


# --------------------------------------------------------------------------- #
# The snapshot: one study node, recursively.
# --------------------------------------------------------------------------- #

def _annotate_fan_members(arc: list, decisions: list) -> None:
    """Give each fan member back its OWN question, in place.

    Why this join has to exist. One `run_fan` decision spends N moves and appends N
    arc rows, but writes a SINGLE decisions/decideN.json. The arc row carries no
    `domain` at all — its move_type is the bare string "single" and its `finding` is
    the parent fan decision's reasoning, copied identically onto every member. So a
    watcher saw six consecutive rows reading "single" with the same sentence under
    each, and could not tell which candidate any of them investigated. The questions
    were on disk the whole time, in the decision's `fan_domains`.

    The join is POSITIONAL, and that is safe because the producer makes it so:
    run_study_fan (pi_agent/study.py) pre-assigns run-ids sequentially, collects
    into a fixed-size list indexed by launch order, and appends to arc.jsonl
    sequentially afterward — "Returns the results in move order". So a run_fan at
    seq S owns rows S .. S+len(fan_domains)-1, in fan_domains order. Confirmed
    against study-20260730T034915Z, whose rows 3-8 are one six-member fan.

    It still FAILS SOFT, because being readable while things are broken is this
    module's entire job: a missing row (fan still in flight), a short or non-list
    fan_domains, a non-integer seq, or a row that already carries a real domain all
    leave the row exactly as it was rather than raising or inventing a label.
    """
    by_seq = {a.get("seq"): a for a in arc if isinstance(a.get("seq"), int)}
    for d in decisions or []:
        if not isinstance(d, dict) or d.get("action") != "run_fan":
            continue
        domains = d.get("fan_domains")
        start = d.get("seq")
        if not isinstance(domains, list) or not domains or not isinstance(start, int):
            continue
        for i, question in enumerate(domains):
            row = by_seq.get(start + i)
            if row is None or row.get("domain"):
                continue  # not written yet, or already labelled — never overwrite
            if isinstance(question, str) and question.strip():
                row["domain"] = question
            row["fan_index"] = i + 1
            row["fan_width"] = len(domains)
            # The finding is the PARENT's reasoning repeated on every member, so it
            # is worth reading once at the head of the fan and noise on the rest.
            row["finding_repeats_fan"] = i > 0


def _arc_entry_view(entry: dict, *, runs_root: Path, with_run: bool, log_lines: int) -> dict:
    """One move as a watcher reads it: what kind, whether it stood, what it found,
    what it cost, and the one-line finding the director attached."""
    results = entry.get("results") or []
    verified = sum(1 for r in results if isinstance(r, dict) and r.get("verified"))
    tool_output = entry.get("tool_output") or {}
    view = {
        "seq": entry.get("seq"),
        "at": entry.get("at"),
        "move_type": entry.get("move_type"),
        "run_id": entry.get("run_id"),
        "succeeded": entry.get("succeeded"),
        "outcome": entry.get("outcome"),
        "outcome_plain": _plain_outcome(entry),
        "publishable": entry.get("publishable"),
        "results_total": len(results),
        "results_verified": verified,
        "results": [
            {
                "label": r.get("label"),
                "value": r.get("value"),
                "verified": r.get("verified"),
                "reason": r.get("reason"),
            }
            for r in results
            if isinstance(r, dict)
        ],
        "artifacts": [
            a.get("name") for a in entry.get("reusable_artifacts") or [] if isinstance(a, dict)
        ],
        "cost": entry.get("cost"),
        "finding": entry.get("finding"),
        "child_study_id": tool_output.get("child_study_id"),
        "child_termination": tool_output.get("child_termination"),
        # A recorded failure carries its own words: `error` is the exception text a
        # guarded action raised, `detail` the honest sentence a refused action wrote
        # ("no moves remain to run an experiment"). Both belong in the ledger.
        # The hypotheses an ideation call produced. Without these a watcher sees
        # "call_ideation: done" and nothing about WHAT was proposed — which is the
        # most interesting thing that happens in an ideation turn.
        "hypotheses": [
            h.get("statement") for h in (tool_output.get("hypotheses") or [])
            if isinstance(h, dict) and h.get("statement")
        ],
        "ideation_depth": tool_output.get("depth"),
        "blocked_on": tool_output.get("blocked_on") or [],
        # T0.1: numbers this move established that contradict ones the study
        # already held. Read off the arc entry itself (not tool_output — the
        # study layer writes it, not the run), and compacted here so the reader
        # stays the one place that knows the on-disk shape.
        "quantity_conflicts": [
            {"kind": c.get("kind"), "quantity": c.get("name"),
             "detail": c.get("detail")}
            for c in (entry.get("quantity_conflicts") or [])
            if isinstance(c, dict)
        ],
        "error": tool_output.get("error"),
        "detail": tool_output.get("detail"),
    }
    # Computed from the finished view, so it can read results_total/run_id.
    view["state"] = _move_state(view)
    if with_run and entry.get("run_id"):
        view["run"] = read_run(entry["run_id"], runs_root=runs_root, log_lines=log_lines)
    return view


def _sum_cost(arc_views: list) -> dict:
    calls = tokens = 0
    for v in arc_views:
        c = v.get("cost") or {}
        if isinstance(c, dict):
            calls += int(c.get("calls") or 0)
            tokens += int(c.get("tokens") or 0)
    return {"calls": calls, "tokens": tokens}


def snapshot(
    study_id: str,
    *,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = RUNS_ROOT,
    depth: int = 0,
    max_depth: int = 6,
    log_lines: int = 25,
    _seen: Optional[set] = None,
) -> dict:
    """Read one study — and every sub-study beneath it — into a single JSON-able
    picture of RIGHT NOW.

    The node carries: the identity, the arc as moves a human can read, the director's
    turns (its reading and reasoning verbatim), verification counts, spend, the live
    phase, and the run dir of whatever is currently in flight. Children are the
    sub-investigations spawned from the arc, read the same way.

    Never raises on a missing or half-written file: a study that has just been created
    reads as a valid node with an empty arc.
    """
    sid = _safe_id(study_id) or study_id
    # `seen` carries the ids already read, including this one, so a child that links
    # back at an ancestor (or at a sibling twice) is read once and cannot loop.
    seen = _seen if _seen is not None else set()
    seen.add(sid)
    study_dir = Path(studies_root) / sid
    identity = read_json(study_dir / "study.json") or {}
    arc_raw, torn = read_jsonl(study_dir / "arc.jsonl")
    decisions = read_decisions(study_dir)
    report = read_json(study_dir / "report.json")

    arc = [
        _arc_entry_view(e, runs_root=runs_root, with_run=True, log_lines=log_lines)
        for e in arc_raw
    ]
    _annotate_fan_members(arc, decisions)

    node: dict = {
        "study_id": identity.get("study_id", sid),
        "exists": study_dir.is_dir(),
        "goal": identity.get("goal"),
        "mode": identity.get("mode"),
        "created_at": identity.get("created_at"),
        "parent_study_id": identity.get("parent_study_id"),
        "allowed_substrates": identity.get("allowed_substrates"),
        "depth": depth,
        "arc": arc,
        "arc_torn_line": torn > 0,
        "decisions": decisions,
        "report": report,
        "children": [],
    }

    # Verified-vs-total across this study's own moves.
    node["verified"] = sum(a["results_verified"] for a in arc)
    node["claims"] = sum(a["results_total"] for a in arc)
    node["publishable_moves"] = sum(1 for a in arc if a.get("publishable"))
    node["spend"] = _sum_cost(arc)
    # A finished study's report also counts the DIRECTOR's own calls, which never
    # appear in the arc (the arc carries each run's cost, not the deciding turns).
    # Carried separately rather than folded in, so the live number and the final
    # number are never silently mixed.
    node["spend_reported"] = (report or {}).get("total_spend")

    # Budget: final state if the report exists, else the last decision's view of it
    # — the only live source of "moves left" while a study is still running.
    node["budget"] = (report or {}).get("budget_final")
    if not node["budget"]:
        for d in reversed(decisions):
            if isinstance(d.get("budget_seen"), dict):
                node["budget"] = d["budget_seen"]
                break

    last_change = newest_mtime(study_dir, depth=2)
    for a in arc:
        run = a.get("run") or {}
        if run.get("last_write") and (not last_change or run["last_write"] > last_change):
            last_change = run["last_write"]

    # --- phase ------------------------------------------------------------- #
    n_arc = len(arc)
    # A decision file caught mid-flush has a seq but no content yet. It still proves
    # the turn happened, so it counts toward n_dec — but the ACTION it chose cannot be
    # read yet, so only complete decisions drive what the view says is in flight.
    complete = [d for d in decisions if not d.get("incomplete")]
    n_dec = max([d["seq"] for d in decisions], default=0)
    n_complete = max([d["seq"] for d in complete], default=0)
    in_flight: dict = {}
    if report:
        term = (report.get("termination") or {})
        node["state"] = "finished"
        node["phase"] = f"finished — {term.get('reason') or 'unknown reason'}"
        node["termination"] = term
    elif not study_dir.is_dir():
        node["state"] = "missing"
        node["phase"] = "no such study on disk"
    elif n_complete > n_arc:
        last = complete[-1]
        action = last.get("action") or "?"
        node["state"] = "running"
        in_flight = {
            "decision_seq": last.get("seq"),
            "action": action,
            "instrument": last.get("instrument"),
            "reasoning": last.get("reasoning"),
            "detail": last.get("detail"),
        }
        if action in ("run_experiment", "call_integration"):
            rid = f"{node['study_id']}-m{n_arc + 1}"
            in_flight["run_id"] = rid
            in_flight["run"] = read_run(rid, runs_root=runs_root, log_lines=log_lines)
            node["phase"] = f"move {n_arc + 1} running — {action}" + (
                f" on {last.get('instrument')}" if last.get("instrument") else ""
            )
        elif action == "spawn_sub_investigation":
            in_flight["child_study_id"] = f"{node['study_id']}-sub{last.get('seq')}"
            node["phase"] = f"move {n_arc + 1} running — sub-investigation"
        else:
            rid = f"{node['study_id']}-cap{last.get('seq')}"
            in_flight["run_id"] = rid
            in_flight["run"] = read_run(rid, runs_root=runs_root, log_lines=log_lines)
            node["phase"] = f"move {n_arc + 1} running — {action}"
    else:
        node["state"] = "running"
        node["phase"] = f"director deciding turn {n_complete + 1}"
        in_flight = {"decision_seq": n_complete + 1, "action": "deciding"}
    node["in_flight"] = in_flight
    node["decisions_made"] = n_dec
    node["moves_recorded"] = n_arc

    # --- children ---------------------------------------------------------- #
    child_ids: list = []
    for a in arc:
        if a.get("child_study_id"):
            child_ids.append(a["child_study_id"])
    if in_flight.get("child_study_id"):
        child_ids.append(in_flight["child_study_id"])
    if depth < max_depth:
        for cid in child_ids:
            if cid in seen:
                continue
            seen.add(cid)
            if not (Path(studies_root) / (_safe_id(cid) or "")).is_dir():
                continue
            node["children"].append(
                snapshot(
                    cid,
                    studies_root=studies_root,
                    runs_root=runs_root,
                    depth=depth + 1,
                    max_depth=max_depth,
                    log_lines=log_lines,
                    _seen=seen,
                )
            )

    flight_run = (in_flight.get("run") or {}).get("last_write")
    if flight_run and (not last_change or flight_run > last_change):
        last_change = flight_run
    for child in node["children"]:
        if child.get("last_change") and (
            not last_change or child["last_change"] > last_change
        ):
            last_change = child["last_change"]
    node["last_change"] = last_change
    node["quiet_seconds"] = (time.time() - last_change) if last_change else None
    return node


def totals(node: dict) -> dict:
    """Roll a node and everything under it into the numbers a watcher wants at a
    glance: how many claims stood out of how many were made, how many moves ran, and
    what the whole tree has spent."""
    verified = node.get("verified") or 0
    claims = node.get("claims") or 0
    moves = len(node.get("arc") or [])
    calls = (node.get("spend") or {}).get("calls") or 0
    tokens = (node.get("spend") or {}).get("tokens") or 0
    studies = 1
    for child in node.get("children") or []:
        c = totals(child)
        verified += c["verified"]
        claims += c["claims"]
        moves += c["moves"]
        calls += c["calls"]
        tokens += c["tokens"]
        studies += c["studies"]
    return {
        "verified": verified,
        "claims": claims,
        "moves": moves,
        "calls": calls,
        "tokens": tokens,
        "studies": studies,
    }


def active_node(node: dict) -> dict:
    """The deepest node that is actually moving. A parent whose current move is a
    sub-investigation is not itself doing anything — the child is — so this is the
    node whose phase belongs at the top of the view."""
    for child in node.get("children") or []:
        if child.get("state") == "running":
            return active_node(child)
    return node


def director_processes(goal: Optional[str] = None) -> list:
    """Whether a director process is alive, asked of the operating system rather
    than inferred from files. Best-effort and never fatal: if `ps` is unavailable
    the view simply says it could not tell, which is honest, instead of claiming a
    run is dead. When `goal` is given, only processes whose command line carries
    that goal are returned — that is what ties a process to THIS study."""
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,args="],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except Exception:  # noqa: BLE001
        return []
    # A MISSING GOAL MUST NOT MEAN "MATCH EVERY DIRECTOR". With goal None or ""
    # the needle was "", `needle and ...` was False, and the filter fell through
    # — so ANY pi_agent process in the process table counted as this study's.
    # health() then reported a long-dead study as "RUNNING — director process
    # alive (pid ...)" for as long as any other director happened to be up. And
    # goal IS None on the path that matters: study.json missing, or caught
    # half-written by a study that is starting or has been damaged, which is
    # exactly when a watcher most needs the truth. Returning nothing is the
    # honest answer — health() then falls through to its disk-quiet reasoning,
    # which reports "still writing" or "vanished" on evidence rather than on a
    # coincidence.
    needle = (goal or "")[:60]
    if not needle:
        return []
    procs = []
    for line in out.splitlines():
        line = line.strip()
        if "pi_agent" not in line or "grep" in line:
            continue
        pid, _, args = line.partition(" ")
        if needle not in args:
            continue
        if not pid.isdigit():
            continue
        procs.append({"pid": int(pid), "args": args.strip()})
    return procs


def health(root: dict, events: list, processes: list, *, process_checked: bool = True) -> dict:
    """THE ONE LINE a watcher needs: is this run alive, is it over, and did anything
    actually kill it?

    This exists because the terminal cannot answer it. A child subprocess printing a
    traceback looks exactly like a fatal error, and once convinced the owner a healthy
    run had died. So the verdict here is assembled from the things that actually
    decide it — a written report, a live process, files still changing — and the
    recorded failures are counted separately and named as what they are.

    Returns {state, headline, detail, counts} where state is one of:
      "running"  the study is moving; recorded failures may exist and are not deaths
      "finished" the study wrote its report and ended on its own terms
      "ended-badly" the study wrote a report whose termination was itself a failure
      "vanished" no report, no process, nothing changing — it probably died
      "unknown"  a report is missing and the process could not be checked
    """
    counts = {
        "fatal": sum(1 for e in events if e["severity"] == "fatal"),
        "recorded": sum(1 for e in events if e["severity"] == "recorded"),
        "watch": sum(1 for e in events if e["severity"] == "watch"),
    }
    recorded_note = (
        f"{counts['recorded']} recorded failure(s) — written down and routed around, "
        "not deaths"
        if counts["recorded"]
        else "no recorded failures"
    )
    if root and root.get("state") == "finished":
        term = root.get("termination") or {}
        reason = term.get("reason")
        if reason in FATAL_TERMINATIONS:
            return {
                "state": "ended-badly",
                "headline": "ENDED BADLY — the director could not decide and the arc stopped",
                "detail": term.get("detail"),
                "counts": counts,
            }
        return {
            "state": "finished",
            "headline": f"FINISHED — {reason or 'no reason recorded'}",
            "detail": term.get("detail") or recorded_note,
            "counts": counts,
        }
    if not process_checked:
        return {
            "state": "unknown",
            "headline": "RUNNING (process not checked)",
            "detail": recorded_note,
            "counts": counts,
        }
    if processes:
        pids = ", ".join(str(p["pid"]) for p in processes)
        return {
            "state": "running",
            "headline": f"RUNNING — director process alive (pid {pids})",
            "detail": recorded_note,
            "counts": counts,
        }
    quiet = root.get("quiet_seconds") if root else None
    quiet_txt = f"nothing has changed on disk for {int(quiet // 60)} min" if quiet else ""
    if quiet is not None and quiet < 120:
        return {
            "state": "unknown",
            "headline": "NO MATCHING PROCESS — but files are still changing",
            "detail": "the director process could not be matched by its goal text; "
                      "the study is still writing, so treat it as alive. " + recorded_note,
            "counts": counts,
        }
    return {
        "state": "vanished",
        "headline": "NO PROCESS AND NO REPORT — this run appears to have stopped",
        "detail": (quiet_txt + ". No report.json was written, so it did not end on its "
                   "own terms. " + recorded_note).strip(". "),
        "counts": counts,
    }


_SEVERITY_ORDER = {"fatal": 0, "recorded": 1, "watch": 2}


def full_snapshot(
    study_id: Optional[str] = None,
    *,
    studies_root: Path = STUDIES_ROOT,
    runs_root: Path = RUNS_ROOT,
    log_lines: int = 25,
    check_process: bool = True,
) -> dict:
    """Everything the view draws, in one call: the study tree, the deepest active
    node, rolled-up totals, the failure ledger with its severities, and whether a
    director process is alive."""
    sid = study_id or latest_study(studies_root)
    if not sid:
        return {
            "study_id": None,
            "error": "no studies found",
            "at": time.time(),
            "root": None,
            "totals": {"verified": 0, "claims": 0, "moves": 0, "calls": 0, "tokens": 0,
                       "studies": 0},
            "events": [],
            "processes": [],
        }
    root = snapshot(sid, studies_root=studies_root, runs_root=runs_root, log_lines=log_lines)
    active = active_node(root)
    procs = director_processes(root.get("goal")) if check_process else []
    events = sorted(
        failure_events(root),
        key=lambda e: (_SEVERITY_ORDER.get(e["severity"], 9), e.get("study_id") or "",
                       e.get("seq") or 0),
    )
    return {
        "at": time.time(),
        "study_id": root.get("study_id"),
        "root": root,
        "active_study_id": active.get("study_id"),
        "active_phase": active.get("phase"),
        "active": active,
        "totals": totals(root),
        "events": events,
        "health": health(root, events, procs, process_checked=check_process),
        "processes": procs,
        "process_checked": check_process,
    }
