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
