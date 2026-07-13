# Days 3–4 — 17-D through Step-17 close (2026-07-11 → 2026-07-13)

Compact narrative, written at the 17-CLOSE doc session from disk plus strategist
dictation. Disk-derivable facts were re-derived; strategy-chat decisions (deadline,
new steps, lanes) are recorded as dictated and marked so.

## 17-D and Step 22, in parallel
17-D (Evolution: four strategies on the Sonnet pin, 2-variant cap, variants through
the full Reflection chain and an in-memory tournament pool) and Step 22 (paper agent:
sidecar-first validation handoff on the Haiku pin, mandatory What-Humans-Must-Validate,
paperlint) were built in parallel git worktrees and true-merged to main as `04d27e8`
and `c957f3b`, build commits preserved verbatim. Union suite 218/218 at the merge.

The 17-D overnight witness PASSED mechanically (4/4 slots, zero relaunches, md5
comparable) with a sobering result: **6 variants emitted, 0 accepted**, zero-accept
tolerance holding 3/3. The mandatory dedup check closed outcome (c) — tf-idf bands for
siblings and genuinely distinct hypotheses interleave, so 0.85 stands as a
near-verbatim detector only, recalibration refused on evidence. same2 drew the first
k=0 since 17-fix-A, arming the parent-pool forensic trigger (any k=0 slot OR ≥2 slots
at k≤1 in the 17-E witness → forensic session before 17-CLOSE). Closed at `db877f7`.

## 17-E: recon reshaped the step, then the build
Recon found the step was not what the book sketched: review 6 was a BUILD, not a wire
(the seam was inert by design); cross-round hypothesis ids are unstable, killing any
naive ranking-stability termination; and battery semantics needed explicit
variants/rounds fields. Built at `41fe473`: meta-review on Opus, per-family feedback
blocks code-appended to Generation/Reflection/Ranking, per-round research overview,
review 6 active-but-advisory on Haiku, iteration controller (ROUNDS=2) inside stage 1.
250/250 offline.

**Witness PASSED and the trigger did NOT fire**: 4/4 slots, zero relaunches, md5
`373c886b` ×4, k = {4,4} same / {4,2} alt. The loop ran live (2 rounds in same1/alt2),
feedback blocks were proven word-for-word in round-2 transcripts, Evolution went 12
emitted / 6 accepted with the first variant debate win and the first rank-1 variant
delivery, and dedup saw its first live customers — zero flags, parent-child max
0.3409. Full record: `docs/milestone_17E.md`.

## 17-CLOSE
Build items landed at `c9b8837` (263/263, FAST GREEN): battery launch-HEAD recording,
variant run-total fields, richer dry-run pins + measured per-round cost lines, judge
id-hygiene, gate-1 near-tie display, strip_fence prose tolerance, tfidf drift test.
Rulings R-C1..R-C6 recorded (R-C5: Step-18 sizing trigger FIRED on measured
124 calls / 101.7 min per slot → 4 runs/arm; parallel-arms finalized at 18-prep).

The supervised obligation was split-witnessed (`docs/milestone_17CLOSE.md`):
- **Run A** (human): rank-2 override at gate 1, live loop-back off a defer, the
  project's **first refine verdict**, an honest halted_synthesis when Colima was down,
  and an honest more_data ending. 90 calls, 1h35m.
- **Run B** (auto): all gates self-resolved for 2 passes, **an Evolution variant (ev2)
  won gate 1 at Elo 1258.3**, and the memory loop closed — Run A's lessons appeared
  verbatim in Run B's generation context. Killed externally at ~00:06Z mid-pass-3.

**The venue error and its rule**: Run B died because it was launched as a Claude Code
background task — a strategist process error, and the first live instance of the
external-kill scenario (no run_record). The plain-Terminal-under-caffeinate rule is
now ABSOLUTE for all runs, supervised included.

Step 17 CLOSED on this evidence, with debts carried to Run C (2026-07-13 AM, plain
Terminal, human mode): the executed solver path under the post-17 pipeline, and the
Stage-6 real-pipeline paper + paperlint. The checksum snapshot was moved by amended
ruling to 18-prep after Run C (the `373c886b` md5 era ended by design when Runs A/B
journaled; journal md5 now `d708f701`).

## Strategy decisions (dictation; not disk-derivable)
- Deadline compressed to **Aug 2** with rulings C1–C6.
- **Step 23 added**: gate-1 auto-chooser.
- **Circuits** conditionally scheduled as the 4th domain.
- **Professor card-review lane opened.**
