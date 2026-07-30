# Is an experimenter move that crashed before writing anything safe to retry?

**Status: ANALYSIS ONLY. Nothing is merged, no code changed.** This memo answers
the question that was asked and stops there.

**The answer, up front: NO — not on the rule as proposed.** "Crashed before
writing anything" is not decidable from outside with the evidence the system
currently keeps, and the two crashes that motivated the question fall on OPPOSITE
sides of the line. One wrote nothing. The other wrote 94 files over 29 minutes.
A rule that cannot tell them apart would have replayed the second.

There IS a sound narrower rule, and a cheap way to make it decidable. Both are
described in §5. Neither is built.

---

## Contents

1. [What actually happened](#1-what-actually-happened)
2. [Why the retry is disabled here, and why the director is different](#2-why-the-retry-is-disabled-here-and-why-the-director-is-different)
3. [Is "wrote nothing" decidable from outside?](#3-is-wrote-nothing-decidable-from-outside)
4. [The side effects a workspace check cannot see](#4-the-side-effects-a-workspace-check-cannot-see)
5. [The narrower rule that would be sound](#5-the-narrower-rule-that-would-be-sound)
6. [Recommendation](#6-recommendation)

---

## 1. What actually happened

Two of 16 moves in `study-20260730T034915Z` died on the same exception:

```
CRASH: crashed during free investigation
       (Exception: Claude Code returned an error result: success)
```

Read from disk, they are not the same event at all:

| | m10 | m13 |
|---|---|---|
| workspace entries | **0** | **94** (~6 MB) |
| run dir created | 02:24 | 04:21 |
| last workspace write | — | 04:52 |
| crash logged | 02:28 | 04:56 |
| elapsed before crash | ~4 min | ~35 min |
| files include | — | `aashto93_scoring.py`, `aft_interval.py`, `buffer_curve.csv`, `__pycache__/`, `_blob.txt` … |

Both left `log.txt` with an identical four-line story and an identical crash
string. **The exception is the same; the world it left behind is not.** m10 is a
clean candidate for replay. m13 had been working for half an hour and had written
most of a producer set.

This is the whole finding. The population of "transport crash" is not
homogeneous, and nothing in the crash itself distinguishes the two.

## 2. Why the retry is disabled here, and why the director is different

`model_call._transport_with_retry` (model_call.py:930-936) sets the retry budget
to zero for any tooled call:

```python
tooled = capabilities is not None and capabilities is not SEALED and capabilities.uses_tools
budget = 0 if tooled else len(TRANSPORT_RETRY_BACKOFFS)
```

The stated reason is exact: a tooled call "may already have written files or run
commands before the transport died, and blindly replaying the whole agentic loop
would re-commit every one of those side effects with nothing rolling them back or
even noticing."

`pi_agent/free_director.py:906` documents the one exemption, and its argument is
worth restating precisely because it does NOT generalise: the director's call
"produces a JSON decision and nothing else, so replay is safe. Hence the retry
here, at the one call site where idempotence is provable."

Note the word: **provable**. The director's idempotence is a property of its
CONTRACT — it is a sealed-shaped call whose only output is a returned object.
Nothing about it depends on inspecting what a particular invocation did. The
experimenter's contract is the opposite: writing files and running solvers is its
job. So the experimenter can only ever get a per-invocation, evidence-dependent
argument, never a contractual one. That is a weaker thing and should not be
called by the same name.

## 3. Is "wrote nothing" decidable from outside?

Three candidate oracles.

**(a) Workspace emptiness.** `runs/<id>/workspace/` is empty ⇒ nothing written.
Cheap, and it does separate m10 from m13 correctly. But it is unsound in the
direction that matters — see §4. It observes ONE directory and an experimenter
can affect state well outside it.

**(b) The action trail — the strongest available.** `model_call` already threads
an `action_trail` list through `_invoke_transport` (model_call.py:644-769) and
appends an entry for every `ToolUseBlock` and its result. The list is mutated IN
PLACE, so a partially-filled trail survives the exception and is still in scope
inside `_transport_with_retry`'s loop (model_call.py:938-955), which is exactly
where a retry decision is made. An empty trail means the agent invoked no tool at
all, which implies no side effect of any kind — not just no file.

Today that trail is only persisted on the SUCCESS path
(`_append_action_trail`, called at model_call.py:1339 after the call returns), so
on a crash it is discarded. It exists at the decision point; it is simply not
consulted or kept.

**(c) The crash string.** Useless. Identical for both moves.

**The hole in (b), which is the crux.** The trail records what THIS PROCESS
OBSERVED, not what the agent DID. `"Claude Code returned an error result:
success"` is `is_error=True` with `stop_reason='success'` — the CLI subprocess
reporting failure while claiming the underlying stop was normal. That is
consistent with a failure at or after the end of the loop, which is the benign
case. It is also consistent with a streaming or delivery failure in which
messages the agent genuinely produced never reached us — in which case the trail
is empty and the work happened anyway.

So an empty trail is strong evidence, not proof. m10's empty workspace is
independent corroboration for that ONE case, but "corroborated once" is not a
rule.

**Verdict on decidability: NO for the general claim "wrote nothing", YES for the
narrower observable "this process saw no tool call, and the workspace is
empty".** Those are different propositions and the difference is the whole
answer.

## 4. The side effects a workspace check cannot see

An experimenter move under the FULL profile can, before crashing:

| side effect | escapes the workspace? | reversible? |
|---|---|---|
| `docker exec` into a long-lived `*-prod` container (of12, ngspice, ccx, dolfinx…) writing under `cases/` | **yes** | no |
| an MCP connector call to an EXTERNAL service | **yes — off this machine entirely** | no |
| `run_python_experiment` sandbox job | no (`--rm`, `--network=none`, ephemeral) | n/a |
| journal / memory append | **yes** | no |
| cost meter and token spend | **yes** | no — replay always double-spends |
| files under `runs/<id>/workspace/` | no | in principle |

Only the third row is genuinely free to replay. The first two are why an
emptiness check on one directory is the wrong instrument: a move can leave that
directory pristine and still have posted to an external API.

The cost row deserves separate emphasis. Even a PERFECTLY safe replay is not
free: m13 burned ~35 minutes and its share of ~$18 across the two crashes. A
retry rule that is sound but doubles the spend on long moves needs a wall-clock
or token guard of its own, which is a second design question this memo does not
answer.

## 5. The narrower rule that would be sound

If this is ever built, the defensible version is:

> Retry a tooled experimenter call at most once, and ONLY when **all** of:
> 1. the in-place `action_trail` is empty (no tool use observed);
> 2. `runs/<id>/workspace/` contains no entries;
> 3. elapsed time before the failure is under a small bound (m10: ~4 min) — a
>    long silent run is more likely a lost stream than a fast clean failure;
> 4. the retry budget is 1, never the sealed path's full ladder.

Conditions 1 and 2 are independent oracles for the same fact, which is the point:
each covers the other's blind spot. Condition 3 is the guard against the
streaming-failure hole in §3, and it is a heuristic — it should be named as one
rather than dressed up.

**Two prerequisites, both currently missing:**

- the action trail must be PERSISTED on the crash path (a few lines near
  model_call.py:1339, which today only fires on success). Without it, the
  strongest oracle is thrown away at the moment it is needed;
- condition 1 must be threaded to the retry decision. The list is already in
  scope at model_call.py:938 — this is a read, not new plumbing.

**A cheaper alternative worth weighing first.** Persist the trail on crash and
change NOTHING else. The next few crashes then arrive with evidence attached, and
the question "was the trail empty when the workspace was empty?" becomes
measurable instead of arguable. Two data points — one of which contradicts the
proposed rule — is a thin base for adding an automatic replay to the one call
site the codebase deliberately exempted.

## 6. Recommendation

**Do not add the retry now.** The evidence base is two events that disagree.

**Do consider persisting the action trail on the crash path**, because it is
small, it is pure gain for post-mortems regardless of what is decided about
retries, and it converts this question from an argument into a measurement. It
also has a second payoff: m13's trail would say what those 29 minutes actually
accomplished, which right now is unrecoverable.

**If a retry is wanted sooner**, the honest framing is that it would be a
heuristic guarded by two corroborating oracles, NOT the provable idempotence that
justified the director's exemption — and the comment at
`pi_agent/free_director.py:906` should not be cited as precedent for it, because
its argument is contractual and this one cannot be.
