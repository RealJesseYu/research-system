# NEXT — the ordered plan

**Owner ruling 2026-07-31: BUILD EVERYTHING FIRST, THEN RUN.** The point is to use
the actual product, not to keep testing a half-built one. Runs are Part 6 and
nothing in Parts 1–5 waits on a run.

Picking up **Sunday 2026-08-02**. Nothing below has been started.

Reference: `docs/roadmap_capability.md` (the impossible-task ladder),
`docs/roadmap_status.md` (what broke and got fixed),
`docs/comparison_protocol.md` (the experiment).

Last updated 2026-07-31 · HEAD `6969b3c` · suite 2637 passed / 1 skipped

---

## PART 1 — THE COMPLETION RULE. The headline change.

**A study MUST NOT produce output until one of exactly three things is true:**

1. **It completely finished the goal.** No "it can't be applied", no "this is not
   useful", no "further work is needed" as a way out. Finished means finished.
2. **It ran out of tokens** — and then it is PICKED UP AND CONTINUED, not written
   up. Output happens after the continuation finishes the goal, not before.
3. **The task is genuinely impossible for the system.** **THIS IS NOT AN EASY
   DEFER.** The bar is deliberately brutal: "impossible" must mean the system
   cannot do it at all, not that it is hard, expensive, slow, or that the agent
   would rather stop. Anything short of that is case 2.

**The diagnosis this comes from, checked 2026-07-31:** the gearbox paper
(`study-20260731T033623Z`) DOES carry the enforced skeleton — `## Bottom line`,
Abstract, What was built, How it performs, How to build it. So the structural fix
landed and the owner still had to dig, and still found nothing usable. **The
problem is not formatting. It is that a paper was produced at all for work that had
not finished the goal.** Do not attempt to fix this with more sections.

- [ ] **1.1 Build the three-outcome gate.** A study ends in FINISHED / OUT-OF-BUDGET
      (→ continue) / IMPOSSIBLE (→ a stated, evidenced impossibility). Only FINISHED
      and IMPOSSIBLE may write a deliverable, and IMPOSSIBLE writes what it proved
      impossible and why — not a paper about what it half-did.
- [ ] **1.2 Make "impossible" expensive to claim.** It must be evidenced and
      specific. The failure mode to design against is the agent reaching for it as a
      polite exit. Consider: what would the system have to have TRIED before the
      claim is admissible.
- [ ] **1.3 Kill the graceful-degradation habit in the writing stages.** Today an
      unfinished study still yields a well-formed document with the shortfall in
      Limitations. Under this rule that document should not exist.

## PART 2 — NO INTERNAL LIMIT MAY DECIDE THE RESEARCH

**Credits, loop counts and ceilings may bound COST. They may never bound the
OUTCOME.** A study stops because it is done or genuinely cannot proceed — never
because a counter ran out and the write-up was easier than continuing.

- [ ] **2.1 Max loops / move ceilings set high enough to be irrelevant**, so the
      only real bound is tokens, and tokens trigger continuation (1.1 case 2) rather
      than a write-up.
- [ ] **2.2 Audit every internal cap for whether it can silently end research.**
      Known live examples to start from: the move ceiling (now derived), the
      per-move token allowance, the 200-turn cap, `MAX_LOOPBACKS`, `MAX_SURVIVORS`.
      Each one: does hitting it end the science, and if so, does it continue instead?

## PART 3 — CONTINUATION. Required by Part 1, and wanted in its own right.

- [ ] **3.1 Continue a study that ran out of budget** — pick up where it stopped and
      carry on to the goal. `--resume-study` exists and is the seam; it currently
      resumes an arc, not an unfinished goal with an output rule attached.
- [ ] **3.2 Continue a study AFTER it has produced a paper.** Give it a new prompt:
      change something, add an experiment, go further. The paper is a checkpoint,
      not a terminus.

## PART 4 — INTERJECTION AND CONTROL. The human in the loop, by choice.

- [ ] **4.1 Interject mid-run.** The director picks a hypothesis or a direction and
      the owner wants a different one — say so, live, and have it take effect.
- [ ] **4.2 Skip or alter a decision with a prompt.** Not only redirect: override.
- [ ] **4.3 Skip verification on demand.** Owner's call, per run or per claim.
      (Note for the build: the wall is what makes a kept number honest, so this
      needs to be a recorded, visible choice — not a silent mode.)

## PART 5 — USABILITY. Making it a product rather than a CLI.

- [ ] **5.1 Front end.** Watch a run in progress properly. `liveview` is the
      read-only core and now autostarts; this is the real surface, and it shares a
      seam with Part 4 — interjection needs somewhere to be typed.
- [ ] **5.2 Easier prompting: the prompts write themselves.** A fully autonomous
      loop where the owner states an aim and the system composes the goal strings,
      rather than the owner hand-writing every one.

## PART 6 — CAPABILITY. What makes the impossible tasks possible.

Full detail and evidence in `docs/roadmap_capability.md`. Tier 0 is DONE and
validated (quantity register, incremental emission, units at 100%).

- [ ] **6.1 TIER 1 — the constraint substrate.** T1.1 constraints as first-class
      objects · T1.2 re-check on edit (the mechanism that makes coupling visible) ·
      T1.3 progressive commitment · T1.4 a conflict is a decision, not a note.
- [ ] **6.2 TIER 2 — the maintained design object.** T2.1 a domain representation
      the agents EDIT rather than describe — geometry, interfaces, load paths,
      budgets, tolerances. **The item that decides whether "build a robot" is
      reachable, and the actual research.** T2.2 long-horizon credit assignment.
- [ ] **6.3 TIER 3 — scale.** Fan-out is built and used once · intermediate signal
      from a running move · **the design must outlive the study boundary** (T3.3 —
      not a duration problem; see the reframe in the capability roadmap).

## PART 7 — SECURITY

- [ ] **7.1 Security and multi-tenancy.** Running generated code is a security
      problem, not cleanup. Before anything is shared or shipped.

---

## PART 8 — THE RUNS. Only after Parts 1–7. Use the finished product.

- [ ] **8.1 Experiment 2, completed.** Includes arm B — **owner ruling: arm B runs
      AFTER the architecture is finished, not before.** The frozen goal string and
      the measured-cost command are in `docs/comparison_protocol.md` and
      `run_comparison.sh`; do not retype the goal.
- [ ] **8.2 Experiment 3** (goal 3, the simulation-driven science attempt, arm C
      only by earlier ruling). Needs `RESEARCH_GPU_BUDGET_USD` set.
- [ ] **8.3 As many experiments as the remaining credits allow.** Produce as many
      real results as possible on the finished product.

---

## Standing numbers and rules

- **Cost: $1.98 per million reported tokens** (measured 2026-07-31, up from $1.30 —
  the turn-counter fix doubled real per-move work). **A run costs roughly 2x its
  token budget in dollars.**
- Always `--token-budget` and `--director free`; `--max-moves` derives, omit it.
- Long runs from a plain Terminal under `caffeinate`, never from a session.
- Never `git add -A`. `pytest tests/`, one suite at a time.
- **Every build prompt ends with: commit your work before you stop, and run
  `git status` to confirm nothing is left untracked.** Three sessions in two days
  finished green without committing; once the main file was untracked.

## Carried, small, unruled

- Push `run-artifacts`? Built, backfilled, cleaned, audited clean, sitting local —
  every study's output currently exists on one laptop.
- `docs/memo_transport_retry_experimenter.md` and `docs/memo_succeeded_semantics.md`
  both end in a proposal awaiting a ruling.
- Prior-art check on the architecture itself — no check on record, and it gates any
  novelty claim including the architecture paper.
