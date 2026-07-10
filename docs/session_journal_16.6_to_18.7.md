# Session journal — Step 16.6 (measurement rails) through Step 18.7 (model tiers)

Written 2026-07-09 from disk state only: `memory/journal.jsonl` (milestones
`step17-progress-and-reorder`, `step16.6`, `step18.7`), git commits `964d482`,
`74e0ecd`, `7f9c112`, `a4dd853`, the harness code and its two batch logs
(`harness/proving_batch_sonnet.log`, `harness/baseline_haiku.log`), the two
report files (`harness/last_run.json`, `harness/killrate_last_run.json`), the
diag4a reference bundle, and the checksum snapshots. Every number below was
re-read from those artifacts, not paraphrased from memory.

---

## 1. Entry state

Phase A (the `~/research-spike` risky-bit spike) and Phase B (Steps 7–16;
"Phase B complete" is commit `019460e`) were done. Phase C had opened with
Step 17, the Co-Scientist ideation rebuild, chunks 1–3 built but the step NOT
closed:

- **Chunk 1** — three retrieval tools in isolation: `retrieval/scholar_search.py`
  (arXiv + Semantic Scholar, keyless), `retrieval/materials_lookup.py`
  (Materials Project), `retrieval/web_search.py` (the one ruled
  model-in-retrieval exception: a bounded Haiku WebSearch call, transcript
  written before the call). Zero pip installs.
- **Chunk 2** — Generation rebuilt to the four Co-Scientist strategies in
  `stages/generation_strategies.py` (literature exploration / simulated debate
  / assumptions identification / research expansion), pool of 10 candidates,
  grounding enforced in code via extra_validator.
- **Chunk 3** — Reflection rebuilt to the six Co-Scientist review types in
  `stages/reflection_reviews.py` (initial, full, deep verification,
  observation, simulation, inert tournament seam); pipeline closed end-to-end;
  smoke run showed deep verification discarding 7 of 8.

**The chunk-4a diagnostic** (read-only; driver lived in the session
scratchpad, later rescued — see §2.4) ran Stage-1 ideation 4 scored times
across two domains. From `harness/diag4a_reference/diag4a_analysis.json` and
`diag4a_progress.txt`:

| run | domain | deep-verify kills | kill rate | k |
|---|---|---|---|---|
| `diag4a-20260707T032231Z-same1` | same | 4/9 | 44% | 3 |
| `diag4a-20260707T055521Z-same2` | same | 9/9 | 100% | 0 (`deep_verify_discarded_all`) |
| `diag4a-20260707T070010Z-same3` | same | 5/8 | 62% | 3 |
| `diag4a-20260707T080219Z-alt1` | alt | 7/8 | 88% | 0 (`all_known_at_filter`) |

Five more launches died before scoring (arXiv HTTP 429, arXiv unreachable
after 5 attempts, and external kills) — nine `runs/diag4a-*` dirs total.
Findings (journal milestone `step17-progress-and-reorder`):

- Deep verification kills 44–100% of survivors every run, wildly variable
  (k=3/0/3 consecutive on the SAME domain); 2 of 4 scored runs were
  zero-survivor — tournament starvation is real.
- Root cause is **coupled**: Generation over-specifies (invented quantitative
  claims no snippet supports) AND deep-verify kills the whole hypothesis over
  an addressable detail (the paper's fundamental-vs-addressable distinction is
  absent). Manual triage: ~55–60% of kills genuinely fundamental, ~40–45%
  should have survived.
- Buried finding: the review gate asserts confidently-false physical constants
  (the Moffatt corner-eddy ratio given as ~0.036 in one run and ~1e-5 in
  another, BOTH used as fatal-kill grounds) — the case-b poison risk is now
  inside the review machinery itself.

**The reorder decision:** Phase C was redrafted instruments-and-cost-first —
TIER 1 = Step 16.6 (measurement rails) + Step 18.7 (model tiers) BEFORE
finishing ideation (deep-verify fix, OpenAlex, tournament, Evolution,
Meta-review) and before the expensive experiments (18, 20). Rationale on
record: 4-hour blind runs are a symptom of building intelligence before
instruments; the rails let the deep-verify fix be verified against a
kill-rate battery instead of blind re-runs. Accompanying rulings: web_search
model-in-retrieval amendment recorded; S2 stays keyless-permanent
best-effort; OpenAlex approved (diagnostic-confirmed need); drops committed
(16.5-as-a-step, Fourier Neural Operator from Step 19, Step 22 to
background).

Commit **`964d482`** (2026-07-07): "Opening commit for Step 16.6: Step 17
chunks 1-3 (retrieval tools, Generation 4 strategies, Reflection 6 review
types) + Phase C reorder milestone. Interim - not a step close, no checksum
snapshot."

---

## 2. Step 16.6 — the measurement rails (four chunks)

### 2.1 Chunk 1 — the cost meter (`cost_meter.py`)

There is no dollar cost per run (subscription auth); cost = MODEL CALLS +
WALL-TIME. `cost_meter.py` is the call-count half:

- **The two-doors ruling** (recorded in the module docstring): the system has
  exactly TWO doors to the model — `model_call._ask_once` and
  `retrieval/web_search._search_once` — and BOTH report into this one meter,
  **tagged by source**, rather than being refactored into a single door. The
  two per-process transcript counters are untouched; the meter is additive.
- Leaf module (imports nothing project-local) so root and `retrieval/` can
  both import it without inverting layer order. Purely observational:
  recording never changes what a door returns.
- Token counts summed **verbatim** from the SDK's `ResultMessage.usage` dict —
  top-level ints only, `bool` explicitly excluded, nothing estimated. No
  usage → only the call is counted.
- `reset()` at run start, `read()` at end; `read()` returns a plain dict copy
  so two snapshots can be diffed per-case. `KNOWN_SOURCES` guarantees both
  doors always appear (a zero is information).

**The ~18k-token overhead finding** (journal, "live fact for 18.7"): a fixed
~18k-token per-call prompt overhead rides every call. Corroborating current
disk data: the latest FAST run's totals divide to ≈16.5k cache-read + ≈2.1k
input + ≈3.6k cache-creation input-side tokens per call — the fixed context
dwarfs each stage's own prompt.

### 2.2 Chunk 2 — the two ledgers (`memory/ledgers.py`) + attempts

Append-only JSONL beside `journal.jsonl`, "so the system's decision data
stops evaporating." Same discipline as `journal.py`: one JSON object per
line, no update/delete; leaf module; writers are observational hooks at their
producers.

- **`fidelity_ledger.jsonl`** — one entry per fidelity-gate verdict:
  `{run_id, verdict (trust/refine/defer verbatim), substrate, rationale,
  outcome: null, timestamp}`. The `outcome` slot is reserved deliberately —
  a later real-world result fills it; that join is the point of Step 21, so
  run_id + timestamp are on every entry from the first. Rationales are
  summarized at the source; `RATIONALE_CAP = 300` is a defensive backstop.
- **`override_ledger.jsonl`** — one entry per HUMAN gate resolution (gate 1,
  2, or 5): system decision vs human decision + `did_override`. Auto mode
  writes nothing: no human decided, nothing to record.
- Ledger writes are intentionally NOT exception-shielded — errors are never
  swallowed, per doctrine. A falsy run_id becomes JSON null, never a crash.

**Attempts-vs-completions** (`cost_meter.record_attempt`, added this chunk
for cost-per-run honesty): each door records an attempt BEFORE invoking the
SDK; `record_call` fires only after the stream is consumed. So
attempts ≥ calls, and the gap is exactly the calls that fired but never
completed (the Step-16 transport-retry path, previously invisible).

**The live defer proof:** run `handfeed3-20260707T183101Z` wrote the ledger's
first (and still only) entry — verdict `defer`, substrate `cavity_2d`,
rationale: the QoI is peak vorticity, a spatial velocity-gradient reduction
the substrate cannot compute (only volAverage/min/max/volIntegrate of written
fields), "fundamentally unextractable by this instrument." Verified on disk:
`memory/fidelity_ledger.jsonl` is exactly 1 line; `override_ledger.jsonl`
does not exist (no human gate has resolved since the writer landed — the
absence is itself correct behavior).

### 2.3 Chunk 3 — the FAST merge gate (`harness/run_harness.py`)

The deterministic battery over the Step-6 fidelity-gate case set, copied
in-repo with answer keys to `harness/cases/cases.json` (16 cases).

- **The two-door constraint forced the direct `call_stage_model` path.**
  The battery runs each case through `harness/fidelity_case_runner.py`: the
  frozen stage-3 `SYSTEM_PROMPT` (imported from `stages.stage3_fidelity_gate`,
  the single source — never copied) + the case's OWN
  substrate/envelope/experiment, exactly as the spike's scorer did. Ratified
  design: NOT through `stage3_fidelity_gate.run()`, because `run()` hardcodes
  `CAVITY_2D_CONTRACT` (14 of 16 cases can't flow through it) and appends to
  the fidelity ledger; and the two-doors ruling forbids opening a third door,
  so the runner reuses the `model_call` door directly. Calls are BARE (no
  `run_id`) so a battery run leaves no dirs under `runs/`; consequence
  disclosed: `ack_run_id` is schema-required but its value unchecked here.
  RULE-1 tripwire carried from the spike: an assert proves the answer key's
  `right_instrument` string never entered the serialized model input.
- **Hard-gate cases 1/6/16** — HUMAN-selected (at the chunk's Part-3 stop,
  2026-07-07, explicitly not auto-selected): clean-trust case 1 and
  clean-defers 6 and 16, zero historical misses across the spike's v1 and v2
  scored runs, wide physics margins. ALL must return their exact `true_label`
  or FAST is **RED and exits 1** — the gate bites. GREEN exits 0.
- **Watch cases 3/4/13** — boundary-sensitive flippers, recorded and warned
  on a miss but NEVER turn FAST red (verdicts are model judgments; a
  must-pass-all battery would go red on model noise, not real regressions).
  Provenance: 13 flipped refine→trust under the frozen v2 prompt (the
  archetypal flipper); 3 flipped trust→refine under v2; 4 flipped
  trust→refine across prompt versions v1→v2.
- **The Hagen-Poiseuille cost-routing trap**
  (`harness/cases/trap_hagen_poiseuille.json`) is REGISTERED in both targets
  with an explicit SKIP — "pending: analytic tier not built (Step 12)" — so
  it can never be silently absent. The case's point is ROUTING, not physics:
  a well-built gate must send fully developed laminar pipe flow (exact
  closed-form answer) to the analytic tier, never to CFD; when the analytic
  tier exists, scoring is BOTH the label AND `right_instrument`.
- **HEAVY target** (`--mode heavy`): all 16 cases, full label scoring, on
  demand — not the merge gate.
- **Ledger-silent invariant, checked in-band:** the battery must write NO
  production ledger entry; the cost report's LEDGER ACTIVITY line is the
  proof and must read 0/0 every battery run (computed as a count delta via
  `ledgers.count_entries`).
- Cost report printed + written to `harness/last_run.json` — OVERWRITE,
  deliberately: the filename means "the latest run"; `runs/` stays the only
  append-only evidence store.

Latest FAST run on disk (2026-07-09T16:04:48Z, the 18.7 pre-close run):
GREEN, hard-gate 3/3, watch miss on case 13 (recorded, non-blocking), 6
calls, 0 rejects, ledger delta 0/0.

### 2.4 Chunk 4 — the kill-rate battery (HEAVY)

**`harness/survival_counter.py`** — deterministic Python, zero model calls,
disk is ground truth. From a run dir it computes:
`deep_verify_kill_rate = discards / initial_survivor_count` (from
`stage1/reflection_reviews.json`) and `k = len(survivors.json)`. The two
legitimate zero-survivor raises are distinguished by file-presence signature
(both verified against the diag4a dirs):

- `reflection_reviews.json` present, `reflections.json` absent →
  `reflect_on_pool` raised after writing its evidence: k=0, reason
  **`deep_verify_discarded_all`**.
- `reflections.json` present, `survivors.json` absent → `filter_survivors`
  raised: k=0, reason **`all_known_at_filter`**.
- NO `reflection_reviews.json` → the run died before reflection completed
  (arXiv/transport failure or killed from outside) → **ABORTED**, k=None —
  never a valid k=0, never averaged into a distribution.

**Validation — ALL MATCH:** `survival_counter.py --validate` recomputes every
`runs/diag4a-*` dir and cross-checks the diagnostic's own numbers in
`harness/diag4a_reference/diag4a_analysis.json`: kills 44/100/62/88%,
k=3/0/3/0 — every scored dir matches, every non-scored dir classifies
ABORTED. Exit 0 only on ALL MATCH.

**The driver rescue:** the chunk-4a driver had lived in the session
scratchpad, NOT the repo. It was rescued into `harness/diag4a_reference/`:
`diag4a_driver.py`, `diag4a_analysis.json`, `diag4a_progress.txt`, plus the
disclosed `diag4a_driver.log`.

**`harness/killrate_battery.py`** (launched via
`run_harness.py --mode killrate`):

- **Two domains**, verbatim from the rescued driver — SAME ("mean-flow
  structure and vortex strength in laminar lid-driven cavity flows") and ALT
  ("secondary corner eddies and their dependence on Reynolds number…") — with
  N repeats EACH (default N=2, the proving size). The battery samples both
  domains symmetrically where the diagnostic itself had run a lopsided 3
  same + 1 alt. The variance is the point (the diagnostic saw k=3,0,3 on the
  same domain).
- **Memory comparability pin:** every run's `stage1/retrieved_memory.json`
  md5 is checked against `373c886b` (verified identical across all nine
  diag4a dirs); a differing run is flagged `non_comparable` and EXCLUDED from
  the per-domain distributions, reported separately.
- **Exception/abort tolerance:** after every attempt the survival counter
  reads the run dir — disk, not the exception message, classifies it. ABORTED
  → relaunched up to `MAX_RELAUNCHES=2`, never recorded as k=0; scored
  (including the two zero-survivor raises) → a real data point. An exception
  AFTER `survivors.json` was written keeps the disk-read k with an honest
  note. The driver's 180 s inter-run sleep (arXiv courtesy) is kept.
- **Orphan-safe run-id minting:** every launch mints
  `killrate-<fresh-UTC-timestamp>-<slot>`, so relaunches and the debris of
  killed batches can never collide with or overwrite an existing run dir.
- **Model pins recorded** in every results file (`current_model_pins()` reads
  the live modules), so a post-18.7 run can never be silently compared
  against an earlier-pins run. `--dry-run` prints the full plan, pins, and
  cost estimate without firing ideation.
- Same ledger-silent invariant (ideation never reaches stage 3 or a human
  gate; delta must be 0/0). Results overwrite `harness/killrate_last_run.json`.

### 2.5 The standing rule + step close

**Standing rule now in force: no change merges without a GREEN FAST harness**
(hard-gate 1/6/16 pass). HEAVY/kill-rate is an on-demand instrument, never a
merge blocker.

Close (commit **`74e0ecd`**, 2026-07-07): FAST GREEN exit 0; survival
`--validate` ALL MATCH; 146/146 tests; fidelity ledger 1 line / override
ledger absent; snapshot `checksums_after_step16_6.txt` (78 files — verified;
`.gitignore` in by carried ruling, `journal.jsonl` out). Disclosed close
mechanics: `.gitignore`'s `cases/` anchored to `/cases/` (the unanchored
pattern was silently ignoring `harness/cases/`); `harness/last_run.json` and
`killrate_last_run.json` marked evidence-class. Zero source/test changes in
the close itself.

Carried out of 16.6 (journal): the full kill-rate BASELINE (5×2=10 runs,
~10–12 h) deferred to post-18.7 and must run on post-18.7 pins (that day's
pins recorded: Sonnet=`claude-sonnet-4-6`, Opus=`claude-opus-4-8`,
Haiku=`claude-haiku-4-5-20251001`); a live 4-run PROVING batch (2×2, today's
pins) is the human's to launch; S2 zero-hit misreport still pending
(17-fix-B); gates 1/2 "override" is a weaker signal than gate 5's (note for
Step 24); ledger writes deliberately not exception-shielded.

---

## 3. Step 18.7 — model tiers (two chunks + two scored batches)

### 3.1 Chunk 1 — the per-stage reject gauge

`cost_meter` gained `record_stage_call` / `record_reject` (model_call door
only — `call_stage_model` is the one point where both completion and stage
are known; web_search calls carry no stage_name and stay door-only, by
design). A REJECT = a COMPLETED call whose output failed schema or
extra_validator and is being re-asked — invisible in the attempts−calls gap
(that gap is mid-stream transport failures), which is exactly why the counter
exists. Surfaced as the REJECTS line (per-stage
`{calls, rejects, reject_rate}` + total) in both harness reports, and as a
per-run `reject_stats` delta in every kill-rate record.

**The format-not-judgment finding:** what the gauge measures is output-FORMAT
compliance, not judgment quality. Live evidence on disk: the Sonnet proving
batch ran 197 stage-attributed calls with **0 rejects**; and the Haiku
baseline's RE-ASK lines (`harness/baseline_haiku.log`) show raw replies that
are sound, well-grounded review judgments — correctly spotting an
off-topic-citation flaw, correctly grounding a novelty verdict in R1 —
written as prose before a fenced JSON block, so the parse fails while the
judgment inside is fine.

### 3.2 Chunk 2 — the downgrade (commit `7f9c112`, 2026-07-08)

The pin-flip half, mechanism verbatim from the commit and verified against
the live code:

- `stages/reflection_reviews.py`: the single shared `SONNET_MODEL` **split**
  into `HAIKU_MODEL = claude-haiku-4-5-20251001` (the four review call sites:
  initial, full, observation, simulation) + `DEEP_VERIFY_MODEL =
  claude-sonnet-4-6` (the deep-verify call site ONLY) — deep verification
  feeds a deterministic kill with no judgment net downstream, so it held the
  stronger tier.
- `stages/generation_strategies.py`: `SONNET_MODEL` renamed `HAIKU_MODEL`
  (all four strategies downgraded).
- Vestigial `stage1_ideation.SONNET_MODEL` deleted (zero call sites; its only
  reference was the battery's pin record).
- `killrate_battery.current_model_pins()` keys updated + `DEEP_VERIFY_MODEL`
  added.
- **HELD, not flipped:** Stage-2 experiment design on Sonnet (no battery
  watches it); ranking / fidelity gate / thought layer unchanged on Opus.

Verified at commit: 146/146 tests; FAST GREEN (hard-gate 1/6/16, exit 0);
ledgers silent; `--dry-run` constructs cleanly and records the split pins. No
live battery run. Also swept in, disclosed: the previously uncommitted
chunk-1 reject instrumentation (cost_meter, model_call, run_harness,
killrate_battery) and `harness/proving_batch_sonnet.log`.

### 3.3 The Sonnet proving batch (2026-07-08, pre-downgrade pins)

Human-launched, proving size 2×2. From `harness/proving_batch_sonnet.log`:
five launches → four scored + one ABORTED `alt1` (relaunched successfully —
the battery's relaunch machinery witnessed live).

**Sonnet baseline, exact numbers from the log's battery report:**

- same domain: k = [0, 1]; kill rates 0.89, 0.86 (the k=0:
  `all_known_at_filter`)
- alt domain: k = [0, 2]; kill rates 1.00, 0.56 (the k=0:
  `deep_verify_discarded_all`)
- totals: 197 model_call + 44 web_search = 241 calls; wall 17,588.5 s
  including sleeps; scored-run walls 3782.1/2953.9/4452.3/3805.1 s (mean
  ≈62.5 min)
- **REJECTS: 0/197, rate 0.0** across every stage; LEDGER ACTIVITY 0/0

**Finding — reject-rate-is-zero → kill-rate-is-the-signal:** with Sonnet's
reject rate pinned at exactly zero, the reject gauge cannot discriminate
tiers for the downgrade decision; the kill-rate distribution (k and
deep-verify kill % per domain) is the comparison signal.

### 3.4 The multi-kill saga and the ps-over-narration lesson

Before the batch above completed, multiple kill-rate batches were killed
mid-run — including runs mistakenly launched inside Claude Code. Six orphan
dirs are retained as evidence (`runs/` is append-only):
`runs/killrate-20260708T{071140,080953,080956,084008,091050,092608}Z-*`.
Note `080953` and `080956` — same slot, three seconds apart: two batches
running concurrently. This was the **first live firing of the external-kill
sentinel watch item** (CLAUDE.md had recorded "zero live instances so far").
The orphan-safe run-id minting meant none of the debris collided with the
real batch. Lessons on record (journal `step18.7`):

- **ps over narration** — the process table, not any session's narration, is
  ground truth for whether a batch is alive (the Step-16 "sessions and
  Terminal runs have independent lifetimes" invariant, relearned the hard
  way).
- **Long runs go in a plain Terminal, never Claude Code.**
- **`caffeinate` + `python` shows as TWO PIDs = one healthy batch** — the
  signature to look for.

### 3.5 The streamline decision

Rather than a separate Haiku proving batch followed by a separate 10-run
baseline, the batches were **collapsed**: one human-launched 5×2 = 10-run
Haiku batch serves as BOTH the downgrade validation and the locked baseline.
Running batches in **parallel** to make up lost time was rejected — slots run
sequentially with the 180 s arXiv-courtesy spacing (the concurrent-launch
debris of 3.4 being the cautionary evidence). Disk corroboration: no Haiku
proving batch exists anywhere in `runs/`; `killrate_last_run.json` records
`repeats: 5` in a single battery invocation. (The decision itself lives in
this journal and the strategy chat; it is not separately recorded on disk.)

### 3.6 The Haiku baseline (2026-07-09) — HELD, and LOCKED

From `harness/baseline_haiku.log` and `harness/killrate_last_run.json`
(timestamp 2026-07-09T09:52:34Z): 13 launches → 10 scored + 3
ABORTED-and-relaunched. The three aborts, each verified in the log:

1. `same1` attempt 1 — arXiv HTTP **500**, zero-retry path (unlike 429),
   RuntimeError.
2. `same2` attempt 1 — `stage1_reflection_full_h4` **exhausted the 3-attempt
   re-ask loop** (prose-before-JSON every attempt): the reject signal
   crossed from absorbed to fatal, once in 13 launches.
3. `same2` attempt 2 — arXiv HTTP **503**, zero-retry path.

All ten slots resolved; zero unresolved; zero non-comparable (memory md5
matched `373c886b` on all ten).

**Verdict: the downgrade HELD** — same regime as the Sonnet proving batch.

**THE LOCKED HAIKU BASELINE** (the pre-fix "before" number for 17-fix-A —
measure the fix against THIS):

| | k distribution | kill rates | k=0 reasons |
|---|---|---|---|
| same domain | **[0, 0, 0, 0, 1]** | 1.00, 1.00, 1.00, 0.857, 0.90 (**86–100%**) | `deep_verify_discarded_all` ×3, `all_known_at_filter` ×1 |
| alt domain | **[2, 1, 1, 1, 0]** | 0.75, 0.90, 0.90, 0.70, 0.80 (**70–90%**) | `all_known_at_filter` ×1 (alt5) |

- **Reject rate: 21/527 = 0.04** overall, concentrated in Reflection
  full-review (`full_h4` 4/15 = 0.267, `full_h2` 3/13 = 0.231, `full_h6`
  2/11 = 0.182, `full_h7` 2/12 = 0.167; deep-verify and initial review: zero
  rejects everywhere).
- Totals: 527 model_call + 114 web_search = 641 calls; battery wall
  34,168.4 s; **scored-run mean ≈ 2,921 s ≈ 48.7 min** — ≈22% faster than
  Sonnet's ≈62.5 min mean (per-call latency, not fewer calls).
- LEDGER ACTIVITY 0/0.
- Haiku roughness, carried as a watch item: the same domain leaned
  total-kill — 3 of 5 runs discarded ALL candidates at deep verification
  (e.g. "all 10 candidates were discarded (0 at the initial review, 10 on
  fundamental flaws at deep verification)").

### 3.7 Step close (commit `a4dd853`, 2026-07-09)

Pre-close verification: pins unchanged since `7f9c112`; FAST GREEN
(hard-gate 1/6/16, exit 0; watch 13 miss recorded, non-blocking); survival
counter `--validate` ALL MATCH; ledgers fidelity=1 / override absent;
146/146 tests. Artifacts: `checksums_after_step18_7.txt` (78 files — verified,
same coverage as 16.6), journal milestone `step18.7`, and
`harness/baseline_haiku.log` committed as batch evidence per the
`proving_batch_sonnet.log` precedent. **Zero source/test/pin changes** in the
close. `a4dd853` is the clean restore point.

**The four carried watch items** (journal `step18.7`, verbatim in substance):

1. External-kill sentinel fired for real (first live instance); orphan dirs
   retained; plain-Terminal / two-PIDs lesson (§3.4).
2. Haiku is slightly rougher at Reflection full-review than Sonnet: same
   domain leaned total-kill (3/5 all-discarded), and one run's re-ask
   exhaustion turned a reject fatal (1 in 13 launches). Carry into 17-fix-A:
   watch whether the fix also cleans up these roughnesses.
3. The odd transport error "Claude Code returned an error result: success"
   did NOT recur (0 occurrences this batch) — de-escalated, note if it
   returns.
4. arXiv 500/503 aborts with zero retry (unlike 429) — 2 of the 3 batch
   aborts; a known unretried path.

---

## 4. Where this leaves the system

16.6 and 18.7 both closed with snapshots. The instruments exist and are
proven: FAST merge gate (standing rule in force), two auto-logging ledgers,
cost meter with per-stage reject stats, survival counter + kill-rate battery
validated ALL MATCH and exercised through two live scored batches. The pin
map is the downgraded one and it HELD. The locked Haiku baseline is the
"before" number. Next: **17-fix-A** — the coupled Generation/deep-verify fix
from the chunk-4a diagnostic, measured against that baseline. See
`docs/context_after_18.7.md` for the handoff.
