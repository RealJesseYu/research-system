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
| Provenance state (from envelope card §2) | `drafted-by-agent` |

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
**Lowest rung.** Maturity `calibrating`; provenance `drafted-by-agent`; the
calibration battery is **drafted but unexecuted** and the slate is an owner ruling
first. A human sits at every trust call on this substrate — and it is unroutable,
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
