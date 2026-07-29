# Intermediate signal from a running move — design record, deliberately not built

**Written 2026-07-29**, closing item 5 of `docs/plan_additive_director.md`
(A1–A4 landed the same day: fan-out, trajectory view, prediction column,
ev2 failed-producer carry). This records the design and the decision NOT to
build yet, per the plan's own instruction — *"Hardest of the five. Do it last,
or after a long run shows what is actually missing"* — and the owner's ruling
that interjection is probably not V1. STOP-and-rule: this is the write-up, so
the deferral is a recorded decision, not a quiet omission.

## The problem

A move is atomic: dispatch a subprocess, wait ~an hour, read JSON. 69–84
agentic turns happen with zero visibility and no ability to redirect. On a
15-hour run that is most of the run spent blind. A1 (fan-out) changes the
economics — N questions now cost ~the wall-clock of one — but each fan is
still a blind hour, and the director is *blocked* inside `run_study_fan`
while it runs.

## The seams that already exist (build on these, invent nothing)

1. **`runs/<id>/log.txt`** is appended live by the run, and `liveview`
   already tails it. This is the *outbound* signal today, consumed by a
   human, not the director.
2. **`arc.jsonl` is re-read from disk every director turn**, so anything
   appended there appears in the very next decision prompt with no new
   plumbing (architecture §8). This is the natural *inbound* seam — and the
   same seam interjection needs, which is why the two must be designed
   together: one typed, validated channel, two writers (run → director;
   human → director), never raw arc writes.

## The shape a V1 should take, when evidence calls for it

- A run appends milestone lines to its own `runs/<id>/signals.jsonl`
  (typed: `{at, kind, note}`, bounded note length). The experimenter is
  *invited* by prompt to emit them; nothing forces it (a forced cadence is
  noise; a free agent that narrates honestly is signal).
- The director's loop, **between** dispatches (and a future async fan),
  surfaces the latest signals of in-flight runs alongside the arc — ADDITIVE:
  the full log stays on disk and in liveview; signals are an extra channel,
  never a replacement for reading what actually happened.
- Redirection (interjection) reuses the same channel in reverse and is a
  separate decision the owner has already deprioritised.

## Why not now

- **The consumer does not exist yet.** The director is synchronous: it is
  inside `run_move`/`run_fan` for the whole move, so there is no turn on
  which it could read a mid-move signal. The signal only becomes readable
  after moves are dispatched asynchronously — a real redesign of the loop's
  termination/budget/resume guarantees, not a wiring job.
- **Tested-first.** No long run has yet shown *which* signal is missing.
  The plan predicts the need; a 15-hour run will name it. Building the
  channel first risks building the wrong one — and a wrong "summary of what
  the run is doing" channel is exactly the substitutive shape the $27.50
  study refuted, if anyone ever leans on it instead of the arc.
- **The additive test is not yet passable.** Until the loop can actually do
  something with a mid-move signal, the field would be dead weight the agent
  can neither use nor ignore.

## Wake condition

Build this when the first multi-hour study under A1 finishes and the
post-mortem names a concrete moment where a mid-move signal (or redirect)
would have changed a decision — or when async dispatch is built for its own
reasons, whichever comes first. Design constraint carried forward: one typed
channel through the arc-read seam, additive beside the un-summarised arc,
never a substitute for it.
