# Debrief — Experiment 1 (goal 1, the defined task)

**2026-07-29.** First head-to-head comparison the project has run. Full verified
numbers in `docs/comparison_results_goal1.md`; protocol in
`docs/comparison_protocol.md`. This is the what-it-means.

---

## 1. What shipped

Three arms on one frozen goal — a single-file C library for the regularized
incomplete beta function, 1e-12 relative on the smaller tail, minimum flops,
region map, per-region worst error, stated limits.

| | arm A (tooled chat) | arm B (Claude Code) | **arm C (this system)** |
|---|---|---|---|
| finished | ✗ ~2/3 through | ✅ | ✅ |
| points over 1e-12 | — | **6** of 57,282 | **0** of 73,688 |
| worst rel. error | — | **1.405e-12** (misses) | **4.508e-13** (meets) |
| baseline measured | — | ✗ | ✅ textbook: 3.26e-10, 1190 fails |
| reference validated | rebuilt on a bug that isn't real | single route | **3 routes, agree to 8.6e-53** |
| cost | budget exhausted | one session (**unmeasured**) | $60.41 / 282 turns |
| packaged | ✗ | ✅ clean dir + REPORT.md | ✗ **no README** |

**Every headline recomputed from raw data, not read from summaries.** Arm B's
from its shipped CSVs; arm C's from `grid.bin` / `errs.bin`. Both matched exactly.

## 2. The result, stated precisely

**The orchestration met a specification a single strong agent missed** — and it
did so at the exact corner that defeated that agent. Arm B's six violations were
all at `a=0.01,b=1000` and its mirror; arm C measures **5.43e-14** there, ~26x
better.

No protocol falsifier fired.

**What this is NOT:** proof that the architecture wins generally. One goal, one
data point, in the *defined-task* class — the class the system was already best
at. It says nothing about open-ended work or discovery.

## 3. What the architecture actually contributed

Not "it ran more compute." Four specific mechanisms did identifiable work:

**The director chose to measure before building.** Move 1 spent a whole move on
an empirical *failure map* rather than code — and it localized the mechanism
exactly: the worst error was dominated by the double-precision log-prefactor,
`1-I` subtraction and CF convergence were *not* binding. Both chat arms reached
the same root cause by insight; arm C reached it by measurement and knew how much
of the error each cause owned. That is a different epistemic position.

**Fan-out made a three-subsystem approach affordable.** Three concurrent
supervisors, one wall-clock hour instead of three. Arm B could not have run three
independent investigations; it had to pick one line and follow it.

**The wall killed claims.** Per-move verified counts: 26/26, 14/16, 21/21, 0/0,
18/21. Five findings across the run were proposed and did *not* survive
re-execution. Neither chat arm had anything that could do that to it.

**It produced a documented negative result.** The Temme/uniform-asymptotic fan
member verified 0 of 16 and was ruled out with the reason recorded — `g_k`
cancels to order `eta^-(2K-1)`, so no fixed precision covers a neighbourhood of
`z=0`. **Arm B scoped that same approach out as future work. Arm C tried it and
killed it.** That asymmetry is the clearest single illustration of what the extra
capacity buys.

## 4. Yesterday's five improvements, on their first live outing

| | status | evidence |
|---|---|---|
| **A1 fan-out** | ✅ **decisive** | 3 concurrent supervisors (pids 3968/9/70), distinct run dirs, no collisions. It is what made the 3-subsystem strategy possible. |
| **A2 trajectory view** | ✅ **used** | The director saw `{usd_spent: 45.12, agentic_turns_spent: 230, decision_cap: 28, decisions_remaining: 25}` and reasoned from it: *"With ~25M tokens and 2 moves left…"* |
| **A3 prediction column** | ✅ **used on every decision, and calibrated** | Before running the integration it predicted *"worst global error in the 5e-13"* range. **Actual: 4.51e-13.** It predicted its own final number to within ~20%. |
| **A4 ev2 failed-producer carry** | ⚠️ **never fired** | 0 failed-carried on all five moves. No declared producer failed its re-emission gate, so the negative store stayed empty. Mechanism remains untested in production. |
| A5 intermediate signal | not built | deferred by design record |

**Three of four earned their keep within 24 hours of landing.** A3's calibration
is the surprise — it was the smallest change and it produced the most interesting
artifact: a director that can be scored on its own foresight.

## 5. What broke, and what is weak

- **Packaging is the real failure.** Arm C's artifacts sit in a run workspace,
  the paper is in a different directory, and there is no README anywhere. Arm B
  shipped a clean directory with reproduce-from-scratch commands. **A single agent
  beat the orchestration on "usable tomorrow"** — the first thing any reader hits.
  Now on the checklist as **C1**.
- **Arm B's cost was never measured.** "4x more expensive" is an estimate.
  Measure it on goal 2.
- **No floor arm.** Arm A had code execution, so the no-tools baseline the
  protocol specified does not exist.
- **The grids differ** (86,190/73,688 vs 71,456/57,282). Each arm chose its own
  sweep, which is part of what was tested, but the two worst-case numbers are not
  measured on identical points. The corner comparison is the like-for-like part.
- **A4 untested**, as above.

## 6. Vision checklist

**Done and proven live**
- Free director decomposing, fanning, integrating, and stopping on its own judgement
- Parallel fan-out — N experiments in the wall-clock of one
- Verification wall overriding the agent's self-report, with claims actually killed
- Real cost recording in dollars and turns; the director reasoning from its own runway
- Prediction-vs-outcome as a calibration channel
- Automatic paper + PDF that opens itself
- **A comparison protocol frozen before any arm ran, and a result that survived mechanical re-derivation**

**In progress**
- The three-goal comparison — 1 of 3 done
- Deliverable packaging (C1)

**Not started**
- Goal 2 (open-ended) and goal 3 (discovery)
- Interjection, front end
- Security / multi-tenancy
- ev2 ever actually firing

## 7. What next

**Goal 2, and it is the one that matters.** The defined-task class was the
system's home ground; open-ended target selection is where the director's
judgement is the whole product. It is also the run that died before ever getting
a fair attempt.

**Two changes to how it is run:** measure arm B's cost this time, and fix C1
first if you want the deliverable to be showable — the packaging weakness will
be more visible on an open-ended goal, not less.

**And keep the frame honest.** What is proven today is one class, one goal. The
claim available right now is: *on a fully specified numerical task, the
orchestration met a bound a single strong agent missed, at the corner that
defeated it, with a better-validated reference and a measured baseline.* That is
a good, defensible sentence. It is not "better than a chat."
