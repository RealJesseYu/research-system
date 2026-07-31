# research-system

Phase B COMPLETE (Step 16): the deterministic six-stage skeleton is built and the
real stages are arriving one by one — stage 1 is real literature-grounded
ideation, gate 1 is pick-one-of-k, stage 2 is real experiment design
producing a typed, Python-validated spec (with machine-readable QoI keys
when, and only when, the QoI is genuinely extractable by the substrate),
stage 3 is a real Opus fidelity gate on the frozen spike v2 prompt,
stage 4 is the real simulation runner (deterministic Python, zero model
calls: verdict-gated case synthesis + execution through `tools/run_cfd.py`
with optional QoI extraction), and stage 5 is the real thought layer (one
Opus call that triages surprise and decides iteration; scored against six
sealed cases before going live — see `stage5_cases/`). See `CLAUDE.md`
for the full architecture and current status.

Step 14 added model-input transcripts and a formal trace audit of one full
run (`trace_audit_step14.md`), plus the journal read-side into ideation.
Its two-arm memory-steering experiment showed that the domain string, not
the retrieved-memory frame, steers ideation flavor: the same memory
produced all-scalar hypotheses on a mixing domain and all-velocity/vortex
hypotheses on an instrument-matched domain (both runs still drew defer).

Step 15 locked the baton schemas: `schemas.py` holds one pure validator
per baton boundary (shapes derived from disk evidence, not invented —
`schema_audit_step15.md` is the audit, `docket_step15_draft.md` the ruled
candidate docket), and the supervisor enforces them at every boundary — a
malformed payload is a loud halt (durable `SCHEMA VIOLATION` line plus a
halted-schema journal record), never a re-ask. The spec schema gained two
optional fields: a parameter may declare role `"derived"` with a
`derived_from` string stating its rule, and `success_criterion` may carry
a two-sided expectation `expected_value` + `tolerance` (both-or-neither,
tolerance > 0; no stage-4/5 consumer yet — it accumulates data for
Step 16/21). Fixed parameter values must now be numeric. Pre-lock specs in
old `runs/` dirs may fail the new rules; they are historical evidence and
are deliberately not edited.

Step 16 closed the loop: gate 5 is now a real decision (accept the thought
layer's iterate decision, override it, or stop), and the supervisor enacts
loop-backs — `back_to_design` re-enters stage 2 carrying the thought as
`prior_thought` (ruled optional field at every boundary); `back_to_ideation`
re-enters stage 1 with the payload reduced to `{domain}` (loop context
arrives via the journal read-side, not the baton). At most 2 loop-backs
per run (`MAX_LOOPBACKS`); a third non-exit decision forces an honest stop
with the recommendation journaled. Enacting `more_data` also stops honestly
— its machinery is Phase C (Step 19) and is not pretended. Chunk 1 added
robustness: transport retries with durable `TRANSPORT-RETRY` lines, a
stage-crash catch that journals a `crashed` run_record, and stage 4 now
consumes spec-declared derived parameters (verified, never guessed).

## Requirements
This project has its own venv at `venv/`, containing `claude-agent-sdk`.
Auth is via the same Claude subscription login the CLI already uses — no
API key needed.

Tests also require the venv's interpreter — run them as
`venv/bin/python3 tests/<test_file>.py` (the system python lacks the SDK).

## Connectors (MCP)

Optional. Copy `mcp_servers.example.json` to `mcp_servers.json` (gitignored)
and point it at any MCP server — stdio or http/sse. The free experimenter can
then call that server's tools directly as `mcp__<server>__<tool>`. With no
such file, every path is byte-identical to running without connectors.

A bundled reference connector, `connectors/pubchem_mcp_server.py`, serves
PubChem compound lookups (name/CID/SMILES → structure, or one curated
property) and needs no API key.

**To let a connector's answer become a KEPT number**, add `"_verifiable": true`
to that server's block. That is your assertion, as the operator, that the server
is a deterministic data source with no model inside it — because a kept number is
re-run at verification time through `tools/run_mcp_tool.py`, and no model may
enter that path. Without the declaration the connector still works for
exploration; its results are reported as honest unverified caveats.
Full setup and the reasoning: `docs/memo_connector_bridge.md`.

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

To re-run stage 4 alone from a past run's stage-2/3 evidence (no model
calls at all; `--force-label trust|refine|defer` overrides the verdict
label and is recorded in the handfeed's source.json; `--payload <file>`
feeds a hand-authored payload instead of a past run):

```
venv/bin/python3 handfeed_stage4.py --source-run <run-directory-name>
```

To run the thought layer alone on a sealed scored case (no supervisor, no
journal writes ever — the answer key never reaches the model; scores are
written to the handfeed dir after the model evidence is saved):

```
venv/bin/python3 handfeed_stage5.py --case stage5_cases/case_a.json
```

To hand-drive the production solver wrapper on a case under `cases/` (no
model calls, no supervisor; prints the summary JSON):

```
venv/bin/python3 tools/drive_cfd.py cavity_baseline \
    --qoi-field U --qoi-operation volAverage --qoi-component mag
```

The QoI flags build the optional request `{"field": "<existing field, e.g.
U or p>", "operation": "volAverage|min|max|volIntegrate", "component":
"mag"|0|1|2 (optional)}`; omit them to just run the case.

## What you should see

**Auto mode:** the run prints one line per stage ("STAGE N (name): done ->
saved ...") and one pair of lines per gate ("GATE ...: reached" / "GATE
...: auto-approved"), then finishes with a line reporting the baton's
final history-entry count (should be 6 — one per stage).

Stage 4 additionally prints its own `STAGE4` lines, one per thing it did,
depending on the fidelity verdict:

- defer: `STAGE4 skipped_defer: no case built, no solver run`
- trust/refine, per mini-run:
  `STAGE4 run N/M case=<run_id>_runN status=... converged=... qoi=...`
- if the spec's QoI carries no machine-readable keys:
  `STAGE4 qoi_request=none (QoI ... not extractable by contract: ...)`
- if a case can't be built:
  `STAGE4 halted_synthesis at run N of M: <every offending parameter>`

**Human mode:** the run pauses at least three times — after stage 1, after
stage 2, and after stage 5 (and again at each gate on every loop-back
pass). Gate 1 lists the ranked hypotheses and asks you to pick one by
number. Gates 2 and 5 print a display-only header first — gate 2 a
one-line SPEC summary, gate 5 a boxed FIDELITY VERDICT block followed by
an EXECUTION section showing what stage 4 did (status, plus per-run
one-liners or the skip/halt reason, plus a `flag:` line when the refine
flag is present) and a boxed THOUGHT block (triage / decision /
justification) when stage 5's thought exists — then pretty-print the
current baton. Gate 2 asks:

```
GATE after_stage_2: approve to continue [y] / stop [n]:
```

Gate 5 (Step 16) shows `MODEL DECISION: <decision>` and asks a real
decision:

```
GATE after_stage_5: accept model decision '<decision>' [a] / override
[b=back_to_design, i=back_to_ideation, m=more_data, e=exit] / stop [n]:
```

Both the model's decision and the enacted one are logged
(`model=X enacted=Y (accepted|overridden)`). Three invalid answers in a
row halt the run (same bound as gate 1). Loop-backs re-run stages with
gates live on every pass; re-entered stages write pass-suffixed snapshots
(`baton_after_stage_N_pass2.json`, …) so every pass's evidence survives.

## Watching a run while it happens

A study runs unattended for hours and the terminal is a wall of lines from
the director and every child subprocess at once. `liveview` is a separate
READ-ONLY reader of the files a run already writes — start it, stop it, or
restart it at any time; it cannot affect the run.

`python -m pi_agent` **starts the browser view for you** (as a child process, only
when stdout is a TTY) and closes it when the study ends — `--no-watch` or
`RESEARCH_LIVE_VIEW=0` if you would rather it did not. Launch it by hand for a
finished study, one you did not start, or a scripted read:

```
venv/bin/python -m liveview            # terminal view of the newest live study
venv/bin/python -m liveview --web      # the same picture in a browser (localhost)
venv/bin/python -m liveview --once     # one snapshot, scriptable (exit 1 if it died)
venv/bin/python -m liveview --list     # what studies are on disk
```

It shows the current phase (which move is running, or that the director is
thinking, descending into whichever sub-investigation is actually moving),
the arc so far with sub-studies nested, the director's latest reading and
reasoning in its own words, verified-vs-total claims, spend, and a failure
ledger that separates **recorded** failures (written to the arc, read by the
director on its next turn, study continues — a child's traceback is one of
these) from the one **fatal** case: a director-level termination that
actually ended the investigation. See `docs/liveview.md`.

## Where the output goes

Each run creates `runs/<run_id>/`, named by a UTC timestamp — run-ids are
UTC, so directories can appear future-dated relative to local time —
containing:

- `baton_after_stage_1.json` through `baton_after_stage_6.json` — a
  snapshot of the baton after each stage ran. Useful for seeing exactly
  what any given stage received and produced. Loop-back passes add
  pass-suffixed snapshots (`baton_after_stage_N_pass2.json`,
  `baton_after_gate_1_pass2.json`, …) — pass 1 keeps the unsuffixed names.
- `stage1/` … `stage5/` — each real stage's own evidence (ranked lists,
  spec.json, verdict.json, stage 4's `results.json` with the full wrapper
  summaries, and stage 5's `thought.json`; the baton carries conclusions
  only). `stage1/retrieved_memory.json` records verbatim the journal
  entries stage 1 retrieved at launch (the last-3 window slides as runs
  append, so this file is the proof of what THIS run saw).
- `transcripts/` — one JSON file per model call
  (`<seq>_<stage_name>.json`) holding the fully assembled model input
  (stage_name, model, timestamp, system prompt, serialized stage input),
  written BEFORE the call fires. Write-only evidence: no code ever reads a
  transcript back into a model input or stage logic.
- `log.txt` — everything printed to the terminal during the run, plus the
  gate decisions (auto-approvals or human y/n answers) and one
  `SCHEMA OK after <boundary>` line per passed boundary validation
  (five per completed run: gate 1, stages 2–5). This is the
  supervisor's own record; it is never read by any stage.

Executed mini-runs also synthesize solver cases under
`cases/<run_id>_run<N>/` (evidence-class, gitignored, like `runs/`).

## Memory & retrieval

Long-term memory lives on disk, outside any AI's context — never in a
stage's conversation.

- **Journal** (`memory/journal.jsonl`): an append-only log, one JSON object
  per line, of every run's outcome. The supervisor appends one entry per
  run automatically (on completion or on halting at a gate), and stage 5
  appends a `learned_summary` on non-exit decisions. Stage 1 also READS
  the journal (Step 14): it retrieves the last 3 `learned_summary`
  entries, saves them verbatim to `runs/<id>/stage1/retrieved_memory.json`,
  and injects them into its generation and reflection inputs only, under
  an explicit leads-not-facts frame. To search it
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

MCP connectors ARE wired (see "Connectors" above) — what is not built is
MCP as the transport for the *internal* substrate wrappers, which are
still direct Python calls. Gate 2 still takes only y/n (gate 1 is pick-one-of-k;
gate 5 is the Step-16 accept/override/stop decision). Stages 1–5 are
real — ideation on Sonnet with Opus ranking, experiment design on Sonnet
(the spec validator also enforces that machine-readable qoi keys, when
any appear, carry both `field` and `operation` with the wrapper's exact
vocabulary), the fidelity gate on Opus, the simulation stage on
deterministic Python (no model call), and the thought layer on Opus —
while stage 6 is still a separate-context Haiku ack stub. `more_data`
machinery (Phase C, Step 19) is not built — enacting it stops the run
honestly with a recommendation. See `CLAUDE.md`.
