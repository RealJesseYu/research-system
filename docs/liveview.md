# liveview — watching a study that is already running

## Why it exists

An investigation runs unattended for hours. Everything it does is written to disk as
it happens, but the only thing a human sees is the terminal: the director's prints and
every child subprocess's prints, interleaved, unlabelled, and unbounded. From that wall
you cannot tell

- what phase the study is in,
- what the director just decided and why,
- how much of what it found actually reproduced,
- what it has spent, or
- **whether a traceback scrolling past is fatal.**

That last one is not hypothetical. A child subprocess printing its own traceback once
convinced the owner that a perfectly healthy run had died. The system already handles
that case correctly — `_survive()` in `pi_agent/free_director.py` records the failure
to the arc and lets the director decide next turn — but the terminal cannot show the
difference, and a watcher who cannot tell will kill a good run.

## What it is

A separate **reader**. Not instrumentation: nothing in the running system was changed,
and nothing in the running system imports this. It opens the files the run already
writes and assembles them into one picture.

| file the run writes | what the view takes from it |
| --- | --- |
| `studies/<id>/study.json` | the goal, mode, parent link |
| `studies/<id>/arc.jsonl` | one line per completed move: type, outcome, verified findings, artifacts, cost |
| `studies/<id>/decisions/decide<N>.json` | the director's whole turn — what it read, why, what it chose, and the brief it sent |
| `studies/<id>/report.json` | budget, spend, termination (only exists once the study ends) |
| `runs/<run-id>/log.txt` | the live per-run log, tailed |
| `runs/<run-id>/verification.json` | per-claim verdicts with reasons |
| `runs/<run-id>/workspace/` | how much the experimenter has actually built |

## How it knows the live phase

No heartbeat file, no cooperation from the running system. A decision file is written
**before** its action runs, and an arc line is appended **after** it finishes, so the
two counts give the phase away:

```
decisions > arc   ->  the decided action is IN FLIGHT (the decision names it)
decisions == arc  ->  the director is THINKING about its next move
report.json       ->  it is over, and the termination says how
```

For an in-flight experiment the run id is derivable (`<study>-m<arc+1>`), so the view
opens that run dir and shows its log tail, workspace size and last write. For an
in-flight `spawn_sub_investigation` the child study id is derivable too
(`<study>-sub<decision seq>`), so the view follows it down and reports the phase of
whichever node is actually moving — a parent waiting on a child is not itself working.

## Recorded vs fatal

This is the distinction the view exists to make, and it is deliberately conservative:
**only a director-level termination is fatal.**

- **fatal** — `report.termination.reason` is `director_failed`. The arc stopped early
  and budget may be unspent.
- **recorded** — a move raised and was recorded; a sub-investigation returned nothing;
  claims failed the verification wall (including a re-run that exited with a
  traceback). The director reads these on its next turn and continues. They are data.
- **watch** — nothing failed, but something deserves a human's eye: a move that
  measured honestly and found nothing publishable (a negative result, not a
  malfunction), or a long silence on disk.

Liveness itself is asked of the operating system, not guessed: the view matches a
running `python -m pi_agent` process by the goal in its command line. If there is no
process, no `report.json`, and nothing has changed on disk, it says the run appears to
have stopped — and says which of those three facts it is standing on.

## Using it

Usually you don't have to. **`python -m pi_agent` brings the web view up by itself**
and takes it down when the study ends — `pi_agent/watch.py` spawns
`python -m liveview --web` as a CHILD PROCESS (never an import: the run path must
stay unable to reach this package, which is why the view can be rewritten while a
study is running). It starts only when stdout is a TTY, so cron, CI, piped launches
and the test suite behave exactly as they did before; `--no-watch` or
`RESEARCH_LIVE_VIEW=0` turns it off, `RESEARCH_LIVE_VIEW=1` forces it on without a
TTY. If 8765 is taken it moves up to 8776 and prints the port it took. Failing to
start is never fatal — one line, and the study runs on.

Everything below is still there for a study you did not launch yourself, a finished
one, or a scripted read:

```
venv/bin/python -m liveview                     # newest study still running
venv/bin/python -m liveview --study study-XXXX  # a specific one, finished or not
venv/bin/python -m liveview --web [--port 8765] # browser view, 127.0.0.1 only
venv/bin/python -m liveview --once [--no-color] # one snapshot; exit 1 if it ended badly
venv/bin/python -m liveview --json              # one snapshot as JSON
venv/bin/python -m liveview --list              # studies on disk
```

The web view polls `/api/snapshot` every four seconds and additionally lets you expand
any move to see its individual claims (value, verdict, reason), read the full brief the
director sent, and switch studies. Routes are read-only, ids from the URL are validated
against the id pattern before they touch a path, and the server binds loopback only.

## Guarantees

- **Read-only.** No function writes into `studies/` or `runs/`. A test fingerprints a
  study tree (paths, sizes, mtimes to the nanosecond) before and after a full snapshot
  and requires it to be identical.
- **Safe on live files.** Every read tolerates a file caught mid-write: a torn last
  line in `arc.jsonl` is skipped and flagged, a half-flushed JSON file reads as absent.
- **Bounded cost.** Directory walks are depth- and count-limited, and log tails are read
  from the end of the file, so watching a run cannot slow it down. A snapshot of a
  three-study tree takes ~0.03 s.
- **Cannot loop.** Child links are followed through a visited set and a depth cap, so a
  cycle in the study tree is read once.

## Layout

```
liveview/reader.py    disk -> one JSON-able snapshot (pure; the only file that reads)
liveview/render.py    snapshot -> terminal lines (pure)
liveview/tui.py       the redraw loop
liveview/web.py       stdlib http.server + the single-page view
liveview/__main__.py  the CLI
tests/test_liveview.py
```
