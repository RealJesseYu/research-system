# Free Director / Manager-of-Managers Plan

**Written:** 2026-07-23. **Status:** agreed with the owner; build starting.
**Read after:** `docs/architecture_collapse_manifest.md` (the collapse this
continues) and the PRIME DIRECTIVE in `CLAUDE.md`. This doc is the single source of
truth for the *next* architecture step: turning the director into a true manager.

---

## 0. The one thing this step is for

The experimenter was already freed (`stages/free_experimenter.py`): a FULL agent,
any tool, no cage. **The director was not.** Today the director (`pi_agent/decider.py`
+ `pi_agent/loop.py`) is a reactive loop-controller: one Opus call per move that
reads a flat arc and returns one of four verbs (`run_single` / `run_campaign` /
`run_fan` / `stop`). It manages a *sequence*, not a *project*. It cannot decompose a
goal into subsystems, delegate, allocate budget per piece, track dependencies, or
integrate. It is the last cage — the director-level analogue of the sealed pipeline
already purged below it.

**The vision:** there is ONE primitive — *a free agent in a loop with tools* — and
"spawn a sub-investigation" is simply one of its tools. A manager of managers is not
new machinery; it is **recursion of the free-agent primitive already validated**. The
whole task spectrum collapses into depth-of-recursion the agent *chooses*:

- *"Solve this math problem"* → the agent just solves it. No decomposition, no routing —
  because nothing is mandatory.
- *"Design a house / build a robot"* → the top agent elects to split into subsystems,
  spawns a sub-agent per piece (each choosing its own trial count under the budget it
  was handed), and integrates — because the task earns it, not because a pipeline forces it.

## 1. Principles (locked — do not re-litigate)

- **Freedom in *what*, hard ceiling on *how much*.** The human sets the ceiling; the
  super-director decides everything downstream so it can't go too complex or run too many
  tests. Same split the repo already uses (free experimenter but `max_iters`; free
  director but `max_moves`) — extended from a line to a tree.
- **Nothing is mandatory except the measurement boundary.** Ideation, heavy validation,
  data analysis, decomposition — all *optional tools* the director/experimenter reach for
  when the task warrants. The ONE invariant that stays is the **propose/measure boundary**:
  a measurement comes from a tool/sandbox, never from an agent's narration; a kept number
  must be re-runnable. It is not a stage or a gate — it is a law of physics enforced at the
  tool layer, invisible until you keep a number. It is what lets you leave the room.
- **Two meanings of "deterministic" — keep them separate.**
  - *In lit review:* deterministic API sources (arXiv / OpenAlex / Semantic Scholar) give
    **citable, reproducible grounding**; Claude's native `WebSearch`/`WebFetch` give breadth
    and recency. **Ideation uses BOTH.** Neither is verification — both are retrieval.
  - *Verification* is a separate deterministic subsystem (`stages/verification.py`, no model
    in it) that re-runs an artifact to reproduce a kept number. About trusting results, not
    literature.
- **Build the free path alongside, then purge the cage** (the repo's proven M1 pattern).
- **Run-venue rule (absolute):** live/long runs from a plain Terminal under `caffeinate`,
  never a builder-session background task. Live outings are the owner's, not a builder job.
- **STOP-and-rule; verification purity (no model in the verify path); never `git add -A`.**

## 2. Phase 0 rulings (recorded 2026-07-23; reversible if the owner disagrees)

- **R-FD-1 — Build alongside, not mutate.** The free director is a NEW module; the enum
  director (`decider`/`loop`) keeps working until the free path is live-validated, then the
  enum cage is purged. (M1 pattern.)
- **R-FD-2 — Moves is the enforced ceiling; cost-cap derives moves.** The human sets EITHER
  `--max-moves` OR a `--cost-cap`. Moves stay the always-enforced hard bound (per-run cost is
  not yet visible to the parent — see `loop.py`'s own note that a spend-denominated ceiling
  needs per-run cost reporting that does not exist). Given a cost-cap, the super-director
  derives a move ceiling from a per-move cost estimate. Real mid-run cost enforcement is a
  Phase-1 sub-task (build per-run cost reporting first).
- **R-FD-3 — Children return verified artifacts, never narration.** A sub-investigation's
  result is read from the record it leaves on disk (the existing `dispatch.read_run_result`
  pattern), extended to nested studies. A child can never narrate a number up to its parent.
- **R-FD-4 — Decomposition is emergent-first.** The free director decomposes by *choosing*
  to spawn sub-investigations; ordering/dependencies emerge from judgment + memory. An
  explicit dependency/DAG structure is added only when a real run shows emergent ordering
  failing (tested-first). No mandatory work-breakdown scaffolding.
- **R-FD-5 — write_memory uses a distinct kind (2026-07-24).** The director's `write_memory`
  appends a `director_note` journal kind, NEVER `learned_summary` — that channel is what
  ideation reads and the kill-rate battery pins by md5 ("learned-summary poison risk"), and
  a distinct kind keeps director notes inert to it. `read_memory` reads both kinds; nothing
  else reads `director_note`. This resolves the Phase-4 hold and wires the last action.
- **R-FD-6 — Ideation depth is the director's dial (2026-07-25, owner-ruled).** `call_ideation`
  was always correctly a TOOL in the open action space — callable at any turn, returning ranked
  hypotheses into the arc for the director to act on, never a mandatory opening phase. But it
  hardcoded `depth='quick'` (one generation strategy), so the full Co-Scientist apparatus
  (four generation strategies, six review types, Elo tournament, evolution, meta-review) was
  unreachable from the director path — you could have strong ideation OR a directed arc, not
  both. RULING: add an optional `depth` field ("quick" | "full") to the `call_ideation` action,
  **defaulting to quick**. Rejected alternatives: always-full (makes every study expensive
  whether or not the ideas are the deliverable) and budget-derived (hides a research judgment
  inside an accounting rule). The director already reasons about budget and about whether it
  needs one direction or many, so this is exactly the call it is positioned to make. `depth` is
  valid ONLY on `call_ideation` — naming it elsewhere is a re-ask, not a silent ignore. The
  depth used rides the arc entry, because "thin ideas from a quick pass" and "thin ideas the
  full apparatus could not improve on" are different facts. Absent depth ⇒ quick ⇒ behavior
  byte-identical to before the dial.

## 3. Task plan (ordered; connectors are explicitly AFTER all of this)

### Phase 1 — Recursive budget spine (safety-critical, first)
Recursion without a provably-terminating, divided budget is the runaway-cost / infinite-
decompose hazard. Build the guarantee before anything recursive.
1. **Budget object** (`pi_agent/budget.py`) — a finite total that **divides down the tree**:
   `allocate(k)` transfers k moves to a child it cannot exceed; `spend(n)` for this-level
   work; sum across the whole tree is conserved (= root total, partitioned). Hard `max_depth`
   backstop. Provably finite (every op strictly decreases some node's pool; nothing increases
   it; depth capped). Tested-first.
2. **Human ceiling input** — accept `--max-moves` OR `--cost-cap`; cost-cap → derived moves
   via a recorded per-move estimate.
3. **Per-run cost reporting** — make each subprocess run report its spend to disk so the
   parent can read it (the `loop.py` gap). Turns the cost-cap from derived-estimate into a
   real enforced ceiling.

### Phase 2 — The free director itself
4. **Free director shell** (`pi_agent/free_director.py`) — a FULL agent in a loop, like
   `free_experimenter`, whose action space is *open tools* not a four-verb enum:
   `spawn_sub_investigation`, `call_ideation`, `call_validation`, `call_data_analysis`,
   `read/write_memory`, `allocate_budget`, `stop`.
5. **Offline-faked test harness** for the director loop (patch the transport seam) — prove
   call path + budget accounting with faked judgment.
6. **First small live outing** — plain Terminal, `caffeinate`, tiny ceiling, flat (non-
   recursive) goal, to confirm the free director matches the enum director before recursion.

### Phase 3 — Everything-is-a-tool refactor
7. **Ideation → callable tool** using BOTH search styles (native + deterministic API), via the
   already-built `depth` switch; the free director *calls* it, never a mandatory stage.
8. **Split validation** — keep the thin propose/measure boundary as a sandbox-enforced law;
   make the heavy validation apparatus an optional tool the director calls when stakes warrant.
9. **Data analysis → callable tool** on the same footing.
10. **Mandatory-nothing audit** — confirm no path forces an agent through a stage it didn't
    choose, except the measurement boundary.

### Phase 4 — Manager of managers (recursion)
11. **`spawn_sub_investigation` wired live** — nested studies (`study.py` already carries a
    `parent-link`; extend from nested runs to nested studies).
12. **Measurement boundary survives every depth** — a grandchild's numbers still come from
    tools and bubble up only as verified artifacts.
13. **Memory accumulates across the tree** — parent reads verified child results from disk,
    not transcripts; the arc becomes a tree.

### Phase 5 — Composition & integration for real subsystems  ✅ (built 2026-07-23)
14. **Rich artifact hand-off — ALREADY BUILT (record corrected).** Contrary to this
    plan's original assumption, `stages/verification.py` already wires file hand-off:
    code↔code (R-ART-5) AND substrate emit (`emit_artifacts`) + consume-with-resolver
    (R-ART-7/8) in `_run_one_step`/`_run_steps`, all re-run under the same executor so a
    composed number re-proves. Do NOT rebuild. The narrow remaining deferrals: the
    **case-build** substrate call style emitting a file (the literal R-ART-6, needs a
    live emitting CFD-class substrate) and **cross-run** file hand-off (a child run's
    output file feeding a parent integration run). Both are expand-on-evidence, left for
    a real live composition that needs them.
15. **Integration probes + joint verification — BUILT at the director level.** New
    first-class action `call_integration` (pi_agent/free_decider.py): the director
    dispatches a real experiment that ASSEMBLES the arc's verified parts (including
    bubbled sub-investigation findings) and measures whether they compose — the run's
    experimenter authors an assembling composition, the wall verifies the joint number.
    Reuses run_move/composition/wall (no new verification machinery; purity intact). The
    prompt makes it explicit: do NOT declare a decomposed goal answered until an
    integration check has stood ("each part optimal, the assembly still fails" — which
    per-number re-running cannot catch). Guidance, not a hard gate (R-FD-4). Honest
    limit: this composes verified SCALARS now; full physical (file/geometry) assembly
    across separate sub-runs needs the deferred cross-run file hand-off above.
16. **Interface/dependency handling** — still deferred (emergent-first, R-FD-4); wake
    only if a real run shows emergent ordering failing.

### Phase 6 — Prove the whole thing
17. **Offline-faked full recursive run** end-to-end.
18. **One small live `caffeinate` outing** on a genuinely multi-subsystem toy goal (2–3 real
    subsystems that compose — not a robot yet), under a human cost/move ceiling, walk-away,
    producing a verified reproducible result tree + write-up.

**Then — and only then — connectors** get wired into a profile; by then a connector result is
just another re-runnable artifact the free agents already handle.

## 4. The two genuinely hard, genuinely novel tasks
Everything else is mostly applying rulings already made one level up. The real engineering:
- **#1 / #3 (divided budget + provable termination + real cost reporting)** — recursive
  freedom is only safe to walk away from if the budget provably bounds the tree.
- **#15 (joint verification)** — where even the propose/measure boundary isn't automatically
  enough, because the thing to trust is an *interaction*, not a number.

## 5. Discipline reminders
- The tree carries the owner's uncommitted work — **never `git add -A`**; stage only files a
  task changes.
- Tested-first, no gold-plating, expand only on evidence.
- Give a mini-debrief after each finished brick (what shipped / how it moves the vision /
  done–in-progress–not-started checklist).
