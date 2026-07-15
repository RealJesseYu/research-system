# Induced rules v1 — meta-induction over cross-run artifacts

One Opus pass (`META_INDUCE_MODEL = claude-opus-4-8`, R-MI-1) over a deterministically-composed digest of on-disk artifacts. These rules are **advisory sidecar output only** — nothing any pipeline model sees was changed by this pass (no retrieval wiring, no injected blocks, no prompt text). Provenance basis is the model's, over provenance-tagged inputs.

- digest size: 20725 chars ≈ 5182 tokens (cap 10000)
- induction call: outcome=ok, attempts=1
- rules accepted: 8   dropped (zero supporting artifacts): 0

## Rule 1

**QoIs requiring vorticity or other derived velocity-gradient fields (enstrophy, circulation, streamfunction saddle topology) are unextractable on the cavity_2d/icoFoam substrate, which only reduces already-written fields; such hypotheses must be redesigned onto a global-reducible proxy or routed to an instrument with field-derivative post-processing.**

- provenance basis: `said`
- suggested scope: Design/QoI-selection stage for any cavity_2d hypothesis involving vorticity, circulation, or streamfunction quantities
- supporting artifacts: 20260712T194452Z, handfeed3-20260707T183101Z, 20260713T020121Z, validate18-T1-same1-ev1, 20260706T090043Z

## Rule 2

**The substrate exposes only whole-domain volAverage/min/max/volIntegrate over U/p and never raw field arrays, so any QoI needing spatial masking or sub-domain decomposition (corner-excluded core pressure, corner-eddy chords, primary-vortex KE fraction, recirculation-region counts) is untestable without added offline post-processing.**

- provenance basis: `said`
- suggested scope: QoI feasibility screening for spatially-localized observables in the lid-driven cavity
- supporting artifacts: 20260714T152314Z, validate18-T1-alt1-ev2, validate18-T2-alt1-h10, validate18-T3-same1-ev1, 20260706T030119Z

## Rule 3

**Non-canonical geometry or spatially-varying lid boundary conditions (central obstacles, S-shaped/multi-block meshes, codedFixedValue/bimodal lid profiles, non-square aspect ratios) halt the case builder, which accepts only its canonical scalar parameter vocabulary; such hypotheses require builder extension or a different instrument before any run.**

- provenance basis: `said`
- suggested scope: Instrument-fit check before dispatching any non-canonical-geometry or custom-BC cavity design
- supporting artifacts: 20260712T212952Z, 20260713T020121Z, handfeed4-20260706T045429Z, validate18-T1-same2-ev2, validate18-T1-alt2-ev2

## Rule 4

**Global field extrema are dominated by singular/primary-flow features rather than the secondary structures under study: min(Uy) saturates with Re and is insensitive to corner vortices, and min(p) is set by the non-convergent top-lid corner singularity — so global extremum QoIs are unfaithful proxies for secondary-vortex or core-pressure claims.**

- provenance basis: `mixed`
- suggested scope: Validity assessment of global min/max QoIs targeting secondary or core-localized flow features
- supporting artifacts: 20260706T063330Z, 20260714T152314Z

## Rule 5

**At gate 1 the system's rank-1 selection is consistently overridden by the human to a lower-ranked option, while gate 2 approvals are never overridden — indicating the ranking model over-prefers its top candidate at selection time.**

- provenance basis: `measured`
- suggested scope: Gate-1 candidate ranking / selection calibration
- supporting artifacts: 20260712T194452Z, 20260713T020121Z, 20260714T152314Z

## Rule 6

**Gate 5 repeatedly returns designs to back_to_design or more_data across runs, and the fidelity ledger records the matching outcomes as defer/refine with no verified y/n resolution (Brier uncomputable, all 18 unresolved), showing designs on this substrate systematically fail to reach an executed, scored outcome.**

- provenance basis: `measured`
- suggested scope: Pipeline-level throughput and gate-5 loopback on cavity_2d experiments
- supporting artifacts: 20260712T194452Z, 20260713T020121Z, 20260714T152314Z, GATE-BETS HEADLINE

## Rule 7

**Specs are frequently constructed as duplicate experiments — the pi-gate sweep flags 20 specs for repeated Re within tolerance and the anomaly scanner finds identical QoI values (volAverage|U| = 0.416835 and 0.193007) across distinct runs — so dispatched sweeps should be de-duplicated before execution.**

- provenance basis: `measured`
- suggested scope: Pre-dispatch spec validation / de-duplication of Re sweeps
- supporting artifacts: PI-GATE SWEEP SUMMARY, ANOMALY-SCANNER FINDINGS, handfeed4-20260704T083221Z, handfeed4-20260706T045314Z

## Rule 8

**Courant/stability limits are a recurring on-disk risk: the pi-gate sweep flags 15 specs for estimated Courant exceeding its limit, and the anomaly scanner shows max_Courant outliers (~0.60) far above the IQR fence — timestep/mesh spacing should be checked against U*dt/dx before running.**

- provenance basis: `measured`
- suggested scope: Numerical-stability pre-check on time_step/mesh_resolution before solver dispatch
- supporting artifacts: PI-GATE SWEEP SUMMARY, ANOMALY-SCANNER FINDINGS, handfeed4-20260704T083221Z, handfeed4-20260706T045314Z

---

## Strategist review (2026-07-14)

These eight rules are **proposals, not adopted policy.** They are advisory
sidecar output from one Opus meta-induction pass; nothing any pipeline model
sees was changed by them, and **adoption of any rule as a real gate, prompt
edit, or retrieval block requires a recorded ruling** — same discipline as a
frozen prompt or a locked schema. Until then they are hypotheses about the
system's behavior, held for review.

**R6 is flagged partially confounded.** R6 reads the fidelity ledger's 18
unresolved outcomes (Brier uncomputable, `n_resolved=0`) as evidence that
"designs on this substrate systematically fail to reach an executed, scored
outcome." That inference over-reaches. The `outcome: null` field is null because
there is **no real-world scoring channel wired yet** — resolving a gate bet
against a faithful/usable ground-truth label is a **Step-21 schema slot awaiting
real-world results**, not a record that runs did not execute. In fact six run
directories did execute the solver (see `docs/step25_failure_bins.md`
composition note). "All 18 unresolved" is a missing-label artifact, not
non-execution.

**R6's real support is the verdict mix, not the unresolved count:** 13 defer /
5 refine / **0 trust** across the ledger. Zero designs earned a clean trust
verdict on this substrate — *that* is legitimate evidence about throughput and
instrument-fit, and it stands independently of the scoring gap. Read R6 as "no
design has cleared to trust on cavity_2d," not as "designs don't execute."
