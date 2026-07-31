# NEXT — the ordered list

**One screen, one order, one thing at a time.** Everything else is reference:
`docs/roadmap_capability.md` (what makes impossible tasks possible),
`docs/roadmap_status.md` (what broke and got fixed), `docs/comparison_protocol.md`
(the experiment).

**Do these in order. Do not start an item below a gate until the gate resolves.**

Last updated 2026-07-31 · HEAD `476de8a` · suite 2637 passed / 1 skipped

---

## PHASE 1 — free. No compute. Do all four this week.

- [ ] **1.1 Rule: push `run-artifacts`?** It is built, backfilled, cleaned of
      third-party content (9.8 MB, 1088 files, 15 commits) and sitting local. My
      audit is clean. Today every study's output exists on exactly one laptop.
      **Decision only — the work is done.**
- [ ] **1.2 Rule the two memos.** `docs/memo_transport_retry_experimenter.md` and
      `docs/memo_succeeded_semantics.md`. Both end in a proposal by design and are
      waiting on you. Neither blocks anything; both are cheap to close.
- [ ] **1.3 Prior-art check on the architecture itself.** ~1 hour. The ideation
      apparatus is a documented AI Co-Scientist reimplementation; the assembled
      system (free director, divisible budget, recursion, no-model wall, carry bus)
      has **no prior-art check on record**. This gates any novelty claim you make
      anywhere, including the paper in 4.3.
- [ ] **1.4 Add a commit line to the standard build prompt.** *"Commit your work
      before you stop, and run `git status` to confirm nothing is left untracked."*
      Three sessions in two days finished green without committing; once the main
      file was untracked. This is now a recurring failure, not an incident.

---

## PHASE 2 — settle experiment 2. ~$20, then a decision.

- [ ] **2.1 Run arm B.** One Claude Code session, the frozen goal-2 string, cost
      measured:
      ```
      mkdir -p ~/exp2-armB && cd ~/exp2-armB
      GOAL2=$(sed -n 's/^GOAL2="\(.*\)"$/\1/p' ~/research-system/run_comparison.sh)
      [ ${#GOAL2} -eq 1144 ] || echo "GOAL STRING WRONG — STOP"
      claude -p "$GOAL2" --dangerously-skip-permissions --output-format json > armB.json
      ```
      It is the only thing that can settle experiment 2 outright: if one agent
      thinks to check Pavement ME, the falsifier fires regardless of arm C.

- [ ] **GATE A — read arm B, then choose ONE:**
      - **arm B is weak** → experiment 2 stands as a partial result; write it up
        from what exists and move to Phase 3. **Do not re-run arm C.**
      - **arm B is strong** → arm C's re-run becomes the deciding evidence. Budget
        it at ~$300 (see the cost note below) and disclose in the write-up that
        arm C had two attempts and arm B one.

---

## PHASE 3 — the capability path. This is the actual goal.

- [ ] **3.1 Run ONE real design-class study.** Not the gearbox toy — a genuine
      coupled design with subsystems that constrain each other. This is the
      deliverable you care about AND it reads the Tier-1 gate at zero marginal
      cost, so **do not buy a separate probe for the gate.**
      Budget ~40M tokens ≈ **$80**. Watch: `venv/bin/python3 -m liveview` (now
      starts itself).

- [ ] **GATE B — did a conflict fire, on real coupled work?**
      - **YES** → build **T1.1–T1.4**: constraints as first-class objects,
        re-check on edit, progressive commitment, conflict-as-decision.
        `docs/roadmap_capability.md` Tier 1.
      - **NO, with units well populated** → the constraint direction does not pay
        at this scale. Say so, and rethink before spending on Tier 2.

- [ ] **3.2 T2.1 — the domain representation agents EDIT rather than describe.**
      Only after Gate B says yes. Geometry, interfaces, load paths, budgets,
      tolerances as a structured object. **This is the real research and the item
      that decides whether "build a robot" is reachable.** Months, not days.

---

## PHASE 4 — contingent. Do not plan past Gate B.

- [ ] 4.1 **T2.2** long-horizon credit assignment · **T3.1** fan-out is built and
      used once · **T3.2** intermediate signal from a running move.
- [ ] 4.2 **The wet-lab regime.** You have lab access, which makes discovery-class
      goals reachable — but an assay is a move that takes days. That is
      `--resume-study` plus the blocker channel, both of which exist. Design it
      only after Gate B.
- [ ] 4.3 **The architecture paper.** Thirty findings in `docs/` are internal
      records, not research: no framing, no baseline, no positioning, and most are
      n=1. Needs 1.3 first.

---

## Standing numbers

- **Cost: $1.98 per million reported tokens** (measured 2026-07-31, up from $1.30).
  The turn-counter fix doubled real per-move work. **A run costs roughly 2x its
  token budget in dollars.**
- Always pass `--token-budget` and `--director free`. `--max-moves` now derives
  from the budget; omit it.
- Long runs from a plain Terminal under `caffeinate`. Never from a session.
- Never `git add -A`. Run `pytest tests/` one suite at a time.
