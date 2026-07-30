# `succeeded = bool(publishable)`: options and blast radius

**Status: ANALYSIS ONLY. Nothing is merged, no code changed.**

**The answer, up front:** the one-line assignment at `pi_agent/dispatch.py:547`
conflates two different questions — *did this move do its job?* and *did this
move answer the whole goal with reproduced numbers?* — and reports the second
under the name of the first. Experiment 2's move 3 ran, measured, and reproduced
21 of 21 claims, then entered the arc as `succeeded: false`.

The display half is already fixed (735d6e5, `liveview/reader.py:_move_state`).
What is NOT fixed is the value the **director reads** and the **failure taxonomy**
branches on. Four options below; **Option C is the recommendation**, and Option D
is the one that looks cheapest and is the trap.

---

## Contents

1. [The defect, precisely](#1-the-defect-precisely)
2. [Blast radius: every consumer](#2-blast-radius-every-consumer)
3. [Four options](#3-four-options)
4. [Recommendation](#4-recommendation)

---

## 1. The defect, precisely

```python
# pi_agent/dispatch.py:547
succeeded = bool(result.publishable)
```

`publishable` is set by the experimenter itself (`stages/free_experimenter.py:77`)
and its contract is a conjunction of two independent conditions:

> `"publishable": <true only if the question is answered and every kept finding reproduced>`

So `succeeded: false` currently means **at least one of**:

- the move never ran (dispatch error, crash, honest halt) — m10 and m13 above;
- the move ran, measured, reproduced everything, but was a SCOUT that was never
  asked to answer the whole goal;
- the move ran and answered the question but some finding did not reproduce;
- the move ran, answered, and reproduced — but the agent judged the answer
  incomplete.

Four different states, one bit. The middle two are *results*. The first is a
*non-event*. Treating them alike is what made a 21/21 reproduction read as a
failure.

The existing docstring already half-admits the problem — "a halt or an
unpublishable paper is a real outcome the PI reads, not a dispatch failure — but
it is not a success to build the arc on" — which is a defensible statement about
`publishable` and an indefensible one about a field named `succeeded`.

**Note a stale reference:** `liveview/reader.py:433` cites
`pi_agent/dispatch.py:528`; the assignment is now at line **547**. Worth fixing
whenever that file is next touched.

## 2. Blast radius: every consumer

Complete sweep of `succeeded` across `pi_agent/`, `stages/`, `liveview/`:

| site | role | effect of a change |
|---|---|---|
| `pi_agent/dispatch.py:547` | the assignment | the change itself |
| `pi_agent/dispatch.py:510` (`as_dict`) | serializes into `MoveResult.raw` | shape change reaches the arc |
| `pi_agent/study.py:238` | `record_move` writes it to the arc | **persisted** — old studies keep old semantics |
| `pi_agent/study.py:308` | `study_findings` — the PI's own read | **this is what the director reasons over** |
| `liveview/render.py:285` | `"stood" if succeeded else "ran"` | already guarded by `state` |
| `liveview/reader.py:430` `_move_state` | the landed three-state read | derives from `succeeded` + `outcome` |
| `pi_agent/free_director.py:217` | `_record_capability` for NON-run moves | different producer, same field |
| `pi_agent/capabilities.py` (12 sites) | capability moves set their own | independent of `publishable` |
| `stages/study_paper.py` / `build_critic.py` | read `verified`, NOT `succeeded` | **unaffected** — the paper path is clean |

**Two properties worth naming.**

*The paper and verification paths do not touch this.* `collect_study_evidence`
splits on each finding's `verified` flag, which is the wall's verdict. So no
option here can alter what a paper reports as established. That materially
lowers the risk of every option below.

*The arc is append-only and already written.* Any change is prospective. Existing
studies keep records written under the old meaning, so any consumer must tolerate
both — which is an argument for adding a field rather than redefining one.

## 3. Four options

### Option A — leave it, document it

Add a comment at :547 naming the conflation, and rely on `_move_state` for
display.

*Cost:* zero. *Benefit:* zero for the director, which never sees `_move_state` —
that lives in `liveview`, a read-only viewer. The thing that actually reads
`succeeded` to decide what to do next keeps reading a wrong bit. Rejected unless
nothing else is affordable.

### Option B — redefine `succeeded` to mean "the move ran and produced measurements"

`succeeded = result.outcome not in {dispatch_error, crashed, halted, ...}`.

*Pro:* the field finally means what its name says.
*Con:* it **silently changes the meaning of an existing key** that is persisted in
every past arc and read by the director. Old records say one thing, new records
another, and nothing on disk distinguishes them. Also loses the
"answered-and-reproduced" signal entirely unless something else carries it —
`publishable` survives inside `raw`, but the director's `study_findings` view
does not surface it today. Rejected: an undetectable semantic flip on
append-only evidence.

### Option C — keep `succeeded`, ADD the state the director should read *(recommended)*

Promote the three-state read that already exists into the arc record, alongside
the unchanged `succeeded`:

```
succeeded : unchanged, still bool(publishable)   # no past record reinterpreted
state     : "stood" | "ran" | "did_not_run"      # NEW, the honest read
```

`liveview/reader.py:_move_state` is already written, already tested, and already
encodes exactly the right three-way distinction — including the vocabulary
("a RESULT", not a failure). This option MOVES that logic to where the record is
constructed instead of leaving it in the viewer, then surfaces `state` in
`study_findings` so the director reads it.

*Pro:* purely additive, so append-only evidence is respected and old arcs stay
readable; no consumer breaks; the viewer keeps working via `view.get("state") or
<derive>`; the director gets the distinction it needs.
*Con:* two fields where a reader might expect one — mitigated by making `state`
the documented one to branch on and `succeeded` the legacy narrow flag.
*Blast radius:* `dispatch.py` (construct), `study.py:238/308` (persist + surface),
`liveview/reader.py` (import rather than define). The paper path is untouched.

### Option D — make the experimenter report scope, so `publishable` stops being asked the wrong question

Add a field distinguishing "I answered the whole question" from "I answered the
question I was given", so a scout can be publishable within its own scope.

*This is the one that looks cheapest and is not.* It changes a prompt contract
(`free_experimenter.py:77`), which means every already-recorded `publishable`
was produced under a different definition, and the field is consumed by the
verification and paper paths. It also asks a model to self-assess scope, which is
exactly the kind of judgement the system elsewhere insists on deciding in Python.
Worth revisiting only if scope-blindness shows up somewhere `state` cannot fix.

## 4. Recommendation

**Option C**, and only after there is a reason beyond tidiness — the concrete
trigger would be evidence that the director actually mis-steered on this bit
(re-running a scout it thought had failed, or abandoning a line that had in fact
reproduced). Experiment 2 proves the *display* misled a human; it does not yet
prove the *director* misread it, and that distinction should decide whether this
is worth spending on.

What makes C the right shape when it is spent: it is additive, it reuses logic
that already exists and is already correct, and it leaves both the append-only
arc and the verification/paper path untouched.
