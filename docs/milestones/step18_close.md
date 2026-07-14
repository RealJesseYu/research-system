# Milestone Step-18 CLOSE — the compute dial set on a measured two-arm curve

Date: 2026-07-14 (doc-only close session; ZERO live model/API calls. Every number
re-derived from disk — `harness/killrate_18_T1b.json`, `harness/killrate_18_T2b.json`,
`harness/killrate_18_T3b.json`, `harness/validation_batch_18.json`, the `harness/
witness_18_*.log` witness logs, `harness/witness_validate18.log`, `memory/
fidelity_ledger.jsonl`, and git. Disk-vs-dictation mismatches are flagged in the
asterisk list at the end.)

Question Step 18 was built to answer: **how many ideation rounds is the compute dial
worth?** Two arms, one variable (round budget), measured for both survivors-produced
and downstream survival.

## MEASUREMENT — the two-arm design and the re-run that made it clean

- **Two arms, one dial.** Arm 1 = 1× rounds (`--repeats 2 --rounds 1`); arm 2 = up-to-4×
  rounds (`--repeats 1 --rounds 4`, the iteration controller self-terminating on the
  MAX_SURVIVORS count cap before the budget is spent). Same domains, same pins, same
  code — the only moved variable is the round budget.
- **Sunday's first attempt was bug-truncated.** The first pass (launched at HEAD
  `cede65da`, "18-PREP state") is preserved as `harness/killrate_18_T1.json /
  _T2.json / _T3.json` but is NOT the scored record: it carried an OpenAlex **HTTP 400**
  grounding-transport failure — one per file in `killrate_18_T2.json` and
  `killrate_18_T3.json` — that truncated slots (e.g. T2/alt1 reached round 3 under the
  fault). Combined with an **18.5 comparability confound** (the memory-reach extension,
  commit `4a9312c`, altered Stage-2 substrate under the runs), the Sunday batch could
  not be compared arm-to-arm.
- **Full Monday re-run at HEAD `934142d`.** The scored record is the "b" batch —
  `killrate_18_T1b.json / _T2b.json / _T3b.json`, all recording
  `launch_git_head` `934142d7` ("QUEUE-14"). **Pin `073ff57e`** on all six slots
  (`expected_memory_md5` and the per-attempt `memory_md5` agree, `comparable: true`
  throughout). **Zero HTTP-400s post-fix** — no `HTTP 400` string appears in any b-file;
  the grounding-transport failure did not recur.

## RESULTS — the curve

**1× arm** (`killrate_18_T1b.json`, 4 slots):

| slot | k | rounds_completed | calls (total) |
|------|---|------------------|---------------|
| same1 | 2 | 1 | 66 |
| same2 | 2 | 1 | 74 |
| alt1  | 3 | 1 | 85 |
| alt2  | 2 | 1 | 90 |

k = **2, 2, 3, 2 → mean 2.25**; mean cost **78.8 calls/slot** (≈79).

**4× arm** (`killrate_18_T2b.json` + `killrate_18_T3b.json`, 4 scored slots):

| slot | k | rounds_completed | calls (total / model_call) |
|------|---|------------------|-----------------------------|
| T2b/same1 | 4 | 2 | 169 / 145 |
| T2b/alt1  | 3 | 2 | 213 / 183 |
| T3b/same1 | 4 | 1 | 83 / 71 |
| T3b/alt1  | 4 | 2 | 169 / 145 |

k = **4, 3, 4, 4 → mean 3.75**; `rounds_completed` = **2, 2, 1, 2**; mean cost
**158.5 calls/slot total** (136.0 model_call-only) — see asterisk 1 on the dictated
"~144".

- **Self-termination at ≤2 rounds is universal** across every clean 4× completion: no
  post-fix (Monday) 4× slot ran past 2 rounds despite a 4-round budget; the controller
  ends on `survivor_count_cap` or `round_budget_exhausted` (both witnessed in
  `witness_18_T3b.log` / `witness_18_T1b.log`). Counting all eight four-round
  slot-attempts ever run, the sole attempt to reach round 3 is the Sunday
  pre-fix, HTTP-400-flagged T2/alt1 — not a clean self-termination (asterisk 2).
- **One slot exception-flagged**, per ruling **R-18-D1**: `T2b/alt1` carries
  `"Exception: Claude Code returned an error result: success"` — a transport wrap that
  fired *after* scoring (k=3 was already produced; `comparable: true`). The flag travels
  with the data downstream (it reappears as `[EXC-FLAGGED]` in validation).

## RULING R-18-1 — ideation default rounds = 2

**The measured knee.** The dial buys survivors from 2.25 → 3.75 for roughly 2× the
per-slot cost, and the controller *never once* chose to spend a 3rd round on this
problem class. `rounds=2` is set as the ideation default: it is where self-termination
lands and where the marginal round stops being taken.

The quality leg of the case (not just survivor count): larger pools with Evolution
variants riding at top Elo ranks (e.g. `witness_18_T1b.log` final_elo shows `ev1`/`ev2`
above the base pool; `witness_18_T3b.log` shows `ev1` winning to rank 1), and
meta-review feedback visible in the round-2 generation/reflection prompts. Rank
robustness, not merely headcount, is what the second round buys.

## VALIDATION-SURVIVAL — the floor, and what it reveals

The 8 rank-1 winners (4 from the 1× arm, 2+2 from the two 4× batches) were driven
through **stages 2→5 in auto mode, single-pass, no loop-backs**
(`harness/validation_batch_18.json`, `witness_validate18.log`; `reports_consumed` =
the three b-files):

| arm | slot | hyp | verdict | solver | stage5 | survived |
|-----|------|-----|---------|--------|--------|----------|
| T1 | same1 | ev1 | defer  | 0/0 | setup_error → back_to_design | no |
| T1 | same2 | ev2 | refine | 0/0 (halted_synthesis) | setup_error → back_to_design | no |
| T1 | alt1  | ev2 | defer  | 0/0 | setup_error → back_to_design | no |
| T1 | alt2  | ev2 | defer  | 0/0 | setup_error → back_to_design | no |
| T2 | same1 | h5  | refine | **3/3 executed** | out_of_envelope → more_data | no |
| T2 | alt1  | h10 `[EXC-FLAGGED]` | defer | 0/0 | setup_error → back_to_design | no |
| T3 | same1 | ev1 | defer  | 0/0 | setup_error → back_to_design | no |
| T3 | alt1  | ev1 | defer  | 0/0 | setup_error → back_to_design | no |

- **Survival 0/4, 0/2, 0/2 — both arms 0.00** (`per_arm` fractions all `0.0`).
- **Verdicts: 6 defer / 2 refine.** The one refine that reached the solver (T2/same1 h5)
  **executed 3/3 converged runs** and still ended honestly in `more_data` — the trust
  gate let it in as an admitted proxy, and the thought layer refused to claim survival on
  a proxy QoI.
- **FINDING.** Tournament selection optimizes *rhetorical fitness* — the winners are the
  most persuasive hypotheses, not the most executable. Nothing upstream of Stage 3 knows
  the substrate's extraction contract, so the rank-1 winners overwhelmingly demand QoIs
  the wrapper cannot produce (streamfunction topology, sub-domain circulation,
  saddle-point contours — see the six `validate18-*` rationales in
  `memory/fidelity_ledger.jsonl`). **The fidelity/trust gate was the only component not
  fooled.**
- **CAVEAT, disclosed.** At a 0.00 floor the survival metric **cannot discriminate the
  arms** — it tells us the selection objective is misaligned with executability, not
  which round budget is better. The arm decision (R-18-1) rests on the survivor/rank
  curve, not on survival.

## DEBT — Stage-6 paper debt re-carried

The Stage-6 paper + paperlint obligation carried from Run C did **NOT** convert this
session: validation was stages 2→5 only, `paper_written: false` on all 8 runs. It is
**re-carried** to the scheduled supervised **human-mode** run (ledger #4-candidate,
owner-selected domain, envelope-checked before launch).

## RULINGS ENTERING THE RECORD

- **R-18-1** — ideation default `rounds=2` (above).
- **R-18-D1** — an exception that fires after a slot's k has been scored is recorded as
  an `exception` flag on that slot; the slot stays `comparable` and its flag travels with
  its data into every downstream consumer (witnessed: `T2b/alt1` → validation
  `T2/alt1 [EXC-FLAGGED]`).
- **R-18-2 — selection-objective triad.** Novelty / impact / alignment become
  separately toggleable selection criteria. Impact + alignment rubric edits scheduled
  **Thursday, post-card**; the droppability question is merged into **Step 35** task
  typing.
- **AMENDED-PLAN designations (owner-approved):**
  - buffer-day **priority ladder** adopted;
  - **add-on 3a (multi-QoI)** promoted to **Week 2**;
  - **corpus-collection standing rule** — fidelity/override ledgers, failure records,
    and expert amendments are retained proprietary assets, **never published raw**;
  - post-8/2 queue reordered with the **strategy tournament first**.

## HYGIENE LEDGER (named, dated — 2026-07-14)

1. **Battery abort-classifier misread** (n=1 live): a zero-survivor honest halt
   (`T3b/same1` first attempt, `RuntimeError: … all 1 hypotheses were judged 'known' …
   this run halts here`) was logged by the classifier as an infrastructure death rather
   than a legitimate stage-1 outcome. Characterized; the slot was correctly re-attempted
   (`004733Z`, k=4).
2. **Flaky `test_report_path` in discovery mode** (n=3): intermittent under test
   discovery ordering. Noted, not yet fixed.
3. **Docker guard extension** (caught live at ledger-#3 preflight): daemon-up ≠
   container-up — the preflight guard now checks the container, not just the Colima
   daemon. Directly motivated by Run A's colima-down halt (milestone_17CLOSE).
4. **CLAUDE.md S2-key discrepancy**: documentation-vs-config mismatch on the Semantic
   Scholar key, recorded for cleanup.
5. **S2 API key errand** (free tier, config-only): obtain and wire the free S2 key to
   quiet the recurring HTTP 429s seen throughout the b-batch retrieval
   (`witness_18_T2b.log`). No code change; config only.

## Asterisks (dictation vs disk)

1. **4× arm cost.** Dictated "~144 calls/slot"; disk per-slot **totals** are
   169 / 213 / 83 / 169 → **mean 158.5 total** (136.0 model_call-only). The 1× figure
   "~79" matches disk total mean 78.8. Recorded from disk; ~144 is closest to the
   model_call-only-ish middle but is not a clean disk mean — the exact numbers above are
   the record.
2. **"≤2 rounds universal across all 8 four-round slot-attempts."** True for every
   Monday post-fix 4× attempt (`rounds_completed` 2, 2, 1, 2) and for every clean
   self-termination. The one attempt on disk reaching **round 3** is the **Sunday
   pre-fix** `killrate_18_T2.json` alt1, which was **OpenAlex-HTTP-400 exception-flagged**
   — an exception-truncated, bug-batch data point, not a clean self-termination. The
   universality claim is stated over clean completions; the outlier is disclosed here.
3. **Pin note.** All six b-batch slots recorded `memory_md5` `073ff57e` at run time
   (the comparability pin). The on-disk memory md5 has since advanced — the validation
   batch appended the six `validate18-*` fidelity-ledger verdicts — so a fresh md5 of
   `memory/fidelity_ledger.jsonl` no longer reads `073ff57e`. Expected: the pin is a
   run-time invariant, not a frozen-forever file hash.

## Step 18: CLOSED on this evidence.
The compute dial is set at `rounds=2` on a measured two-arm curve (k 2.25 → 3.75,
self-termination at ≤2 rounds universal on clean completions); downstream survival is
0/8 in both arms, which localizes the next problem precisely — tournament selection
optimizes persuasiveness, and the trust gate held the line. Paper debt re-carried;
R-18-2 and the amended-plan designations are on the record.
