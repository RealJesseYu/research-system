# Context after Step 18.7 — handoff for the 17-fix-A strategy session

Written 2026-07-09 at the Step-18.7 close (commit `a4dd853`). Purpose: let a
cold strategy session resume at the 17-fix-A read-only reality check with
zero re-derivation. Everything here was verified from disk at write time.
(No prior dedicated handoff doc existed in the repo; this one mirrors
CLAUDE.md's structure — what-this-is, rulings, status, next — since CLAUDE.md
has served as the de-facto handoff.)

## What this is

The real build of an autonomous research system: a relay of six AI stages
(Ideation → Experiment-Design → Fidelity-Gate → Simulation → Thought-Layer →
Paper) coordinated by a plain-Python supervisor that is deterministic and
never calls a model. Stages exchange small typed batons, never transcripts;
schemas are locked (`schemas.py`) and enforced in Python. Three human gates
(after stage 1, after stage 2, at stage 5's iterate decision), two modes
(`human` stops and asks; `auto` logs and proceeds — the mode never changes
what stages do). Memory lives on disk, never in context. Upper layers are
substrate-agnostic (the current substrate is 2D lid-driven-cavity CFD behind
`tools/run_cfd.py`, but no stage code may name it).

**The project's contribution** is (a) the pre-run **fidelity gate** — an
Opus judgment on whether a proposed experiment can be trusted to the
instrument (trust / refine / defer), proven in the spike and production since
Step 10 — and (b) **experimentation intelligence** (Phase C, in progress):
ideation, verification, and decision machinery that is measured, not hoped
at.

Phase A (the `~/research-spike` risky-bit) and Phase B (Steps 7–16, the loop
closes) are complete. Phase C was reordered instruments-and-cost-first after
the Step-17 chunk-4a diagnostic: TIER 1 (Step 16.6 measurement rails +
Step 18.7 model tiers) is now DONE; the ideation fix (17-fix-A) is next.

## Model roles and the pin map after the 18.7 downgrade

Roles: Haiku = volume work and stubs; Sonnet = calls that feed deterministic
consequences with no judgment net; Opus = hard judgments only. Verified
model strings (from the live pins, recorded in every kill-rate results
file): `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-8`.

Current pins (verified in code at `a4dd853`):

| Call site | Pin |
|---|---|
| Generation, all 4 strategies (`generation_strategies.HAIKU_MODEL`) | Haiku |
| Reflection initial / full / observation / simulation (`reflection_reviews.HAIKU_MODEL`) | Haiku |
| **Deep verification** (`reflection_reviews.DEEP_VERIFY_MODEL`) | **Sonnet** — HELD: it feeds a deterministic kill with no judgment net |
| Stage 2 experiment design (`stage2_experiment_design.SONNET_MODEL`) | **Sonnet** — HELD: no battery watches it |
| Stage 1 ranking (`stage1_ideation.OPUS_MODEL`) | Opus |
| Stage 3 fidelity gate (`stage3_fidelity_gate.OPUS_MODEL`) | Opus |
| Stage 5 thought layer (`stage5_thought_layer.OPUS_MODEL`) | Opus |
| web_search wrapper, model_call default (stage-6 stub) | Haiku |

The downgrade **HELD**: the 10-run Haiku baseline sits in the same regime as
the 4-run Sonnet proving batch (Sonnet: k∈{0,1,0,2}, kills 56–100%, reject
0.0).

## Working rhythm and standing rulings

- **Two doors to the model, and only two** — `model_call._ask_once` and
  `retrieval/web_search._search_once`; both report into the one shared
  `cost_meter`, tagged by source. Nothing may open a third door (this is why
  the fidelity battery calls `call_stage_model` directly with the frozen
  stage-3 prompt instead of `stage3.run()`).
- **Judgment in models, control in code.** Anything we can't afford to have
  broken is enforced by Python (schemas, validators, deterministic
  discards), never by hoping a prompt is remembered.
- **Summarize at the wrapper.** Raw tool output never reaches a stage; only
  bounded summaries travel.
- **No change merges without a GREEN FAST harness** (hard-gate cases 1/6/16;
  exit 0). HEAVY / kill-rate is an on-demand instrument, never a merge
  blocker.
- **Scored runs: fix-and-disclose is FORBIDDEN.** A scored run's result
  stands as launched; a broken scored run is relaunched, never patched
  mid-flight and disclosed.
- **Long runs go in a plain Terminal, never Claude Code** (learned live: the
  external-kill sentinel fired for the first time on batches launched inside
  Claude Code; six orphan `runs/killrate-20260708T*` dirs retained as
  evidence).
- **ps over narration.** The process table is ground truth for whether a
  batch is alive — never a session's narration. Sessions and Terminal runs
  have independent lifetimes.
- **`caffeinate` + `python` = TWO PIDs = one healthy batch** — the signature
  to check for.
- Tested-first, expand only on evidence, no gold-plating; `runs/` is
  append-only evidence; the checksum snapshot is the FINAL write of any step
  close; keep honest records including what didn't go to plan.

## WHERE WE ARE

Steps 16.6 and 18.7 are both CLOSED with checksum snapshots
(`checksums_after_step16_6.txt`, `checksums_after_step18_7.txt`, 78 files
each). Full narrative: `docs/session_journal_16.6_to_18.7.md`. Commit
**`a4dd853`** (Step 18.7 CLOSE) is the clean restore point.

**THE LOCKED HAIKU BASELINE** — the pre-fix "before" number for 17-fix-A;
measure the fix against THIS (source: `harness/killrate_last_run.json` +
`harness/baseline_haiku.log`, 10 scored runs, 2026-07-09):

- same domain: **k = {0, 0, 0, 0, 1}, deep-verify kills 86–100%**
  (three of the k=0 runs discarded ALL candidates at deep verification)
- alt domain: **k = {2, 1, 1, 1, 0}, kills 70–90%**
- reject rate **~0.04** (21/527), concentrated in Reflection full-review
- **~48.7 min mean wall per run** (≈22% faster than Sonnet; per-call
  latency, not fewer calls)
- comparability pins recorded in the results file; memory block md5
  `373c886b` on all ten runs

**The four carried watch items** (journal milestone `step18.7`):

1. External-kill sentinel fired for real (first live instance) — orphan dirs
   retained; plain-Terminal / two-PIDs discipline now standing.
2. Haiku is slightly rougher at Reflection full-review than Sonnet: the same
   domain leaned total-kill (3/5 runs discarded all 10 at deep-verify), and
   one run exhausted the 3-attempt re-ask loop causing an abort (reject
   crossed absorbed→fatal once in 13 launches). Watch whether 17-fix-A also
   cleans these up.
3. "Claude Code returned an error result: success" did NOT recur (0 this
   batch) — de-escalated; note if it returns.
4. arXiv 500/503 aborts with zero retry (unlike 429) — 2 of the batch's 3
   aborts; a known unretried path.

## IMMEDIATE NEXT: 17-fix-A

The coupled Generation/deep-verify fix from the chunk-4a diagnostic
(journal milestone `step17-progress-and-reorder`), **three parts**:

1. **Generation: stop over-specifying.** Hypotheses invent quantitative
   claims no retrieved snippet supports; those invented specifics are what
   deep verification then executes on.
2. **Deep verification: fundamental-vs-addressable.** The Co-Scientist
   paper's distinction is absent — a whole hypothesis dies over an
   addressable detail. Only genuinely fundamental flaws should kill;
   addressable ones should be noted, not fatal. (Diagnostic triage: ~55–60%
   of kills genuinely fundamental, ~40–45% should have survived.)
3. **Confident-false-constant guard.** The review gate asserted the Moffatt
   corner-eddy ratio as ~0.036 in one run and ~1e-5 in another — both as
   fatal-kill grounds. The case-b poison risk is inside the review machinery;
   a kill must not rest on an unverifiable asserted constant.

**Current position: the read-only reality check** — re-read the live
Generation/Reflection code and the diag4a + baseline evidence before
changing anything; no edits until the check is done.

**Success criterion:** against the locked Haiku baseline, the deep-verify
kill rate drops; a rankable pool (k > 1) survives reliably (tournament
starvation ends); the kills that remain are genuinely fundamental on
inspection. Measured via the kill-rate battery — same two domains, same
memory pin, pins recorded — never via blind re-runs. Per the standing rule,
every merge along the way needs a GREEN FAST harness.

## Instruments available (all proven live)

- **FAST merge gate**: `python harness/run_harness.py --mode fast` — hard-gate
  1/6/16 (RED → exit 1), watch 3/4/13 (recorded, non-blocking),
  Hagen-Poiseuille trap SKIPPED-but-registered, ledger-activity 0/0 in-band
  check. Report → `harness/last_run.json` (overwrite).
- **HEAVY fidelity battery**: `--mode heavy` — all 16 cases, full scoring.
- **Kill-rate battery**: `--mode killrate [--repeats N] [--dry-run]` — the
  17-fix-A measuring instrument. Two diag4a domains × N repeats, relaunch on
  ABORTED (max 2), 180 s arXiv spacing, memory-md5 comparability pin, pins
  recorded, orphan-safe run ids. Report → `harness/killrate_last_run.json`
  (overwrite). Launch big batches from a plain Terminal under `caffeinate`,
  tee to a `harness/*.log` (precedent: `proving_batch_sonnet.log`,
  `baseline_haiku.log`).
- **Survival counter**: `python harness/survival_counter.py --validate`
  (recomputes the diag4a dirs, must print ALL MATCH) or
  `python harness/survival_counter.py runs/<id>` for any single run.
- **Ledgers**: `memory/fidelity_ledger.jsonl` (1 entry, defer, from
  `handfeed3-20260707T183101Z`; null `outcome` slot reserved for Step 21) and
  `memory/override_ledger.jsonl` (absent — correctly: no human gate resolved
  since the writer landed). Batteries must never write them.
- **Cost meter** (`cost_meter.py`): per-door calls + attempts + verbatim SDK
  tokens, per-stage `{calls, rejects, reject_rate}` (the REJECTS line).
  Reject = completed-but-invalid, re-asked — a format signal, not a judgment
  signal. ~18k-token fixed prompt overhead rides every call.
- **Tests**: 146/146 as of `a4dd853`.

## Carried TODOs (beyond 17-fix-A)

- **S2 zero-hit fix (17-fix-B):** zero-hit Semantic Scholar replies omit
  `data` entirely and the wrapper misreports legitimate no-results as errors;
  `retrieval/` was frozen when found — needs its ruling.
- **OpenAlex (17-fix-B):** approved on the diagnostic evidence — per-hypothesis
  arXiv retrieval returns off-topic noise (full-sentence `all:` queries
  matching CMS/ATLAS/IceCube papers).
- **CLAUDE.md status refresh:** the status section still ends at Step 17
  chunk 3 — 16.6 and 18.7 exist only in journal/commits/this doc. Refresh at
  the 17-fix-A close.
- **Hagen-Poiseuille cost-routing trap:** registered SKIPPED "pending:
  analytic tier not built (Step 12)"; when the analytic tier exists, scoring
  becomes label AND routing.
- Gates 1/2 "override" is a weaker signal than gate 5's genuine model
  decision — note for Step 24.
- arXiv 500/503 retry parity with 429 (watch item 4) — fix only on evidence
  it keeps costing relaunches.

## Key artifacts

`docs/session_journal_16.6_to_18.7.md` (full technical narrative) ·
`harness/` (run_harness, fidelity_case_runner, killrate_battery,
survival_counter, cases/, diag4a_reference/, both batch logs, both report
files) · `cost_meter.py` · `memory/ledgers.py` · journal milestones
`step17-progress-and-reorder`, `step16.6`, `step18.7` · commits `964d482` →
`74e0ecd` → `7f9c112` → `a4dd853` (restore point).
