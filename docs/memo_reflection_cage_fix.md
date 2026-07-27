# Memo — the reflection cage: ideation scored down anything the registry did not enroll

**Written:** 2026-07-26. **Ruling:** R-CAGE-1. **Status:** built, suite green.
**Supersedes:** the instruction sentence of R-WIN-1's instrument-contract block
(R5, owner 2026-07-17). The block itself, its single-source body, and its
unconditional placement are UNCHANGED — only the sentence that read the block as
a boundary is replaced.

---

## 1. What was wrong

`stages/reflection_reviews.py` appended this to the **full review** — the merit
review that feeds the deterministic quality/novelty filter:

> INSTRUMENT CONTRACTS (what the available instruments can actually measure)
> …every routable contract verbatim…
> **"Candidates whose test requires measurements outside every listed contract
> must be treated as weaker bets, stated in the reasoning."**

Ten routable substrate contracts were presented as *what the available
instruments can measure*, and anything outside them was to be marked down.

So a hypothesis testable against a public dataset (AlphaFold DB, PubChem,
Materials Project), a connector, or plain code was — by that sentence — a weaker
bet. It scored lower in the review that feeds the filter, and could be discarded
**before the free experimenter ever saw it**.

That is the PRIME DIRECTIVE's cage in miniature. The registry was bounding what
the system was allowed to *think*, not merely offering tools it could *use*. And
it did so at the one point in the pipeline where a candidate can be killed
silently — ideation's filter — rather than at execution, where a real limit
would announce itself.

**Generation already had this right.** `FEASIBILITY_NUDGE_INSTRUCTION` in
`stages/generation_strategies.py` says:

> "a hypothesis is untestable only if NOTHING available could evaluate it — not
> merely if no named solver exposes it"

and names connectors explicitly among real instruments. The two halves of
ideation contradicted each other, and reflection was the wrong half.

## 2. R-CAGE-1 (the ruling)

**The instrument-contract block informs a review; it never bounds it.** The
instruction sentence is replaced with one that matches generation's direction:

> These contracts describe what the VALIDATED instruments measure. They are NOT
> the limit of what this run can reach: the experimenter also has code, a shell,
> the web, any configured connector, and any public dataset or API it can call
> (AlphaFold DB, PubChem, Materials Project and the like). Treat a candidate as
> a weaker bet only if NOTHING available could evaluate it — not merely because
> no listed contract covers it — and say which of those routes you considered
> when you do.

The header changes with it, from *"what the available instruments can actually
measure"* to *"what the VALIDATED instruments measure — one part of what this run
can reach, not the whole of it"*.

**What is deliberately NOT changed.** The block stays unconditional; its body
stays `routable_contracts_block()` verbatim (single source of truth, R5); it
stays appended to the same review; no kill path is added or removed. Grounding a
merit judgment in what the validated instruments actually do is good and stays.
Only its reading as a fence is retired.

## 3. The second half: inputs are not claims (free experimenter)

Removing the sentence does not remove all the pressure, because some of it is
structural rather than written. `publishable` requires at least one verified
finding, and the experimenter prompt already says a finding you cannot back must
be `verified: false`. An agent optimizing for a publishable run drifts away from
sources it cannot verify — no prompt edit deletes that gradient.

So `stages/free_experimenter.py` gains an explicit statement of the distinction
that was previously only implicit:

> INPUTS ARE NOT CLAIMS, so do not avoid a source just because you could not
> verify it. Looking things up is normal and expected… Only the values you
> REPORT as findings need artifacts… Never narrow the investigation to what
> happens to be easy to verify — that is how a system ends up weaker than simply
> thinking about the problem.

This is the same boundary CLAUDE.md's PRIME DIRECTIVE already draws
(*"Reproducibility applies to a KEPT result… It is NEVER a reason to restrict
which tools the agent may reach for"*), said where the agent actually reads it.

## 4. Scope of the audit behind this

The prompts on the production path were read, not assumed:

- `free_experimenter.py` — **not caging.** "NO restriction on HOW you
  investigate", "Nothing limits which tools you reach for", "You are NOT limited
  to these". No change needed beyond §3's addition.
- `substrate_tools_catalog()` — **not caging.** "optional conveniences, NOT a
  boundary."
- `generation_strategies.py` feasibility nudge — **not caging** (and switched
  off by default): explicitly names connectors and defines untestable as
  "NOTHING available could evaluate it".
- `reflection_reviews.py` instrument-contract block — **the one cage.** Fixed
  here.

One sentence, unconditional, in the one place that can silently drop a
candidate. Nothing else on the production path bounded the agent to the
registry.

## 5. Verification

No test pinned either string (checked before editing). Full suite green after
the change.

## 6. Open watch

The gradient described in §3 is real and only partly addressed by prose. If a
future run shows the experimenter still steering away from unverifiable-but-
useful sources, the next lever is structural rather than textual: currently a
finding is either a verified claim or an unverified caveat, with nothing in
between for "a sourced input I used and cited". A third state would say it
better than another paragraph of instruction.
