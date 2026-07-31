# Capability roadmap — what would make previously-impossible tasks possible

**Written 2026-07-30**, after the experiment-2 post-mortem. The checklist in
`docs/roadmap_status.md` tracks *fixing what broke*. This file tracks the
separate question the owner is actually building toward: **what would let this
system do things no single strong agent can do at all** — "design this robot",
"build this house with its plumbing", "solve this disease".

Every item is marked **MEASURED** (evidence on disk names it) or **REASONED**
(it follows from the analysis, nothing has tested it). Do not let a REASONED item
harden into a fact — that is the failure this project keeps catching.

---

## 0. The frame: two different walls, and only one of them is architecture

| class | example | what actually bounds it |
|---|---|---|
| **Design-class** | a house, a robot, a chip, a mechanism | **Architecture.** Constraints are codified and machine-checkable. This is reachable, and it is where "previously impossible" is available. |
| **Discovery-class** | "solve this disease" | **Physical experiment access.** You cannot solve a disease without wet-lab work. No orchestration fixes this — it is a robotic-lab / CRO / partnership problem. |

**Aim at design-class.** Discovery-class is bounded by reach, and reach is bought,
not built.

## 1. The core gap, in one sentence

**The system produces an arc of FINDINGS. A big goal needs a maintained DESIGN.**

Findings are append-only and independent. A design is mutable and coupled —
plumbing constrains framing constrains load paths — and the hard part is that
changing one silently invalidates three others. There is currently **no
representation of the thing being built** for that invalidation to register
against.

**MEASURED — both headline failures of `study-20260730T034915Z` are instances:**

- Three fits of the same coefficient on overlapping data gave `b_sn` = **0.32,
  3.65, 7.43** — a 23× spread, one implying a 260-year pavement life against an
  observed 12.4. The paper calls it *"a first-order unresolved problem… the single
  strongest reason this replacement is not ready to use"*, and it surfaced in §5.2
  of the write-up rather than when the second fit landed.
- σ ≈ 0.36 was compared against 1.46 across **different response variables**
  (years vs ESALs). The entire 4× headline was that substitution.

**Neither is a verification failure.** Each number reproduces perfectly on its
own. `stages/reusable_artifacts.py` is a file hand-off — shape-check, prove the
producer reproduces, stamp a step id. Occurrences of *constraint / conflict /
consistency / contradict* in `reusable_artifacts.py` and `verification.py`:
**zero**. An artifact says "here is a file and the code that regenerates it". It
never says "this value must agree with that one".

---

## TIER 0 — before the next run. Both small, both MEASURED.

- [x] **T0.1 Quantity register with conflict detection.** BUILT 2026-07-30 —
      `stages/quantity_register.py`, wired at `pi_agent/study.py::record_move`,
      surfaced in the director's turn, liveview and the CLI summary. Design
      record and the honest limits: **`docs/memo_quantity_register.md`**.
      Proven on the real values in the real order (`b_sn` 3.6537 -> 7.4314 fires
      at move 14; sigma years-vs-ESALs fails on units), 60 offline tests, no
      model in it, nothing gates. UNPROVEN ON A REAL RUN: replayed against
      `study-20260730T034915Z` it fires zero times, because every one of that
      study's six elasticity estimates was unverified and so carried no name to
      collide on, and `units` did not exist. The next study is the measurement.
      The original statement of the item follows.
      The minimum viable
      constraint artifact, and the one new capability on this page that is cheap.
      A deterministic store — **no model in it, same discipline as the wall** —
      where a move registers a quantity it has established: `name, value, units,
      producer, move`. On every write, a mechanical check: does this name already
      exist with a different value outside tolerance, or different units? If yes →
      **conflict surfaced to the director on its next turn.**
      It answers a different question from verification. Verification asks *does
      this recompute*; this asks **does this contradict something already
      established** — which is why verification caught neither failure above.
      Catches both: `b_sn` conflicts at move 14 instead of §5.2; the years-vs-ESALs
      comparison fails on units, mechanically.
      ADDITIVE: a move MAY register quantities; nothing forces it, nothing gates.
- [ ] **T0.2 Incremental emission.** Moves 15 and 16 both died after the expensive
      analysis and before writing the cheap producer files — **98 findings lost in
      the last mile**, two independent instances in one study. A move that emits
      each scalar as it computes it leaves verified numbers even when cut off.

**Nothing else on this page should start before these two.**

---

## TIER 1 — the constraint substrate. REASONED.

This is where "maintained design" starts to be real. Nothing here has been tested;
T0.1 is the probe that tells you whether the direction is worth it.

- [ ] **T1.1 Constraints as first-class objects**, not just quantity equality. A
      registered relation that must hold between quantities (`a ≤ b`,
      `a = f(b, c)`, "this clearance ≥ this diameter"), machine-checkable, owned by
      the move that declared it.
- [ ] **T1.2 Re-check on edit.** When a quantity changes, everything declared
      downstream of it re-checks automatically. This is the mechanism that makes
      coupling visible: the plumber's change trips the framer's constraint.
- [ ] **T1.3 Progressive commitment.** Freeze a decision so downstream work is not
      silently invalidated, and know the cost of unfreezing it. Without this, a
      long design either never settles or settles by accident.
- [ ] **T1.4 A conflict must be a DECISION, not a note.** It reaches the director
      as something to resolve, with the option to halt the arc. Compare the current
      behaviour: three contradictory coefficient sets shipped in the deliverable
      "so the discrepancy can be attacked rather than buried" — honest, and far too
      late.

---

## TIER 2 — the maintained design object. REASONED, and this is the real research.

- [ ] **T2.1 A domain representation the agents EDIT rather than describe.**
      Geometry, interfaces, load paths, power/thermal/timing budgets, tolerances —
      a structured object, not prose. A house has one (BIM, code clauses, spans);
      a robot has one (CAD, kinematics, power). **This is the item that decides
      whether "build a house" is reachable**, and it is the part I could find no
      prior art for as an agent substrate. It sits ON the Tier-0/1 substrate; it
      cannot be built first.
- [ ] **T2.2 Long-horizon credit assignment.** Which of 200 past decisions caused
      the failure discovered now. Today the arc is a log, not a dependency graph.

---

## TIER 3 — scale and duration. REASONED, except where noted.

- [ ] **T3.1 Wall-clock.** Every move is ~1 hour and strictly sequential;
      **MEASURED** as the long-run ceiling. Fan-out exists and has been used once.
      With the move ceiling now derived from tokens, fanning is structurally cheap
      and under-used.
- [ ] **T3.2 Intermediate signal from a running move** (A5, deferred by design in
      `docs/design_intermediate_signal.md`). 69–84 turns of zero visibility.
      Blockers now reach the arc, so this is the remaining blind spot.
- [ ] **T3.3 Cross-study composition.** Dropped earlier as "not wanted", and that
      ruling should be revisited on this axis alone: **a house cannot be one
      study.** Anything at that scale is many studies composing into one design,
      which is Tier 1 + Tier 2 operating across study boundaries.

---

## TIER 4 — reach. Not architecture, and worth saying out loud.

- [ ] **T4.1 Physical experiment access** — robotic labs, CROs, real assays. This
      is the binding constraint on every discovery-class goal, and no amount of
      orchestration substitutes for it. Bought or partnered, not built.

---

## Carried, unrelated to capability but still open

- [ ] **Arm B** (~$20, an hour). Every claim of the form "the orchestration does X"
      is unfalsifiable without one strong agent measured on the same frozen goal.
- [ ] **Auto-commit ruling** (`docs/memo_auto_commit_run_code.md`). Three
      decisions. **`runs/` and `studies/` are gitignored with zero tracked files —
      every study's output exists only on this laptop.**
- [ ] **Two memos awaiting a ruling** — `memo_transport_retry_experimenter.md`,
      `memo_succeeded_semantics.md`.
- [ ] **Prior-art check on the architecture itself.** The ideation apparatus is a
      documented reimplementation of AI Co-Scientist (CLAUDE.md names the four
      strategies and six review types). The assembled system — free director with a
      divisible budget, recursion, the no-model wall, carry bus — has **no prior-art
      check on record**. This is the same discipline the system now applies to its
      own targets; it should apply it to itself before claiming novelty anywhere.
- [ ] **The architecture paper.** Thirty findings/memos in `docs/` are internal
      records, not research: no framing, no baseline, no positioning. Most are n=1.
      Writing it would surface which claims need a second run to be defensible.
