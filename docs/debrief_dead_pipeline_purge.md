# Session debrief — the dead-pipeline purge

**Date:** 2026-07-23. **Branch:** `iterate-experiment-loop`.
**Commits:** `11ff177` → `800243f` → `c45fb48` (this debrief adds one more).
**Suite:** 1364 passed, 1 skipped (from a 1806 baseline; the drop is deleted
legacy tests, not lost live coverage).

---

## What this session did

Executed §3 of `docs/handoff_free_agent_purge.md`: **deleted the dead static
pipeline.** Free is already the default production entry, so the whole
six-stage relay + its scaffolding was dead code. It is now gone. The free agent
is the ONLY production path.

Done in careful, suite-green sub-steps, each traced before cutting (the handoff
warned a prior session got burned by asserting-without-tracing):

| Commit | Cut | Suite after |
|---|---|---|
| `11ff177` | Supervisor gutted **1980 → 235 lines**: static relay, 3 gates, loop/retry/barren/desk/crash machinery, substrate maturity hook, `LEGACY_PIPELINE` switch. Deleted `gate1_chooser` + the three unimported handfeed side-doors. | 1806 |
| `800243f` | Director's in-process **CHAIN move + `chain_runner`** deleted (the decider never emitted it). Dead-stage **harness batteries** deleted (fidelity_case_runner, calibration_battery, triage_battery, validation_batch) + c13 probe; `run_harness` slimmed to killrate + paperlint. | 1438 |
| `c45fb48` | **`stage2_experiment_design` + `stage3_fidelity_gate` + `handfeed_stage2`** deleted. 8 wholly-dead test files removed; 7 mixed test files surgically reworked to keep their live coverage. | 1364 |

Net: ~60 files deleted, ~15 reworked.

## What this bought

The repo no longer carries a deterministic six-stage pipeline that outweighed
the free agent it was meant to serve — the "cage heavier than the chat" the
PRIME DIRECTIVE targets. Nothing about a production run changed (it already went
straight to the free agent); the win is that the codebase now describes what it
actually does, so no future session can drift back into treating the caged
pipeline as the real architecture. Substrates remain fully available as optional
tools (the catalog the free agent sees is intact).

## Two corrections to the handoff (found by tracing, not asserting)

The handoff listed these as deletable. They are **live tool infrastructure** —
deleting them would have broken the free agent's substrate dispatch. **KEPT:**

- `stage4_case_builder` — `tools/substrate_dispatch` calls `build_case()`
- `stage4_simulation` — `tools/substrate_dispatch` imports `translate_qoi`
- `stage2_spec` — `tools/substrate_selection` imports its validators

Also kept by design: `stage5_thought_layer` (inert; the locked `schemas.py`
imports it — owner ruling "option a": leave the schema inert, never touch the
locked file); `campaign_controller` (owner WIP in its test; it feeds the live
`stage4_simulation`). `capability_guard`'s sealed-stage name strings for the
deleted stages are harmless vestigial policy, left in place.

## Loose ends for the owner

- `tests/test_campaign_controller.py` carries owner WIP **plus** a one-method fix
  (removed a test of the deleted maturity hook) — left **uncommitted** so the WIP
  isn't bundled. Commit it when ready.
- Owner-dirty files (`CLAUDE.md`, `memory/journal.jsonl`, etc.) were never staged.

## What's next (not started this session)

1. **Per-run workspace** — the free agent writes artifacts to the repo ROOT
   (`collatz/`, `run_tpsa_check.py`, `artifacts/` are visible in `git status`).
   Give each run a `runs/<id>/workspace/`. Smallest, highest-value fix.
2. **Controller re-verify** — `verified=True` is currently the agent re-running
   its own number. Wire a deterministic no-model re-run of the saved artifact
   (the wall, on a kept number). Depends on #1.
3. **Wire a connector** — add an MCP connector to the FULL profile so the agent
   reaches a tool that isn't already a substrate wrapper (any domain). The jump
   to genuinely-new capability; lands better after #1–2.

Recommendation: #1 then #2 as a pair — they are the "reproducible records" half
of the "a chat, AND MORE" value proposition.

Memory updated: `memory/purge-dead-pipeline-done.md` (+ the MEMORY.md pointer)
records the outcome and the LIVE-not-dead corrections so the next session won't
re-attempt deleting the kept modules.
