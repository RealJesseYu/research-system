# Milestone 17-CLOSE — Step 17 CLOSED on Run A + Run B evidence

Date: 2026-07-12/13 (doc-only close session; every number re-derived from disk —
`runs/20260712T194452Z/`, `runs/20260712T212952Z/`, `memory/journal.jsonl`,
`memory/fidelity_ledger.jsonl`, `memory/override_ledger.jsonl`, git. Disk-vs-dictation
mismatches are flagged in the asterisk list.)

## Rulings R-C1..R-C6 (recorded as ruled in the strategy chat)
- **R-C1 — log convention** (recorded; not build-shaped this session).
- **R-C2 — tfidf/proximity drift test**: landed in `c9b8837`
  (`tests/test_tfidf_drift.py` captures both TfidfVectorizer constructor-arg sites).
- **R-C3 — judge-prompt id-hygiene**: landed in `c9b8837` (ids only, never
  positional/order words, in RANKING_SYSTEM_PROMPT_V2 + DEBATE_JUDGE_SYSTEM_PROMPT).
  Motivation on record: the position-2 watch at **6/6 verdicts across 3 split
  debate matches** (see milestone_17E.md).
- **R-C4 — gate-1 near-tie Elo + overview display**: landed in `c9b8837`
  (display-only, never-raise, human mode).
- **R-C5 — Step-18 sizing**: the sizing trigger FIRED on the measured 17-E witness
  cost (**124 calls / 101.7 min mean per slot**) → **4 runs per arm**; the
  parallel-arms ruling is to be finalized at 18-prep.
- **R-C6 — strip_fence single-fence prose tolerance**: landed in `c9b8837` on the
  frozen smoke6 crash fixture.

## Supervised obligation — split-witnessed across two runs

### Run A — `20260712T194452Z`, human mode (19:44:52Z → 21:19:35Z, 1h34m43s ≈ 1h35m)
90 model inputs assembled (90 transcripts = 77 model_call + 13 web_search), all logged
calls attempts=1.
- **Rank-2 pick demonstrated**: gate 1 human answer '2' → h7 selected (rank 2 of 4);
  recorded in the new `memory/override_ledger.jsonl` as system "select rank 1" vs
  human "select rank 2", did_override=true.
- **Live loop-back**: pass 1 verdict defer (vorticity sub-domain circulation QoI not
  extractable) → skipped_defer → thought triage setup_error, decision back_to_design,
  human accepted → payload reduced to {domain, chosen_hypothesis, prior_thought},
  re-entered at stage 2.
- **First-ever refine verdict**: pass 2 redesigned onto min(Ux) and drew **refine**
  ("mesh-independence explicitly not claimed… admitted indirect proxy") — the first
  refine in `memory/fidelity_ledger.jsonl` across the project's entire history (all
  prior verdicts defer).
- **Honest halt on colima-down**: refine → execution attempted → `STAGE4
  halted_synthesis at run 1 of 3: cannot build: blockMesh failed (exit 1): Cannot
  connect to the Docker daemon` (Colima socket down). Zero solver runs; thought triage
  setup_error, decision more_data, human accepted → run ended honestly
  (`completed_more_data_unwired`, 9 history entries, run_record journaled). Two
  learned summaries journaled (substrate can't do vorticity/sub-domain integrals;
  verify the container runtime before dispatching).

### Run B — `20260712T212952Z`, auto mode (21:29:52Z → killed ~00:06:15Z, 2h36m23s)
144 model_call + 23 web_search calls completed; 168 transcripts on disk (the 168th,
`0145_stage2_experiment_design.json`, is the pass-3 stage-2 input written before the
call fired — orphaned by the kill; write-before-call behaved as designed).
- **All gates self-resolved through 2 full passes**: gate 1 auto-selected rank 1,
  gates 2/5 auto; both passes defer → skipped_defer → back_to_design (auto-accepted).
- **First live Evolution gate-1 win**: gate 1 selected **ev2 (rank 1 of 5) at Elo
  1258.27** — a tournament-ranked Evolution variant chosen as the run's hypothesis.
- **Memory loop witnessed**: Run B's generation transcripts carry Run A's two learned
  summaries verbatim in the leads block:
  - "The cavity_2d solver requires a running Docker/Colima daemon; verify the
    container runtime is up before dispatching the Re 200-1000 sweep, then re-execute
    the identical spec."
  - "This substrate cannot compute vorticity or sub-domain circulation integrals; a
    circulation-ratio QoI must be redesigned around a substrate-native whole-domain
    proxy (e.g., min(Ux) or stream-function extrema) or routed to an external
    post-processing pipeline before any Re-sweep can test secondary-vortex emergence."
- **KILLED EXTERNALLY at ~00:06Z mid-pass-3**: last log line is the pass-3 gate-1
  schema check; no run-ended line, **no run_record journaled** — the first live
  instance of the watched external-kill scenario (CLAUDE.md watch item: "zero live
  instances so far — build it only when one actually occurs"; the build condition is
  now met). Run B's two learned summaries (pass 1 and pass 2) WERE journaled before
  the kill.
- **Root cause = launch venue, a strategist process error**: Run B was launched as a
  Claude Code background task instead of a plain Terminal. **The
  plain-Terminal-under-caffeinate rule is restored ABSOLUTE for ALL runs, including
  supervised runs.**

## Carried debts → Run C (2026-07-13 AM, plain Terminal, human mode)
1. **Executed solver path under the post-17 pipeline** (Run A reached refine but
   halted on colima-down; Run B's passes drew defer; no post-17 supervised run has
   yet executed the solver).
2. **Stage 6 real-pipeline paper + paperlint outing** (Step 22's owed supervised
   real-run outing).

## AMENDED RULING — checksum snapshot moves to 18-prep
The checksum snapshot that would normally be this close's FINAL write moves to
**18-prep, after Run C**. Rationale: the pin's semantic target is Step-18
comparability, and the `373c886b` memory-md5 era ended BY DESIGN when Runs A and B
journaled learned summaries (journal md5 is now `d708f701`; journal +5 lines: Run A's
2 learned summaries + run_record, Run B's 2 learned summaries). A snapshot cut tonight
would pin a state Run C is about to change.

## Step 17: CLOSED on this evidence.
Generation (4 strategies) + Reflection (6 reviews) + Elo tournament + Evolution +
meta-review/feedback/iteration loop are all live and witnessed; the supervised system
demonstrated human override, live loop-back, refine, honest infrastructure halt,
auto-mode self-resolution, variant selection at gate 1, and cross-run memory — with
debts and the venue rule recorded above.

## Asterisks (dictation vs disk)
1. Run B call dictation "144+23" matches logged calls exactly; the transcript count is
   168 because the orphaned in-flight pass-3 input is also on disk.
2. Dictation "first live firing of the external-kill sentinel": per CLAUDE.md the
   sentinel is a WATCH-LIST item not yet built; what fired is the watched condition's
   first live instance (kill leaving no run_record). Wording corrected here.
3. Run A duration derived as 19:44:52Z (run id) → 21:19:35Z (final log/journal write):
   1h34m43s, vs dictated 1h35m. Run B: 21:29:52Z → 00:06:15Z log mtime = 2h36m23s, vs
   dictated 2h36m; kill time "~00:06Z" matches.
4. ev2's gate-1 Elo on disk is 1258.2747 (dictated 1258.3, rounding).
5. Transport shape note: Run A also absorbed max-turns TRANSPORT-RETRYs on
   stage1_meta_review (×1) and stage5_thought_layer (×1); Run B on
   stage1_tournament_debate_turn2 (×1) and stage1_meta_review (×2). All recovered,
   attempts=1 after retry — the max-turns watch (milestone_17E.md) extends to Opus
   thought-layer and Haiku debate calls.
