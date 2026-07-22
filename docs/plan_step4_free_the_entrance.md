# Step ④ — Free the entrance (the autonomy payoff)

**Written:** 2026-07-22. **Branch:** `iterate-experiment-loop`.
**Why this exists:** M1 routed exact tools into the free experimenter loop and M2
deleted the dead ceremony — but every run is still forced down the rigid
**full-ideation → gate-1 (collapse to ONE hypothesis + ONE instrument) →
execute** funnel. The experimenter is free only *inside* the box gate 1 already
closed. Step ④ removes that funnel so the system can decide its own arc — the
part of the vision that ends "on rails."

**The wall is untouched.** Everything below keeps `stages/verification.py` and
the propose→measure→verify boundary exactly as-is. Freedom in HOW it
investigates; a hard wall only at the result boundary.

---

## The three bricks (smallest/safest first)

### ④.1 — Ideation on-demand (default quick). **[building now]**
**Restriction removed:** full ideation apparatus fires on every run.
`stage1_ideation.run(baton, depth=...)` already supports `quick` (one
literature-grounded generation, same delivered `{hypotheses, hypotheses_ranked}`
contract) vs `full` (the whole Co-Scientist apparatus). Today the supervisor
always calls it with the `full` default.
- **Change:** thread `ideation_depth` through the supervisor, default **quick**;
  escalate to `full` via a `--ideation-depth full` flag (and, later, a director
  decision). `stage1_ideation.run`'s OWN default stays `full` — that protects the
  kill-rate battery and direct callers, which need the full apparatus. The
  default lives at the supervisor layer, exactly where the manifest §6-step-1
  said to put it.
- **Risk:** low. Same downstream contract; gate 1 and stages 2–6 unchanged;
  test seam (stub stages) untouched. Reversible with the flag.

### ④.2 — Make the free director runnable as THE entry. **[building now]**
**CORRECTION (2026-07-22, verified in code):** the free-deciding director is
**already built and tested**, not "not started" as an earlier draft said —
`pi_agent/loop.py investigate(goal, *, allowed_substrates, mode, max_moves)`:
open a study → loop [free Opus decides the next question/move/instrument over the
arc (`decider.py`) → dispatch it (`dispatch.py`) → record] until the PI judges it
done or the hard `max_moves` ceiling → write a study report. Tests:
`test_pi_loop`, `test_pi_dispatch`, `test_pi_study`, `test_pi_gate`. Do NOT
rebuild it (plan §"DO NOT rebuild").
**What is actually missing:**
- **④.2a — a CLI entry [this brick].** `investigate()` is a library function
  with no `__main__`/argparse, so "give it a goal and walk away" is not a runnable
  command; the owner runs `supervisor.py` (a single run) instead. Add
  `python -m pi_agent --goal "..."` wrapping the existing tested `investigate()`.
  Small, safe (new entry point, no behavior change), tested.
- **④.2b (later, lower priority):** each director move dispatches a *full
  `supervisor.py` pipeline run* (`_default_command`), so the experimenter loop is
  reached only inside a dispatched run (post-M1, for exact instruments), behind
  that run's ideation + gate-1. Making the experimenter a first-class director
  move is possible but less urgent now that M1 already routes dispatched runs to
  it. Keep it **thin** — no growing typed menu (plan §C1).

### ④.3 — De-funnel gate 1 (no forced single hypothesis + single instrument).
**Restriction removed:** every run collapses to ONE hypothesis and ONE instrument
before the experimenter thinks; the experimenter is handed that one hypothesis as
its whole goal.
- **Change:** for the exact/experimenter path, let the investigation receive the
  goal/domain (or a small candidate set) and self-direct, composing whatever
  exact tools it needs — the experimenter already composes multiple exact tools
  inside its loop; only the *entry* forces one. Gate-1's instrument pick becomes
  "is an exact path available?" rather than "pick the one instrument."
- **Risk:** medium. Touches the gate-1 payload shape / routing — check against
  the locked schema (`substrate_id` is a locked post-gate-1 key; changing its
  role is STOP-and-rule). May be doable without a schema edit by keeping the
  field but relaxing what fills it. Settle when we reach it.

---

## What stays (guardrails, unchanged)
- `stages/verification.py` — the wall. No model in the verification path.
- Cavity byte-identity; the approximate-instrument pipeline (fidelity gate +
  stages 2–5) — approximate tools keep the rigid path; they have no experimenter.
- Hard `max_moves` / turn budgets on any open-ended director/experimenter loop.
- Never `git add -A`; STOP-and-rule for locked schemas / trust-bearing config.

## Sequence
④.1 now (safe opener) → ④.2 (settle the design fork, then build the thin
director) → ④.3 (de-funnel the entry). Each brick is tested-first, suite green,
committed with explicit paths.
