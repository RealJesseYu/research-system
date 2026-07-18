# Substrate maturity registry (Step 28)

The registry is the single source of truth for **which substrates the system
knows about and how far each has climbed the trust ladder**. It is code —
`tools/substrate_registry.py` — not a mutable store, because maturity and
routability are trust-bearing facts. The supervisor consults it before it lets
a fidelity *trust decision* (a `trust`/`refine` verdict) route to real
execution.

## The table

| substrate_id | wrapper | card | maturity | routable | cost tier | notes |
|---|---|---|---|---|---|---|
| `cavity_2d_cfd` | `tools/run_cfd.py` | `docs/envelope_card_cavity2d.md` | **provisional** | **yes** | low | real runs accruing, mini-21 pending; routable since Step 28 (was the sole routable substrate until the R2 flip) |
| `calculix_cantilever_fea` | `tools/run_fea.py` | `docs/envelope_card_calculix_cantilever.md` | calibrating | no | low | battery pending owner OK |
| `code_sklearn_eval` | `tools/run_code.py` | `docs/envelope_card_code_sklearn_eval.md` | calibrating | no | low | battery not on the run manifest — owner decision pending |
| `fenicsx_cantilever_elastic` | `tools/run_fenicsx.py` | `docs/envelope_card_fenicsx_cantilever_elastic.md` | calibrating | no | low | slate drafted (15 cases); battery pending owner OK on the slate ruling |
| `sympy_symbolic_exact` | `tools/run_scipy.py` | `docs/envelope_card_sympy_symbolic_exact.md` | calibrating | **yes** | low | sci-Python Regime A (exact symbolic CAS); card provisionally signed (owner, 2026-07-16), S1-S6 + S2a/S4a/S4b all RULED (owner, 2026-07-16); battery executed 2026-07-17 (28/30 draws in-band, 8/10 cases unanimous, hook witnessed 16/16 zero-silent-trust, wrapper self-checks 5/5); routable=True RULED Packet B Phase 1 (owner 'start phase 1' + Phase-1.0 ruling line, 2026-07-17: OperationSetRegime, item 1), maturity CALIBRATING unchanged — every trust decision human-required via the maturity hook. Regime B (scipy_numeric_quad) is QUEUED and has no row. |
| `ngspice_linear_passive` | `tools/run_ngspice.py` | `docs/envelope_card_ngspice_linear_passive.md` | calibrating | **yes** | low | battery executed 2026-07-17 (30/30 draws in-band, 10/10 cases unanimous, hook witnessed 18/18 zero-silent-trust); routable=True RULED R2, maturity CALIBRATING unchanged RULED R3 (owner, 2026-07-17) — every trust decision human-required via the maturity hook |
| `web_search` | `tools/web_search_stub.py` | (this doc) | retrieval-provisional | no | minimal | structurally never trusted alone |

## The ladder semantics and the promotion rule

For routable substrates the ladder runs **calibrating → provisional → mature**,
low to high. *Calibrating* means a card exists (or a battery is being
assembled) but the substrate has not earned unattended trust — not routable
by default; **amended by ruling R3 (owner, 2026-07-17):** a calibrating
substrate whose battery has run may be ruled routable, with every trust
decision touching it human-required via the maturity hook (never silently
trusted). *Provisional* means real runs are accruing and the wrapper behaves,
but calibration is not complete; a provisional substrate may be routable, but
any trust decision that touches it is **human-required** (the supervisor marks
it `needs_human_signoff` and, in auto mode, downgrades the trust/refine verdict
to defer-class handling rather than trusting it silently). *Mature* means
calibration is complete and trust decisions may proceed unattended. **No
substrate is mature today** — the routable set since the Packet B Phase 1
flip is `cavity_2d_cfd` (provisional), `sympy_symbolic_exact` (calibrating,
Phase-1-routable), and `ngspice_linear_passive` (calibrating, R3-routable),
all non-mature, so every trust decision the pipeline can
currently make is human-required by construction. `web_search` sits in its own class,
*retrieval-provisional*, deliberately outside the ladder: it is a retrieval
source that is structurally never trusted alone, so it is never routable.

**Promotion happens only by recorded ruling.** Moving a substrate up a rung, or
flipping `routable`, is a governance act performed by editing
`tools/substrate_registry.py` under a recorded ruling — never at runtime, never
from a prompt, never inferred from a run. That is why the registry is plain
Python data.

## What this registry does NOT authorize

Enrolling `calculix_cantilever_fea` and `code_sklearn_eval` here as
*calibrating / unroutable* records that the system knows about them; it does
**not** authorize the pipeline to route to them. **Registration-for-routing of
the FEA and code substrates is a separate future ruling.** Until that ruling,
`cavity_2d_cfd` remains the only substrate a run can execute on, exactly as
before Step 28.

---

# Router Card — (fenicsx_cantilever_elastic, linear-elastic small-deflection static)

> **STATUS: DRAFT — STAGING ONLY.** Merged by the Wave Guide, not by this
> session. The substrate is **UNREGISTERED** and enters at maturity
> `calibrating` = **UNROUTABLE**; nothing routes to it today. Promotion is a
> separate owner ruling.

> **Status of routing in the system:** there is still no standalone
> multi-substrate router. The fidelity gate's `right_instrument` field is the
> only routing decision the system makes. This card is authored so that when a
> router exists it has abstract facts to choose on — and, more immediately, so
> the **second cantilever instrument** is a real, describable alternative to the
> first.

---

## 1. Identity
| Field | Value |
|---|---|
| Substrate | `fenicsx_cantilever_elastic` |
| Physics regime | linear-elastic isotropic small-deflection static cantilever; single tip load, one clamped end |
| Envelope card | `docs/envelope_card_fenicsx_cantilever_elastic.md` |
| Provenance state (from envelope card §2) | `provisionally-signed (owner, 2026-07-16)` (copied from card §2 at commit 4800a93 — the card is the source of truth; re-verify at merge) |

## 2. Capability summary (abstract — no solver names above the wrapper)
| Property | Value |
|---|---|
| Physics served | static deflection and stress of a slender, singly-clamped, tip-loaded elastic prism under small deformation and a linear isotropic material law |
| QoIs servable | one scalar displacement extremum (validated) and one scalar pointwise stress extremum (reported-only) per run; both returned every run |
| QoIs NOT servable | anything time-dependent, any field export, any masked/sub-domain reduction, any eigenvalue, any per-run QoI selection |
| Validated-envelope summary | envelope §3A: the reference beam at three refinements, 1.31% → 0.31% from the closed form, **at the validated element order only** |

## 3. Choose this substrate when
- The hypothesis is about **static elastic deflection** of a slender beam-like
  body, and a **displacement scalar** is the quantity that tests it.
- A **closed-form reference exists** for the case (the envelope is validated
  against one, and outside that reference's own validity the endorsement lapses).

## 4. Do NOT choose this substrate when
- The quantity of interest is a **stress extremum** — it is reported-only, and
  its maximum sits on a singularity that has no converged value to find.
- The body is **stubby** (the reference stops being the right reference), the
  deflection is **large** (the physics assumption breaks), or the material is
  **near-incompressible** (a numerical failure the instrument cannot see).
- Anything **nonlinear, dynamic, contacting, buckling, or plastic** is involved.

## 5. Cost tier
**low.** Measured, not assumed: **0.45 s warm to 3.6 s cold** wall-clock per run
on the family-v1 ladder (envelope §7), 600 s hard kill. The cold/warm spread is
kernel compilation on first use and is published as a **range**, never a rate.

## 6. Confidence
**Lowest rung.** Maturity `calibrating`; provenance
`provisionally-signed (owner, 2026-07-16)` (copied from card §2 at commit
4800a93 — the card is the source of truth; re-verify at merge); the
calibration battery is **drafted but unexecuted** and the slate is ruled
(owner, 2026-07-16); the battery spend is what remains owner-gated. A human
sits at every trust call on this substrate — and it is unroutable,
so there are none to sit at yet.

## 7. Relationship to the sibling cantilever substrate — READ BEFORE ROUTING

This substrate and `calculix_cantilever_fea` serve **the same physics regime on
the same reference beam** and are, at the routing layer, genuine alternatives.
Two facts must travel with that:

1. **They are independent by construction.** This substrate carries its own copy
   of the closed-form reference, its own contract text, and shares no code with
   its sibling. Their agreement on the reference beam (1.31% vs 1.47% at the
   coarsest rung, both converging from below) is therefore **evidence**, not a
   tautology — which is the entire point of building a second one.

2. **They are not interchangeable, and the difference is not a preference.**
   The sibling's element fixes bending locking *in the element formulation*, so
   it hits ~1.5% on eight elements with no choices to make. This instrument
   **exposes that choice as typed input** (`element_degree`) and will accept,
   solve, and confidently report a locked, badly wrong answer if given the low
   order — with nothing in its diagnostics to say so. A router that treats these
   two as drop-in equivalents on `{envelope, cost, confidence}` alone will
   eventually route a case here, get a clean converged number, and be wrong by
   tens of percent. **The element-order bound (envelope ruling G5) must survive
   into any routing decision, or routing to this substrate is unsafe.**

---

# STAGED — router entry for `sympy_symbolic_exact` (Regime A)

> **STAGED, NOT MERGED.** The router card / cost tiers are **FROZEN** for this
> wave. Drafted from `docs/templates/router_card_TEMPLATE.md`. The Wave Guide
> merges serially.
>
> **SUBSTRATE-AGNOSTIC BY CONSTRUCTION.** Per the architecture invariant
> ("nothing above a tool wrapper may ever mention a specific solver by name") and
> the template's own instruction, **no solver is named below**. Upper layers see
> only abstract properties: validated envelope, cost, confidence. The concrete
> stack (SymPy 1.14.0 / SciPy 1.18.0 / `scipy-img`) lives in the envelope card
> §1 and in `tools/scipy_env/RESOLVED_VERSIONS.md`, both of which are
> human-facing and below-the-wrapper.

---

## 1. Identity

| Field | Value |
|---|---|
| Substrate | `sympy_symbolic_exact` |
| Physics regime | Regime A — **exact symbolic manipulation of one closed-form expression**. Not a simulation; not numerics. There is no discretization, no mesh, and therefore **no discretization-artifact family** — the disease that dominates the CFD and FEA cards is structurally absent here. |
| Envelope card | `docs/envelope_card_sympy_symbolic_exact.md` |
| Provenance state (from envelope card §2) | **`provisionally-signed`** (owner, 2026-07-16; history: `drafted-by-agent` → `provisionally-signed`). **S1–S6 + S2a/S4a/S4b are RULED (owner, 2026-07-16)** — see `docs/envelope_card_sympy_symbolic_exact.md` §3B and `onboarding/sympy_symbolic_exact/contract.py`, which are the sources for every bound named here. A provisional signature grants **interim authority**; it does **not** grant routability — see §4. |

## 2. Capability summary (abstract — no solver names)

| Property | Value |
|---|---|
| Physics served | Hypotheses reducible to **one closed-form expression in declared symbols** and **one** of: definite/indefinite integration, differentiation, limits, series expansion, algebraic root-finding, ODE solution. |
| QoIs servable | **Exact symbolic results** — an expression, or an exact scalar — each independently verified by back-substitution before it is returned. |
| QoIs NOT servable | Anything requiring: numeric quadrature as the *answer* (that is a **queued** separate regime); optimization/minimization; multi-expression systems; field data; time series; statistical quantities; anything about a physical apparatus. **Also: any claim beyond the expression as typed** (see §5). |
| Validated-envelope summary | Envelope card §3A — 7 operations exercised live, worst verified residual **4.05e-10** across 33 jobs (`diff` of `sin(10*x)`, the binding arm; only **2.47×** inside the ruled 1e-9); §3B **all six bounds RULED (owner, 2026-07-16)**, plus S2a (the residual verifies the RETURNED object) and S4a/S4b (a decline raised by the operation call is `unevaluated`). |

## 3. Cost tier

| Field | Value |
|---|---|
| **Cost tier** | **`cheap`** (template vocabulary: `cheap \| moderate \| expensive`) |
| Registry `cost_tier` | **`low`** — ⚠ **vocabulary mismatch, flagged for the Wave Guide:** `tools/substrate_registry.py` uses `low` / `minimal`, while `router_card_TEMPLATE.md` specifies `cheap` / `moderate` / `expensive`. The two fields are **not** the same vocabulary today. This entry states both rather than silently picking one; reconciling them is a Wave-Guide decision, not this session's. |
| Measured basis | Envelope card §7 — **8 live jobs this session**, `runtime_s` **0.617 – 1.403 s**; wall-clock is **container-startup-dominated**, not compute-dominated. |
| Hard kill limit | **600 s** default and ceiling; a contained resource bomb returned a named failure in **10.131 s** under an injected 10 s wall. |
| **Per-unit rate** | **RANGE: ≈0.6 – 1.8 s / job.** Deliberately **not** a constant: the range spans the whole operation set, and the spread tracks container startup + whether a cross-check is run, **not** symbolic difficulty. **An unevaluated non-answer costs the same as a solved one** — the substrate spends the effort either way, so cost is **not** a usable predictor of success here. |

*Cheapest tier in the fleet by an order of magnitude (sub-2 s vs the CFD
substrate's per-step solver rates), but see §5 — **cheap is not a reason to
route here**, because the routing question is whether the hypothesis is
expressible, not whether it is affordable.*

## 4. Confidence / maturity

| Field | Value |
|---|---|
| Maturity rung | **`calibrating`** — the entry rung. **Unroutable.** |
| Human-at-trust-calls? | **YES — unconditionally**, and the ruling+signature do **not** change this. The §3B bounds are now decided and the card carries interim authority, but the substrate remains **unroutable and uncalibrated** (no battery has run), and it would enter at `calibrating` even if registered. |
| Override history | **None** — the substrate has never run under the supervisor and has no ledger entries. |
| Calibration | Slate **PROPOSED** (`docs/scipy_calibration_cases_v1.md`), **unexecuted**, and **not yet loadable** by the battery (see `registry_row.md` §4). |

## 5. Routing rules

- **Prefer this substrate when:** the hypothesis is **exactly expressible as one
  closed-form expression**, the question is **about that expression itself**, and
  an **exact** answer is wanted rather than an approximate one.

- **Route away (defer) when:**
  - the operation is **outside the allowlist** (S1) — refuse by name; **never
    reach for a nearby operation as a workaround** (e.g. do not answer a
    minimization request by solving for stationary points);
  - the operation returns **`unevaluated`** (S4) — an **honest non-answer**, not
    a failure. Route to the right instrument; **do not re-ask, and do not report
    it as an error.** Some questions have no closed form, and saying so is the
    correct output;
  - the claim depends on an **assumption set whose match to intent cannot be
    established** (S5, the declared **KNOWN GAP**);
  - the request needs **numeric quadrature as the answer** — a **QUEUED separate
    regime** (owner ruling 2026-07-16). The numeric arm exists here **only** as a
    verification diagnostic and **must never be surfaced as a result.**

- **⚠ THE ROUTING TRAP — the one this card exists to prevent.** This substrate's
  failure mode is **not** returning a wrong number; it is returning an
  **exactly right number to the wrong question**, with residual 0.0 and full
  verification, indistinguishable at the router from a genuine success. Both
  measured this session:
  - an exact integral offered as a **mean value** (off by the interval length);
  - an exact radian evaluation offered against a **degrees** claim.

  So: **trust the result about exactly the expression as typed; always defer the
  modeling/utility claim separately** (S3). A high-confidence, cheap, exact,
  verified result from this substrate is **still not** an answer to a question it
  was never given. **Never let cost tier `cheap` + residual `0.0` read as "safe
  to route".**

- **Tie-break vs a peer substrate:** cost tier, then confidence — **but only
  among substrates that can actually express the hypothesis.** Expressibility is
  a **gate, not a tie-break**: this substrate is the cheapest in the fleet and
  would win almost every cost tie-break it entered, which is exactly why the
  expressibility gate must come first.

---

# Router entry — `ngspice_linear_passive` (STAGED)

The Wave Guide merges this. Nothing reads it today.

**Lands in:** the router card / cost-tier table (`docs/substrate_registry.md`),
alongside the `cost_tier` field carried by the `SubstrateRecord` row that
`registry_row_fragment.py` stages.

**Substrate-agnostic by construction:** no solver name, no container name, and
no netlist syntax appears below. Upper layers see capability, cost, and
maturity — nothing else. (The solver *is* named in the wrapper, the contract,
and the card; those all sit at or below the tool-wrapper line.)

---

| Field | Value |
|---|---|
| Substrate id | `ngspice_linear_passive` |
| Capability summary | Solves idealized lumped linear passive electrical networks and returns one scalar per run: a steady operating-point value, a swept response, a frequency response, or a time response. |
| Physics regime | Ideal linear passive networks — energy storage and dissipation with no nonlinearity, no device physics, and no physical-assembly effects. |
| Question shapes it answers | "What does this idealized network do?" — a steady value, a slope across a sweep, a corner frequency, a value at a stated time, or a screened extremum of a transient. |
| Question shapes it does NOT answer | Anything about a physical assembly (tolerance, parasitics, ESR, grounding); anything resting on device-model fidelity; anything nonlinear or behavioural; any analysis outside the four offered. |
| QoI cardinality | ONE scalar per run. No vector, no time series, no second quantity from the same solve. |
| Cost tier | **low** |
| Measured rate | **0.19 – 0.85 s** wall-clock per run (range, never a constant — see below) |
| Hard kill | 600 s → reported failure |
| Maturity | **`calibrating`** |
| Routable | **No** |

---

## Cost tier — the basis

`low`, on the same rung as `cavity_2d_cfd`, `calculix_cantilever_fea`, and
`code_sklearn_eval`.

Measured range **0.19 – 0.85 s per run** (median 0.26 s, n=31), from two on-disk
evidence files: `selfcheck_evidence.json` (9 single runs, 0.253 – 0.667 s) and
`coarse_extremum_evidence.json` (22 single runs, 0.19 – 0.848 s). Published as a
**range with its per-point evidence**, never as a per-run constant, per the D5
doctrine. (Note: `selfcheck_evidence.json` check b reports `runtime_s_total`
1.535 s — that is a six-run sweep total, not a single run, and is excluded from
the range.)

**Why the range is nearly flat and does not scale with the problem:** the cost
is container-exec overhead, not solve time. The networks in this regime solve in
milliseconds; a 30,023-row transient and a 3-element steady solve differ by well
under 3x. Do not model this substrate's cost as
proportional to circuit size or simulated duration — over the whole exercised
envelope it is close to a fixed per-invocation toll. If a future case ever does
approach the 600 s kill, that is a signal the case has left this regime, not a
cost-model refinement.

## Routing status

**Unroutable, deliberately.** Enrolling a row does not authorize routing (see
`substrate_registry.py`'s module docstring). Three things are true today and
each independently blocks routing:

1. **Maturity is `calibrating`.** The 15-case battery is assembled and
   pre-registered but **UNEXECUTED** — no calibration result exists.
2. **No fidelity contract is wired.** `contract_for("ngspice_linear_passive")`
   RAISES `LookupError` by design; the substrate has a registry row but no
   `_CONTRACTS` entry, exactly like FEA and code. See
   `registry_row_fragment.py` for why that raise is the invariant.
3. **Selection does not exist.** `sole_routable_id()` RAISES if the routable set
   is not exactly one. Promoting this substrate to routable without building
   multi-substrate node selection (Step 35, task typing) lands there loudly —
   which is the intended seam.

Promotion is a separate recorded ruling, after the battery runs and after an
external reviewer signs the card.
