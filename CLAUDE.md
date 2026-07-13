# research-system — Autonomous Research System

## What this is
This is the real build of an autonomous research system: a relay of six AI stages
(Ideation → Experiment-Design → Fidelity-Gate → Simulation → Thought-Layer → Paper)
coordinated by a plain-Python supervisor. We are in **Phase B, Step 12**. The
deterministic skeleton is built and the real stages are arriving one by one: stage 1 is
real literature-grounded ideation (generate → reflect → deterministic filter → Opus
ranking), gate 1 is pick-one-of-k, stage 2 is real experiment design (one Sonnet
call producing a typed spec enforced by Python validation), stage 3 is a real
fidelity gate (one Opus call on the spike's frozen Step-6 v2 prompt, verdict
enforced by Python), and stage 4 is the real simulation runner (deterministic
Python, ZERO model calls: verdict-gated — defer skips, trust/refine executes —
with deterministic case synthesis feeding `tools/run_cfd.py`, the graduated
solver wrapper with optional QoI extraction). Stages 5–6 are still
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
- **QoI tie-break doctrine (Step-13 amendment).** When more than one quantity of
  interest could genuinely test the hypothesis, prefer one the substrate contract can
  extract — a tie-break among genuinely equivalent tests, never a license to substitute
  a weaker test; the fidelity gate checks surrogacy claims.
- **Single-sided success criteria are anomaly-blind in the passing direction.** Scored
  case b proved a 3x-too-high result still "passes" an above-threshold criterion and
  reads as clean success. Step-15 schema candidate: a two-sided expectation.
- **The setup_error/out_of_envelope overlap at skips and halts is characterized and
  deliberately unpatched.** When nothing executed, both labels are literally true; no
  prompt or definition patch until evidence shows the ambiguity matters downstream.
- **Learned-summary poison risk.** On non-exit decisions stage 5 journals its
  learned_summary verbatim, and the thought layer can assert false physics confidently
  (case b). Noted for Steps 21/23 (mechanical checks, journal hygiene).
- **Transcripts are write-only evidence.** runs/<id>/transcripts/ records every
  assembled model input, written before the call fires. No code may ever read a
  transcript back into a model input or stage logic (unit tests excepted) — a read-back
  would be a covert channel between fresh contexts.
- **Per-process transcript sequencing joins the parallelization revisit list.** The
  transcript sequence counter is process-global; if stages ever run in parallel
  processes, sequencing must be revisited.
- **Memory-steering characterization (Step-14 two-arm result).** Arm 1 (mixing domain,
  memory visible): zero drift, all-scalar ideation. Arm 2 (instrument-matched domain,
  same memory): all four hypotheses drifted to velocity/vortex QoIs. Steering lives in
  the domain string, not the memory frame; drift did not by itself reach executability
  (both arm-2 runs defer on spatial-masking/derived-field QoIs).
- **Baton schemas are locked (Step 15).** schemas.py is the lock artifact; changes to
  it require a recorded ruling, same discipline as frozen prompts.
- **Schema violations halt loudly, never re-ask.** A malformed baton after a stage
  returned is a broken invariant, not a model error — the supervisor logs SCHEMA
  VIOLATION, journals a halted-schema run_record, and stops; no correction loop.
- **Deferred schema candidates and their wake conditions (Step-15 docket).**
  Candidate 1 (categorical parameter role): wake on a second live categorical
  occurrence or a downstream mis-read. Candidate 4 (coupled/redundant sweep
  declaration): wake on a consistent-redundant sweep misleading a downstream stage —
  half-met in the Step-15 crashed demo (a derived 'Re' in mini-run dicts halted the
  builder loudly rather than misleading); the derived-parameter mini-run convention
  question is deferred to Step 16.
- **Two-sided expectation accumulates unconsumed until Step 16/21.** success_criterion
  MAY carry expected_value + tolerance (both-or-neither, validated); no stage-4/5
  consumer is wired yet, deliberately — the field gathers real usage data first.
- **Step-16 named opening items (from the Step-15 crash).** SDK-exception handling in
  call_stage_model (an SDK/transport exception propagates uncaught, bypassing the
  3-attempt re-ask loop — first fired live in demo attempt 20260706T054646Z) and
  crashed-run journaling (a crashed run leaves no run_record; none backfilled).
  Both closed in Step 16 chunk 1 (transport retry; stage-crash catch).
- **Loop bound is 2 (Step 16)** — at most MAX_LOOPBACKS=2 loop-backs per run; a
  third non-exit decision forces an honest stop with the recommendation journaled
  (completed_loop_bound_forced_exit). Stays 2 until evidence demands otherwise.
- **more_data is unwired until Step 19.** Enacting it ends the run honestly
  (completed_more_data_unwired) — Phase-C experimentation intelligence is not built,
  and no stub consumer is pretended.
- **prior_thought ruling (Step 16, recorded schemas.py change).** Optional
  prior_thought at post-gate-1 (back_to_design surgery), tolerated at every boundary,
  valid thought shape when present; back_to_ideation carries NO prior_thought —
  stage 1's journal read-side is the cross-hypothesis channel.
- **Gate 5 logs model-vs-enacted, both, every pass** — "model=X enacted=Y
  (accepted|overridden)" in log.txt; decisions never enter baton history.
- **Sessions and Terminal runs have independent lifetimes.** Never assume a lost
  builder session killed a run — the disk and the still-running process are ground
  truth (the Step-16 demo survived its session and completed under human gates).
- **External-kill sentinel is on the watch list.** A run killed from outside leaves
  no run_record; zero live instances so far — build it only when one actually occurs.

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

Phase B, Step 10 — chunk 2 of 2 COMPLETE (2026-07-04): .gitignore gained
.DS_Store (the one tracked copy removed from the index only;
memory/journal.jsonl stays tracked, deliberately); prompt-freeze re-verified
from disk — 2029 identical prefix bytes between stage 3's SYSTEM_PROMPT and
the spike's PROMPT_V2, diverging exactly at the output-format swap (chunk
1's reported 2015 was terminal line-wrap corruption). Full auto run
20260704T033305Z verified from disk: 6 history entries, verdict.json ==
payload.fidelity_verdict, payload byte-stable through stages 4–6 (plus the
known stub iterate_decision:"exit"), spec valid on fresh validate_spec,
run_record journaled — and the stage-2 RE-ASK correction loop fired LIVE
for the first time (fenced attempt-1 reply rejected as unparseable,
recovered on attempt 2; durable RE-ASK line in log.txt). Human demo
20260704T034650Z verified from disk: rank 2 of 4 chosen at gate 1 (h3),
valid spec, verdict defer with a spec-specific rationale (missing
scalar-field extraction vs the auto run's missing spanwise dimension — two
different, defensible defers), gates 2/5 answered y, no gate vocabulary in
history, run_record journaled. Fence watch: auto run Sonnet 7 NOTEs + the
unstripped fenced re-ask, Haiku 3/3, Opus 0/7; demo Sonnet 8/8, Haiku 3/3,
Opus 0/8 — running Opus total 0/56. Gate 5 in human mode prints the FULL
baton JSON (run_gate), so the verdict is visible but buried — surfacing it
is a pending strategy-chat decision; no display change made this chunk.
Step-10 milestone journaled (run_id "step10") with load-bearing Q&As.
Step 10 COMPLETE (stage 3 real: Opus fidelity gate on the frozen Step-6 v2
prompt; verdict in payload + runs/<id>/stage3/verdict.json; gate-surfacing
decision pending). Step 11 next, scope not guessed here.

Phase B, Step 11 — chunk 1 of 2 COMPLETE (2026-07-04): opening preflight
clean — all 25 Step-10 baseline checksums OK, zero drift. Tidy: model_call.py
fence detection is now the pure function strip_fence(reply) -> (text,
was_fenced), and a fence is recorded (terminal print + durable per-stage NOTE
via _log_fence_note, same run_id-derived path and same bare-call limitation
as RE-ASK) the moment it is seen, BEFORE any parse — so fenced-unparseable
replies are now counted, closing the Step-10 undercount in code (live proof
awaits the next natural fenced-unparseable reply, not contrived);
log_stage_call no longer writes the NOTE (it would double-count), so the NOTE
now precedes its STAGE_MODEL_CALL line in log.txt; correction loop,
isolation, and the 3-attempt bound untouched; 1 new unit test. README
truth-edits (header → Step 11 + wrapper line; the literature index IS wired
into stage 1; stages 1–3 real on Sonnet/Sonnet/Opus, stubs 4–6 Haiku;
stale "still plumbing (Haiku…)" section replaced by "What is NOT built
yet"). supervisor.py gained DISPLAY-ONLY human-mode gate headers printed
before the baton dump, built by pure never-raise payload->str functions:
build_gate2_header (spec title | QoI name | estimated run count) and
build_gate5_header (prominent FIDELITY VERDICT block: label / rationale /
right_instrument — this closes Step-10's pending gate-surfacing decision);
no logic/gating/parsing/snapshot/auto-mode change; 5 new unit tests.
.gitignore gained cases/ (evidence-class, like runs/). What-this-is header
truth-edited Step 10 → 11 + wrapper sentence (disclosed). Substrate probe:
colima already running; of12 and of12-spike containers both alive; of12-img
was MISSING → recreated per the named contingency (docker commit of12
of12-img, sha 2c01407a5d61; of12 read, never modified); foamRun answers
inside of12-spike, nothing written. Production substrate:
cases/cavity_baseline copied from ~/research-spike/cases/lid_cavity and
reset to {0/, constant/ (incl. polyMesh), system/} — DISCLOSED: the
first-preference pristine scratchpad copy (lid_cavity_GOOD, spike session
547170a4) survives only as an empty directory skeleton (tmp cleanup pruned
every file), so the spike-cases fallback was used; container of12-prod
created from of12-img exactly as: docker --context colima run -d --name
of12-prod -v /Users/jesseyu/research-system/cases:/work/cases of12-img:latest
sleep infinity (of12/of12-spike untouched). tools/run_cfd.py graduated
(copy-never-link): every proven behavior survives — controlDict declares
solver/endTime/deltaT (tool never guesses), docker exec with OpenFOAM bashrc
sourced, output to log.<application> in the case dir, 600 s timeout, log
parsed to the same small summary with the exact converged definition
(endTime reached AND all start-of-final-step residuals < 1e-3), full log
NEVER returned; only required adaptations (container of12-prod, paths under
/work/cases); the remembered 5th-failure stop counter is NOT in the spike's
run_cfd.py (it lived in the spike agent's MCP wrapper) so nothing
experiment-specific needed a keep/remove call. New OPTIONAL QoI extraction
(the step's one new capability, minimal tier): only after a run that reached
endTime, postProcess runs at -latestTime with OpenFOAM's stock caseDicts
volFieldValue configs (volAverage / cellMin / cellMax / volIntegrate,
mapping operations {volAverage,min,max,volIntegrate}; component "mag" chains
the stock mag() field function first; 0|1|2 picks from a parsed vector), and
deterministic Python (parse_volfieldvalue_dat, pure) reads the last data row
of postProcessing/<func>/<time>/volFieldValue.dat; success adds qoi {name,
field, operation, value, time}, ANY failure adds qoi_error and never a
number; field names are locked to an identifier regex before shell
interpolation; parser unit-tested against a frozen REAL captured fixture
(tests/fixtures/volFieldValue.dat). tools/drive_cfd.py is the minimal no-AI
CLI. Live proof on cavity_baseline (foamRun/incompressibleFluid to t=20):
(1) no-QoI run converged=true; (2) QoI volAverage(mag(U)) = 0.4168179 m/s at
t=20 — physically plausible (0 < 0.417 < lid speed 2 m/s, Re≈200
recirculating cavity); (3) determinism: identical repeat returned exactly
0.4168179; (4) negative check field "c" → qoi_error "postProcess ran but
wrote no volFieldValue output for volAverage(c)", NO qoi block. Summary
sizes 470 / 610 / 610 / 556 bytes (pretty-printed) — the raw log appears in
none. Verified from disk: 39/39 tests (32 prior + 7 new); frozen list
byte-identical to the Step-10 baseline (drift exactly model_call.py,
supervisor.py, README.md, CLAUDE.md, .gitignore + new files); spike grep = 2
prose docstring matches (substrates.py, stage 3), 0 code. Honest asterisks:
QoI extraction writes postProcessing/ and (for mag) a mag(U) field file into
the case's latest time dir — case-local evidence, never returned; the
negative check revealed postProcess exits 0 on a missing field, so that path
is caught by the no-output-file check and its message is generic; the QoI
gate is reached_end, not converged (fields exist either way; deliberate);
summary byte sizes are of the pretty-printed JSON the driver prints. NOT a
step close — no checksum snapshot. Chunk 2 = substrates.py contract
truth-edit (QoIs are now extractable) + five-spec re-run + step close.

Phase B, Step 11 — chunk 2 of 2 COMPLETE (2026-07-04): CAVITY_2D_CONTRACT
truth-edited (substrates.py's only change; 39/39 tests still pass): section
3 now offers the OPTIONAL single QoI per run (volAverage | min | max |
volIntegrate on a field the case already wrote, optional component mag or
0|1|2, latest written time only; qoi {name, field, operation, value, time}
on success; reached-endTime precondition with convergence reported
separately and unconverged QoIs unendorsed — usability is downstream
judgment; qoi_error and NO number on ANY failure), and the two false limits
bullets were replaced with the precise boundary: velocity/pressure-field
statistics YES, concentration/tracer fields NO (no scalar-transport
physics), no new fields, no time-series, no multi-QoI, single-shot only;
every still-true limit kept verbatim (2D laminar, Re≈200 envelope,
convergence ≠ physical validity, regime-assumption axis uncovered).
Five-spec re-run through the UNCHANGED gate (same specs from disk, same
gate code, same frozen prompt; the only moved variable was the contract):
5/5 defer again, no label moved — NOT scored, no answer keys, rationales
are the evidence; the rationales now cite the new precise boundary (no
scalar-transport physics / no concentration field on three; the
single-shot/no-time-series limit on one; the Re≈200 envelope on two) where
Step 10 cited blanket no-field-extraction; runs
handfeed3-20260704T062651Z/-062712Z/-062724Z/-062744Z/-062804Z, all
attempts=1, zero RE-ASK, Opus fence 0/5. Builder's human demo
20260704T063051Z verified from disk: rank 2 of 4 chosen at gate 1 (h4,
S-shaped sidewall undulation), baton_after_gate_1 payload exactly {domain,
chosen_hypothesis {id, statement, rationale}} matching the ranked list's
rank-2 entry; spec.hypothesis_id h4 and fresh validate_spec []; verdict.json
== payload.fidelity_verdict (defer: 2D momentum-only, no concentration
field, cannot represent the 3D S-undulation nor extract the Danckwerts
mixing index — engages the UPDATED contract's boundary); gates 2/5 answered
y; 6 history entries; no supervisor gate vocabulary in history (substring
hits triaged: stage name 'stage3_fidelity_gate' + stage-1's own 'ranked'
note); run_record journaled; both new pretty headers durable in log.txt
(SPEC line 65; boxed FIDELITY VERDICT lines 234–238) — logger.log writes
them, not terminal-only. Demo mechanics: 18 model calls all attempts=1,
zero RE-ASK; fence watch Sonnet 8/8, Haiku 3/3, Opus 0/7 (with re-run:
running Opus total 0/68) — the fence-fix's fenced-unparseable undercount
case has still never occurred naturally. Step-11 milestone journaled
(run_id "step11") with load-bearing Q&As. README gained the drive_cfd
usage + QoI request shape. Checksum snapshot
checksums_after_step11_chunk2.txt is this step's FINAL write.
Step 11 COMPLETE (run_cfd graduated as production substrate with single-QoI
extraction; contract truth-edited; gate re-run on five specs; demo
witnessed). Step 12 next, scope not guessed here.

Phase B, Step 12 — chunk 1 of 2 COMPLETE (2026-07-04): stage 4 is real —
deterministic verdict-gated execution, the Haiku ack stub retired (stages
5–6 stay stubs). Opening preflight: 31/31 Step-11 checksums OK, zero drift;
of12-prod already Up; cavity_baseline's clean {0/, constant/, system/}
intact but carrying its own Step-11 live-proof artifacts (time dirs 2–20,
logs, postProcessing/) — reported, not repaired; the builder copies ONLY
the clean subtrees (and not polyMesh — blockMesh regenerates the mesh) so
synthesized cases can never inherit stale results a -latestTime QoI would
silently read. stages/stage4_case_builder.py (NO model calls): build_case
partitions each run's FULL param dict into buildable {kinematic_viscosity →
physicalProperties nu (its true home in the baseline), lid_velocity → 0/U
movingWall vector, cavity_length → blockMeshDict vertices (uniform scaling,
depth included), mesh_resolution → N N 1 cell counts, end_time/time_step →
controlDict endTime/deltaT with writeInterval = the exact step count so the
final time dir is guaranteed (non-integral ratio = honest halt)} /
ignorable (EMPTY, deliberately) / everything else → CaseSynthesisError
naming every offender; reynolds_number is verified against an EXPLICIT
U/L/nu decomposition (within 1%; inconsistent or undecomposable = halt —
the builder never invents a decomposition); every template rewrite is
subst-count-checked (exactly 1, or 8 vertices); blockMesh runs inside
of12-prod as part of synthesis, failure = CaseSynthesisError with a bounded
log tail. stages/stage4_simulation.py behind the frozen run(baton)->baton:
defer → skipped_defer (nothing executed); trust/refine → sequential
mini-runs, each build_case + run_cfd, cases cases/<run_id>_run<N>/;
CaseSynthesisError → halted_synthesis (honest outcome, no further runs,
relay onward); refine adds flag "refine — survivors require downstream
confirmation"; the spec QoI becomes a qoi_request ONLY via machine-readable
qoi {field, operation, component?} keys validated against the wrapper's own
vocabularies (never parsed from free text; missing/invalid → per-run
qoi_error "not extractable by contract"); evidence = full wrapper summaries
at runs/<id>/stage4/results.json, payload.execution_results = conclusions
only {status, flag?, runs:[{converged, qoi_value|qoi_error, wall_clock_s}]};
one code-authored history note. handfeed_stage4.py side door: --source-run
(prefers baton_after_stage_3.json; else spec.json + verdict.json + chosen
record), --force-label trust|refine|defer (recorded as forced_label +
original_label in source.json), and --payload <file> for hand-authored
payloads (recorded hand_authored: true) — the addition Task 5a needed.
specs/handcrafted_baseline_qoi.json: hand-authored two-run executable
baseline spec (validate_spec = [], hypothesis_id hand-baseline), wrapped by
specs/handcrafted_baseline_payload.json with a HAND-AUTHORED trust verdict
(disclosed: not a stage-3 output). Three witnessed paths from disk: (a)
EXECUTED handfeed4-20260704T083221Z — 2 real solver runs, both converged,
run 1 volAverage(mag(U)) = 0.4168353 at t=20 (vs Step-11's 0.4168179, NOT
exact: deltaT 0.005 here vs baseline 0.002 — different discretization,
0.004% apart), run 2 = 0.1930067 (lid 1.0 — lower, as expected; sub-linear
vs lid 2.0 because Re halves to 100), history "executed 2 mini-run(s): 2
converged, 2 QoI extracted"; (b) SKIPPED handfeed4-20260704T083312Z from
the demo's defer — execution_results exactly {status: skipped_defer}, zero
case dirs created; (c) HALTED handfeed4-20260704T083329Z from the h4
sinusoidal-floor spec forced trust — halted_synthesis at run 1 of 3 naming
all eight unsupported parameters, zero solver invocations, plus the honest
qoi_translation_error for its free-text QoI. Tests 47/47 (39 prior + 8 new:
5 builder — clean build read back from tmp via test seams
cases_root/run_mesh=False, unsupported halt, Re-inconsistency halt,
Re-without-decomposition halt, non-integral end_time/time_step halt — and 3
translate_qoi). Builder unit tests do NOT run blockMesh live (disclosed);
the live proofs cover it. README truth-edits: header → Step 12 + stage 4
real, "What is NOT built yet" → stubs 5–6, handfeed_stage4 usage added.
Honest asterisks: stage4_case_builder.py lives in stages/ per the build
order but is substrate-side machinery (tool-wrapper layer conceptually —
stage code above it names no solver); extractable QoIs are signalled by
machine keys inside spec.qoi that validate_spec tolerates but does not yet
require/check (expand on evidence — stage 2's prompt doesn't know them yet,
so today every model-authored spec records qoi_error); --payload was not in
the task's flag list (needed for 5a, evidence marked hand_authored);
synthesized-case controlDict keeps the template's "(answer key)" comment
header (prose only); README "What you should see" doesn't yet describe
stage 4's STAGE4 log lines — chunk 2's supervisor runs will truth-edit
displays. Stage 4 has never run under the supervisor yet. NOT a step close
— no checksum snapshot. Chunk 2 = auto run + human demo + close.

Phase B, Step 12 — chunk 2 of 2 COMPLETE (2026-07-04): mini-preflight clean
(HEAD de02839, status clean, of12-prod already Up). Opening tidy (all ruled):
cases/cavity_baseline pruned back to exactly {0/, constant/ (incl. polyMesh —
the Step-11 reset template originally carried it), system/} at this recorded
checkpoint — deleted the Step-11 live-proof artifacts (time dirs 2–18; time
dir 20 incl. the derived mag(U) field; log.foamRun 7.0 MB; log.postProcess;
postProcessing/) because template ≠ evidence store (proof evidence lives in
the frozen fixture and reports); controlDict header truth-edited "(answer
key)" → "Production template, graduated from the Step-5 spike case." (Re line
kept; grep confirms "answer key" gone project-wide). Gate-5 header extension
(ratified JC6d, the chunk's ONLY supervisor change, display-only):
build_gate5_header appends an EXECUTION section when
payload.execution_results exists — status, then per-run one-liners (run N:
converged true/false, qoi <value> | qoi_error <msg>) for executed, "nothing
executed: defer verdict" for skipped_defer, "reason: <halt reason>"
otherwise; pure never-raise, refine flag deliberately not printed (not in the
ruling's list); 5 new unit tests, 52/52 total. Auto run 20260704T084910Z
verified from disk (452.76 s wall clock; stage-4 elapsed <1 ms by baton
mtimes): defer verdict (2D in-plane velocity proxy for an inherently-3D
Péclet-reduction mechanism) → skipped_defer branch — 6 history entries with
stage 4's code-authored "skipped (defer)", execution_results exactly
{status: skipped_defer}, zero cases/<id>_run* dirs, honest results.json,
payload byte-stable through stages 5–6 (known iterate_decision:"exit"),
verdict.json == payload.fidelity_verdict, ECHO_CHECK stages 2+3, 17 calls
all attempts=1, zero RE-ASK, run_record journaled. Human demo
20260704T090024Z verified from disk: rank 2 of 4 chosen at gate 1 (h2),
gate-1 payload exactly {domain, chosen_hypothesis} matching the rank-2 entry
verbatim, spec.hypothesis_id h2 + fresh validate_spec [], defer verdict (no
scalar-transport physics so the concentration-variance QoI does not exist;
cannot reproduce the 3D Hopf instability at Re_c≈1914) → skipped_defer
branch, gates 2/5 answered y, gate-5 header durable in log.txt with BOTH the
verdict block (line 226) and the new EXECUTION lines (229–230), 6 history
entries, no gate vocabulary in history (substring hits triaged: stage name
'stage3_fidelity_gate' + stage-1's own 'ranked' note), run_record journaled.
Fence watch both runs: Sonnet 8/8, Haiku 2/2 (denominator now 2 — stage 4
makes no model call), Opus 0/7 each — running Opus total 0/82. Honest
asterisks: both supervised runs drew defer, so the executed and halted
branches have still run only through the chunk-1 side door — expected until
stage 2 learns the contract's machine-readable QoI keys (the NAMED Step-13
opening change; also a Step-15 schema candidate); the discretization pair
0.4168179 @ dt=0.002 vs 0.4168353 @ dt=0.005 is 4-sig-fig agreement, and
chunk 1's "mismatch" wording was a strategy-chat dictation error, resolved.
Step-12 milestone journaled (run_id "step12") with load-bearing Q&As.
Checksum snapshot checksums_after_step12_chunk2.txt is this step's FINAL
write.
Step 12 COMPLETE (stage 4 real: verdict-gated deterministic runner; case
synthesis with honest halts; mini-experiment execution through run_cfd;
supervised in both modes). Step 13 next, scope not guessed here.

Step 13 COMPLETE (stage 5 real; thought layer scored 4/6 triage, 5/6
decision; over-trust characterization on record; supervisor records but
does not loop). Step 14 next, scope not guessed here.

Step 14 chunk 1 COMPLETE (model-input transcripts live, 17/17 verified;
journal read-side into ideation with leads-not-facts frame; arm-1
memory-steering result: zero drift on mixing domain). Chunk 2 next:
instrument-matched domain runs + trace audit + step close.

Step 14 COMPLETE (transcripts + trace audit; journal read-side into
ideation; memory-steering characterized: the domain string, not the memory
frame, steers ideation flavor — arm 2 drifted all four hypotheses to
velocity/vortex QoIs, but executability was not reached, both runs defer).

Step 15 chunk 1 COMPLETE (2026-07-06): three-run baton evidence gathered —
RUN A full auto (defer → skipped_defer, setup_error/back_to_design), RUN B
executed path via new handfeed --then-stage5 (QoIs 0.4168353/0.1930067
exactly reproduce Step 12; thought engaged the sharpened free-text
expectation, none/exit, no journal append), RUN C halted path (five
offenders named; setup_error/back_to_design, learned_summary journaled);
schema_audit_step15.md (JC1 lens: zero Q1 schema failures across all
exercised boundaries; two weak Q2 trim signals) and docket_step15_draft.md
(six draft dispositions) written. AWAITING joint docket ruling in the
strategy chat (HARD STOP); chunk 2 = schema lock. No snapshot yet — this
is NOT a step-closing chunk.

Step 15 COMPLETE (baton schemas locked: schemas.py + supervisor boundary
enforcement; docket ruled 3 in / 2 deferred / 1 rejected; audit: no Q1
baton failures across defer/executed/halted paths). Step 16 next, scope
not guessed here.

Step 16 COMPLETE — PHASE B COMPLETE: the loop closes human-in-the-loop
(gate-5 decision live, both loop-back types consumed, bound-2 witnessed
firing in both modes; robustness: transport retry, crash catch; derived
convention consumed). Step 17 next (Phase C), scope not guessed here.

Phase C, Step 17 — chunk 1 COMPLETE (2026-07-06): three retrieval tools for
the Co-Scientist ideation rebuild, built and proven in isolation — NO Stage-1
wiring yet. retrieval/scholar_search.py (search_arxiv + search_semantic_scholar,
stdlib+certifi in the fetch_literature.py style, 1400-char snippet cap, arXiv
1-per-3s throttle, bounded 429/503 retry, honest errors);
retrieval/materials_lookup.py (direct REST to api.materialsproject.org
materials/summary with _fields + X-API-KEY — mp-api/pymatgen deliberately NOT
installed per ruling; MP_API_KEY read from project-root .env via python-dotenv;
ground state chosen by lowest energy_above_hull; scalar-only returns, raises on
every failure mode); retrieval/web_search.py (the RULED exception: retrieval is
deterministic EXCEPT this one tool — one bounded Haiku call through the same
SDK/auth path as model_call.py with allowed_tools=["WebSearch"], max_turns=6,
JSON-array-only output enforced in Python; transcript written to
runs/<id>/transcripts/ BEFORE the call fires, hence the run_id parameter;
model_call.py untouched — the wrapper carries its OWN per-process transcript
sequence counter, filenames can't collide with model_call's but cross-module
sort order isn't guaranteed, joining the parallelization revisit item).
.gitignore gained .env; .env holds the personal MP key and is confirmed
untracked. Zero pip installs (pip list diff empty); 146/146 tests pass;
everything downstream of gate 1 byte-untouched. Proofs on query "lid-driven
cavity flow bifurcation": arXiv 3 on-topic records (incl. the cubical-cavity
Hopf bifurcation at Re_c=1914); web_search 3 records under run
websearch-smoke-20260706T185225Z with transcript 0001_web_search.json on disk
(one result independently corroborating Re_c=1914); lookup_material("Al",
["density"]) → density 2.7200502 g/cm3 (matches aluminum ~2.70). Honest
asterisks: search_semantic_scholar returned HTTP 429 through two full bounded
retry cycles (keyless shared pool throttled) — the FAILURE path is proven live,
the success path has never run; the free S2_API_KEY env var is already
supported and is the fix if 429s persist. web_search does not durably log
fence NOTEs (its fence-strip is silent — the fence watch does not count this
wrapper); it also has NO transport retry (one call by ruling; model_call's
Step-16 retry does not cover it). The MP material_id returned
(mp-aaaaaafe) is an unfamiliar id format vs classic mp-134 — value plausible,
format noted for watching. The builder wrote the user's MP key into .env after
the user pasted it into the chat (disclosed; the key now exists in that chat
transcript — regenerate it if the transcript is ever shared). NOT a step
close — no checksum snapshot, no commit. Chunk 2 next, scope not guessed here.

Phase C, Step 17 — chunk 2 COMPLETE (2026-07-06): Generation rebuilt to the
four Co-Scientist strategies. stages/generation_strategies.py (the one
permitted helper module — keeps the four strategies legible and
independently testable while stage1_ideation.py keeps its stage-flow role)
holds retrieval gathering, all four strategies, and pool assembly;
stage1_ideation.py's Generation block now calls generate_candidate_pool, and
Reflection/filter/Ranking plus the delivered object are UNTOUCHED. The
strategies (all Sonnet through call_stage_model, per the Generation-is-
generative ruling): (1) literature_exploration — corpus RAG + live arXiv
REQUIRED (their failure propagates, an honest stage failure), S2 + web
optional-preferred (a RuntimeError is recorded in evidence and the run
proceeds); one call producing exactly 4 hypotheses, each citing ref ids
validated against the actually-provided snippets inside the re-ask loop.
(2) simulated_debate — HARD CAP DEBATE_TURNS=3, one fresh Sonnet call per
persona (theorist / computational scientist / skeptical reviewer), each
receiving the same bounded refs + structured debate-so-far through call
arguments (construction-level isolation; never a transcript); the final
turn's hypothesis is the converged result → 1 candidate. (3)
assumptions_identification — two calls: identify 3-5 testable intermediate
assumptions (conditional reasoning, no retrieval), aggregate into exactly 3
hypotheses citing assumption numbers (validated). (4) research_expansion —
one call reviewing the pool-so-far → exactly 2 hypotheses each naming the
gap it fills; meta_review_feedback is a None-defaulted UNUSED seam parameter
(Meta-review is a later chunk; no feedback channel invented). Pool = 10
candidates (4/1/3/2), canonical ids h1..h10 assigned in deterministic
Python; per-run evidence: retrieved_literature.json (per-source records +
per-source errors + the combined ref-tagged list), debate.json,
assumptions.json, generation.json (pool with per-candidate strategy
provenance). The leads-not-facts memory block goes to strategies 1 and 4
only (1 as old Generation's descendant, 4 because steering is its job);
debate and assumptions stay memory-free. Smoke run
gen4smoke-20260707T002700Z verified from disk: 11 combined refs (corpus 3,
arXiv 3, S2 2, web 3) — Semantic Scholar's keyless SUCCESS path ran live
for the first time (chunk 1 had only ever proven its 429 path; S2_API_KEY=
placeholder added to .env, user chose to proceed keyless); all four
strategies contributed; citations are real (h2 ties arXiv:1607.05126's
Re_c≈1914 Hopf bifurcation to a web benchmark's vortex-center
trajectories); web_search received the run_id and its write-before-call
transcript 0001_web_search.json is on disk; snippets capped at 1400 chars
both in evidence and inside the literature call's assembled input (12,353
bytes total) — no raw tool output entered any Generation context; 7 Sonnet
calls all attempts=1, zero RE-ASK, Sonnet fence 7/7 (running watch).
Verified: 146/146 tests, pip list fingerprint identical (zero installs),
schemas.py/supervisor/model_call/baton/tools/stages 2-6/tests all
byte-untouched (git diff empty on the frozen surface). Honest asterisks:
the full supervised pipeline has not yet run over the new Generation —
Reflection now receives 10 candidates instead of 6 (cost grew accordingly)
and the next chunk's runs will witness that path; the two per-process
transcript counters (model_call + web_search) both emitted 0001_*.json into
the same run dir — the known cross-module sort-order caveat, now witnessed
live, stays on the parallelization revisit list; materials_lookup is
deliberately NOT wired into Generation (no strategy names it and a fluids
domain carries no formula — wake when a domain does); the old
"stage1_ideation_generation" transcript/log stage name is retired in favor
of per-strategy names. NOT a step close — no checksum snapshot, no commit.
Chunk 3 next, scope not guessed here.

Phase C, Step 17 — chunk 3 COMPLETE (2026-07-07): Reflection rebuilt to the
six Co-Scientist review types. stages/reflection_reviews.py (the one
permitted helper module, mirroring generation_strategies.py's role) holds
all six review units, per-hypothesis retrieval, and the orchestrator;
stage1_ideation.py's Reflection block now calls reflect_on_pool, and the
filter/Ranking/delivered object are UNTOUCHED — reflections keep the exact
{hypothesis_id, novelty, critique, quality} contract, and no schemas.py
change was needed (the enforced boundary is post-gate-1, unchanged). The
six types: (1) initial review — ONE Sonnet call over the whole pool, NO
tools, pass/discard per candidate on correctness/quality/novelty/
preliminary-safety, gating BEFORE any tool spend; (2) full review — one
call per initial survivor, grounded in per-hypothesis retrieval (corpus +
arXiv required, S2 + web best-effort — same source policy as Generation);
the novelty verdict must cite ref ids actually shown (extra_validator
inside the re-ask loop; a 'known' verdict requires ≥1 ref) and verdict +
rationale + cited refs are saved per hypothesis — THE WATCH; this review
supplies the filter's novelty/critique/quality fields; (3) deep
verification — assumptions → sub-assumptions → per-assumption evaluation,
invalidating elements, fundamental_flaw bool; a fundamental flaw discards
DETERMINISTICALLY (Python, not prompt hope); (4) observation review — same
bounded refs plus journal leads (the ONE review unit receiving memory,
leads-not-facts frame preserved); (5) simulation review — step-wise mental
simulation + failure scenarios; (6) recurrent/tournament review — INERT
SEAM (None-defaulted tournament_state; no model call when None; raises on
non-None rather than silently ignoring it — same pattern as
meta_review_feedback). Evidence: stage1/reflection_reviews.json (initial
verdicts, per-hypothesis retrieval records incl. per-source errors, all
review outputs, both discard lists, final reflections). Smoke run
reflect6smoke-20260707T010004Z (full Stage 1, ~58 min wall, 40 Sonnet
calls all attempts=1 + 9 web-search Haiku calls, zero RE-ASK, Sonnet fence
40/40, ZERO Opus calls — ranking was trivial): 10 generated → 8 passed
initial review (h6/h8 discarded citing benchmark contradictions) → 7 of 8
discarded at deep verification (fundamental_flaw=true, each naming
specific physics) → 1 reflected → 1 survived filter → k=1 trivial ranking
→ delivered object {domain, hypotheses, hypotheses_ranked} intact: the
pipeline CLOSES over chunk-2's Generation. Novelty-check inspection
(h5/h1/h3): verdicts genuinely grounded — each rationale names what the
cited refs do and do not establish (e.g. h5: benchmarks tabulate ψ extrema
but no log-log β fit exists); web records did the heavy lifting, corpus
contributed, but per-hypothesis arXiv retrieval returned OFF-TOPIC noise
(full-sentence statements as all:-queries matched CMS/ATLAS/IceCube
papers; the models correctly never cited them), and S2 contributed ZERO
the entire run — 429s plus a NEWLY WITNESSED failure shape: zero-hit S2
replies omit 'data' entirely (keys [offset, total]), so the wrapper
reports legitimate no-results as an error (retrieval/ was frozen this
chunk; needs a ruling). Honest asterisks: deep verification is
aggressively lethal (7/8 discarded) — whether those are true fundamental
flaws or systematic over-triggering is the open watch, and it left k=1 so
Ranking had nothing to judge; the arXiv noise strengthens the OpenAlex
case; per-run cost grew to 49 model calls (the initial gate saved ~8
Sonnet calls + 2 retrieval rounds by discarding 2 of 10); the two
per-process transcript counters now interleave at scale (9 web + 40
model_call in one run dir). 146/146 tests; pip fingerprint identical;
58/60 Step-16 checksums OK (drift exactly CLAUDE.md + stage1_ideation.py).
NOT a step close — no checksum snapshot, no commit. Chunk 4 next, scope
not guessed here.

Catch-up (this status section previously ended at Step 17 chunk 3; the
interim record lives in journal milestones step17-progress-and-reorder /
step16.6 / step18.7, commits 964d482→74e0ecd→7f9c112→a4dd853, and
docs/context_after_18.7.md): the Step-17 chunk-4a diagnostic triaged deep
verification's lethality (~55-60% of kills genuinely fundamental, ~40-45%
should have survived) and Phase C was reordered instruments-and-cost-first.
Step 16.6 CLOSED (measurement rails: cost meter, ledgers, FAST merge gate —
hard-gate 1/6/16, exit 0, never skipped before a merge — and the kill-rate
battery; snapshot checksums_after_step16_6.txt). Step 18.7 CLOSED (model
tiers: per-stage reject gauge; Generation all-4-strategies + Reflection
initial/full/observation/simulation Sonnet→Haiku, deep-verify HELD on
Sonnet (feeds a deterministic kill, no judgment net), stage 2 HELD on
Sonnet, Opus stages unchanged; downgrade validated — Haiku baseline in the
Sonnet regime; the 10-run Haiku kill-rate baseline LOCKED as 17-fix-A's
"before": same-domain k={0,0,0,0,1} kills 86-100%, alt k={2,1,1,1,0} kills
70-90%, reject ~0.04, memory md5 373c886b; snapshot
checksums_after_step18_7.txt).

17-fix-A CLOSED (2026-07-10): the coupled Generation/deep-verify fix
(commit b000274 — Generation no-invented-numbers instruction + warn-only
unsupported-number signal; deep-verify fundamental-vs-addressable with
addressable_notes never fatal; constant guard: a kill may not rest on a
remembered constant) measured against the locked Haiku baseline
(harness/killrate_17fixA.log). HONEST RESULT: 8 of 10 slots produced
comparable data — same5 and alt1 UNRESOLVED (arXiv 429/503 exhausted
MAX_RELAUNCHES; a grounding-transport failure, NOT a fix failure).
Same-domain k={1,1,3,1}, alt-domain k={2,1,3,4}; ZERO zero-survivor runs
(vs baseline 4/5 same-domain) — tournament starvation eliminated.
Deep-verify kill rate 25-67% same / 20-67% alt (vs baseline 86-100% /
70-90%). generation_unsupported_number = 7 total, 0 in most scored runs;
reject_rate 0.013; ledger 0/0; all 8 comparable runs matched memory md5
373c886b. Manual inspection confirmed: remaining kills are genuinely
fundamental (structural/circular/scale defects; no remembered-constant
kills — the constant guard holds), survivors are real, and carried
addressable_notes correctly kept otherwise-killed hypotheses as rankable
survivors. VERDICT: both halves of the success criterion met, with
disclosed caveats — 8/10 comparability, and "reliably ≥1, frequently ≥2,
occasionally ceiling-4" survivors rather than a clean always-≥2. Close
work: the carried Step-16 QoI-name watch item folded in (tools/run_cfd.py
reports 'cellMax(U)[1]'-style names — a numeric component now shows in the
QoI name; the on-disk postProcessing/ dir name is unchanged) and the two
stale per-function docstring sets corrected to the post-18.7 pins
(generation_strategies.py, reflection_reviews.py — deep-verify's Sonnet
docstring untouched). Verified GREEN at close: 146/146 tests, FAST
hard-gate 3/3 / zero watch misses / ledger 0/0 / exit 0,
survival_counter --validate ALL MATCH. Milestone journaled (run_id
"17-fix-A"). Checksum snapshot checksums_after_17fixA.txt is this close's
FINAL write.
17-fix-A COMPLETE.
17-fix-B (S2 zero-hit fix + keyed-free OpenAlex hard-required novelty
grounding, cfa767e): merged to main at fc0c6b7 (2026-07-10); witnessed
kill-rate run PASSED 2026-07-10 (4/4 slots resolved, zero relaunches, all
md5-comparable; see docs/milestone_17fixB_witness.md); owes live S2
re-probe only.
docs/milestone_17fixA.md now exists (reconstructed; see its RECORD
CORRECTION block).
17-C (Elo tournament) CLOSED (built 5038c1e; witnessed PASS, 4/4 slots,
zero relaunches, all md5-comparable; HARD STOP read recorded — see
docs/milestone_17C.md).
17-D (Evolution) MERGED to main (2026-07-11, true merge 04d27e8, build
commit e599e47 preserved verbatim): four strategies on Sonnet pin
(EVOLUTION_MODEL claude-sonnet-4-6); 2-variant cap — simplification
always + seeded rotation; variants reviewed by the full Reflection chain
and ranked via in-memory tournament pool; evolution_variants.json
evidence; survivors.json and battery k untouched. Witness + dedup check
CLOSED 2026-07-12 — see the 17-D CLOSED paragraph below and
docs/milestone_17D.md.
Step 22 (paper agent) MERGED to main (2026-07-11, true merge c957f3b,
build commit 6bda1fd preserved verbatim): sidecar-first validation
handoff on Haiku pin (STAGE6_MODEL claude-haiku-4-5-20251001); mandatory
What-Humans-Must-Validate from the sidecar; markdown deliverable, TeX
queued; lint-with-error-feedback; harness --mode paperlint; offline-refs
seam. Smoke witnessed live; owes supervised real-run outing at 17-CLOSE.
Merge-session verification (2026-07-11): union suite on the combined
tree 218/218 tests across 21 files, all green (supersedes the stale
146-test count above); FAST run twice, both GREEN hard-gate 3/3 (second
run logged a warn-only watch miss, case 13 refine→trust — recorded, does
not affect GREEN). Main HEAD at status write: c957f3b (pasted from
git rev-parse in-session).
17-D CLOSED (2026-07-12, doc-only close; every number re-derived from
disk — see docs/milestone_17D.md): mechanism witnessed PASS on the
overnight battery launched from 14f96e6; competition path
live-unexercised, carried to 17-E. Facts: 4/4 slots, zero relaunches, md5
373c886b on 4/4; 6 variants emitted (2 per Evolution-running slot; same2
halted pre-Evolution at zero parents), 0 accepted; emission schema
rejects 0/6 on pin claude-sonnet-4-6; zero-accept tolerance fired 3/3
without crash; combination guard fell back twice, logged; survivors.json
integrity holds (exactly 7 fields per record, zero ev-ids, k counts
Generation survivors only); cost 275 calls (228 model + 47 web_search),
mean 68.75 calls / 61.0 min per slot excluding the 3×180 s designed
sleeps; reject rate 0.031 (bar 0.04; 17-C 0.028). MANDATORY dedup check
CLOSED outcome (c), method deviation disclosed (zero variants reached any
pool, so live flags could not fire; the pre-registered offline salvage
ran on the identical vectorizer path — parents-only refit reproduced
same1's live matrix to the last digit): sibling band 0.117–0.227,
departure band 0.058–0.229, distinct-parent controls 0–0.197 across 17-C
and tonight — bands interleave (alt2's ev1, the parent minus its
qualifiers, scores 0.1947, BELOW genuinely distinct pairs); no tf-idf
threshold separates siblings from distinct. RULING: 0.85 stands as a
near-verbatim detector; recalibration refused on evidence;
embedding-class similarity upgrade queued post-deadline; recorded
pattern — the Reflection chain is the de-facto sibling filter upstream
of dedup. PARENT-POOL WATCH ARMED: k [3,0] same / [1,1] alt vs 17-C's
[3,4]/[3,3]; same2 k=0 all_known_at_filter — first zero-survivor run
since 17-fix-A (filter kills cite R10/R11/R12 and read defensible);
deep-verify kill rates 0.5/0.778/0.7/0.5, same2 above fix-A's
same-domain top; frozen-file diff acd7dd0..14f96e6 on
generation_strategies.py + reflection_reviews.py empty (re-verified
live at close). TRIGGER (ruled): the 17-E witness read audits
same-domain kill rationales; any k=0 slot OR ≥2 slots at k≤1 →
dedicated forensic session before 17-CLOSE, and Step 18 does not launch
until it resolves. One dictation-vs-disk asterisk recorded in the doc:
S2 429'd 38 non-zero-hit retrieval rounds on disk (dictated 39; 9
zero-hit-repaired rounds confirmed; 47 rounds total).
17-E BUILT (2026-07-12, committed on main together with this status edit;
parent HEAD 14f96e6): meta-review + feedback loop + research overview +
iteration controller. stages/meta_review.py — META_REVIEW_MODEL
claude-opus-4-8, ONE Opus call per round boundary over a code-composed
round_record (reflection outcomes incl. kill reasons; tournament results
resolved to statements incl. verdict reasons and debate verdicts;
evolution outcomes + reject reasons; dedup flags; the standing
ranking-withhold pattern verbatim); schema-checked with bounded list
sizes; NEVER crashes the run — any failure degrades to the empty feedback
object, logged and recorded. Per-family feedback blocks
(compose_feedback_block, round 1 = explicit empty block) code-appended to
Generation (framed for selective use + the prior round's research-overview
directions; the dead meta_review_feedback seam revived across all 5
Generation prompt sites), Reflection (framed as recurring factors every
future review must definitively address; all 5 review call sites), and
the 3 tournament-judge sites. stage1/research_overview.json written every
round (last round = end-of-run synthesis); it never enters the baton —
the gate-1 payload wall is untouched, no schemas.py change. Review 6
ACTIVE on Haiku pin claude-haiku-4-5-20251001: one call per survivor over
prior-round tournament results resolved to statements by the controller
(raw cross-round ids never reach it); ADVISORY only — no new kill path;
tournament_state=None keeps the inert path, reason string corrected.
Iteration controller inside stage1_ideation.run: ROUNDS=2 beside
MAX_SURVIVORS, run() rounds override, battery --rounds default 1 (scored
runs stay baseline-comparable single passes); memory retrieval stays
outside the loop (md5 pin meaning preserved); rounds work in
stage1/round<N>/ and canonical stage1 files = LAST SUCCESSFUL round;
rounds.json per-round audit trail; k=1 rounds write a trivial-marker
tournament_state.json; zero-survivor raise in round >=2 terminates
standing on the last successful round (round 1 crashes honestly, exactly
as before); termination = round budget + MAX_SURVIVORS count cap ONLY
(ranking-stability detection deferred — cross-round ids unstable);
exactly ONE add_history per run. Battery slot records gain
variants_emitted / variants_accepted / rounds_completed /
termination_reason — k derivation byte-identical. Stale tournament-seam
prose corrected (reflection_reviews.py, stage1_ideation.py,
generation_strategies.py). Deviations disclosed: research-contacts
identification and publication-format decoding omitted. Verified:
250/250 tests offline (32 new in tests/test_meta_review.py; one
spec-driven edit to test_evolution's trivial-branch assertion — the
trivial marker replaced the old no-state-file behavior); FAST GREEN
hard-gate 3/3, zero watch misses, ledger 0/0, exit 0 (the session's only
live calls). 17-E OWES the overnight witness: --mode killrate
--repeats 2 --rounds 2; the 17-D-armed trigger (any k=0 slot OR >=2
slots at k<=1 → forensic session before 17-CLOSE) applies to its read.
Next: 17-E overnight witness --repeats 2 --rounds 2 + witness read;
then 17-CLOSE.

17-CLOSE build items LANDED (2026-07-12): item 1 (QoI-name truthfulness)
verified ALREADY IMPLEMENTED at 17-fix-A close (tools/run_cfd.py
component-carrying 'cellMax(U)[1]'-style names, commit 6e4796b) — the
named milestone_17C.md record does not exist; CLAUDE.md's 17-fix-A close
paragraph is the record (disclosed, no code change); killrate battery
records launch_git_head via git rev-parse at launch (null +
launch_git_head_note on git failure, never a crash); survival_counter
gains ADDITIVE variants_emitted_total / variants_accepted_total (summed
across stage1/round*/evolution_variants.json when round dirs exist, else
the canonical file; last-round fields keep their meaning) and the battery
copies them into slot records; dry-run pin listing now includes
EVOLUTION_MODEL / META_REVIEW_MODEL / REVIEW6_MODEL (live module
attributes — battery reports record the richer pin set too, a disclosed
consequence) and cost lines state the 17-E measured per-round figures
(≈85 calls / ≈72 min) times requested rounds; judge-prompt id-hygiene
sentence (ids only, never positional/order words) inserted in
RANKING_SYSTEM_PROMPT_V2 + DEBATE_JUDGE_SYSTEM_PROMPT; gate-1 near-tie
display (supervisor build_gate1_neartie_display, display-only,
never-raise): final-round rank/id/Elo table from stage1/
tournament_state.json + research-overview direction summaries in human
mode; model_call single-fence prose tolerance (extract_single_fenced_block
— on parse failure only, exactly-one-fence replies parse as the block,
else existing behavior), fixture = the EXACT smoke6-20260711T083510Z
attempt-1 crash reply frozen at tests/fixtures/smoke6_prose_wrapped_reply
.txt (source run dir lives in the build-22 worktree's runs/, disclosed);
tfidf/proximity drift test (tests/test_tfidf_drift.py) captures both
sites' TfidfVectorizer constructor args and fails on divergence.
Verified: suite 263/263 offline (250 + 13 new); FAST GREEN hard-gate 3/3,
zero watch misses, rejects 0/6, ledger 0/0 (the session's only live
calls); survival_counter --validate ALL MATCH. Next: supervised run +
demo.

Step 17 CLOSED (2026-07-12/13, doc-only close on Run A + Run B evidence —
docs/milestone_17E.md + docs/milestone_17CLOSE.md + docs/journal_day3-4.md
are the record; every number re-derived from disk). 17-E witness PASSED
(4/4 slots, zero relaunches, md5 373c886b x4, forensic trigger NOT fired;
loop live in same1/alt2, count cap in same2/alt1; feedback blocks proven
in round-2 transcripts across all three families; Evolution 12 emitted /
6 accepted with the first variant debate win and first rank-1 variant
delivery; dedup zero flags with live customers, parent-child 0.3409
unflagged; position-2 watch 6/6 across 3 split matches; mean 124 calls /
101.7 min per slot, rejects 0.019). Rulings R-C1..R-C6 recorded.
Supervised obligation split-witnessed: Run A 20260712T194452Z (human) —
rank-2 pick, live loop-back, the project's FIRST refine verdict, honest
halt on colima-down, honest more_data ending (90 calls, 1h35m); Run B
20260712T212952Z (auto) — all gates self-resolved through 2 passes,
Evolution variant ev2 won gate 1 at Elo 1258.3, memory loop witnessed
(Run A's learned summaries verbatim in Run B's generation context),
KILLED EXTERNALLY ~00:06Z mid-pass-3 (144+23 calls, 2h36m) — root cause
= launch venue (Claude Code background task), a strategist process
error; first live instance of the watched external-kill scenario (no
run_record; the sentinel's build condition is now met). THE RUN-VENUE
RULE IS ABSOLUTE: every run, supervised included, launches from a plain
Terminal under caffeinate — never from a builder-session background
task. The 373c886b memory-md5 pin era ENDED BY DESIGN when Runs A/B
journaled learned summaries (journal md5 now d708f701); by AMENDED
RULING the checksum snapshot moves from this close's final write to
18-prep after Run C. CARRIED DEBTS to Run C (2026-07-13 ~9 AM, plain
Terminal, human mode): executed solver path under the post-17 pipeline;
Stage-6 real-pipeline paper + paperlint. Next action: Run C, then
18-prep (snapshot + parallel-arms ruling; Step-18 sizing already ruled
at 4 runs/arm on the measured 17-E cost).
