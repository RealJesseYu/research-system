"""tests/test_liveview.py — the live view is a READER, and these tests hold it to it.

Three things are being protected here.

1. IT TELLS THE TRUTH ABOUT WHAT IS HAPPENING. The phase is inferred from the two
   counts the system already writes (a decision file before an action, an arc line
   after it), so the tests drive those counts directly and check the view says the
   right thing at each point, including part-way down a tree of sub-investigations.

2. IT DISTINGUISHES A RECORDED FAILURE FROM A FATAL ONE. This is the whole point:
   a child subprocess printing a traceback once convinced the owner a healthy run
   had died. A traceback in a verification verdict must read as data; only a
   director-level termination may read as fatal.

3. IT NEVER TOUCHES THE RUN. A study tree is fingerprinted (paths, sizes, mtimes)
   before and after a full snapshot, and the fingerprint must be identical — the
   view may not create, modify, or even bump the mtime of anything it reads. It
   must also survive files caught mid-write, because that is the normal state of a
   study that is being appended to right now.

Everything is built in tmp_path: studies/ and runs/ are gitignored evidence, so a
test may never depend on a real run being present on disk.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import pytest

from liveview import reader, render, tui
from liveview.reader import (HEALTH_STATES, TERMINAL_HEALTH_STATES,
                             director_processes)


# --------------------------------------------------------------------------- #
# Fixture builders: a study tree exactly as the running system writes one.
# --------------------------------------------------------------------------- #

def _mk_study(root: Path, sid: str, goal: str = "a goal", *, mode: str = "auto",
              parent: str | None = None) -> Path:
    d = root / sid
    (d / "decisions").mkdir(parents=True, exist_ok=True)
    (d / "study.json").write_text(json.dumps({
        "study_id": sid, "goal": goal, "mode": mode, "allowed_substrates": None,
        "created_at": "2026-07-26T00:00:00+00:00", "parent_study_id": parent,
    }))
    return d


def _add_decision(study_dir: Path, seq: int, action: str, *, instrument=None,
                  reading="what it read", reasoning="why it chose this",
                  detail=None, remaining=3, total=8) -> None:
    (study_dir / "decisions" / f"decide{seq}.json").write_text(json.dumps({
        "seq": seq,
        "input": {"budget": {"remaining": remaining, "total_at_node": total,
                             "spent_here": total - remaining}},
        "decision": {"action": action, "instrument": instrument, "reading": reading,
                     "reasoning": reasoning, "detail": detail},
        "timing": {"model": "claude-opus-5", "duration_seconds": 12.5, "attempts": 1},
    }))


def _add_move(study_dir: Path, seq: int, *, move_type="single", run_id=None,
              succeeded=True, outcome="completed free investigation (publishable)",
              results=None, cost=None, finding="a finding", tool_output=None) -> None:
    entry = {
        "seq": seq, "at": "2026-07-26T01:00:00+00:00", "move_type": move_type,
        "run_id": run_id, "succeeded": succeeded, "outcome": outcome,
        "publishable": succeeded, "results": results or [], "cost": cost,
        "reusable_artifacts": [], "tool_output": tool_output or {}, "finding": finding,
    }
    with open(study_dir / "arc.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")


def _add_report(study_dir: Path, reason: str, detail: str = "because") -> None:
    (study_dir / "report.json").write_text(json.dumps({
        "study_id": study_dir.name, "termination": {"reason": reason, "detail": detail},
        "budget_final": {"remaining": 2, "total_at_node": 8, "spent_here": 6},
    }))


def _mk_run(runs_root: Path, run_id: str, *, log="line one\nline two\n",
            verification=None, workspace_files=0) -> Path:
    d = runs_root / run_id
    (d / "workspace").mkdir(parents=True, exist_ok=True)
    (d / "log.txt").write_text(log)
    for i in range(workspace_files):
        (d / "workspace" / f"f{i}.py").write_text("x = 1\n")
    if verification is not None:
        (d / "verification.json").write_text(json.dumps(verification))
    return d


@pytest.fixture()
def tree(tmp_path):
    """A parent study mid-flight with one finished sub-investigation beneath it."""
    studies, runs = tmp_path / "studies", tmp_path / "runs"
    parent = _mk_study(studies, "study-P", "compose two verified parts")
    _add_decision(parent, 1, "spawn_sub_investigation")
    _add_move(parent, 1, move_type="spawn_sub_investigation", run_id="study-P-cap1",
              outcome="sub_investigation_done",
              results=[{"label": "span", "value": 2.0, "verified": True,
                        "reason": "reproduced"}],
              tool_output={"child_study_id": "study-P-sub1",
                           "child_termination": "budget_spent"})
    child = _mk_study(studies, "study-P-sub1", "size the wing", parent="study-P")
    _add_decision(child, 1, "run_experiment", instrument="python_experiment")
    _add_move(child, 1, run_id="study-P-sub1-m1",
              results=[{"label": "glide ratio", "value": 12.0, "verified": True,
                        "reason": "reproduced"},
                       {"label": "sink rate", "value": 0.59, "verified": False,
                        "reason": "mismatch"}],
              cost={"calls": 1, "tokens": 1000})
    _add_report(child, "budget_spent")
    _mk_run(runs, "study-P-sub1-m1", verification={
        "total": 2, "verified": 1, "failed": 1, "publishable": False,
        "verdicts": [
            {"verified": True, "label": "glide ratio", "reason": "reproduced"},
            {"verified": False, "label": "sink rate", "reason": "mismatch",
             "detail": "re-running produced 0.61, not 0.59"},
        ]})
    return {"studies": studies, "runs": runs, "parent": parent, "child": child}


def _snap(tree, sid="study-P", **kw):
    return reader.full_snapshot(sid, studies_root=tree["studies"],
                                runs_root=tree["runs"], check_process=False, **kw)


# --------------------------------------------------------------------------- #
# 1. Tolerance: files caught mid-write are normal, not errors.
# --------------------------------------------------------------------------- #

def test_torn_last_jsonl_line_is_skipped_and_counted(tmp_path):
    p = tmp_path / "arc.jsonl"
    p.write_text(json.dumps({"seq": 1}) + "\n" + '{"seq": 2, "move_ty')
    entries, skipped = reader.read_jsonl(p)
    assert [e["seq"] for e in entries] == [1]
    assert skipped == 1


def test_half_written_json_reads_as_none_not_a_crash(tmp_path):
    p = tmp_path / "report.json"
    p.write_text('{"study_id": "x", "termin')
    assert reader.read_json(p) is None
    assert reader.read_json(tmp_path / "absent.json") is None


def test_snapshot_survives_an_arc_being_appended_to(tree):
    with open(tree["parent"] / "arc.jsonl", "a") as f:
        f.write('{"seq": 2, "move_type": "sing')  # a line mid-append
    snap = _snap(tree)
    assert snap["root"]["arc_torn_line"] is True
    assert len(snap["root"]["arc"]) == 1  # the complete move is still shown
    assert snap["health"]["state"] in ("running", "unknown")


def test_tail_lines_reads_the_end_of_a_large_log(tmp_path):
    p = tmp_path / "log.txt"
    p.write_text("".join(f"line {i}\n" for i in range(5000)))
    lines = reader.tail_lines(p, limit=3)
    assert lines == ["line 4997", "line 4998", "line 4999"]


# --------------------------------------------------------------------------- #
# 2. The live phase, from the counts the system already writes.
# --------------------------------------------------------------------------- #

def test_fresh_study_reads_as_deciding_its_first_turn(tmp_path):
    studies = tmp_path / "studies"
    _mk_study(studies, "study-N")
    snap = reader.full_snapshot("study-N", studies_root=studies,
                                runs_root=tmp_path / "runs", check_process=False)
    assert snap["root"]["state"] == "running"
    assert snap["root"]["phase"] == "director deciding turn 1"
    assert snap["root"]["arc"] == []


def test_a_decision_ahead_of_the_arc_means_that_move_is_in_flight(tree):
    """A decision file is written BEFORE its action runs, an arc line after it
    finishes — so decisions > arc is exactly 'a move is running right now'."""
    _add_decision(tree["parent"], 2, "call_integration", instrument="python_experiment")
    _mk_run(tree["runs"], "study-P-m2", log="=== starting ===\n", workspace_files=3)
    snap = _snap(tree)
    root = snap["root"]
    assert root["phase"] == "move 2 running — call_integration on python_experiment"
    flight = root["in_flight"]
    assert flight["run_id"] == "study-P-m2"
    assert flight["run"]["workspace_files"] == 3
    assert flight["run"]["finished"] is False
    assert "=== starting ===" in flight["run"]["log_tail"]


def test_equal_counts_mean_the_director_is_thinking(tree):
    snap = _snap(tree)
    assert snap["root"]["phase"] == "director deciding turn 2"
    assert snap["root"]["in_flight"]["action"] == "deciding"


def test_the_live_phase_descends_into_a_running_sub_investigation(tmp_path):
    """A parent whose current move is a sub-investigation is not itself doing
    anything — the child is, and the child's phase is what a watcher wants. The
    child's id is derivable before the parent's arc mentions it: the system mints
    <parent>-sub<decision seq>, so the view can follow a spawn the moment it starts."""
    studies, runs = tmp_path / "studies", tmp_path / "runs"
    parent = _mk_study(studies, "study-P", "compose two parts")
    _add_decision(parent, 1, "spawn_sub_investigation")       # in flight: no arc line
    child = _mk_study(studies, "study-P-sub1", "size the wing", parent="study-P")
    _add_decision(child, 1, "run_experiment", instrument="python_experiment")
    _mk_run(runs, "study-P-sub1-m1", log="=== child run ===\n")
    snap = reader.full_snapshot("study-P", studies_root=studies, runs_root=runs,
                                check_process=False)
    assert snap["root"]["phase"] == "move 1 running — sub-investigation"
    assert snap["root"]["in_flight"]["child_study_id"] == "study-P-sub1"
    assert snap["active_study_id"] == "study-P-sub1"
    assert snap["active_phase"] == "move 1 running — run_experiment on python_experiment"
    text = "\n".join(render.render(snap, color=False))
    assert "in sub-investigation study-P-sub1" in text


def test_a_decision_file_caught_mid_flush_does_not_invent_a_phase(tree):
    """A decision is written the instant the director finishes thinking, so the view
    can catch one half-flushed. The turn counts (it happened) but its chosen action
    cannot be read yet, so the view must not report a move as running off a blank."""
    (tree["parent"] / "decisions" / "decide2.json").write_text('{"seq": 2, "decis')
    snap = _snap(tree)
    assert snap["root"]["phase"] == "director deciding turn 2"
    assert snap["root"]["decisions_made"] == 2
    text = "\n".join(render.render(snap, color=False))
    assert "what it read" in text          # still shows the last COMPLETE turn
    assert "None" not in snap["root"]["phase"]


def test_a_finished_study_reports_its_termination(tree):
    _add_report(tree["parent"], "director_judged_complete", "the goal is answered")
    snap = _snap(tree)
    assert snap["root"]["state"] == "finished"
    assert snap["health"]["state"] == "finished"
    assert "director_judged_complete" in snap["health"]["headline"]


def test_missing_study_is_reported_not_raised(tmp_path):
    snap = reader.full_snapshot("study-nope", studies_root=tmp_path / "studies",
                                runs_root=tmp_path / "runs", check_process=False)
    assert snap["root"]["state"] == "missing"


# --------------------------------------------------------------------------- #
# 3. Recorded vs fatal — the distinction the terminal cannot make.
# --------------------------------------------------------------------------- #

def test_a_traceback_in_a_verdict_is_recorded_data_not_a_death(tree):
    """THE REGRESSION THIS VIEW EXISTS FOR. A child subprocess dying and printing
    its traceback is a failure the system records and routes around; it must never
    be presented as the run dying."""
    _mk_run(tree["runs"], "study-P-m2", verification={
        "total": 3, "verified": 0, "failed": 3, "publishable": False,
        "verdicts": [{"verified": False, "label": "spiral mode", "reason": "rerun_failed",
                      "detail": "the experiment exited 1. stderr: Traceback (most recent "
                                "call last): ModuleNotFoundError: No module named 'cl'"}]})
    _add_move(tree["parent"], 2, run_id="study-P-m2", succeeded=True,
              outcome="completed free investigation (nothing publishable)")
    snap = _snap(tree)
    tracebacks = [e for e in snap["events"] if "did not reproduce" in e["title"]]
    assert tracebacks, "a failed verification must appear in the ledger"
    assert all(e["severity"] == "recorded" for e in tracebacks)
    assert snap["health"]["counts"]["fatal"] == 0
    assert snap["health"]["state"] in ("running", "unknown")
    text = "\n".join(render.render(snap, color=False))
    assert "0 fatal" in text
    assert "the director reads it on its next turn" in text


def test_only_a_director_level_termination_is_fatal(tree):
    _add_report(tree["parent"], "director_failed",
                "the free director could not produce a decision: Exception")
    snap = _snap(tree)
    fatal = [e for e in snap["events"] if e["severity"] == "fatal"]
    assert len(fatal) == 1
    assert snap["health"]["state"] == "ended-badly"
    assert "ENDED BADLY" in snap["health"]["headline"]


def test_ordinary_terminations_are_not_fatal(tree):
    for reason in ("budget_spent", "director_judged_complete", "decision_cap"):
        _add_report(tree["parent"], reason)
        snap = _snap(tree)
        assert [e for e in snap["events"] if e["severity"] == "fatal"] == []
        assert snap["health"]["state"] == "finished"


def test_a_move_that_found_nothing_is_a_result_not_a_failure(tree):
    _add_move(tree["parent"], 2, succeeded=False,
              outcome="completed free investigation (nothing publishable)")
    snap = _snap(tree)
    barren = [e for e in snap["events"] if "nothing publishable" in e["title"]]
    assert barren and barren[0]["severity"] == "watch"
    assert "negative" in barren[0]["means"]


def test_a_raised_action_is_recorded_with_its_error(tree):
    _add_move(tree["parent"], 2, move_type="call_ideation", succeeded=False,
              outcome="call_ideation_failed",
              tool_output={"error": "RuntimeError: the tool broke"})
    snap = _snap(tree)
    ev = [e for e in snap["events"] if "call ideation raised" in e["title"]]
    assert ev and ev[0]["severity"] == "recorded"
    assert "RuntimeError" in ev[0]["detail"]
    assert "the director read it and continued" in ev[0]["means"]


def test_no_process_and_no_report_reads_as_vanished(tree):
    """The honest opposite case: nothing running, nothing written, nothing changing."""
    old = time.time() - 3600
    for p in tree["parent"].rglob("*"):
        os.utime(p, (old, old))
    os.utime(tree["parent"], (old, old))
    snap = reader.full_snapshot("study-P", studies_root=tree["studies"],
                                runs_root=tree["runs"], check_process=True)
    # No pi_agent process is running this tmp_path goal, so the view must say so.
    assert snap["health"]["state"] in ("vanished", "unknown")
    if snap["health"]["state"] == "vanished":
        assert "did not end on its own terms" in snap["health"]["detail"]


def test_a_long_silence_is_flagged_to_watch_not_declared_dead(tree):
    old = time.time() - (reader.QUIET_SECONDS + 600)
    for p in list(tree["parent"].rglob("*")) + [tree["parent"]]:
        os.utime(p, (old, old))
    for p in list(tree["runs"].rglob("*")) + [tree["runs"]]:
        os.utime(p, (old, old))
    for p in list(tree["child"].rglob("*")) + [tree["child"]]:
        os.utime(p, (old, old))
    snap = _snap(tree)
    quiet = [e for e in snap["events"] if "no file has changed" in e["title"]]
    assert quiet and quiet[0]["severity"] == "watch"
    assert "not by itself a failure" in quiet[0]["detail"]


# --------------------------------------------------------------------------- #
# 4. The numbers: verified-vs-total, spend, budget, tree roll-up.
# --------------------------------------------------------------------------- #

def test_totals_roll_up_across_sub_investigations(tree):
    tot = _snap(tree)["totals"]
    assert tot["studies"] == 2
    assert tot["moves"] == 2                       # one parent move, one child move
    assert (tot["verified"], tot["claims"]) == (2, 3)
    assert tot["tokens"] == 1000 and tot["calls"] == 1


def test_budget_comes_from_the_live_decision_before_a_report_exists(tree):
    assert _snap(tree)["root"]["budget"]["remaining"] == 3
    _add_report(tree["parent"], "budget_spent")
    assert _snap(tree)["root"]["budget"]["remaining"] == 2   # report wins once written


def test_per_move_claims_are_available_for_drill_down(tree):
    child = _snap(tree, "study-P-sub1")["root"]
    move = child["arc"][0]
    assert move["results_verified"] == 1 and move["results_total"] == 2
    assert move["run"]["verification"]["failed"] == 1
    assert move["run"]["verification"]["verdicts"][1]["reason"] == "mismatch"


def test_a_cycle_in_child_links_cannot_loop_forever(tmp_path):
    studies = tmp_path / "studies"
    a = _mk_study(studies, "study-A")
    b = _mk_study(studies, "study-A-sub1", parent="study-A")
    _add_move(a, 1, move_type="spawn_sub_investigation",
              tool_output={"child_study_id": "study-A-sub1"})
    _add_move(b, 1, move_type="spawn_sub_investigation",
              tool_output={"child_study_id": "study-A"})   # points back at its parent
    snap = reader.full_snapshot("study-A", studies_root=studies,
                                runs_root=tmp_path / "runs", check_process=False)
    assert snap["totals"]["studies"] == 2


# --------------------------------------------------------------------------- #
# 5. Read-only: watching may not change a single byte of the run.
# --------------------------------------------------------------------------- #

def _fingerprint(root: Path) -> dict:
    out = {}
    for p in sorted(root.rglob("*")):
        st = p.stat()
        out[str(p)] = (st.st_size, st.st_mtime_ns, st.st_mode)
    return out


def test_a_full_snapshot_changes_nothing_on_disk(tree):
    before = {"s": _fingerprint(tree["studies"]), "r": _fingerprint(tree["runs"])}
    for _ in range(3):
        reader.full_snapshot("study-P", studies_root=tree["studies"],
                             runs_root=tree["runs"], check_process=False)
    after = {"s": _fingerprint(tree["studies"]), "r": _fingerprint(tree["runs"])}
    assert before == after


def test_rendering_and_the_terminal_view_change_nothing_either(tree, tmp_path):
    before = {"s": _fingerprint(tree["studies"]), "r": _fingerprint(tree["runs"])}
    out = (tmp_path / "out.txt").open("w")
    tui.watch("study-P", once=True, color=False, out=out,
              studies_root=tree["studies"], runs_root=tree["runs"])
    out.close()
    after = {"s": _fingerprint(tree["studies"]), "r": _fingerprint(tree["runs"])}
    assert before == after


def test_ids_from_outside_cannot_escape_the_evidence_roots(tree):
    assert reader._safe_id("../../etc/passwd") is None
    assert reader._safe_id("study-P/../../x") is None
    assert reader._safe_id("study-P-m4") == "study-P-m4"
    assert reader.read_run("../../etc", runs_root=tree["runs"]) is None


def test_directory_walks_are_bounded(tree, monkeypatch):
    """A watcher must not cost the run it watches: the heartbeat walk stops after a
    bounded number of entries however large a workspace grows."""
    big = tree["runs"] / "study-P-m2" / "workspace"
    big.mkdir(parents=True)
    for i in range(50):
        (big / f"f{i}.txt").write_text("x")
    monkeypatch.setattr(reader, "_MAX_WALK_ENTRIES", 5)
    assert reader.newest_mtime(tree["runs"]) is not None   # returns, does not walk all


# --------------------------------------------------------------------------- #
# 6. The drawing itself.
# --------------------------------------------------------------------------- #

def test_the_terminal_view_shows_the_things_a_watcher_asked_for(tree):
    _add_decision(tree["parent"], 2, "call_integration", instrument="python_experiment",
                  reading="the two parts each stand alone",
                  reasoning="only a joint measurement can catch the composition failure")
    _mk_run(tree["runs"], "study-P-m2", log="=== supervisor run starting ===\n")
    text = "\n".join(render.render(_snap(tree), color=False, width=100))
    assert "move 2 running — call_integration on python_experiment" in text   # phase
    assert "only a joint measurement" in text                                 # reasoning
    assert "the two parts each stand alone" in text                           # reading
    assert "2/3" in text                                                      # verified
    assert "THE ARC SO FAR" in text                                           # the arc
    assert "=== supervisor run starting ===" in text                          # live log
    assert "FAILURES" in text


def test_rendering_never_raises_on_a_bare_or_broken_snapshot():
    assert render.render({"error": "no studies found", "root": None}, color=False)
    minimal = {"root": {"study_id": "s", "arc": [], "children": [], "state": "running",
                        "phase": "?", "in_flight": {}, "decisions": []},
               "totals": {}, "events": [], "health": {}}
    assert render.render(minimal, color=False)


def test_watch_once_exit_code_flags_a_bad_ending(tree, tmp_path):
    out = (tmp_path / "a.txt").open("w")
    assert tui.watch("study-P", once=True, color=False, out=out,
                     studies_root=tree["studies"], runs_root=tree["runs"]) == 0
    out.close()
    _add_report(tree["parent"], "director_failed", "could not decide")
    out = (tmp_path / "b.txt").open("w")
    assert tui.watch("study-P", once=True, color=False, out=out,
                     studies_root=tree["studies"], runs_root=tree["runs"]) == 1
    out.close()
    assert "ENDED BADLY" in (tmp_path / "b.txt").read_text()


def test_latest_study_prefers_the_one_still_running(tree):
    _mk_study(tree["studies"], "study-Z", "an older finished study")
    _add_report(tree["studies"] / "study-Z", "budget_spent")
    assert reader.latest_study(tree["studies"]) == "study-P"
    _add_report(tree["parent"], "budget_spent")
    assert reader.latest_study(tree["studies"]) in ("study-P", "study-Z")


def test_a_long_abandoned_study_does_not_outrank_the_one_that_just_finished(tree):
    """A run killed long ago is unfinished forever. Preferring "unfinished" blindly
    would show that corpse instead of the study that just completed — which is exactly
    what happened the first time a live run finished under this view."""
    stale = _mk_study(tree["studies"], "study-OLD", "abandoned yesterday")
    _add_decision(stale, 1, "run_experiment")
    old = time.time() - (reader.QUIET_SECONDS + 7200)
    for p in list(stale.rglob("*")) + [stale]:
        os.utime(p, (old, old))
    _add_report(tree["parent"], "director_judged_complete")   # this one just ended
    assert reader.latest_study(tree["studies"]) == "study-P"


def test_list_studies_marks_children_and_finished_state(tree):
    listed = {s["study_id"]: s for s in reader.list_studies(tree["studies"])}
    assert listed["study-P-sub1"]["parent_study_id"] == "study-P"
    assert listed["study-P-sub1"]["finished"] is True
    assert listed["study-P"]["finished"] is False


# --------------------------------------------------------------------------- #
# 7. The web view: same data, read-only routes, no path escapes.
# --------------------------------------------------------------------------- #

@pytest.fixture()
def server(tree):
    from liveview.web import serve

    httpd = serve(port=0, studies_root=tree["studies"], runs_root=tree["runs"],
                  open_browser=False, serve_forever=False)
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def _get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_web_serves_the_page_and_the_snapshot(server):
    code, body = _get(server + "/")
    assert code == 200 and b"<!doctype html>" in body[:40]
    code, body = _get(server + "/api/snapshot")
    snap = json.loads(body)
    assert code == 200
    assert snap["study_id"] == "study-P"
    assert snap["totals"]["claims"] == 3
    assert "health" in snap and "events" in snap


def test_web_log_and_decision_routes(server):
    code, body = _get(server + "/api/log?run=study-P-sub1-m1&n=5")
    assert code == 200 and json.loads(body)["lines"] == ["line one", "line two"]
    code, body = _get(server + "/api/decision?study=study-P-sub1&n=1")
    assert code == 200 and json.loads(body)[0]["action"] == "run_experiment"


def test_web_refuses_ids_that_try_to_leave_the_evidence_roots(server):
    for path in ("/api/log?run=../../../etc/passwd",
                 "/api/decision?study=../../../etc",
                 "/api/log?run="):
        code, _ = _get(server + path)
        assert code == 400
    assert _get(server + "/nope")[0] == 404


def test_web_snapshot_matches_the_reader(server, tree):
    direct = _snap(tree)
    served = json.loads(_get(server + "/api/snapshot?study=study-P")[1])
    assert served["root"]["phase"] == direct["root"]["phase"]
    assert served["totals"] == direct["totals"]
    assert len(served["events"]) == len(direct["events"])


# ---------------------------------------------------------------------------
# follow: print each thing ONCE.
#
# THE COMPLAINT: "i keep getting the same damn message over and over again, i
# want it ONCE and i want to see what its actually doing."
#
# Two bugs behind it. The dashboard repainted every tick; a first fix compared
# the RENDERED STRING, which carries a live clock in its header, so it differed
# every tick and repainted anyway. And the shape was wrong regardless — a study
# is quiet for minutes at a time, so what a watcher wants is a log of what
# happened, not a picture that redraws. Change is now detected from the study's
# own state (decision seq, arc seq, health), never from rendered text.
# ---------------------------------------------------------------------------

def _follow_snap(decisions=(), arc=(), state="running", study_id="s1"):
    return {"active": {"exists": True, "study_id": study_id, "mode": "auto",
                       "goal": "g", "decisions": list(decisions), "arc": list(arc)},
            "health": {"state": state, "headline": "done", "detail": "d"}}


def _follower():
    from liveview.follow import Follower
    return Follower(color=False)


def test_the_same_snapshot_twice_prints_nothing_the_second_time():
    f = _follower()
    snap = _follow_snap(decisions=[{"seq": 1, "action": "call_ideation", "reasoning": "why"}])
    assert f.events(snap)
    assert f.events(snap) == []
    assert f.events(snap) == []


def test_a_clock_in_the_data_cannot_cause_a_reprint():
    """The exact defect: comparing rendered text let a header timestamp defeat
    change detection."""
    f = _follower()
    snap = _follow_snap(decisions=[{"seq": 1, "action": "stop", "reasoning": "done"}])
    f.events(snap)
    snap2 = dict(snap, at="a-different-timestamp")
    assert f.events(snap2) == []


def test_a_new_decision_prints_the_action_and_the_reasoning():
    """'i want to see what its actually doing' — the director's own words."""
    f = _follower()
    f.events(_follow_snap())
    out = "\n".join(f.events(_follow_snap(decisions=[
        {"seq": 1, "action": "run_experiment", "reasoning": "probe cheaply",
         "reading": "the last move showed X", "domain": "measure Y"}])))
    assert "run_experiment" in out
    assert "probe cheaply" in out
    assert "the last move showed X" in out
    assert "measure Y" in out


def test_ideation_hypotheses_are_shown():
    f = _follower()
    out = "\n".join(f.events(_follow_snap(arc=[
        {"seq": 1, "move_type": "call_ideation", "succeeded": True,
         "hypotheses": ["replace the pile-capacity chart"]}])))
    assert "replace the pile-capacity chart" in out


def test_verified_counts_ride_a_finished_move():
    f = _follower()
    out = "\n".join(f.events(_follow_snap(arc=[
        {"seq": 1, "move_type": "single", "succeeded": True,
         "results_verified": 8, "results_total": 9}])))
    assert "8/9 verified" in out


def test_a_blocker_is_announced_once_with_the_human_action():
    f = _follower()
    snap = _follow_snap(arc=[{"seq": 1, "move_type": "single", "succeeded": True,
                       "blocked_on": [{"need": "the licensed dataset",
                                       "human_action": "download it to data/"}]}])
    out = "\n".join(f.events(snap))
    assert "BLOCKED" in out and "download it to data/" in out
    assert f.events(snap) == []


def test_an_incomplete_decision_waits_until_it_is_whole():
    """Decision files can be caught mid-write; printing a torn one and then
    reprinting it whole would be exactly the duplication complained about."""
    f = _follower()
    torn = _follow_snap(decisions=[{"seq": 1, "action": "stop", "incomplete": True}])
    assert [l for l in f.events(torn) if "decision 1" in l] == []
    whole = _follow_snap(decisions=[{"seq": 1, "action": "stop", "reasoning": "done"}])
    assert [l for l in f.events(whole) if "decision 1" in l]


def test_the_end_is_announced_once():
    """Uses a state health() ACTUALLY EMITS.

    This asserted on state="ended-well" — a string health() has never returned
    (it emits finished / ended-badly / vanished / running / unknown). So it
    "proved" the end-announcement worked using an input the producer cannot
    produce, while the real terminal state, "finished", fell straight through
    follow.py's check: a study that completed normally never printed its
    headline and `python -m liveview` polled forever on the default path. The
    vocabulary now lives in reader.TERMINAL_HEALTH_STATES and both sides use it.
    """
    f = _follower()
    f.events(_follow_snap())
    done = _follow_snap(state="finished")
    assert f.events(done)
    assert f.events(done) == []


@pytest.mark.parametrize("state", sorted(TERMINAL_HEALTH_STATES))
def test_every_terminal_state_ends_the_follower(state):
    """Parametrised over the real set, so a state added to health() without
    teaching follow.py about it fails here instead of in production."""
    f = _follower()
    f.events(_follow_snap())
    assert f.events(_follow_snap(state=state)), state


def test_a_running_state_does_not_end_the_follower():
    f = _follower()
    f.events(_follow_snap())
    assert f.events(_follow_snap(state="running")) == []


def test_no_terminal_state_is_missing_from_healths_vocabulary():
    """TERMINAL_HEALTH_STATES must be a subset of what health() can emit —
    otherwise it names a state nobody produces, which is how this broke."""
    assert TERMINAL_HEALTH_STATES <= set(HEALTH_STATES)


def test_a_sub_studys_first_events_are_not_swallowed():
    """active_node() switches to the deepest RUNNING child, and every study
    numbers its decisions and moves from 1 — so a bare-seq dedup set marked a
    child's seq-1 events "already seen" and dropped them. Recursion is live, so
    this silently threw away the start of every sub-study."""
    f = _follower()
    parent = _follow_snap(study_id="root", state="running")
    parent["active"]["decisions"] = [
        {"seq": 1, "action": "run", "reasoning": "PARENT turn"}]
    child = _follow_snap(study_id="root-sub1", state="running")
    child["active"]["decisions"] = [
        {"seq": 1, "action": "run", "reasoning": "CHILD turn"}]

    assert "PARENT turn" in "\n".join(f.events(parent))
    printed = "\n".join(f.events(child))
    assert "CHILD turn" in printed
    assert "root-sub1" in printed          # and the switch is announced


def test_a_null_goal_does_not_match_every_director():
    """With goal None the needle was "" and the filter fell through, so ANY
    pi_agent process counted as this study's — health() then called a long-dead
    study RUNNING for as long as any other director was up. goal is None exactly
    when study.json is missing or caught half-written, i.e. when a watcher most
    needs the truth."""
    assert director_processes(None) == []
    assert director_processes("") == []


def test_every_option_main_reads_actually_exists():
    """REGRESSION. --dashboard was added to the dispatch logic by an unchecked
    string replace that never matched, so main() read args.dashboard on a
    namespace that had no such attribute and `python -m liveview` died with an
    AttributeError on its default path. The --once smoke test passed because
    --once bypasses that exact branch.

    Parse the real parser with no arguments and assert every option the entry
    point reads is present."""
    import re

    from liveview.__main__ import _build_parser, main  # noqa: F401
    import inspect

    ns = _build_parser().parse_args([])
    src = inspect.getsource(main)
    for attr in sorted(set(re.findall(r"\bargs\.([a-z_]+)", src))):
        assert hasattr(ns, attr), f"main() reads args.{attr}, which the parser never defines"


def test_the_default_view_is_the_event_log_not_the_dashboard():
    ns = _build_parser_ns()
    assert ns.dashboard is False


def _build_parser_ns():
    from liveview.__main__ import _build_parser
    return _build_parser().parse_args([])


# --------------------------------------------------------------------------- #
# Fan members get their own question back (2026-07-30).
#
# One run_fan decision spends N moves and appends N arc rows, but writes a SINGLE
# decisions/decideN.json. The arc row has no `domain`, its move_type is the bare
# string "single", and its `finding` is the parent's reasoning copied onto every
# member — so six consecutive rows read identically and a watcher could not tell
# which candidate any of them investigated. Found live in experiment 2.
# --------------------------------------------------------------------------- #

def _fan_arc(n=3, start=2):
    return [{"seq": start + i} for i in range(n)]


def test_each_fan_member_is_labelled_with_its_own_question():
    from liveview.reader import _annotate_fan_members

    arc = _fan_arc(3)
    _annotate_fan_members(arc, [{"seq": 2, "action": "run_fan",
                                 "fan_domains": ["question A", "question B",
                                                 "question C"]}])
    assert [a["domain"] for a in arc] == ["question A", "question B", "question C"]
    assert [a["fan_index"] for a in arc] == [1, 2, 3]
    assert all(a["fan_width"] == 3 for a in arc)


def test_the_parents_repeated_reasoning_is_flagged_after_the_first_member():
    """The finding is identical on every member, so it is worth reading once."""
    from liveview.reader import _annotate_fan_members

    arc = _fan_arc(3)
    _annotate_fan_members(arc, [{"seq": 2, "action": "run_fan",
                                 "fan_domains": ["a", "b", "c"]}])
    assert [a["finding_repeats_fan"] for a in arc] == [False, True, True]


def test_a_fan_still_in_flight_annotates_only_the_rows_that_exist():
    """Members land as they finish; a missing row must not raise or shift labels."""
    from liveview.reader import _annotate_fan_members

    arc = _fan_arc(2)  # 2 of 4 landed so far
    _annotate_fan_members(arc, [{"seq": 2, "action": "run_fan",
                                 "fan_domains": ["a", "b", "c", "d"]}])
    assert [a["domain"] for a in arc] == ["a", "b"]
    assert [a["fan_width"] for a in arc] == [4, 4]


def test_a_real_domain_on_the_row_is_never_overwritten():
    from liveview.reader import _annotate_fan_members

    arc = [{"seq": 2, "domain": "what the row itself recorded"}]
    _annotate_fan_members(arc, [{"seq": 2, "action": "run_fan",
                                 "fan_domains": ["from the decision"]}])
    assert arc[0]["domain"] == "what the row itself recorded"


def test_a_non_fan_decision_annotates_nothing():
    from liveview.reader import _annotate_fan_members

    arc = _fan_arc(2)
    _annotate_fan_members(arc, [{"seq": 2, "action": "run_experiment",
                                 "domain": "one question", "fan_domains": None}])
    assert all("domain" not in a and "fan_width" not in a for a in arc)


@pytest.mark.parametrize("decisions", [
    None,
    [],
    [None],
    ["not a dict"],
    [{"seq": 2, "action": "run_fan", "fan_domains": None}],
    [{"seq": 2, "action": "run_fan", "fan_domains": []}],
    [{"seq": 2, "action": "run_fan", "fan_domains": "not a list"}],
    [{"seq": None, "action": "run_fan", "fan_domains": ["a"]}],
    [{"seq": "2", "action": "run_fan", "fan_domains": ["a"]}],
    [{"action": "run_fan", "fan_domains": ["a"]}],
    [{"seq": 2, "action": "run_fan", "fan_domains": [None, 7, ""]}],
])
def test_malformed_decisions_never_raise(decisions):
    """Being readable while things are broken is this module's whole job."""
    from liveview.reader import _annotate_fan_members

    arc = _fan_arc(3)
    _annotate_fan_members(arc, decisions)  # must not raise


# --------------------------------------------------------------------------- #
# A move has THREE states, not two (2026-07-30).
#
# dispatch.py sets succeeded = bool(publishable), and publishable requires the
# question ANSWERED *and* every finding reproduced. So experiment 2's move 3 —
# 21/21 claims verified, and the target the whole study was then built on —
# rendered as ✗ FAILED. The view must not teach a watcher to distrust honest
# reporting.
# --------------------------------------------------------------------------- #

def test_a_publishable_move_stood():
    assert reader._move_state({"succeeded": True}) == "stood"


def test_a_move_that_verified_everything_is_not_a_failure():
    """The move-3 case, exactly: perfect reproduction, publishable false."""
    state = reader._move_state({
        "succeeded": False,
        "outcome": "completed free investigation (nothing publishable)",
        "results_total": 21, "results_verified": 21,
    })
    assert state == "ran", "a move with 21/21 verified must never read as failed"


@pytest.mark.parametrize("outcome", [
    "dispatch_error: RuntimeError: boom",
    "crashed during free investigation (ValueError: x)",
    "halted_synthesis",
    "setup_error",
    "skipped_defer",
])
def test_a_move_that_never_measured_did_not_run(outcome):
    assert reader._move_state({"succeeded": False, "outcome": outcome,
                               "results_total": 0}) == "did_not_run"


def test_every_state_has_a_word_and_they_are_distinct():
    words = [reader.STATE_WORD[s] for s in reader.MOVE_STATES]
    assert len(set(words)) == len(words)
    assert "failed" not in " ".join(words).lower(), (
        "'failed' is the word this whole change exists to stop using for a move "
        "that ran and measured")


def test_the_failures_panel_does_not_claim_nothing_stood_when_things_stood():
    entry = {"succeeded": False,
             "outcome": "completed free investigation (nothing publishable)",
             "results_total": 21, "results_verified": 21}
    means = reader._barren_means(entry)
    assert "ALL 21" in means
    assert "nothing it produced stood" not in means


def test_a_genuinely_barren_move_still_says_so():
    means = reader._barren_means({"results_total": 0, "results_verified": 0})
    assert "nothing it produced stood" in means


def test_a_partial_move_reports_the_split():
    means = reader._barren_means({"results_total": 28, "results_verified": 4})
    assert "4 of 28" in means


# --------------------------------------------------------------------------- #
# Long fields wrap; they do not get truncated to one clipped line.
# --------------------------------------------------------------------------- #

def _plain():
    return render._Painter(color=False)


def test_a_long_field_wraps_instead_of_clipping():
    text = " ".join(["incumbent"] * 60)
    lines = render._field(_plain(), 80, "  ", "asked", text)
    assert len(lines) > 1, "a 60-word field must wrap, not vanish behind an ellipsis"
    assert "incumbent" in lines[-1], "the tail of the text must survive"
    assert all(len(l) <= 80 for l in lines)


def test_the_label_appears_once_and_the_text_column_aligns():
    lines = render._field(_plain(), 80, "  ", "asked", " ".join(["w"] * 90))
    assert lines[0].count("asked") == 1
    assert "asked" not in "".join(lines[1:])
    # every continuation starts in the same column as the first line's text
    col = lines[0].index("w")
    assert all(l.index("w") == col for l in lines[1:])


def test_limit_bounds_a_runaway_field_and_marks_the_cut():
    lines = render._field(_plain(), 80, "  ", "why", " ".join(["x"] * 400), limit=3)
    assert len(lines) == 3
    assert lines[-1].endswith("…")


def test_an_empty_field_renders_nothing():
    for empty in (None, "", 0):
        assert render._field(_plain(), 80, "  ", "asked", empty) == []


def test_the_arc_never_prints_a_failure_mark_beside_verified_claims():
    node = {"arc": [{"seq": 3, "move_type": "single", "state": "ran",
                     "succeeded": False, "results_total": 21,
                     "results_verified": 21,
                     "outcome": "completed free investigation (nothing publishable)"}]}
    text = "\n".join(render._arc_lines(node, _plain(), 100))
    assert "21/21 verified" in text
    assert "✗" not in text
    assert "ran, not publishable" in text
