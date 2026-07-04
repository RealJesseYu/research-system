# research-system — Autonomous Research System

## What this is
This is the real build of an autonomous research system: a relay of six AI stages
(Ideation → Experiment-Design → Fidelity-Gate → Simulation → Thought-Layer → Paper)
coordinated by a plain-Python supervisor. We are in **Phase B, Step 10**. The
deterministic skeleton is built and the real stages are arriving one by one: stage 1 is
real literature-grounded ideation (generate → reflect → deterministic filter → Opus
ranking), gate 1 is pick-one-of-k, and stage 2 is real experiment design (one Sonnet
call producing a typed spec enforced by Python validation). Stages 3–6 are still
separate-context Haiku ack stubs. An earlier
risky-bit spike at `~/research-spike` answered two yes/no questions: (a) can an AI agent
drive and self-recover an OpenFOAM simulation, and (b) does a simple pre-run fidelity
check work — the project's first original contribution. This project is the production
system that spike's pieces graduate into.

## Architecture invariants
These rules must never be violated by any future change, no matter how small or how
convenient it seems in the moment:

- **Six stages, six fresh contexts.** Each stage is eventually its own AI call in its own
  fresh context. No stage ever sees another stage's conversation transcript.
- **The supervisor is deterministic Python with no AI inside it.** It schedules stages,
  saves batons, enforces gates, and prints/logs. It never calls a model.
- **Stages exchange only small typed batons — never transcripts.** A baton is a small
  structured object (see `baton.py`). Raw tool output (e.g. a full solver log) must be
  summarized at the tool wrapper *before* any agent sees it — never handed to a stage
  wholesale.
- **Memory lives in an external store, never in context.** Long-term memory is on disk,
  outside any AI's conversation. Built in Step 7 chunk 3 as plain files (an append-only
  JSONL journal) plus the spike's proven TF-IDF search — a deliberate deviation from the
  build book's "vector DB" option, per tested-first: no vector database, no embeddings,
  no new services until a real run shows the simple version failing.
- **Three human gates, two modes.** Gates occur after stage 1, after stage 2, and at
  stage 5's iterate decision. A mode switch (`human` / `auto`) changes gate *behavior*
  only — `human` mode stops and asks; `auto` mode logs the gate and proceeds. The mode
  never changes what the stages themselves do.
- **Model roles.** Sonnet = workhorse (does the bulk of each stage's work). Opus = hard
  judgments only (ranking in ideation, the fidelity call, the iterate decision). Haiku =
  triage and stubs (cheap, fast, low-stakes passes).
- **Substrate-agnostic upper layers.** Nothing above a tool wrapper may ever mention
  OpenFOAM or any specific solver by name. Upper layers only see abstract properties:
  validated envelope, cost, confidence. This keeps the system able to swap solvers later
  without touching stage logic. Clarified 2026-07-03: payload DATA may name substrate
  specifics (model-authored spec content travels up the baton); stage code and the
  supervisor must never branch on substrate names found in payloads.
- **Spike isolation is a runtime property.** The invariant is zero RUNTIME references
  to `~/research-spike` — no imports, no paths, no file reads. Truthful prose
  provenance in comments/docstrings is permitted. Preflight greps are a proxy for this
  check: matches are triaged code-vs-prose, and only code matches violate the
  invariant. (Clarified 2026-07-03.)
- **All tools reached over MCP eventually.** (MCP = Model Context Protocol, the standard
  way an AI model calls out to external tools.) Not built yet in this chunk.

## Working discipline
- **Tested-first.** Build the smallest piece, verify it actually works, then move on.
- **Expand only on evidence.** Don't add capability because it might be needed later —
  add it when something we've actually run shows it's needed.
- **No gold-plating.** Build exactly what the current step specifies. Nothing extra.
- **Plain-language explanations continue during builds.** Comprehension is preserved as
  a load-bearing-ideas section in each step's closing journal entry; no say-back gates.
- **Builder-tooling note.** Claude Code runs on Fable 5 as of 2026-07-03;
  system-under-test model strings unchanged.
- **The checksum snapshot is the FINAL write of any step close.** Nothing edits after
  it.
- **Anything we can't afford to have broken goes in code, not in a prompt.** Schemas and
  checks (like `baton.validate()`) are enforced by Python, not by hoping an AI remembers
  a rule from a prompt.
- **Keep honest records, including what didn't go to plan.** Status notes below should
  reflect reality, not aspiration.
- **`runs/` is append-only evidence:** demo and failure runs are kept deliberately;
  pruning happens only at a recorded checkpoint, never silently mid-step. A retention
  policy gets designed only when accumulation actually hurts.

## Pointers to the spike
- `~/research-spike` is **read-only reference**. Never modify it from this project.
- Its `run_cfd` wrapper (deterministic, stdlib-only, returns a bounded summary — never
  the full solver log) graduates into **Step 11**.
- Its TF-IDF documentation index (`search_docs`) has been copied into `retrieval/`
  (Step 7 chunk 3) as `solver_docs`; the index was rebuilt from copied corpus files
  rather than copying `index.pkl` itself, to keep this project fully self-contained.
- Its Step-6 fidelity-gate findings shape **Steps 10, 13, and 21**: the trust/refine
  boundary is at least 3-axis (envelope position; resolve-vs-approximate instrument
  class; regime-assumption certainty). The third axis — whether the assumption that
  places a case "in-envelope" is itself certain — is **NOT handled** by the current
  fidelity check and must not be pretended to be handled until it actually is.

## Current status
Phase B, Step 7 — chunk 1 of 3 COMPLETE (2026-07-01). Deterministic skeleton verified
end-to-end on disk: auto and human demo runs under runs/, final batons carry exactly six
history entries, gate decisions live only in log.txt.

Phase B, Step 7 — chunk 2 of 3 COMPLETE (2026-07-01): all six stages are real
separate-context Haiku calls via model_call.py, verified in auto and human modes.

Phase B, Step 7 COMPLETE (2026-07-02): deterministic skeleton + six real
separate-context Haiku stages + memory store and three retrieval indices (journal,
solver_docs, literature), plus two rulings deferred from the strategy chat applied
post-verification: model_call.py's fence-stripping tolerance now prints a NOTE when it
fires, and Working discipline records that runs/ is append-only evidence. Step 7 is
closed.

Phase B, Step 8 COMPLETE (2026-07-02): minimal ideation live in stage 1 —
Generation (six hypotheses grounded in retrieved literature, Sonnet), Reflection
(novelty + 1-5 quality judged per hypothesis against its own retrieved snippets,
Sonnet), a deterministic novelty/quality filter (pure Python, discards "known",
keeps ≤4 survivors, ties by generation order), and Ranking (round-robin pairwise
comparisons over survivors, Opus, per CLAUDE.md's model roles — a hard judgment
call). Verified end-to-end: two auto-mode runs plus one human-mode run (id
20260702T054621Z) all confirmed from disk — ranked payload intact through all six
stages, all three gates behave correctly, ranking.json's win-count/tiebreak math
re-derived by hand matches the payload order both auto runs, gate vocabulary never
leaks into baton history. The fence_stripped tolerance is a durable line in each run's log.txt, not
just a terminal print. Fencing observation updated: as of 2026-07-03, Opus
calls no longer fence (0/30 across five runs); Sonnet and Haiku still fence
~100%; two-sided watch continues. Milestone recorded in the journal (run_id "step8"). Step 8 is closed.

Phase B, Step 9 — chunk 1 COMPLETE (2026-07-02): gate after_stage_1 is now
pick-one-of-k — a pure parse_gate1_selection (14 unit tests), human mode
re-prompts and halts after 3 invalid answers, auto mode selects rank 1, and in
both modes the supervisor (deterministic Python, no model) then shrinks the
payload to {domain, chosen_hypothesis} and snapshots baton_after_gate_1.json;
the ranked list stays on disk in stage1/ evidence and baton_after_stage_1.json
only. Gates 2 and 5 unchanged. stages/stage2_spec.py holds the typed stage-2
spec schema (hypothesis_id enum-pinned to the gate-1 winner) and validate_spec,
whose plain-language errors are written to be sent back to a model as guided
corrections (16 unit tests). substrates.py holds CAVITY_2D_CONTRACT, drafted
from the spike read-only, including its honest limits (2D laminar only; no
field-derived QoIs extractable today). Neither new file is imported by anything
yet — the stage-2 stub was deliberately NOT rewritten; baton.py, model_call.py,
stage 1, and stubs 3–6 verified byte-identical by checksum. Verified from disk
on auto run 20260703T024855Z: h3 selected at rank 1 of 4, payload exactly
{domain, chosen_hypothesis} after the gate, stubs 2–6 clean on the new shape,
six history entries, run_record journaled. Fence watch: Sonnet fenced 7/7 and
Haiku 5/5, but Opus fenced 0/6 — the first run where a tier stopped fencing;
keep counting per run. Known validator gaps, deliberate (expand on evidence):
unknown parameter names inside mini_experiment runs are not flagged, and
"one sentence" fields are not length-enforced.
Phase B, Step 9 — chunk 2 COMPLETE (2026-07-02): stage 2 is real — one Sonnet
call turns the gate-1 chosen hypothesis into a typed experiment spec, grounded
in CAVITY_2D_CONTRACT (substrates.py's first consumer) and enforced in Python.
call_stage_model gained an optional extra_validator (deep plain-language errors
re-asked inside the same bounded 3-attempt loop); validate_spec now flags
unknown parameter names in mini_experiment runs (17 unit tests — closes one of
chunk 1's two recorded gaps; "one sentence" length is still unenforced); the
contract carries an indicative-cost sentence. handfeed_stage2.py is a side door
that rebuilds the post-gate-1 baton from a past run's stage1 evidence and calls
stage 2 directly — no supervisor, no stage-1 spend. Verified from disk on two
hand-feeds from source run 20260702T054621Z (handfeed-20260703T032655Z-h3,
handfeed-20260703T033013Z-h4): saved specs pass a fresh validate_spec, correct
hypothesis_id, echo-check logged, payload.experiment_spec identical to
spec.json, exactly one code-authored history entry each, and the two specs
differ substantively and match their physics (obstacle vs sinusoidal floor) —
variance as authorship. Both calls succeeded on attempt 1, so the correction
loop — the chunk's new machinery — has never fired live. Fence watch: Sonnet
2/2. Frozen list (baton.py, supervisor.py, stage 1, stubs 3–6, gate-1 tests)
verified byte-identical by checksum. Honest asterisks: build_spec_schema is not
called by stage 2 (its checks are strictly contained in validate_spec, which
enforces the enum pin via the extra_validator; used only by its unit test); the
cost sentence's numbers (~2 s steady, ~53 s transient to 5 s) could not be
corroborated from the spike's surviving on-disk log (which shows 12.5 s solver
time to t=5 s, 37.7 s to t=20 s; no steady log survives) — written as dictated,
ruling pending; model-authored spec CONTENT names solvers and now travels up
the baton (stage code stays substrate-agnostic) — ruling pending; real stage 2
has not yet run under the supervisor, and stubs 3–6 have never seen the new
{domain, chosen_hypothesis, experiment_spec} payload shape.
Step 9 COMPLETE (stage 2 real; gate 1 pick-one-of-k); Step 10 next, scope
not guessed here.

Phase B, Step 10 — chunk 1 of 2 COMPLETE (2026-07-04): opening tidy + stage 3
real. model_call.py now durably logs every re-ask the moment it fires — a
RE-ASK line (stage, attempt, JSON-encoded verbatim error incl. raw reply,
i.e. exactly what is re-sent to the model) appended to the run's log.txt for
both schema and extra_validator failures; final-failure behavior, isolation,
and the 3-attempt bound unchanged. Proven live from disk on
runs/logging-test-20260704T030312Z (Haiku; stateful validator rejected
attempt 1 with the verbatim marker string; attempts=2 recorded; throwaway
script deleted, evidence kept). The log path is derived from
stage_input["run_id"] because the calling stages were frozen this chunk — a
bare call without run_id prints the line but cannot durably log it.
Truth-edits applied (What-this-is; README header; stage2_spec.py docstring)
plus the new spike-isolation invariant line (zero RUNTIME refs; prose
provenance permitted; greps triaged code-vs-prose). Project-local git
initialized from ~/research-system only (~/.git untouched), .gitignore
exactly venv/ runs/ __pycache__/, opening commit "post-Step-9 tree + tidy" =
1923 files. Stage 3 is real: ONE Opus (claude-opus-4-8) call through
call_stage_model; the spike's PROMPT_V2 judgment text is frozen in the stage
file and verified byte-identical (2015 bytes — zones, v2 trust-vs-refine
paragraph, judge-only-from-given guard) against the read-only spike; the
only swap is the output-format block + case-fill tail → JSON envelope
{ack_run_id, verdict{label enum trust|refine|defer, rationale,
right_instrument}} enforced in Python (extra_validator); no axis-3 language
added, deliberately. Evidence at stage3/verdict.json; payload gains
fidelity_verdict (no existing field removed); exactly one code-authored
history entry; ECHO_CHECK logged. handfeed_stage3.py side door reconstructs
the post-stage-2 payload from a source run's disk evidence (prefers
baton_after_stage_2.json — all five sources used it) and runs stage 3 alone.
Five-spec eyeball run (NOT scored; no answer keys; rationales are the
evidence): h3 + h4 (Step-9 hand-feeds) and h5/h1/h4 (runs 20260703T035155Z /
041005Z / 042647Z) ALL came back defer; five calls, all attempts=1, zero
RE-ASK lines, Opus fence 0/5 (running Opus total now 0/41). Verified from
disk: frozen list byte-identical vs Step-9 checksums; stage2_spec.py drift
proven docstring-only by checksum reversal; 32/32 tests pass; spike grep = 2
prose matches (substrates.py + stage 3 provenance docstrings), 0 code.
Honest asterisks: tasks resequenced (tidy + git init before the model_call
edit) so the opening commit is a true post-Step-9+tidy tree; stage 3 has
only run through the side door, never under the supervisor; the 5/5 defer
unanimity is an observation, not a scored result. NOT a step-closing chunk —
no checksum snapshot written. Chunk 2 scope not guessed here.
