# Incremental emission — T0.2 built, and what it does and does not catch

**Built 2026-07-30.** Roadmap item `docs/roadmap_capability.md` T0.2. Code:
`tools/emit_finding.py` (the full rationale is in its module docstring),
`stages/free_experimenter.py::_read_emitted / _merge_emitted`, one paragraph of
`SYSTEM_PROMPT`, and a three-sentence amendment to
`model_call.py::_WIND_UP_MESSAGE`.

## The failure, re-derived from disk

From `runs/study-20260730T034915Z-m15|m16/free_investigation.json` and
`verification.json`, not from the study's write-up:

| move | findings | with an artifact | verified |
|---|---|---|---|
| m15 | 34 | **0** | 0 |
| m16 | 26 | **0** | 0 |

Both moves did the expensive work and computed every number for real. m15's own
`blocked_on` names the nine producer files it never wrote and points at
`make_producers.py` — **the batch emitter it wrote and never ran**, still in its
workspace. m16's says it in one line: *"the token budget ran out after the data
rebuild and analysis but before the producer files were written."*

Both were cut off by the turn wind-up (`docs/finding_m16_stopping_mechanism.md`
tabulates 9 of 12 completed moves stopped the same way).

## Why shape discipline did not cover it

`SYSTEM_PROMPT` already carried ONE SCALAR, ONE FILE **and** `WRITE EACH ONE AS
YOU GO` (`tests/test_producer_discipline.py` pins both). m15 understood the shape
and planned exactly it — as **one batch, at the end**. The gap is WHEN, not HOW,
and the batch is the entire defect: N producers written together is one
all-or-nothing event, so a move cut off anywhere before it loses all N.

A stronger sentence was the weakest option on the table. The sentence was already
there, and this project has now watched a requested-but-unenforced structure fail
to happen three times (the paper skeleton, which needed `study_lint.py`; units,
still only asked; and this). What was missing was not instruction but a **reason
to pay the cost now rather than later** — and that reason has to be mechanical.

## What was built

`emit("m_b_sn.py", "b_sn", units="1", label="...")`, one Bash line from the
agent's workspace:

1. runs that file through **the same entry point the verification wall re-runs
   artifacts with** (`tools.run_python_experiment`, `--network=none`, same
   ceilings) and reads `metrics["b_sn"]`;
2. on success appends one line to `emitted_findings.jsonl` in the workspace,
   already shaped as a finding with its `artifact` filled in;
3. on failure appends **nothing** and returns the sandbox's own diagnostics.

`_merge_emitted` then folds that channel into the run's findings after the call
returns, with two effects:

- **APPEND** — an emitted quantity absent from the report becomes a finding.
  *This is the m16 shape: the work happened, the report did not.*
- **UPGRADE** — a reported finding naming the same quantity but carrying no
  artifact adopts the emitted producer. *This is the m15 shape: 34 real numbers,
  every artifact field empty.* A finding that already names its own artifact is
  left alone — the agent's choice beats the channel's.

Nothing downstream needed changing: everything reads
`runs/<id>/free_investigation.json`, so merged findings reach the wall, the
quantity register (T0.1), the paper and the director by the paths that existed.

**The incentive is the mechanism.** What `emit` writes enters the record whether
or not the agent survives to mention it, so emitting early is the only way a
number is safe. That is what a prompt sentence could not supply.

### Crash salvage

An escaping exception used to lose the whole move. Now, *if and only if* the
channel has something in it, the run is finalized from it — same wall, same
files — and the exception is re-raised afterwards, so a crash is still a crash
and `run_exact_route` journals it exactly as before. **Nothing emitted ⇒
re-raise immediately, byte-identical to before.** The salvaged summary names
itself as a salvage so no reader mistakes it for the agent's own account.

## Why the wind-up message does NOT ask for producers

The wind-up is the one moment the agent is guaranteed to be listening — and the
one moment it can do nothing about this, because **the same tracker that sends
the message denies every tool call**
(`_wrap_can_use_tool_with_allowance`, `_wrap_hook_with_allowance`). m16's session
transcript is the proof: a `Write` denied at 09:56:08Z carrying that exact text,
immediately before its final JSON. Asking there for producers would ask for what
the harness has just forbidden.

Widening the reserve to let a Write through was considered and rejected: the
reserve exists to guarantee the final answer gets written, and an agent granted
writes at wind-up can spend all of it emitting files and return nothing — losing
everything instead of the tail.

So the message is amended only to the two things that cost no tool call: *what
you already emitted is saved and picked up automatically*, and *name the producer
file you already wrote as that finding's artifact*.

## ADDITIVE — pinned

`SCHEMA["required"]` is unchanged; `_validate_free_result` never mentions
emission; nothing blocks, fails or shapes a move; a run that never calls `emit`
writes no channel file and behaves exactly as before. A test greps `stages/`,
`pi_agent/` and `tools/` and pins that **no production code calls `emit`** — the
agent calls it or it does not; a stage calling it for the agent would be the
harness authoring findings.

`stages/verification.py` is untouched.

## Honest limits

- **UNPROVEN ON A REAL RUN.** Like T0.1, the next study is the measurement.
  What *is* live-proven (2026-07-30, real docker sandbox): a numpy producer
  emitted `b_sn = 0.56` correctly, and a producer that opens a URL was refused
  with the sandbox's own traceback and wrote nothing.
- **Double execution.** A producer runs once at emit and again at the wall.
  Deliberate — the wall must stay independent — and the cost is one sandbox
  spin-up per number.
- **Emit passing does not guarantee the wall passes.** A nondeterministic
  producer can differ between the two runs. That is the wall working.
- **The channel holds proven producers only.** A failed producer emits nothing,
  so a number whose file never worked is still only as safe as the agent's
  report. This is the right trade: the alternative puts unbacked numbers into the
  record from nowhere.
- **Merge keys on quantity NAME, never on label.** An emitted number whose name
  matches no reported finding is appended with `emit`'s generated label rather
  than the agent's prose. Mechanical beats clever here; a fuzzy label match would
  silently attach a producer to the wrong number.
- **Re-emitting one name does not multiply findings — first wins.** Two values
  under one name is a *contradiction*, and adjudicating contradictions is the
  quantity register's job (T0.1), not the merge's.
