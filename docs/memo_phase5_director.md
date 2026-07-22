# Phase 5 memo — widening the director (R-DIR ruling)

Deliverable toward the owner's north star's *arc* half: a director that pursues a
goal over many cycles, **decomposing it into questions and sequencing them** —
not just running one experiment. Manifest §6 step 5 ("widen the PI action space
beyond run_single/run_campaign/stop so the director can dispatch investigations
and set ideation depth"). Written 2026-07-21. Builder ruling, **owner-amendable**;
recorded before the action-space change, per STOP-and-rule.

## What is already here (checked, not assumed)

- **The PI loop** (`pi_agent/loop.py`): `investigate(goal, max_moves, …)` — decide
  (an Opus call over the arc) → build a `Move` → dispatch it → record in the arc,
  under a hard `max_moves` ceiling. The decision carries `next_domain` (the
  question for the next run) and an optional `instrument`.
- **The decider** (`pi_agent/decider.py`): `DECISION_VALUES = (run_single,
  run_campaign, stop)`. This is the 3-move action space.
- **The dispatch layer** (`pi_agent/dispatch.py`): `MoveType` already has
  **SINGLE, CAMPAIGN, CHAIN** and a uniform `invoke_move`. So a new move type is
  additive to machinery that already exists.
- **The gap the first live outing exposed:** the experimenter
  (`tools/compose_agent.py` driving `run_investigation`) receives `state`
  (measurements, budget, iteration) but **no research question**. With no goal it
  self-directs to wiring self-tests (exactly what the outing did). A director that
  dispatches an investigation must be able to tell it WHAT to investigate.

## Ruling

**R-DIR-1 — The experimenter must accept a question (the enabling first brick).**
`run_investigation` gains an optional `goal` threaded into the strategy `state`;
`compose_agent` surfaces it as `research_question` in its input and its prompt
pursues it when present. Absent (a standalone probe), behaviour is unchanged —
the experimenter self-directs as before. This is the atom every director move
below depends on, and it ships and is tested first.

**R-DIR-2 — A new PI move: `run_investigation` (dispatch the experimenter).**
`MoveType.INVESTIGATION` + an `invoke_move` branch that runs the experimenter loop
on the decision's `next_domain`, returning the same `MoveResult` envelope
(succeeded = the investigation is publishable). Added to `DECISION_VALUES`, the
decider menu, and `loop._DECISION_TO_MOVE_TYPE`. The experimenter is the
exact-tool, tool-composing investigator; a `run_single`/`run_campaign` stays the
full static pipeline. The PI chooses which fits the question. Its own recorded
brick, after R-DIR-1.

**R-DIR-3 — Ideation depth as a director choice.** The decider may set
`depth` (`quick` | `full`) per move, threaded to `stage1_ideation.run(depth=…)`
(the switch is already built). Cheap by default; escalate when the question
warrants. Its own brick.

**R-DIR-4 — Goal decomposition (the intelligence, last).** The director's real
value — break a goal into sub-questions and sequence them — is a decider-prompt
and arc-shape change, built ONLY once R-DIR-1..3 give it the moves to sequence.
No new mechanism is invented ahead of the moves it would drive (no gold-plating).

## Scope discipline

Each brick is proven by a test before the next; the loop is already exercisable
offline with faked `decide`/`run_move`, so every brick is provable without a live
model. No schema change, no measurement path touched, no `git add -A`. The hard
`max_moves` ceiling (loop.py) is never loosened — an open-ended loop of powerful
agents must stay bounded.
