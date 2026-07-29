# Plan — five additive improvements to the director

**Written 2026-07-29.** Owner ruled: do all five. This is the handoff — a fresh
session should be able to execute from here without re-deriving anything.

Companions: `docs/architecture.md` (why the system is shaped this way),
`docs/system_map.md` (every `file:line`), `docs/roadmap_status.md` (the checklist).

---

## The principle these five are chosen by

`study-20260728T225951Z` ($27.50, 26 verified findings) tested seven memory
policies in simulation and five against a real one-action-per-turn LLM director.
**Every bounded or summarised memory policy lost to the do-nothing floor** —
re-reading the whole arc — and some made the director three times worse.

The mechanism matters more than the scoreboard: an injected FALSE "already
answered" record was re-probed **0.0 times** under a summarised ledger and
**1.67 times** under plain full-arc re-read. A summary can carry a wrong belief
that nothing ever challenges. **The un-summarised arc is the self-correction
mechanism.**

So the line is not complexity vs simplicity. It is:

> **ADDITIVE — adds a capability the agent may use or ignore — is fine.
> SUBSTITUTIVE — replaces the agent's access to what actually happened — is not.**

The carry bus is a complex add-on and ideation independently endorsed it
(h5/ev1: *"continuity is carried better by re-executable producers than by
natural-language conclusions"*). It adds artifacts and removes nothing. Memory
policies substitute for history. That is the whole difference.

**All five below are additive. None removes anything from the director's view.**
Anything proposed later must pass that test before it is built.

---

## 1. Wire parallel fan-out into the free director  ← START HERE

**Why first:** it is mostly wiring something that already works, and it attacks
the real ceiling on long research. Every move in the last study was **69–84
agentic turns and ~1 hour of wall clock**, strictly sequential — four moves took
about three hours. A 15-move study is a 15-hour serial chain. Memory was never
the wall; **wall-clock serialism is.**

**What already exists:** `pi_agent/study.py:378 run_study_fan(study, moves, *,
findings, invoke, runs_root, max_parallel=4)`. It is careful, finished code:
run-ids pre-assigned sequentially so two runs never share a directory; a bounded
`ThreadPoolExecutor` (each move is an external process, so threads are right);
results appended to `arc.jsonl` **sequentially afterwards**, so the append-only
arc is never written concurrently; a move that raises is caught and recorded as
a failed result rather than sinking the fan; results returned in move order.

**Its only caller is `pi_agent/loop.py:133`** — the enum director, which nothing
uses. The free director cannot reach it.

**To build:**
- A new action in the director's vocabulary. `ACTION_VALUES`
  (`free_decider.py:57-67`), `_ENVELOPE_FIELDS` (`:69-73`), and the validator
  (`make_action_validator`, `:119-238`) are all strict — a new field is rejected
  unless added in all three. Mirror how `depth` / `pool_size` /
  `novelty_priority` are done.
- The action needs **several domains**, so it needs a list-shaped field. Validate
  it: non-empty, every entry a non-empty string, and a sane upper bound.
- **Budget: an N-wide fan must spend N moves.** `budget.can_spend(N)` then
  `budget.spend(N)` — not 1. Getting this wrong breaks the conservation
  invariant, which is one of the few hard guarantees the system has.
- **The token allowance needs dividing.** `_move_allowance`
  (`free_director.py:56-66`) hands a dispatched move the **entire** remaining
  budget. With N running at once that over-grants N-fold. Split it, and say in
  the docstring what the split is.
- Record each fanned move in the arc as its own entry, so nothing downstream
  (cost report, liveview, resume) needs to learn a new shape.

**Traps:** `run_study_fan`'s `invoke` seam defaults to `dispatch.invoke_move`;
keep the seam. Resume accounting (`_moves_consumed`, `free_director.py:416-436`)
counts move-consuming arc types — a fan's entries must be counted correctly or
`--resume-study` will mis-add.

---

## 2. Show the director its own trajectory

**Why:** it plans with almost no self-knowledge. It sees moves and tokens. It
does **not** see dollars, wall-clock, turns spent, or its own decision cap
(`free_director.py:640` — invisible to it). You cannot pace a long campaign
without knowing your runway.

**Why it is nearly free now:** item C (`a1b7dae`, 2026-07-28) began recording
`usd`, `turns` and the per-field token breakdown on every arc entry. **The data
already exists and is simply not surfaced.**

**To build:** extend `_budget_view` (`free_director.py:516-546`) with dollars
spent, agentic turns spent, and decisions remaining against the cap. Display
only — no new collection, no new constraint. Keep the never-raise discipline:
the view already degrades to `"unknown — token accounting failed this turn"`
rather than lying, and anything added must do the same.

---

## 3. Let the director record a prediction, and see it against the outcome

**Why:** this is h13's insight — the one genuinely interesting thing ideation
produced — moved to the additive side of the line. **h13 failed because it used
predictions to decide what to FORGET.** Used additively the prediction decides
nothing; it is a column that gets compared to what happened, giving the director
a calibration signal on its own judgement across a long arc. That is
self-correction, which the false-record result says is the thing that matters.

**To build:** an optional field on the action — what the director expects this
move to show. Store it on the arc entry beside `finding`. On subsequent turns
show prediction next to outcome so the comparison is in front of it.

**Do not:** gate anything on it, score it, or let a wrong prediction change what
the director may do next. The moment it constrains, it has become substitutive.

---

## 4. Intermediate signal from a running move

**Why:** a move is atomic today — dispatch a subprocess, wait an hour, read
JSON. 69–84 turns happen with **zero visibility and no ability to redirect.**
On a 15-hour run that is most of the run spent blind.

**The seam that exists:** `runs/<id>/log.txt` is appended live and `liveview`
already reads it; the director does not. The harder version is streaming from
the SDK call itself.

**This is the same seam interjection needs**, so design them together — but note
the owner's ruling that interjection is probably not V1.

**Hardest of the five. Do it last, or after a long run shows what is actually
missing.**

---

## 5. ev2 — persist failed producers with the regime that broke them

**Why:** the one untested idea ideation produced. *"Continuity is carried better
by a persisted corpus of failed and superseded re-executable producers — each
stored with the input regime in which it broke — than by a high-fidelity library
of successes alone, because deliberately lossy, error-tagged transmission acts
like immune negative selection: success-only chains ratchet capability on the
familiar regime while progressively losing the ability to detect that the regime
has shifted."*

Move 2's simulated "negative store" won at 1.55x and then died against a real
director — **but that was at the memory-policy level, where it substituted for
history.** ev2 as stated operates at the **artifact** level, alongside the carry
bus, adding failed producers next to successful ones. That is additive.

**To build:** extend the carry bus (`_carry_block` / `inherited_artifacts`,
`free_director.py:136-200`) to carry a bounded set of failed/superseded
producers tagged with the regime in which they broke.

**Caveat to respect:** its simulated ancestor is already once-refuted. Treat
this as a hypothesis to test, not a fix to ship — and prefer measuring it
against a matched floor, the way move 4 did.

---

## Order, and why

1. **Fan-out** — biggest gain, mostly wiring, attacks the real ceiling.
2. **Trajectory** — nearly free, data already recorded.
3. **Prediction column** — small, additive, gives the long arc a self-correction signal.
4. **ev2** — a hypothesis; measure it, do not assume it.
5. **Intermediate signal** — hardest; design with interjection, after a long run.

1 and 2 together are the cheapest real increase in director capability
available, and both are offline.

---

## Rules that carry

- **PRIME DIRECTIVE:** never make either agent less capable than a bare chat
  with tools. Every item above is additive by construction — keep it that way.
- **Nothing ends an arc except the director.** Fan-out especially: a failing
  member is a recorded result, never a crash.
- **Verification purity** — no model in `stages/verification.py`, ever.
- **Never `git add -A`** — other sessions work in this tree.
- **STOP-and-rule** — a contract or locked-schema change gets recorded in
  `docs/`, not decided quietly.
- **Do not launch a live run to test these.** The owner's weekly compute is
  reserved for the long run. Offline tests only.

## Known traps in this repo

1. **Assert-without-looking.** It caught the coordinating session three times in
   two days, including a claim that ideation had never run when it had run
   three times. Check before claiming.
2. **Unchecked edits** — a string-replace that silently misses ships code
   reading a flag that was never added.
3. **A smoke test that cannot reach the change** — exercise the branch you wrote.
4. **Test fakes have signatures** — widening an injected callable breaks
   three-arg fakes silently; use the `_seam_accepts_*` idiom.
5. **Shadowing test helpers** — a module-level `_snap()` in an appended block
   once broke 16 unrelated tests.

## Verify before finishing

    venv/bin/python3 -m pytest tests/ -q     # expect 2203 passed, 1 skipped

`tests/test_run_code.py::TestJails::test_timeout_kills_container_and_leaves_nothing`
is a known Docker flake that passes on re-run.
