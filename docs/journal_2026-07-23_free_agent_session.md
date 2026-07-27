# Technical journal — the free-agent session

**Date:** 2026-07-23 · **Branch:** `iterate-experiment-loop` · **Commits:** `a2de795 → 45306a5` (11 new)
**Suite:** ended green at 1411 passed, 1 skipped. **One thread:** turn the caged six-stage pipeline into a free agent, then build the machinery that makes it *more* than a chat.

---

## 0. One-paragraph summary

Deleted the dead static pipeline (the cage) and rebuilt the "and more than a chat" layer on top of the free agent: a per-run workspace, a verification wall that independently re-runs every kept number, MCP connectors, the two dormant capabilities restored as opt-in routes (Co-Scientist ideation + paper write-up), model-tier selection, and a director fan-out for parallel exploration. Several handoff assumptions were corrected by tracing. One capability (#1, #2) is live-validated; the rest are wired + unit-tested, pending Terminal runs.

---

## 1. The dead-pipeline purge (commits `11ff177`, `800243f`, `c45fb48`)

**Decision:** free is already the default production entry, so the whole deterministic six-stage relay + gates + loop machinery was dead code. Deleted it in three green sub-steps, tracing every caller first.

**Deleted (the cage — matched the PRIME DIRECTIVE):**
- Supervisor's static relay, three human gates, loop-back/retry/barren/desk/crash machinery, the substrate maturity hook (supervisor **1980 → 235 lines**).
- **gate-1** (`gate1_chooser`) — the funnel that collapsed many hypotheses to *one hypothesis + one instrument*; the single most anti-research piece.
- **stage-3 fidelity gate** — the "fidelity ceremony" the directive named as over-engineering.
- **stage-2 experiment-design** (rigid typed-spec stage), the director's in-process **CHAIN** move + `chain_runner`, and the dead-stage harness batteries (fidelity/calibration/triage/validation) + `run_harness`'s fast/heavy/triage/calibration modes.
- ~40 legacy test files (deleted or surgically reworked to keep only live coverage).

**BIG FINDING — the handoff's delete-list was wrong about three modules.** Tracing (not asserting) showed these are **live tool infrastructure**; deleting them would have broken the free agent's substrate dispatch:
- `stage4_case_builder` — `substrate_dispatch` calls `build_case()`.
- `stage4_simulation` — `substrate_dispatch` imports `translate_qoi`.
- `stage2_spec` — `substrate_selection` (the director) imports its validators.
- (`capability_guard`'s stage names are policy *strings*, not imports — no blocker.)

**Kept by design:** `stage5_thought_layer` (inert; locked `schemas.py` imports it — owner ruling "option a": leave the schema inert, never touch the locked file); `campaign_controller` (owner WIP + it feeds the live `stage4_simulation`).

**Method that worked (recorded as the discipline):** build the import graph, trace every caller before deleting, let the suite guide the test triage cut-by-cut, commit each green sub-step. Never `git add -A` (owner-dirty files: `CLAUDE.md`, `memory/journal.jsonl`, `test_campaign_controller.py`, …).

---

## 2. Reproducible-records layer — the "and more" that a chat lacks

### 2.1 Per-run workspace (#1, `0139e45`) — LIVE-VALIDATED
**Problem:** the free agent wrote artifacts into the repo root (`collatz/`, `run_tpsa_check.py`).
**Decision:** give each run `runs/<id>/workspace/` as the agent's cwd.
**Design:** an ambient `contextvars.ContextVar` in `model_call` (`agent_workspace()`) sets the SDK `cwd`; **`PYTHONPATH` is set to the repo root** so `from tools.run_X import ...` still resolves from the workspace (the SDK *merges* env onto the inherited process env). Chosen over threading a param through the transport-retry seam, which does signature introspection a new arg would disturb. Absent (no run_id) ⇒ default cwd, byte-identical.
**Interaction found:** `capability_guard` protects `runs/` by *literal text*, so relative writes (`solve.py`) pass and land in the workspace via cwd — the guard needed no change.

### 2.2 Controller re-verify — the wall is authoritative (#2, `13acdea`) — LIVE-VALIDATED
**Problem:** `verified=True` meant *the agent re-ran its own number* (grading its own homework).
**Decision:** a deterministic, no-model pass re-runs each kept finding's saved artifact, and **its verdict — not the agent's self-report — sets `verified` and can only *remove* `publishable`.**
**Design:**
- New verification-wall artifact kind **`workspace_file`**: reads the file the agent saved and re-runs it through the *same* no-network Docker code sandbox (`run_python_experiment`) as an inline `code` artifact. The hardcoded-constant tripwire reads the file's code too.
- Contract: a finding marked verified must carry a re-runnable `artifact` (`{file, quantity}` for a saved script that sets `metrics["<q>"]=<v>`, or `{substrate_id, typed_input, quantity}`). Prompt teaches it; validator enforces it.
- **Consistency decision (important):** the claims passed to the wall are **only the verified-marked findings** — an honest unverified finding is a *caveat*, not a claim, and never gates `publishable`. This keeps `verification.json.publishable` consistent with the run's `publishable`.
- `verify` is injectable so offline tests don't hit Docker.

### 2.3 Live validation of #1 + #2 (run `20260723T072110Z`)
Goal: "sum of the first 10,000 primes." The agent wrote `sum_primes.py` to its **workspace** (repo root stayed clean), and the wall **independently re-ran it in Docker and reproduced `496165411` exactly** (rel_error 0.0, reason `reproduced`), `publishable=true`. Both #1 and #2 proven end-to-end.

---

## 3. Connectors (#3, `414ec25`)

**Decision:** wire the SDK's MCP support into the FULL profile so the free agent can reach any non-substrate tool (CAD, a domain API, …), domain-agnostic, no code change to add one.
**Design:** `load_mcp_servers()` reads a gitignored `mcp_servers.json` (`{"<name>": <config>}`); `_mcp_option_kwargs()` feeds the SDK `mcp_servers` + `strict_mcp_config` and permits each server's tools as `mcp__<name>`. Absent ⇒ byte-identical no-MCP. The capability guard still vets every MCP call (no `memory/`, `runs/`, `.env` reach). `mcp_servers.example.json` documents the format.

---

## 4. The two dormant capabilities, restored as ROUTES

**Framing the owner insisted on:** "I don't want just a regular Claude agent with garnishes." Resolution: the substrates *are* garnish (correctly), but the "more" is the wall + memory + director + the research apparatus. The apparatus was dormant, not deleted — so restore it.

### 4.1 Ideation route (`5fc2d65`)
The Co-Scientist hypothesis apparatus (`stage1_ideation`: generation × 4 strategies, 6 reviews, Elo tournament, evolution, meta-review) was kept but unwired.
**Decision:** restore as **opt-in `--ideate`** — run it first, then hand the free agent the *whole ranked set* as candidate leads. **Not a gate:** breadth is preserved (unlike the deleted gate-1). Best-effort: an ideation failure falls back to the bare domain. Off by default (many model calls).
**Honest note recorded earlier:** this apparatus historically had over-lethal deep-verification (~40–45% false kills); in the current architecture the *real* quality filter is the wall (a claim that won't reproduce doesn't survive), not the tournament.

### 4.2 Paper route (`0adb7dc`)
**Finding:** the old `stage6_paper` is **bound to the deleted pipeline** — it needs a stage-3 fidelity verdict + a stage-5 "thought" object, and emits no figures. Bolting it on a free run would mean *fabricating inputs*. Rejected as dishonest.
**Decision:** a new `stages/free_paper.py` — opt-in **`--paper`** — a *fresh* FULL agent (separate from the one that investigated, so it isn't grading and writing its own work at once) drafts `paper.md` from the **wall-verified findings**, generating figures (matplotlib) from the workspace data. Keeps `stage6_paper`'s one load-bearing habit — a mandatory "What a human must still validate" section — sourced from what the wall could/couldn't reproduce. Best-effort.

---

## 5. Model-tier selection (`20e8037`)

**Ask:** "let me choose model 1 and model 2, so I can do opus opus."
**Decision:** a central `models.py` resolver with three tiers — **heavy** (experimenter/director/paper/hard-judgments; default Opus), **light** (generation/reviews/evolution; default Sonnet), **triage** (web search/sealed; default Haiku). All 14 model pins route through `model_for(tier)`.
**Control:** env (`RESEARCH_MODEL_HEAVY=opus RESEARCH_MODEL_LIGHT=opus`) or CLI (`--model-heavy opus --model-light opus`). Unset ⇒ byte-identical historical mix. Every run logs its resolved `MODELS:` line.

---

## 6. Director fan-out (`45306a5`)

**Architecture question the owner raised:** "is there any reason a single Opus controlling cross-cycle transitions isn't enough?"
**Answer, settled:** **No — for the *decision*, a single Opus is enough; the model is not the bottleneck** (and it already runs FULL, so it deliberates with tools, and it already formulates its own next question). "Shallow" comes from three *structural* limits, not model count:
1. it reasons over **distilled findings**, not the full texture;
2. it moves **one line at a time** (the real breadth limiter);
3. **nothing checks its own framing** — a lone decider can self-reinforce a wrong line across cycles.

**Decision:** fix #2 by *widening the action space*, not adding agents. New **`run_fan`** move: the director proposes 2–4 competing sub-questions that run **as parallel runs in one cycle**, then synthesizes them next turn.
**Concurrency-safe design (`run_study_fan`):** distinct run-ids pre-assigned sequentially, subprocess invokes in a bounded thread pool, results appended to the append-only arc **sequentially** (no race), a failed run recorded as a result (not a crash), and the fan **capped to the remaining move budget** so it can't overrun the hard ceiling.
**#1 and #3 deferred deliberately:** enriching the arc, and the *one* genuine case for a second model — an adversarial critic against self-reinforcement on high-stakes pivots — to be added **on evidence** (once we see the director entrench), not preemptively.

---

## 7. Where it stands vs. the "is it a real research system?" checks

- **Closed loop?** Yes — within a run (agent iterates) and across runs (director reads verified findings, decides next); the cross-run loop is real but its *decision depth* is the growth area.
- **Paper + diagrams?** Yes now (`--paper`, figures from workspace data) — wired + unit-tested, **not yet live-proven**.
- **Thinks like a scientist / chains experiments?** Yes informally (agent-driven chaining + `--ideate` breadth + wall skepticism); **no formal experiment graph** (the old rigid chain was deleted, nothing structured replaced it).
- **Broad task / multiple cycles?** Yes structurally (director + memory + cycles, now with fan-out); a long campaign is unproven live and is *expensive*.

**Is it more than "an agent with garnishes"?** Yes: five things a chat structurally lacks are now on the path — strong hypothesis generation, **mechanical verification** (numbers don't stand on the agent's word), memory across runs, a director running many cycles, and paper write-up with figures.

---

## 8. Open items / next work

1. **Live-validate** the fan-out, the `--ideate`/`--paper` routes, and an all-Opus run (Terminal runs — owner's).
2. **Per-run cost reporting** → a true *token* ceiling for the director (today the hard budget is *moves* only; the loop honestly notes it can't see per-run spend). My recommended next feature.
3. **Deepen the arc** the director reasons over (limiter #1 above).
4. **Adversarial critic** for high-stakes pivots — only if the director is seen to self-reinforce.
5. **Formal experiment graph** — if informal chaining proves insufficient.
6. Housekeeping: owner to commit their WIP in `tests/test_campaign_controller.py`.

---

## 9. Commit trail (this session)

```
11ff177  Purge dead pipeline (part 1): gut supervisor to the free entry
800243f  Purge dead pipeline (part 2): director CHAIN move + dead-stage batteries
c45fb48  Purge dead pipeline (part 3): delete stage 2 + stage 3 modules
fa72eaa  Debrief: the dead-pipeline purge session
0139e45  Per-run workspace for the free agent (#1)
13acdea  Controller re-verify: the wall grades the free agent's numbers (#2)
414ec25  MCP connectors for the free agent (#3)
5fc2d65  Ideation route: restore the Co-Scientist apparatus as an opt-in path
0adb7dc  Paper route: write up a free run from its wall-verified findings (+figures)
20e8037  Model selection: three tier knobs (heavy / light / triage)
45306a5  Director fan-out: one decision can explore a cycle in parallel (run_fan)
```
