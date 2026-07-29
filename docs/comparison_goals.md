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
| 3 | **Scientific discovery** | Simulation-driven prediction, checked against literature | **Arm C only** — comparison dropped (owner) |

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

## Goal 3 — scientific discovery, simulation-driven (REVISED 2026-07-29)

**Owner rulings that shaped this rewrite:**
1. It must use **simulation** — the structure/affinity stack, not just FBA.
2. **The comparison is dropped for this goal.** Owner is near-certain Claude
   Code cannot make scientific discoveries and would rather spend the compute
   on the attempt than on proving the negative. Run arm C only.
   *(Recorded counter-argument, made once and overruled: arm B is the cheap arm,
   so skipping it saves little and costs the ability to answer "how do you
   know?". Noted, not re-litigated.)*

**Dropping the comparison does NOT drop falsifiability.** A discovery nobody can
check is a story. With no arm B to compare against, the goal itself has to carry
the check — which is what the held-out structure below does.

### The simulation stack this goal is built on

| tool | call | gives |
|---|---|---|
| **Boltz-2** | `{protein_sequence, ligand, quantity: "affinity"}` | co-folded complex **and** binding affinity |
| **AutoDock Vina** | `{receptor, ligand, box, quantity: "docking_score"}` | docking score |
| ESMFold / Chai-1 | remote GPU lane | structure (ESMFold validated 0.834 Å CA-RMSD vs 1UBQ) |
| rdkit | local | ligand preparation, descriptors, chemical series |

**The standing discipline applies and is the reason this is trustworthy:** a
remote fold is an **INPUT, never a claim**. Do the expensive thing once, bring
the structure back, and compute the numbers of record **locally**, where they
are cheap and reproducible. That is how ESMFold and Chai-1 were validated.

### The goal

> Pick a protein target with a known ligand-binding site and a published,
> measured affinity series — a set of related compounds whose binding to it has
> been quantified. Withhold nothing from yourself at the start: read what is
> known. Then extend it. Design or select compounds OUTSIDE the published
> series, predict their binding affinity by simulation, and rank them. Commit to
> a ranked list with a stated affinity and a confidence for each, before you look
> for any measurement of them. Then go looking: for every compound you predicted
> where a measured value exists anywhere in the public literature or in
> ChEMBL/BindingDB, report your prediction against the measurement, including the
> ones you got wrong. Report the rank correlation and the mean absolute error
> over every compound you can find data for, not a selected subset. Say which
> predictions rest on the fold being right, which rest on the scoring function,
> and what result would have told you the method does not work.

### Why this is a real discovery attempt and still checkable

- **The prediction is committed before the lookup.** The order is enforced by
  the goal text, and the arc records it — a director that predicts, then
  searches, leaves both in order on disk.
- **The check is public data the arm did not fit to.** No held-out dataset for
  a human to police; the literature is the held-out set.
- **Reporting every hit, not a subset**, is the anti-cherry-pick clause, and the
  one a reader will look for first.
- **It can fail honestly.** If rank correlation is near zero, that is a real
  finding about simulation-based affinity prediction on this target, and the
  goal explicitly asks what result would have shown the method does not work.

### Why it suits the architecture without rigging

Separable parts (target selection / structure / compound set / prediction /
lookup) so fan-out has genuine work; produces numbers, not prose; and the
propose/measure boundary does real work here — affinities are *predictions*
until measured, and the wall cannot verify a prediction about the physical
world, only that the computation reproduces. **That distinction should appear
in the write-up.** An arm that reports predicted affinities as verified findings
has misunderstood its own instrument.

### Cost note

Boltz-2 and the folding lane are remote GPU (Modal, authenticated on this
machine at `~/.modal.toml`). ESMFold measured **$0.042 / 109 s** per fold, so a
compound series is inexpensive — but it is real money on a real bill, and
`RESEARCH_GPU_BUDGET_USD` bounds it. Set it before the run.

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
