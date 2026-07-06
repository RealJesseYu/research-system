# Schema audit — Step 15 chunk 1 (three-run baton evidence)

Pre-registered lens (ratified JC1, restated): at every baton boundary,
exactly two questions. **Q1 (failure signature):** did the receiving stage
demonstrably lack something it needed? Cite the concrete bad call, or state
"none observed". **Q2 (trim signal):** did the receiving stage visibly
ignore something it was sent? Absence-of-reference is weak evidence — said
so wherever it is the only evidence. Facts only; every claim below is read
from disk: `runs/<id>/{transcripts/, stage*/, baton_*.json, log.txt}`,
`memory/journal.jsonl`, and for stage 4 (no model call) the stage code's
deterministic payload reads confirmed by its evidence.

The three runs:

- **RUN A** `20260706T044214Z` — full supervised auto run, domain
  "mean-flow structure and vortex strength in laminar lid-driven cavity
  flows". 17 model calls, 17 transcripts. Gate 1 selected h3 (rank 1,
  stratified-cavity vortex suppression). Verdict defer → stage 4
  skipped_defer → thought setup_error / back_to_design.
- **RUN B** `handfeed4-20260706T045314Z` — hand-authored trust payload
  (`specs/step15_executed_payload.json`, sharpened expected_observation),
  stage 4 executed 2 real solver runs (QoIs 0.4168353 / 0.1930067), then
  live stage 5 via the new `--then-stage5` flag → thought none / exit.
- **RUN C** `handfeed4-20260706T045429Z` — payload reconstructed from run
  `20260705T202645Z`'s `baton_after_stage_3.json` (refine verdict, S-shaped
  sidewall spec), stage 4 halted at synthesis (five offenders named), then
  live stage 5 → thought setup_error / back_to_design.

## RUN A — 20260706T044214Z

### Boundary gate-1 → stage 2

- **Payload carried** (`baton_after_gate_1.json`): exactly `{domain,
  chosen_hypothesis {id, statement, rationale}}` — h3, stratified-cavity
  vortex suppression at Ri = 0.5, Re = 400.
- **Model input** (transcript 0014, claude-sonnet-4-6): keys `{run_id,
  domain, chosen_hypothesis, substrate_contract}` — the contract text is
  delivered by stage code, not by the baton.
- **Q1:** none observed. The one call produced a spec that passes fresh
  `validate_spec` with zero errors on attempt 1: six of its nine parameters
  use canonical contract names, the three non-canonical ones
  (temperature_difference, thermal_expansion_coefficient,
  gravitational_acceleration) are exactly the quantities the buoyancy
  physics requires and the contract's vocabulary section explicitly permits
  declaring.
- **Q2:** none observed. The spec engages everything it was sent: the
  hypothesis's Ri/Re numbers appear in the parameters and criterion, and
  the qoi block quotes the contract's operation vocabulary back verbatim to
  explain why it declined machine keys ("The current substrate supports
  only volAverage | min | max | volIntegrate over fields the case directly
  writes; vorticity is not a written field"). It also names and declines
  the volAverage(mag(U)) proxy as a weaker test — QoI tie-break doctrine
  behavior, engagement rather than ignoring.

### Boundary stage 2 → stage 3

- **Payload carried** (`baton_after_stage_2.json`): gains
  `experiment_spec` (identical to `stage2/spec.json`); nothing removed.
- **Model input** (transcript 0015, claude-opus-4-8): keys `{run_id, spec,
  substrate_contract}` — stage code deliberately narrows: domain and
  chosen_hypothesis are in the payload but not sent.
- **Q1:** none observed. The defer verdict is specific and correct from
  spec + contract alone: "incompressible solver with no energy/buoyancy
  equation, so it cannot represent Richardson-number stratification at
  all, and the required vorticity-circulation QoI is unextractable under
  its contract." No sign the missing hypothesis rationale was needed — the
  spec's own objective and regime carried the physics.
- **Q2:** none observed of what was sent. (The narrowing itself is stage
  code's choice, not the model ignoring baton content.)

### Boundary stage 3 → stage 4

- **Payload carried** (`baton_after_stage_3.json`): gains
  `fidelity_verdict` == `stage3/verdict.json` (label defer).
- **What entered**: no model call; deterministic stage 4 read
  `payload.fidelity_verdict.label` → "defer" → skip branch. Evidence:
  `stage4/results.json` = `{status: skipped_defer, reason: fidelity
  verdict label is "defer" — nothing was executed.}`; zero
  `cases/20260706T044214Z_run*` dirs.
- **Q1:** none observed — the label was present and sufficient to gate.
- **Q2:** on the defer branch stage 4 reads nothing else (experiment_spec
  unread). This is verdict-gating by design, not a trim signal: the same
  fields are consumed on the trust/refine branch (RUN B/C).

### Boundary stage 4 → stage 5

- **Payload carried** (`baton_after_stage_4.json`): gains
  `execution_results` exactly `{status: "skipped_defer"}`.
- **Model input** (transcript 0016, claude-opus-4-8): keys `{run_id,
  chosen_hypothesis, experiment_spec, fidelity_verdict, execution_results,
  stage4_summaries}`; `stage4_summaries` = `[]` (read from
  `stage4/results.json`; nothing executed). Domain is in the payload but
  not sent — stage-code narrowing, as designed.
- **Q1:** none observed. The thought correctly diagnosed the skip
  (setup_error / back_to_design), citing the verdict's substrate limits and
  the spec's success_criterion by content — everything it referenced was in
  its input.
- **Q2:** none observed. All five input components are visibly engaged in
  the assessment except run_id (echoed in ack_run_id, as required) and
  chosen_hypothesis, whose content overlaps the spec's objective here;
  absence of a distinct hypothesis reference is the only evidence and is
  weak.

### Boundary stage 5 → stage 6 (stub)

- **Payload carried** (`baton_after_stage_5.json`): gains `thought` +
  `iterate_decision: back_to_design`.
- **Model input** (transcript 0017, claude-haiku-4-5): keys `{run_id,
  payload}` — the whole payload, into an ack stub.
- **Q1/Q2:** defined at lock, unconsumed (stub until Step 22). No
  evidence either way from an ack; stage 6's real consumption is not
  observable yet.

## RUN B — handfeed4-20260706T045314Z (executed path)

### Boundary payload → stage 4

- **Payload carried** (`baton_before_stage_4.json`): the four hand-authored
  keys `{domain, chosen_hypothesis, experiment_spec, fidelity_verdict}`
  (trust), spec = the sharpened-expectation copy of the handcrafted
  baseline.
- **What entered**: no model call; deterministic reads were
  `fidelity_verdict.label` (trust → execute), `experiment_spec.
  mini_experiment.runs` (both all-canonical, both built —
  `cases/handfeed4-20260706T045314Z_run1` and `_run2` exist), and
  `experiment_spec.qoi`'s machine keys (`{field: U, operation: volAverage,
  component: mag}` → qoi_request; both QoIs extracted).
- **Q1:** none observed — both runs converged (residuals ~1e-7–1e-8),
  QoIs 0.4168353 / 0.1930067, exactly the Step-12 record.
- **Q2:** stage 4 structurally does not read title, objective,
  success_criterion, expected_observation, regime, or full_experiment —
  provable from code, not absence-of-reference. Not a trim signal: those
  same fields are consumed by stage 3 (before) and stage 5 (after) on this
  very payload.

### Boundary stage 4 → stage 5

- **Payload carried** (`baton_after_stage_4.json`): gains
  `execution_results` = `{status: executed, runs: [{converged: true,
  wall_clock_s: 13.03, qoi_value: 0.4168353}, {converged: true,
  wall_clock_s: 13.1, qoi_value: 0.1930067}]}` (conclusions only).
- **Model input** (transcript 0001 in the handfeed dir, claude-opus-4-8):
  the six allowed keys; `stage4_summaries` = both full wrapper summaries
  (status, converged, reason, residuals, Courant, continuity, runtime,
  qoi) read from `stage4/results.json`.
- **Q1:** none observed. The assessment engages the sharpened free-text
  expectation directly and numerically: "These match the predicted values
  (~0.4168 and ~0.1930, ratio ~2.16) essentially exactly" — plus
  residuals, continuity, and Courant from the summaries, and the 0.3
  threshold from the criterion. Nothing it needed was missing. (n=1, not
  scored: this probes engagement when values MATCH; it cannot show what a
  sharpened free-text expectation does under a mismatch — Step-13 case b
  remains the only mismatch datapoint, and there the free-text anchors
  were dismissed as "qualifier-hedged".)
- **Q2:** one visible redundancy: `execution_results.runs`'s
  {converged, qoi_value} duplicate fields also present inside
  `stage4_summaries`; the assessment's numbers are all attributable to the
  summaries (residuals/continuity/Courant appear only there), and
  `wall_clock_s` is referenced nowhere in the thought
  (absence-of-reference — weak evidence, said so). At this one boundary
  the conclusions-only block and the summaries overlap; on the skip/halt
  branches (A, C) there is no overlap because summaries are empty.

## RUN C — handfeed4-20260706T045429Z (halted path)

### Boundary payload → stage 4

- **Payload carried**: reconstructed verbatim from
  `runs/20260705T202645Z/baton_after_stage_3.json` — refine verdict,
  S-shaped-sidewall spec whose 7 parameters include five non-canonical
  names and whose qoi is free-text only.
- **What entered**: deterministic reads — label refine → execute branch;
  qoi translation first: `qoi_translation_error` "QoI 'vol_avg_speed' not
  extractable by contract: spec qoi carries no machine-readable
  field/operation keys (free-text definitions are not translated)"; then
  run 1 synthesis halt: "cannot build: Re, cavity_height, cavity_width,
  mesh_cells_per_meter, s_amplitude_fraction not in the buildable set
  (kinematic_viscosity, lid_velocity, cavity_length, mesh_resolution,
  end_time, time_step)". Zero solver invocations; zero case dirs.
- **Q1:** the halt is the failure signature, but it is a **content**
  failure the current schema permits, not a baton field the receiving
  stage lacked: the baton delivered the spec faithfully, and the spec
  itself declared unbuildable parameter names and a free-text-only QoI.
  The concrete bad call is the halted run-1 build (nothing executed).
- **Q2:** same structural non-reads as RUN B's stage 4; not a trim signal.

### Boundary stage 4 → stage 5

- **Payload carried**: `execution_results` = `{status: halted_synthesis,
  runs: [], reason: <the full halt line above>, flag: "refine — survivors
  require downstream confirmation"}`.
- **Model input** (transcript 0001 in the handfeed dir, claude-opus-4-8):
  the six allowed keys; `stage4_summaries` = `[]`.
- **Q1:** none observed. The thought names all five offenders and the
  six-name buildable set verbatim from `execution_results.reason`, quotes
  the criterion (0.35 m/s at alpha = 0.30) and the expected observation
  accurately from the spec, and lands setup_error / back_to_design. The
  reason field carried everything needed to diagnose the halt.
- **Q2:** the `flag` ("refine — survivors require downstream
  confirmation") is referenced nowhere in the thought —
  absence-of-reference, weak evidence, and with zero surviving runs there
  was nothing for the flag to qualify. Journal note: non-exit decision →
  the live path appended the learned_summary to `memory/journal.jsonl`
  (line 41), quoting the buildable set — the JC6 behavior under
  observation, disclosed.

## Cross-run synthesis

- No boundary in any of the three runs showed a Q1 failure attributable to
  the baton schema: every receiving stage had what it needed, in one call,
  at every exercised boundary (RUN C's halt is spec **content** the schema
  permitted, not a missing baton field).
- Q2 trim signals, each one line:
  - `execution_results.runs` (conclusions) duplicates {converged,
    qoi_value} available inside `stage4_summaries` at the 4→5 boundary on
    the executed branch only (RUN B); `wall_clock_s` unreferenced
    (absence-of-reference — weak).
  - `execution_results.flag` unreferenced by RUN C's thought
    (absence-of-reference — weak; zero survivors meant nothing to
    qualify).
  - No other ignore observed; stage-code narrowing (domain withheld from
    stages 3/5, hypothesis withheld from stage 3) is deliberate design,
    not model-side ignoring, and produced no Q1 failure.
- Stage 6's input is defined at lock, unconsumed (stub until Step 22).
- Bottom line, facts only: across one defer, one executed, and one halted
  path, the current batons carried what was needed; the only observed
  slack is the small executed-branch redundancy above.
