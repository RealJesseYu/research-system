# Architecture Collapse Manifest

**Written:** 2026-07-21. **Status:** decided with the owner; partially built.
**Purpose of this doc:** the single source of truth for *what the system is for*,
*what stays*, *what goes*, and *how a run should work* — so any session can pick
up the collapse without re-litigating it. Read this before adding anything.

---

## 0. The one thing this system is for

**A researcher that works when you are NOT in the room** — runs unattended, for a
long horizon, accumulating a body of work toward a goal, where **every result it
keeps can re-prove itself** because no human witnessed it.

A Claude chat (or two agents) is more capable *while you watch it*. The moment you
leave, a chat falls apart in three ways a research program can't tolerate:
1. it **narrates** results, so somewhere it reports a number it didn't compute and
   no one catches it;
2. it hits a **context limit** and forgets what it did;
3. **nobody directs the arc** — when to stop, when to change tack, what N
   experiments add up to.

Everything we keep exists to close exactly those three gaps. Everything we cut is
ceremony that doesn't, and that currently makes the experimentation phase **weaker
than a plain chat** (agreed, openly — see §3).

---

## 1. KEEP (load-bearing — a chat can't give these)

| Piece | Where | Why it stays |
|---|---|---|
| **Verification** | `stages/verification.py` | You weren't in the room; a kept number must re-run and reproduce. The one thing separating a trustworthy program from an unchecked transcript. Non-negotiable. |
| **Propose/measure boundary** | `experiment_investigation.py`, `pi_agent/`, wrappers | The number of record comes from a tool + verification, **never the model's narration**. This is what makes leaving the room safe. |
| **The experimenter loop** | `stages/experiment_investigation.py` | "run small → look → adapt → scale → stop." Makes it a real experimenter, not a frozen line. The fix for "weaker than a chat." |
| **Composition (substrates-as-tools)** | Phase 1 (`docs/memo_phase1_composition.md`) | One experiment calls several tools and combines them, like a human. |
| **The sandbox** | `tools/run_python_experiment.py` | The room the experimenter runs code/tools in. |
| **Memory + goal-director (PI)** | `memory/`, `pi_agent/` | Accumulation across many runs toward a goal — what makes it a *program*, not a *conversation*. (Action space needs widening — §4.) |
| **Reporting / paper** | `stages/stage6_paper.py` | An unattended run's output must be a readable, honest artifact of what actually reproduced. (Memory-bleed fixed 2026-07-21.) |
| **Fidelity gate — ONLY for approximate physical instruments** | `stages/stage3_fidelity_gate.py` | A CFD-class tool converges to a confidently *wrong* number; reproduction reproduces the wrong number. "Is this valid here?" catches what re-running can't. Real value **only** for that narrow class. |

## 2. DEMOTE / CUT (ceremony or over-restriction — strangles the loop)

| Piece | Why it goes |
|---|---|
| **Six mandatory sealed stages as the spine** | They chop think→act→observe→adapt into disconnected one-shots. The loop is what makes an agent smart. Stages 2–5 collapse **into** the experimenter loop. |
| **One-substrate-per-run** (gate-1 picks one instrument) | A real experiment composes multiple tools. This is the direct cause of "why only one experimental design." The experimenter picks tools per probe. |
| **Static single-spec authoring** (stage 2 freezes one spec, run once) | Locks the experiment before anything runs — no adaptation. Replaced by the experimenter authoring a cheap probe, reading it, authoring the next. |
| **Contract + calibration + maturity ceremony on EXACT tools** | For code / lookups / deterministic tools the code *is* the definition — no "is it valid" question. Pure overhead. Keep the ceremony **only** for approximate instruments. |
| **Fidelity gate as a universal mandatory gate** | For exact tools it gates a non-question. Demote to fire only for approximate instruments. |
| **Gate / loop-back machinery** (`MAX_LOOPBACKS=2`, gate vocabulary, mandatory human gates) | Supervisor ceremony for the frozen pipeline. In a loop, "loop back" is just the agent choosing the next probe. |
| **Elaborate ideation apparatus — KEEP but make ON-DEMAND** | *Owner ruling 2026-07-21:* the apparatus (generation strategies, 6 reviews, tournament, evolution, meta-review) is genuinely valuable and is **NOT cut** — it is too expensive to run **every** time, so it becomes opt-in via a `depth` switch (§4). Default cheap; escalate to full when the PI or the human chooses. |

## 3. Decisions locked this session (do not re-litigate)

- **The system is currently weaker than a chat for raw experimentation** — because the loop is broken into sealed stages. This is a description of today, and the collapse is the fix. Not a defense.
- **Connectors are allowed.** The SDK supports `mcp_servers` (`claude_agent_sdk/types.py`); the `FULL` profile just doesn't wire any today. A "substrate" ≈ a connector + ceremony. Let the experimenter reach for connectors and substrates alike; the only rule is a kept number must be a re-runnable artifact.
- **The ceremony's real job is narrow:** it earns its keep only for tools that can be *confidently wrong* (approximate physical simulators). For everything else it's overhead.
- **Ideation stays, gated on-demand** (see the ideation row above and §4).

## 4. The proposed run (target shape)

You give it a **goal** and walk away.

1. **Director (PI) picks the next question** from goal + arc-so-far (memory). An
   ideation agent proposes candidates; the director picks one — and chooses the
   **ideation depth** (`quick` vs `full`) for that question.
2. **The experimenter investigates** — a `FULL` agent, all tools **and connectors**
   on the table, in a loop: author a cheap probe (a composition recipe) → the
   controller runs it and **verifies** it → the agent reads the *verified* result
   → scale up / switch tools / stop (small-before-big by judgment). One rule: every
   kept number came from a tool + verification. Fidelity check fires only for
   approximate instruments.
3. **Result recorded** to memory (verified answer + re-runnable recipe). Director
   updates the arc, loops or stops.
4. **Write-up** of only the numbers that reproduced.

Net shape: **ideation-agent → experimenter-agent → paper, wrapped in memory + a
goal-director**, plus the thin propose/measure/verify layer. Much closer to "two
agents" than to six stages.

## 5. What is already built toward this (as of 2026-07-21)

- **Phase 1 — composition:** substrates are callable tools one experiment composes,
  verified (`verification.py` gained `kind:"composition"`; `run_composition`;
  hardcoded-combine tripwire). Committed (`2b8fbb8`). Memo:
  `docs/memo_phase1_composition.md`.
- **Phase 2 — the loop:** `stages/experiment_investigation.py` — deterministic
  controller that hosts an experimenter (propose → execute → verify → decide),
  small-before-big emergent. Committed (`964b094`). Tests:
  `tests/test_experiment_investigation.py`.
- **Phase 2 remaining brick:** the **live experimenter *strategy*** — the model
  brain that proposes the next probe. Handoff in `docs/phase2_handoff.md`.
  Owner-gated (highest spend).
- **Ideation depth-switch:** BUILT 2026-07-21 (see §6). Wiring "who chooses" to the
  supervisor/PI is the small remaining step.

## 6. Sequenced collapse plan (ordered)

1. **Ideation depth-switch** — DONE 2026-07-21 (`stage1_ideation.run(depth=...)`,
   `quick` vs `full`). Next: wire the supervisor to default `quick` and let a
   human flag / the PI decision set `full`.
2. **Build the live experimenter strategy** (Phase 2 brick) — the model that drives
   `experiment_investigation.py`. This is the heart; it flips "harness exists" to
   "the experimentation half is a real agent."
3. **Route the experimenter into the pipeline** in place of stages 2–5 for the
   exact-tool path; keep stage 3 (fidelity) firing only for approximate instruments.
4. **Strip the ceremony on exact tools** — a code/connector/deterministic tool needs
   only "record it so it re-runs," not a contract/calibration/maturity row.
5. **Widen the PI action space** beyond `run_single/run_campaign/stop` so the
   director can dispatch investigations and set ideation depth.
6. **Wire connectors** into a profile (`mcp_servers` + tool names) once there's a
   concrete connector to use; a connector result becomes a substrate the moment it
   is a re-runnable artifact.

## 7. Rules to respect (project discipline)
- **Run-venue rule (absolute):** full/long supervised runs launch from a plain
  Terminal under `caffeinate`, never a builder-session background task.
- **STOP-and-rule:** changing a contract, a locked schema, or a "ruled" input is a
  decision to record. Preserve superseded fixtures append-only (`*_pre<x>`).
- **Verification purity:** no model in the verification path.
- **Never `git add -A`** — stage only the files you changed.
- Measurements of record come from a tool/wrapper (deterministic) or the sealed
  sandbox — never narrated by an agent.

## 8. Note on bio-file isolation (2026-07-21)
The bio status narrative was moved out of the always-loaded `CLAUDE.md` into
`docs/status_archive_bio.md` (nothing deleted) because bio content in context was
causing the builder model to route Fable→Opus. The bio wrappers/contracts/
onboarding/tests are untouched and fully wired. The deeper bio content still lives
in `substrates.py` (contracts) + the four wrappers and loads only when opened.
Harness model-routing itself is not controllable from here.
