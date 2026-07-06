# Trace audit — Step 14 (run 20260706T030119Z)

Formal trace of one full supervised auto run (mode=auto, domain "mean-flow
structure and vortex strength in laminar lid-driven cavity flows",
2026-07-06). Every claim below is read from this run's disk evidence only:
`runs/20260706T030119Z/{transcripts/, stage1/ … stage5/, log.txt,
baton_after_*.json}` and `memory/journal.jsonl`. The run made 17 model calls
(17 `STAGE_MODEL_CALL` lines in log.txt) and left exactly 17 transcript
files; every transcript records `{stage_name, model, timestamp_utc,
system_prompt, stage_input_serialized}` — the fully assembled model input,
written before the call.

## Stage 1 — Ideation (1 generation + 6 reflection + 6 ranking calls)

### Generation (transcript 0001, claude-sonnet-4-6)

- **Model input** — `stage_input_serialized` top-level keys: `run_id`,
  `domain`, `literature_snippets`, `prior_observations`. System prompt: the
  Ideation-stage hypothesis-generator identity. `prior_observations` is the
  memory frame: the header line "PRIOR OBSERVATIONS FROM EARLIER RUNS
  (unverified model text - treat as leads, not established facts):" followed
  by the three retrieved journal entries — the retrieved-entries component,
  named: learned_summary of run 20260706T023653Z (h2, 3-D DNS +
  passive-scalar needed), learned_summary of run 20260705T215130Z (h2, 3-D
  transient DNS near Re≈1914 Hopf), learned_summary of run 20260705T214035Z
  (h2, passive-scalar transport + time-periodic lid needed) — verbatim in
  `stage1/retrieved_memory.json`, most recent first.
- **Evidence written**: `stage1/generation.json` (six hypotheses),
  `stage1/retrieved_memory.json` (written by stage code before the call).
- **Baton out**: none directly (stage 1 emits one baton after all sub-calls).
- **Verdict**: delivered object (run_id + domain) + retrieved entries
  (literature snippets from the literature index + the three journal
  entries), nothing more.

### Reflections h1–h6 (transcripts 0002–0007, claude-sonnet-4-6)

- **Model input** — keys: `run_id`, `hypothesis_id`, `hypothesis_statement`,
  `hypothesis_rationale`, `literature_snippets`, `prior_observations`.
  System prompt: the critical-reviewer identity, one hypothesis at a time.
  `prior_observations` is the same three-entry memory frame as generation.
- **Evidence written**: `stage1/reflections.json` (per-hypothesis novelty +
  quality), then `stage1/survivors.json` after the deterministic filter
  (pure Python, no model).
- **Verdict**: delivered object (one hypothesis's own fields) + retrieved
  entries (its snippets + the memory frame), nothing more. No other
  hypothesis's text and no other call's reply enters any reflection input.

### Ranking sub-calls (transcripts 0008–0013, claude-opus-4-8)

Six pairwise comparisons over the four survivors: h2_vs_h3, h2_vs_h4,
h2_vs_h5, h3_vs_h4, h3_vs_h5, h4_vs_h5.

- **Model input** — keys: `run_id`, `domain`, `hypothesis_a`,
  `hypothesis_b`. System prompt: the comparative-judge identity. **No
  `prior_observations` key** — the memory frame enters exactly the
  generation and reflection transcripts (grep over all 17 files: the header
  appears in 0001–0007 only) and nowhere else, as designed.
- **Evidence written**: `stage1/ranking.json` (win counts + order).
- **Baton out** (`baton_after_stage_1.json`): payload exactly `{domain,
  hypotheses (ranked list), hypotheses_ranked: true}`; one code-authored
  history entry "generated 6, 4 survived reflection, ranked via 6 pairwise
  calls".
- **Verdict**: delivered object (domain + the two hypotheses under
  comparison), nothing more — no memory, no reflection scores, no other
  pair's outcome.

### Gate 1 (supervisor, no model)

Auto mode selected rank 1 (h5); `baton_after_gate_1.json` payload is exactly
`{domain, chosen_hypothesis}`. Deterministic Python; no model input to
trace.

## Stage 2 — Experiment design (transcript 0014, claude-sonnet-4-6)

- **Model input** — keys: `run_id`, `domain`, `chosen_hypothesis`,
  `substrate_contract`. System prompt: the Experiment-Design identity
  (chosen hypothesis → typed spec). `substrate_contract` is
  CAVITY_2D_CONTRACT text delivered by stage code, not by the baton.
- **Evidence written**: `stage2/spec.json` (validates fresh with zero
  errors against hypothesis_id h5).
- **Baton out** (`baton_after_stage_2.json`): payload gains
  `experiment_spec` (identical to spec.json); nothing removed.
- **Verdict**: delivered object (domain + chosen hypothesis) + the contract
  text, nothing more — no stage-1 transcript, no ranked list, no memory
  frame.

## Stage 3 — Fidelity gate (transcript 0015, claude-opus-4-8)

- **Model input** — keys: `run_id`, `spec`, `substrate_contract`. System
  prompt: the frozen Step-6 v2 fidelity-judgment text (judge only from what
  is given; trust/refine/defer).
- **Evidence written**: `stage3/verdict.json` (label defer; rationale:
  streamline-masked corner-vortex KE not serviceable by global single-field
  reductions; uniform 128×128 mesh under-resolves the low-Re corner eddy).
- **Baton out** (`baton_after_stage_3.json`): payload gains
  `fidelity_verdict` == verdict.json; nothing removed.
- **Verdict**: delivered object (the spec) + the contract text, nothing
  more — notably no hypothesis rationale, no domain, no memory.

## Stage 4 — Simulation (no model call; deterministic Python)

- **No transcript exists and none should**: stage 4 makes zero model calls.
  Its deterministic inputs, from code (`stages/stage4_simulation.py`) and
  confirmed by evidence: it read `payload.fidelity_verdict` (label "defer")
  and therefore executed nothing; on trust/refine it would also read
  `payload.experiment_spec` (mini_experiment.runs, qoi machine keys).
- **Evidence written**: `stage4/results.json` = `{status: skipped_defer,
  reason: fidelity verdict label is "defer" — nothing was executed.}`; log
  line 62 `STAGE4 skipped_defer: no case built, no solver run`; zero
  `cases/20260706T030119Z_run*` directories.
- **Baton out** (`baton_after_stage_4.json`): payload gains
  `execution_results` exactly `{status: "skipped_defer"}`.
- **Verdict**: inputs were payload fields only; outputs are conclusions
  only. No model saw anything at this stage.

## Stage 5 — Thought layer (transcript 0016, claude-opus-4-8)

- **Model input** — keys: `run_id`, `chosen_hypothesis`, `experiment_spec`,
  `fidelity_verdict`, `execution_results`, `stage4_summaries`. System
  prompt: the post-run thought-layer identity. `stage4_summaries` is read
  by stage code from `stage4/results.json` (bounded wrapper summaries,
  never raw logs); in this run it is the empty list `[]` because nothing
  executed, and `execution_results` is `{status: skipped_defer}`.
- **Evidence written**: `stage5/thought.json` (triage setup_error, decision
  back_to_design); journal append of the learned_summary (non-exit
  decision) plus, at supervisor level, the run_record.
- **Baton out** (`baton_after_stage_5.json`): payload gains `thought` and
  `iterate_decision: back_to_design`; nothing removed.
- **Verdict**: delivered object (four payload fields) + retrieved
  stage-4 summaries (empty here), nothing more — no stage-3 transcript, no
  full solver log (none exists), no memory frame.

## Stage 6 — Paper stub (transcript 0017, claude-haiku-4-5-20251001)

- **Model input** — keys: `run_id`, `payload`. System prompt: the
  placeholder Paper-stage ack identity. `payload` is the full post-stage-5
  payload (domain, chosen_hypothesis, experiment_spec, fidelity_verdict,
  execution_results, thought, iterate_decision) — the baton object itself.
- **Evidence written**: none (ack stub; no stage6/ directory).
- **Baton out** (`baton_after_stage_6.json`): payload unchanged
  (byte-stable vs stage 5); sixth history entry appended. Final baton
  carries exactly 6 history entries.
- **Verdict**: delivered object (the baton payload), nothing more.

## Overall verdict

For this full run, every one of the 17 model calls left a transcript of its
fully assembled input, and each transcript's `stage_input_serialized`
contains exactly the delivered baton-derived object for that stage plus, in
stage 1 only, the retrieved components (literature snippets and the
three-entry retrieved-memory frame) and, in stage 5, the bounded stage-4
wrapper summaries read from disk (empty in this run); the memory frame
appears in the generation and six reflection inputs and nowhere else; the
stage with no model call (stage 4) is traced through its deterministic
payload reads and its results.json evidence; and each baton snapshot shows
what each stage handed onward. No transcript contains another stage's
conversation, a raw solver log, or any supervisor gate decision. The
build-book done-when — "you can trace, for one full run, exactly what each
stage's context contained" — is satisfied for run 20260706T030119Z. This is
isolation evidence, not correctness evidence: it proves what each stage saw,
not that any stage's judgment was right.
