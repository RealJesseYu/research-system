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
| `cavity_2d_cfd` | `tools/run_cfd.py` | `docs/envelope_card_cavity2d.md` | **provisional** | **yes** | low | real runs accruing, mini-21 pending; the sole routable substrate (current behavior) |
| `calculix_cantilever_fea` | `tools/run_fea.py` | `docs/envelope_card_calculix_cantilever.md` | calibrating | no | low | battery pending owner OK |
| `code_sklearn_eval` | `tools/run_code.py` | `docs/envelope_card_code_sklearn_eval.md` | calibrating | no | low | battery not on the run manifest — owner decision pending |
| `fenicsx_cantilever_elastic` | `tools/run_fenicsx.py` | `docs/envelope_card_fenicsx_cantilever_elastic.md` | calibrating | no | low | slate drafted (15 cases); battery pending owner OK on the slate ruling |
| `web_search` | `tools/web_search_stub.py` | (this doc) | retrieval-provisional | no | minimal | structurally never trusted alone |

## The ladder semantics and the promotion rule

For routable substrates the ladder runs **calibrating → provisional → mature**,
low to high. *Calibrating* means a card exists (or a battery is being
assembled) but the substrate has not earned unattended trust — it is never
routable. *Provisional* means real runs are accruing and the wrapper behaves,
but calibration is not complete; a provisional substrate may be routable, but
any trust decision that touches it is **human-required** (the supervisor marks
it `needs_human_signoff` and, in auto mode, downgrades the trust/refine verdict
to defer-class handling rather than trusting it silently). *Mature* means
calibration is complete and trust decisions may proceed unattended. **No
substrate is mature today** — `cavity_2d_cfd`, the sole routable substrate,
sits at provisional, so every trust decision the pipeline can currently make is
human-required by construction. `web_search` sits in its own class,
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
