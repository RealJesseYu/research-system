# research-system

Phase B, Step 11: the deterministic six-stage skeleton is built and the
real stages are arriving one by one — stage 1 is real literature-grounded
ideation, gate 1 is pick-one-of-k, stage 2 is real experiment design
producing a typed, Python-validated spec, and stage 3 is a real Opus
fidelity gate on the frozen spike v2 prompt. The spike's solver wrapper
has graduated into `tools/run_cfd.py` (deterministic, with optional QoI
extraction); it is not wired into any stage yet. See `CLAUDE.md` for the
full architecture and current status.

## Requirements
This project has its own venv at `venv/`, containing `claude-agent-sdk`.
Auth is via the same Claude subscription login the CLI already uses — no
API key needed.

Tests also require the venv's interpreter — run them as
`venv/bin/python3 tests/<test_file>.py` (the system python lacks the SDK).

## Run it

From this directory (`~/research-system`):

```
venv/bin/python3 supervisor.py --mode auto --domain "your research domain here"
```

or

```
venv/bin/python3 supervisor.py --mode human --domain "your research domain here"
```

(`--mode` defaults to `human` if you omit it. `--domain` is required — it
seeds the run's initial baton payload as `{"domain": "..."}`.)

To re-run stage 2 alone from a past run's stage-1 evidence (no supervisor,
no stage-1 spend):

```
venv/bin/python3 handfeed_stage2.py --source-run <run_id> --hyp <hypothesis_id>
```

To re-run stage 3 alone from a past run's stage-2 evidence (no supervisor,
no stage-1/2 spend):

```
venv/bin/python3 handfeed_stage3.py --source-run <run-directory-name>
```

## What you should see

**Auto mode:** the run prints one line per stage ("STAGE N (name): done ->
saved ...") and one pair of lines per gate ("GATE ...: reached" / "GATE
...: auto-approved"), then finishes with a line reporting the baton's
final history-entry count (should be 6 — one per stage).

**Human mode:** the run pauses three times — after stage 1, after stage 2,
and after stage 5 — pretty-prints the current baton, and asks:

```
GATE after_stage_N: approve to continue [y] / stop [n]:
```

Type `y` and press Enter to continue. Typing anything else stops the run
cleanly (no error, no partial mess) at that gate.

## Where the output goes

Each run creates `runs/<run_id>/`, named by a UTC timestamp — run-ids are
UTC, so directories can appear future-dated relative to local time —
containing:

- `baton_after_stage_1.json` through `baton_after_stage_6.json` — a
  snapshot of the baton after each stage ran. Useful for seeing exactly
  what any given stage received and produced.
- `log.txt` — everything printed to the terminal during the run, plus the
  gate decisions (auto-approvals or human y/n answers). This is the
  supervisor's own record; it is never read by any stage.

## Memory & retrieval

Long-term memory lives on disk, outside any AI's context — never in a
stage's conversation.

- **Journal** (`memory/journal.jsonl`): an append-only log, one JSON object
  per line, of every run's outcome. The supervisor appends one entry per
  run automatically (on completion or on halting at a gate). To search it
  by hand:
  ```
  venv/bin/python3 -c "from memory.journal import journal_search; [print(e) for e in journal_search(limit=5)]"
  ```
- **solver_docs index** (`retrieval/solver_docs_index.pkl`): TF-IDF search
  over OpenFOAM tutorial field files and User Guide excerpts. Rebuild with
  `venv/bin/python3 retrieval/build_solver_docs_index.py`; search by hand:
  ```
  venv/bin/python3 retrieval/search.py solver_docs "moving wall velocity boundary condition"
  ```
- **literature index** (`retrieval/literature_index.pkl`): same TF-IDF
  machinery over `retrieval/literature_corpus/` (currently one placeholder
  file; real papers arrive later). Rebuild with
  `venv/bin/python3 retrieval/build_literature_index.py`; search by hand:
  ```
  venv/bin/python3 retrieval/search.py literature "placeholder literature corpus"
  ```

The literature index is wired into stage 1 (Step 8: hypotheses are
grounded in retrieved snippets); solver_docs is not wired into any stage
yet. `supervisor.py` never touches `retrieval/`.

## What is NOT built yet

No MCP tools. Gates 2 and 5 still take only y/n (gate 1 is
pick-one-of-k). Stages 1–3 are real — ideation on Sonnet with Opus
ranking, experiment design on Sonnet, the fidelity gate on Opus — while
stages 4–6 are still separate-context Haiku ack stubs. The graduated
`tools/run_cfd.py` wrapper (plus its `tools/drive_cfd.py` CLI) runs only
by hand — wiring it into stage 4 is Step 12. See `CLAUDE.md`.
