# Why move 16 stopped at 17M of 53M — the real mechanism

Task 5 of the arm-C post-mortem: *"An agent that quits two-thirds under budget and
misreports why cannot be planned around. Find the real stopping mechanism. Report
findings; do not ship a speculative fix."*

**Found, and it is not m16-specific: 9 of the 12 completed moves in the study were
cut off by the same mechanism, and every one of them was told a false reason.**
No code is changed by this document. The fix is a two-line arithmetic correction
and is written out at the end, unapplied, because it materially changes how much
every future move may spend and that is the owner's call.

Every number below is re-derived from disk: `memory/journal.jsonl` run_records,
`studies/study-20260730T034915Z/`, and the Claude Code CLI session transcripts
under `~/.claude/projects/…-m*-workspace/`. (Those CLI transcripts are a
different artefact from `runs/<id>/transcripts/`; nothing here reads any
transcript back into a model input or into stage logic — this is hand
diagnosis, which the invariant explicitly permits.)

## The answer in one line

m16 was stopped by the **turn** wind-up in `model_call.py`, which fired at "turn
197 of 200" — and `turns_seen` counts **SDK content blocks, not turns**, so it
tripped after **97 real assistant turns**, less than half the 200 granted. The
agent was then handed a message beginning `TOKEN ALLOWANCE EXHAUSTED`, and it
repeated that in its report. Its claim was a faithful quotation of the harness.

## The evidence

**1. The trip is in the m16 session transcript, verbatim** (row 374, a denied
`Write` at 09:56:08Z, immediately before the final JSON):

> `TOKEN ALLOWANCE EXHAUSTED for this move (turn 197 of 200 granted for this
> call — the remaining turns are the wind-up reserve). No further tool calls will
> be permitted in this call. Stop investigating now and write your final answer…`

**2. The token half had 36M of headroom.** m16's brief stated
`TOKEN ALLOWANCE FOR THIS MOVE: ~52,871,869`. Its run_record cost is
`tokens: 17,056,120`. `_derive_granted_turns(52.9M, 200) = min(200, 2643) = 200`,
so `soft_stop = 200 − WIND_UP_RESERVE_TURNS = 196`. The token condition
(`tokens_seen >= remaining_tokens`) never came close; the turn condition did.

**3. `turns_seen` counts content blocks.** `_MoveBudgetTracker.note_assistant_message`
is called once per `AssistantMessage` the SDK yields, and the SDK yields **one per
content block** of a single API message. In m16's transcript there are **199
assistant events for 97 unique message ids** — blocks per message
`{2: 47, 1: 24, 3: 23, 4: 3}`. One API message appears as up to four events:

```
msg_011CdXzpeyFqmN3TaMqgsjZ1  blocks: ['thinking']   usage.output_tokens: 1893
msg_011CdXzpeyFqmN3TaMqgsjZ1  blocks: ['text']       usage.output_tokens: 1893
msg_011CdXzpeyFqmN3TaMqgsjZ1  blocks: ['tool_use']   usage.output_tokens: 1893
msg_011CdXzpeyFqmN3TaMqgsjZ1  blocks: ['tool_use']   usage.output_tokens: 1893
```

**4. The same event repeats the same `usage`, so `tokens_seen` is inflated too.**
`note_assistant_message` adds `sum(usage.values())` on every event, and every
event of one message carries that message's identical usage. Summing m16's
transcript the way the tracker does gives **34,734,493 face-value tokens** against
a metered **17,056,120** — a **2.04×** overcount.

**5. It is not one move. It is nine.** Trip text extracted per move, beside the
SDK-reported turn count in each run_record:

| move | assistant events | metered turns | ratio | wind-up | trip reported as |
|---|---|---|---|---|---|
| m3 | 186 | 85 | 2.19 | YES | measured in-call spend (24,281,841 face-value tokens) |
| m4 | 69 | 1 | — | YES | turn 205 of 200 |
| m5 | 90 | 52 | 1.73 | no | *finished voluntarily* |
| m6 | 104 | 54 | 1.93 | no | *finished voluntarily* |
| m7 | 61 | 8 | — | YES | turn 206 of 200 |
| m8 | 96 | 55 | 1.75 | YES | turn 196 of 200 |
| m9 | 264 | 40 | — | YES | turn 196 of 200 |
| m11 | 195 | 119 | 1.64 | YES | turn 196 of 200 |
| m12 | 199 | 124 | 1.60 | YES | turn 197 of 200 |
| m14 | 42 | 26 | 1.62 | YES | turn 230 of 200 |
| m15 | 103 | 57 | 1.81 | YES | turn 221 of 200 |
| m16 | 199 | 105 | 1.90 | YES | turn 197 of 200 |

(m10 and m13 are the two transport crashes and produced no cost record.)

Only **m5 and m6** ever chose to stop. Every other completed move in the study was
cut off — including **m11, the one move that reproduced 12/12**, and **m15 and
m16, the two moves the director spent on making the core reproduce**. Both died
"in the last mile, after the expensive rebuild, before writing the trivial
producer files" exactly because the tool that writes those files was denied.

**6. m3's trip was on tokens, and the same overcount cut it at 37%.** m3 was a fan
member; its brief stated `TOKEN ALLOWANCE FOR THIS MOVE: ~23,840,254` (the
`_fan_member_allowance` share of ~143M over 6). The tracker tripped at
`24,281,841` — but m3's metered spend is `8,713,891`. A **2.79×** overcount ended
it having really used **37%** of its share.

**7. Turn counts above 200 prove the counter is not counting turns.** m14 tripped
at "turn 230 of 200" and m15 at "turn 221 of 200"; a counter that can pass its own
ceiling by 30 before the next tool call is counting something the ceiling was
never denominated in. m4 and m7 (69 and 61 assistant events against 1 and 8
metered turns) are inflated further by the re-ask loop, which builds a fresh
tracker per attempt but runs inside one metered call.

## Why the reported reason was false, in both moves that reported one

- **m16: "the token budget ran out."** It was told, in those words, by
  `_WIND_UP_MESSAGE`, whose text says `TOKEN ALLOWANCE EXHAUSTED` **regardless of
  which of the two conditions tripped**. Its brief had also opened with
  `TOKEN ALLOWANCE FOR THIS MOVE: ~52,871,869`. The agent joined the two
  correctly. The harness is what was wrong.
- **m15: `make_producers.py` "is already written".** Verified false —
  `runs/study-20260730T034915Z-m15/workspace/` holds 28 entries and none is
  `make_producers.py`; no file matching `*producer*` exists in the m14, m15 or m16
  workspaces. m15 tripped at "turn 221 of 200", so its `Write` was denied while it
  was still describing what it was about to do, and its final report describes the
  plan as executed. Same root cause, different symptom: the wind-up arrives
  mid-intent and the wrap-up narrates intent as fact.

**So the blocker channel is not "unverified prose" by nature.** Both false claims
trace to one mechanism that stops an agent abruptly and mislabels why. That does
not make blocker prose trustworthy — it is still model text — but the fix for
these two instances is upstream of the channel.

## What was NOT the cause (each checked, each ruled out)

- **Not the token allowance.** 17.1M of 52.9M, and the tracker's own inflated
  figure (34.7M) was still under.
- **Not the SDK turn ceiling.** `FULL.max_turns = 200`; the SDK reported 105.
- **Not layer 2, the derived turn bound.** `52.9M // 20_000 = 2643`, capped by the
  profile to 200 — the allowance never reduced the ceiling.
- **Not layer 3, the pre-attempt refusal.** One call, `calls_with_turns: 1`; no
  `TokenAllowanceExhausted` was raised and no `halted_token_allowance` record
  exists.
- **Not the context window, and not compaction.** Context grows monotonically from
  70,176 to **288,605** tokens with no drop anywhere — a compaction would show as
  a collapse and a cache-creation spike, and m16's cache creation (270,196;
  2,573/turn) is in line with m12 (2,465) and m11 (3,239).
- **Not wall-clock, not a crash, not an external kill.** The run completed, wrote
  `free_investigation.json`, and journaled a normal run_record.

## STATUS: FIXED 2026-07-30 (owner ruled: fix it)

All three items below shipped. `note_assistant_message` dedupes on the SDK's
`message_id` so a turn is a turn; the wind-up now carries a headline naming which
condition fired (`TURN BUDGET REACHED` / `TOKEN ALLOWANCE EXHAUSTED`) and a turn
trip says outright that the token allowance is NOT exhausted; and the wind-up
leaves a durable `WIND_UP` line in the run's `log.txt` plus a `cut_off` block in
the run_record, which `read_run_result` carries into the arc so the director can
tell a move that FINISHED from one that was CUT OFF. The token condition is
unchanged and pinned by test. **The cost consequence is accepted by ruling:**
moves cut at ~97 turns will now run toward 196, so a move's real cost roughly
doubles; it pairs with the derived ceiling shipped in `32ba045`.

The original write-up follows unchanged, as the record of what was found.

## The fix, as written before it was applied

In `model_call.py`, `_MoveBudgetTracker.note_assistant_message` must count one
API message once. The SDK's `AssistantMessage` carries the message id; dedupe on
it, and both the turn counter and the usage sum become correct at a stroke:

```python
def note_assistant_message(self, usage, message_id=None) -> None:
    if message_id is not None and message_id in self._seen_ids:
        return                      # same API message, another content block
    if message_id is not None:
        self._seen_ids.add(message_id)
    self.turns_seen += 1
    if isinstance(usage, dict):
        self.tokens_seen += sum(v for v in usage.values()
                                if isinstance(v, int) and not isinstance(v, bool))
```

Two further things belong with it, and are named here rather than done:

1. **`_WIND_UP_MESSAGE` must say which condition fired.** It hardcodes
   `TOKEN ALLOWANCE EXHAUSTED` and then interpolates a `reason` that may say
   "turn 197 of 200". An agent stopped by the turn reserve must be told that, or
   it reports a budget it never spent — which is what happened.
2. **The wind-up should leave a durable record.** It `print()`s to stdout; the
   run's `log.txt` has no line for it, which is why this took a session to find.
   It belongs in `log.txt` beside RE-ASK and the fence NOTE, and arguably in the
   run_record so the director can see that a move was cut off rather than
   finished.

**Why this is not shipped here.** Correcting the counter roughly doubles the turns
and roughly triples the in-call token headroom every move actually gets, on the
one path that bounds spend inside a move. That is a budget-policy change with a
real cost consequence, on a system whose next act is a week-ending run. It needs
a ruling, not a quiet commit. The diagnosis is complete and the patch is four
lines; the decision is not mine.

**One consequence to weigh with it.** With the counter fixed, moves that were
being cut at ~97 turns will run toward 196, so a move's real cost roughly doubles
— which is an argument for pairing the fix with the corrected ceiling from task 3
rather than shipping it alone.
