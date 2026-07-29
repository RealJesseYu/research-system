# Comparison protocol — does the architecture beat one strong agent?

**Written 2026-07-29, BEFORE any arm has run.** That ordering is the whole
point: criteria written after seeing output are not criteria. Nothing in this
file may be revised once an arm has been run — if it turns out to be the wrong
protocol, say so and run a second one, but do not edit this one to fit.

Roadmap item B0. Gates B1 (the long run).

---

## 1. The question being answered

**Not** "is this better than a chat." A chat has no tools; that comparison
measures tool access and proves nothing about the architecture.

> **Does the orchestration — director, wall, fan-out, carry bus, verification —
> add value over ONE strong agent with the same model and the same tools?**

That is the question a skeptic asks, and the only one worth spending a week on.
If the answer is no, the architecture is elaborate packaging around Claude Code
and it is far better to learn that from one run.

## 2. The arms

All arms get **the same goal text, verbatim**, and the same wall-clock budget.

| # | Arm | Setup | Purpose |
|---|---|---|---|
| A | **Bare chat** | claude.ai, no tools, one prompt | Floor. Expect it to lose. **Claim nothing from beating it.** |
| B | **Claude Code, one prompt** | Same model, same Bash/Docker/substrate access, no director, no wall, no fan | **THE BASELINE.** This is the comparison that matters. |
| C | **This system** | `python -m pi_agent --director free --paper` | The architecture |

Arm B is the load-bearing one. If C does not beat B, the result is that the
orchestration does not earn its complexity — regardless of what A does.

**Not run this week:** an independent autonomous system (AI Scientist / Sakana
and similar). Closest published analogue, but standing one up is its own
project — dependencies, its own task format, its own model spend — and it would
consume the week that B1 needs. Cite qualitatively; benchmark against B.

## 3. Choosing the goal — constraints, fixed now

The goal must:

1. **Be in the class the system is built for** — multi-hour, tool-using,
   producing numbers rather than prose.
2. **Have a checkable deliverable.** A human must be able to tell, in under an
   hour, whether the answer is right. No "write a strategy document".
3. **Have a measurable objective with a tradeoff** — the shape that produced
   the system's best study to date (cheapest X subject to constraint Y).
4. **Have separable parts**, so decomposition and fan-out have something to do.
   If the goal has one indivisible step, arm C's machinery cannot help and the
   comparison is uninformative.
5. **Be attemptable by arm B.** If Claude Code structurally cannot start, the
   comparison is rigged and the result is worthless.
6. **NOT contain a standing verification instruction.** "Each part must be
   verified before it is built on" cost a previous study most of its budget.
   Say what the deliverable IS.

**Write the goal once, freeze it, give the identical string to all three arms.**

## 4. What a good answer must contain — WRITTEN BEFORE ANY ARM RUNS

Score each arm on these, independently, before comparing them to each other.

| # | Criterion | How it is judged |
|---|---|---|
| 1 | **Answers the question asked** | Yes/no. A near-miss on a different question scores 0 here. |
| 2 | **The headline number is right** | Recompute it by hand or by an independent script. Right / wrong / not checkable. |
| 3 | **The numbers reproduce** | Re-run what the arm supplies. Count: reproduced / claimed. An arm that supplies nothing re-runnable scores 0. |
| 4 | **Alternatives were actually compared** | Count distinct options *measured*, not mentioned. Asserting "X is best" scores 0. |
| 5 | **The deliverable is usable tomorrow** | Could a competent person act on it without asking a question? Yes / partly / no. |
| 6 | **Honest about limits** | Does it say what it did NOT establish? Unmarked over-claim is a serious penalty. |
| 7 | **Cost** | Dollars and wall-clock. Recorded, not scored — it contextualises everything above. |

**Weighting:** 2, 3 and 6 are disqualifying if failed — an answer that is wrong,
unreproducible, or silently over-claiming is not a better answer no matter how
much work went into it. 1, 4 and 5 are where the arms are actually ranked.

## 5. What would falsify the claim

Stated in advance so it cannot be argued away afterwards. **The architecture
does NOT earn its complexity if any of these hold:**

- **Arm B matches or beats arm C on criteria 1, 4 and 5.** One agent with the
  same tools did the same work.
- **Arm C wins only on criterion 3** (reproducibility). That would mean the
  contribution is the verification wall, not the orchestration — a real result,
  but a much smaller claim, and one that could be delivered as a library rather
  than a system.
- **Arm C costs more than ~5x arm B for a margin a reader would call
  incremental.** Being better is not enough; it has to be worth it.
- **Arm C over-claims where B does not.** The wall exists to prevent exactly
  this; if it fails, the central promise fails.

If any of these hold, record it plainly and reopen the roadmap. Do not
re-litigate the criteria.

## 6. Judging procedure

1. Run all three arms on the frozen goal. Keep every transcript and deliverable.
2. Score each arm against §4 **without looking at the other arms**, to avoid
   grading on a curve.
3. **Verify criteria 2 and 3 mechanically** — recompute the headline, re-run
   what each arm supplied. Not by reading.
4. Only then compare.
5. Write the result up including whichever falsifier fired, if any.

**Anyone may judge, but the person judging should not have watched the runs.**
Watching arm C work for three hours makes its output feel earned in a way that
does not survive contact with a reader who only sees the deliverable.

## 7. What this protocol deliberately does NOT settle

- Whether the system is better at goals **outside** the chosen class. One goal
  is one data point; the honest claim afterwards is about that class of task.
- Whether it beats other autonomous research systems. Not tested here.
- Whether it scales — a single run says nothing about the tenth.
