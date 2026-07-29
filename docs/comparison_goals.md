# The three comparison goals

**Written 2026-07-29.** Three task classes, one frozen goal each, the identical
string to every arm. Protocol: `docs/comparison_protocol.md`. AI Scientist
dropped for now (owner, 2026-07-29) — arms are bare chat / Claude Code one
prompt / this system.

Why three: they test different things. A system can be good at a specified task
and useless at an open one, or vice versa. Running all three is how you find out
*which* class the architecture earns its keep on, rather than claiming it
everywhere.

| # | Class | What it tests | Status |
|---|---|---|---|
| 1 | **Defined task** | Execution quality on a fully specified problem | Draft below |
| 2 | **Open-ended task** | Target selection + end-to-end delivery | **HAVE IT** — the engineering prompt |
| 3 | **Scientific discovery** | Finding something true that was not already known | Draft below |

---

## Goal 2 — open-ended (already written, use verbatim)

The engineering prompt from `study-20260727T045848Z`, which died on the
ideation crash later fixed in `dbb9469`. Nothing wrong with the goal — it never
got a fair run.

> Somewhere in the physical world, a consequential engineering decision is still
> made by a fixed rule — a code of practice, a lookup table, a design chart, a
> rule of thumb — that was fitted decades ago to the data available then, and is
> applied uniformly to cases it was never fitted to. Find one where the rule's
> conservatism or error is costing real money, safety margin, or material, and
> where enough public data exists to do better. Choose the target yourself:
> generate many candidates across different fields and pick on expected impact
> and evidence available, not on what is convenient. Then build
> the replacement end to end — obtain the real data, establish what the incumbent
> rule actually achieves on it, build a learned or hybrid model that beats it,
> and quantify the win in the units a practitioner cares about. Go further than a
> benchmark: state where your model must not be trusted, what a practitioner
> would have to change to adopt it, and what it would take to get it accepted by
> whoever owns the rule. If you hit something you genuinely cannot obtain, say
> precisely what you need from me rather than substituting something weaker.

**EDIT APPLIED (owner, 2026-07-29):** *"use ideation to generate many
candidates"* → *"generate many candidates"*. The original named a tool only arm
C has, which would have told arm C to use its apparatus while telling A and B
nothing — a hidden instruction advantage. The goal above is now the frozen
string. **Do not edit it again once an arm has run.**

---

## Goal 1 — defined task (draft)

The class the normal-CDF study fell into, which is the system's best result to
date: a hard specification, a measurable objective, a checkable answer. Scaled
up so the parts are genuinely separable.

**Constraints it satisfies:** checkable in under an hour (every number is
recomputable); measurable objective with a tradeoff; separable parts (four
regimes, each independently developed and then composed); attemptable by Claude
Code; no standing verification clause.

> Produce a single-file C library that evaluates the regularized incomplete beta
> function I_x(a,b) for real a,b in [0.01, 1000] and x in [0,1], returning BOTH
> I_x(a,b) and its complement 1 - I_x(a,b) so that whichever is smaller is
> representable. Achieve a relative accuracy of 1e-12 **on the smaller of the two
> tails**, measured against a high-precision reference, using as few
> floating-point operations per evaluation as you can. Different regions of the
> (a,b,x) domain want different methods; find the regions and the methods, and
> handle the boundaries between them so the result is continuous and the accuracy
> bound holds across them. Deliver the header, the code that generated any tables
> it needs, a map of which method covers which region, and the worst-case
> relative error and operation count per region measured on a dense sweep. State
> the (a,b,x) regions where your implementation should not be trusted and why,
> including any region where double precision cannot hold the stated bound.

**Why this one:** it is the shape that worked (cheapest-X-subject-to-Y), the
domain naturally splits into regimes so fan-out has real work, and correctness
is mechanically checkable against `mpmath.betainc` — a judge can verify the
headline in minutes without trusting any arm's own numbers.

**Alternative if you want it less numerical:** same structure, different
subject — a bit-exact fixed-point implementation of a named DSP transform under
an operation budget, with the error bound proven on a dense sweep.

---

## Goal 3 — scientific discovery, bio (draft)

The hard class, because **discovery has a checkability problem**: you cannot
verify a novel biological claim without an experiment. So the goal must carry
its own falsification route — a prediction that public data can refute.

**Wired capability all arms could use** (arm C has these as substrates; Claude
Code can `pip install` the same libraries, so the comparison stays fair):
`cobrapy` (genome-scale metabolic models), `rdkit`, `mafft`, `homology_search`,
`alphafold_db`, `bio_db_lookup`, plus ESMFold / Chai-1 / Boltz-2 on the GPU lane.

> Using only public data, find a gene whose essentiality a current genome-scale
> metabolic model of *Escherichia coli* predicts incorrectly, and explain the
> failure well enough to fix it. Identify the mismatch between model prediction
> and published experimental essentiality data, determine the biochemical reason
> — a missing reaction, a wrong cofactor, an incorrect gene-protein-reaction
> mapping, an unmodelled isozyme — and produce a corrected model file whose
> prediction for that gene now matches experiment. Then show the correction does
> not break the model elsewhere: report how many other essentiality calls change,
> and whether each change moves toward or away from the experimental data. Say
> which of your conclusions rest on the model being right about things you did
> not check.

**Why this is falsifiable without a wet lab:** the experimental essentiality
data already exists (Keio collection and successors); the model's prediction is
computable; the corrected model's predictions are computable. **Every claim can
be checked by re-running.** The discovery is real — a specific curation error in
a published model — but the verification is entirely computational.

**Why it suits the architecture without rigging:** it has separable parts
(find mismatches / diagnose one / correct it / regression-test the correction),
it produces numbers rather than prose, and it has a natural failure mode the
comparison should expose — an arm that finds a mismatch and *asserts* a cause
without testing the corrected model has not done the work.

**Materials-science alternative** if you prefer: the wiring is thinner —
`lookup_material` is a retrieval call against Materials Project, not a
substrate, and there is no simulation backend for materials — so an arm would
be doing its own computation from scratch. Viable, but bio is the better-armed
choice today.

---

## Before freezing any of these

1. ~~Decide the *"use ideation"* edit on goal 2.~~ **DONE — applied above.**
2. ~~Sanity-check goal 1's accuracy target.~~ **DONE, and the first draft was
   impossible — now fixed.** Checked against scipy: `I_0.5(0.01,1000)` and
   `I_0.999(1000,1000)` both saturate to exactly `1.0` in double precision, so
   *relative* accuracy on the returned value is undefined there; and
   `I_0.5(1000,0.01) = 1.996e-306` sits at the edge of representability. A
   single-value 1e-12 relative spec is unmeetable in the saturation regions and
   would have made every arm fail on an artifact of the spec rather than on
   ability. **Fixed by requiring both the value and its complement, with
   accuracy stated on the smaller tail** — which is how production
   implementations state it. `mpmath` is present in the sandbox image, so a
   high-precision reference is reachable by every arm.
3. ~~Confirm goal 3's data is reachable.~~ **DONE 2026-07-29 — confirmed, and
   the check found something that IMPROVES the comparison.**

   Reachable from a plain machine, all verified live:
   - `bigg.ucsd.edu/static/models/iML1515.json` — **HTTP 200, 3.06 MB**
   - Baba 2006 (the Keio essentiality paper, open access) — HTTP 200
   - EcoCyc — HTTP 200
   - `cobra` is an ordinary PyPI package (current 0.31.1), so any arm can
     `pip install` it.

   **The finding: arm C's cobrapy SUBSTRATE cannot do this goal.** Its envelope
   is `MODEL_ALLOWLIST = ("e_coli_core", "iML1515")`, `QOI_FIELDS =
   ("growth_rate",)`, optional `min_growth` — and **no knockout field at all**
   (`run_cobrapy` rejects `knockouts` as an unsupported field). Gene knockouts
   are the entire goal, so arm C must go around its own substrate via Bash and
   `pip install cobra`, exactly as arm B would.

   **This is good, not bad.** It makes goal 3 **tooling-neutral between B and
   C** — both arms reach the same library the same way — so the comparison
   isolates the orchestration rather than measuring substrate access. It is also
   the PRIME DIRECTIVE working: the substrate is a tool the agent may bypass,
   not a cage that defines what it can attempt.

   Do NOT widen the substrate to cover this before running. Doing so would hand
   arm C an advantage that the comparison is specifically trying not to measure.

**Freeze one goal at a time and run all arms on it before writing the next.**
Nothing here may be edited after an arm has run on it.
