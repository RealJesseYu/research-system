# D.1.1 memo — substrate selection at the four retired-import surfaces

Deliverable of D.1 Step 4 (2026-07-17). **No decisions are made here; the
owner rules.** Format per §10.6: option | cost | era/honesty consequence.

Context. D.1 retired the four `from substrates import CAVITY_2D_CONTRACT`
sites to `contract_for("cavity_2d_cfd")` reads. The Step-1 determination
found **no site has a structural selection key in scope today**, so all
four carry the explicit cavity pin with the `TODO(D.1.1)` marker.
`sole_routable_id()` was not introduced anywhere (it is scheduled for
retirement, acceptance test 2). Every option below that resolves to the
cavity contract preserves era 862531b byte-identity, because
`contract_for("cavity_2d_cfd")` IS `substrates.CAVITY_2D_CONTRACT`
(assertIs chain, tests/test_contract_registry.py:32-37).

A structural fact that shapes all four tables: the three Stage-1 surfaces
(P5, P6, P7) sit **before** any hypothesis is chosen, so in a
multi-substrate future the honest grounding there is plausibly *all
routable contracts*, not a selected one — which needs `routable_ids()`
iteration, not a per-site key. P8 sits **after** the choice and is the one
surface where a genuine one-substrate selection will eventually be needed.

---

## P7 — generation_strategies.build_feasibility_nudge (stages/generation_strategies.py:119)

**What the site could select on:** nothing hypothesis-shaped — Generation
is pre-hypothesis. Only run-level configuration (a supervisor-assigned
substrate for the whole run) could key a read. The domain string is in
scope but parsing it is forbidden (R-28H-1 / substrate-agnostic invariant).

| option | cost | era/honesty consequence for cavity |
|---|---|---|
| A. explicit cavity pin (as landed) | zero further; one marker comment | bytes identical (fixture-proven); the pin is named and visible — honest so long as cavity is the sole routable substrate |
| B. run-level substrate_id threaded from the supervisor (function arg or run config) | signature change through `generate_candidate_pool` + supervisor launch plumbing; no schemas.py change if kept out of the baton payload | bytes identical while the id resolves to cavity; honesty gain is real only once a second substrate is routable — before then it is plumbing that *looks* like selection but can only ever say "cavity" |
| C. nudge carries ALL routable contracts (`routable_ids()` iteration) | small loop + block reformat; fixture re-capture | bytes identical today (one routable id ⇒ one contract, but block glue must be kept byte-stable — a re-capture era risk if glue changes); becomes the honest shape the day a second substrate is promoted, without a selection design |

**Recommendation (recommendation, not a ruling):** A until a second
substrate is actually promoted routable; design C at that promotion —
Generation should see every instrument the run could route to, so P7 never
needs a one-of-N key.

---

## P6 — reflection_reviews.instrument_contract_block (stages/reflection_reviews.py:204)

**What the site could select on:** one candidate hypothesis (the full
review runs per-candidate; `compose_full_review_prompt()` itself takes no
arguments — reflection_reviews.py:226). Candidates carry no substrate
field, and adding one would make substrate selection model-authored text —
the exact thing R-28H-1 forbids keying on.

| option | cost | era/honesty consequence for cavity |
|---|---|---|
| A. explicit cavity pin (as landed) | zero further | bytes identical (rwin1 full_review pin holds); honest while single-substrate |
| B. per-candidate substrate field (model-authored) | prompt + schema churn in Generation output | REJECT-class: keys a trust-bearing read on payload text — violates R-28H-1; era bytes would still match for cavity but honesty is broken by construction |
| C. run-level substrate_id threaded in (supervisor-assigned) | thread through `reflect_on_pool` → review call sites | bytes identical while cavity; same "can only say cavity" honesty caveat as P7-B |
| D. all routable contracts in the block | loop + glue discipline; fixture re-capture risk | bytes identical today; honest multi-substrate shape without per-candidate keys |

**Recommendation:** A now; D at second-substrate promotion, for the same
pre-choice reason as P7.

---

## P5 — gate1_chooser.instrument_contract_block (stages/gate1_chooser.py:63)

**What the site could select on:** the full ranked candidate list
(`choose_hypothesis(run_id, hypotheses, run_dir)`,
stages/gate1_chooser.py:167) — multiple candidates, none carrying a
substrate id. The chooser is the moment of choosing, so selecting a single
substrate *before* it chooses would invert the decision order.

| option | cost | era/honesty consequence for cavity |
|---|---|---|
| A. explicit cavity pin (as landed) | zero further | bytes identical (rwin1 chooser pin holds); honest while single-substrate |
| B. run-level substrate_id threaded in | thread through `choose_hypothesis` + supervisor | bytes identical while cavity; presumes the run was substrate-committed before the hypothesis was chosen — a design commitment the owner may not want |
| C. all routable contracts in the block | loop + glue discipline; fixture re-capture risk | bytes identical today; lets the chooser weigh "which instrument could test this candidate" per candidate — arguably the chooser's actual multi-substrate job |

**Recommendation:** A now; C at second-substrate promotion. The chooser is
the one Stage-1 surface where seeing *all* contracts is not merely honest
but load-bearing for its judgment.

---

## P8 — stage2_experiment_design.run stage_input["substrate_contract"] (stages/stage2_experiment_design.py:184)

**What the site could select on:** the baton payload `{domain,
chosen_hypothesis}` (+ optional prior_thought) — a single chosen
hypothesis exists, but it carries no substrate field and payload-name
parsing is forbidden. The only structural key available today would be
`sole_routable_id()`, forbidden for new sites (D.2 retirement). This is
the first surface downstream of the choice, and the natural home for a
real one-substrate selection.

| option | cost | era/honesty consequence for cavity |
|---|---|---|
| A. explicit cavity pin (as landed) | zero further | bytes identical (d1 stage-2 fixtures hold); honest while single-substrate |
| B. supervisor-assigned substrate_id carried in the baton payload | schemas.py change — **locked artifact, recorded ruling required** — plus supervisor assignment logic and boundary validators | bytes of the model-visible contract unchanged while the id resolves to cavity, but the payload gains a key: post-gate-1 fixtures and the locked exact-key schemas move — a *new era* for the payload wall even though the contract text doesn't move |
| C. task-typing verdict selects the substrate (Step 35) | the whole Step-35 design; not buildable now | the intended end state: selection becomes a recorded, structural decision between gate 1 and stage 2; era for cavity preserved if typing resolves to cavity |
| D. per-call substrate argument with cavity default | small signature change to `run(baton)` — but `run` is the frozen stage interface, so this breaks the relay shape | REJECT-class on interface grounds; no era gain over A |

**Recommendation:** A now; the eventual design is C (Step-35 task typing),
with B as its carrier **only if** the owner rules the schema change worth
a payload-wall era. P8 should not grow ad-hoc selection before Step 35 —
the pin names the debt precisely.

---

Summary for ruling: all four sites landed as option A (explicit pin,
single-sourced, marker in place). The memo's asks are (1) whether the
"all routable contracts at Stage-1 surfaces / task-typed selection at
Stage-2" direction is the standing intent to design against at
second-substrate promotion, and (2) whether P8-B's payload-wall era cost
is acceptable when Step 35 arrives. Nothing needs ruling before then.

---

## Ruling (owner, 2026-07-17)

Direction: APPROVED — the "all routable contracts at Stage-1 surfaces /
task-typed selection at Stage-2" direction is the standing intent to design
against. C/D land with Step-35 as their own era ruling + re-captures —
deliberately NOT at the R2/R3 promotion flip: the four explicit cavity pins
stand un-moved, so the rwin1/d0/d1 era fixtures hold byte-identical through
the flip.

---

## R5 record (owner, 2026-07-17) — the Stage-1 half executed

R5 executes the ruled direction's STAGE-1 HALF: the three Stage-1 surfaces
(P5 gate1_chooser, P6 reflection full review, P7 generation feasibility
nudge) now embed `tools/substrate_registry.routable_contracts_block()` —
per routable substrate, a fixed `ROUTABLE SUBSTRATE: <substrate_id>` header
then `contract_for(id)` VERBATIM, enrollment order, deterministic, fail-loud
inherited from `contract_for`. The `TODO(D.1.1)` markers at those three
sites are retired under R5. This is a deliberate era move: era-of-record
leaves 862531b and becomes the commit landing R5 (its sha is in the git
log — a commit cannot embed its own hash; see docs/disclosures.md R5 entry).

**P8 / Step-35 remains PARKED.** The explicit cavity pin at
stage2_experiment_design (option A) stands un-moved; the eventual design is
option C (Step-35 task typing), its own era ruling + re-captures. The
mismatch limitation and its catch, verbatim from docs/memo_d2_selection.md:

> In production, specs are authored against the contract **stage 2 was
> shown**. Stage-3 selection can therefore only ever re-derive the substrate
> stage 2 already wrote toward — end-to-end mixed-domain routing additionally
> binds to the D.1.1 direction: a selection point **between gate 1 and stage
> 2** (memo P8, option C — Step-35 task typing), so stage 2 is handed the
> contract of the substrate the run will actually route to.

> Stated consequence, plainly: a spec whose declared parameters no routable
> substrate can serve now **raises at stage-3 selection** (supervisor's
> stage-crash catch journals it) instead of being verdicted against cavity's
> contract and halting later at stage-4 synthesis. The refusal moved earlier
> and got louder; nothing is silently judged against the wrong instrument.

So a Stage-1 hypothesis steered toward the ngspice contract still meets the
cavity pin at stage 2 until Step 35; the fidelity gate judges the resulting
spec against the substrate its declared parameters actually select (or the
selection raise above), never silently against the wrong instrument.
