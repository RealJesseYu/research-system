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

### ④.2 — A free-deciding director as the entry. **[the heart — next]**
**Restriction removed:** the arc is a hardcoded sequence; no agent decides what
to do next. `pi_agent/` exists but its only moves are to dispatch a *whole
fixed-pipeline supervisor run* as a subprocess.
- **Change:** widen the director's action space (manifest §6-step-5) so that,
  given a goal + memory/arc, it can dispatch an **investigation** directly — the
  experimenter loop is the investigation primitive — and choose the ideation
  depth for it. Keep it **thin**: a free agent that picks {investigate this
  question, stop} from goal+arc, NOT a growing typed menu of moves (plan §C1 —
  "if you catch yourself adding move #4/#5/#6 as special cases, stop").
- **Risk:** medium/high — this is the real architectural move. Design fork to
  settle before building: does the director reuse `run_exact_route`'s
  investigation as the primitive it calls with a goal, or a new lean entry that
  skips gate-1 entirely? (Leaning: the experimenter loop IS the primitive; the
  director hands it a goal, and ideation becomes a *tool the director calls for
  candidates* when it wants breadth — not a mandatory first stage.)

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
