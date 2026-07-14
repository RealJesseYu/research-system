# Reviewer Rubric — Envelope Cards (one page)

> **STATUS: FINALIZED — human pass 2026-07-15 (Step 20.5 CLOSE).**
> This rubric is the checklist an external domain expert uses to review any
> envelope card (Step 26's expert-review lane). Card unit = (substrate,
> physics-regime) pair.

---

## Purpose

An envelope card is the fidelity gate's grounding: the honest, disk-backed
statement of what a (substrate, regime) pair can and cannot do. A card that
overstates the envelope silently corrupts every downstream fidelity verdict.
The reviewer's job is to confirm the card is **defensible, complete, and
honestly scoped** for the physics it claims — not to re-run the simulations.

---

## What the reviewer checks

For each item: **PASS** / **CONCERN** / **FAIL**, with a one-line reason.

1. **Regime boundaries defensible.**
   Are the validated-envelope ranges (the card's Table 3A) justified by the
   cited evidence, and is the believed-but-unexercised region (Table 3B) clearly
   fenced off from the validated one? A converged run cited as *validated* is a
   FAIL unless mesh-independence / benchmark backing is shown.

2. **Failure modes complete for this physics.**
   Does the card name the failure modes a domain expert would expect for this
   regime? For a laminar 2D cavity: transition/turbulence onset,
   mesh under-resolution, out-of-envelope Reynolds, spurious steady states,
   un-buildable geometry/BCs, un-extractable derived quantities. A missing mode
   the expert knows to be real is a CONCERN or FAIL.

3. **Diagnostics honestly scoped.**
   Does the card correctly separate what internal diagnostics CAN see
   (non-convergence, blow-up, Courant ≫ 1) from what they CANNOT
   (converged-but-wrong, mesh-independence, regime-assumption certainty)?
   Overclaiming diagnostic reach is a FAIL — this is the most dangerous error a
   card can make.

4. **Extraction contract matches solver reality.**
   Do the canonical parameters, the QoI operations, and the single-shot /
   latest-time / no-derived-field limits match what the solver + wrapper
   actually do? A claimed capability the wrapper does not have is a FAIL.

5. **Cost model plausible.**
   Are the quoted rates measured (with citations) rather than guessed, and do
   they cover the regime the card claims? Guessed or uncited cost numbers are a
   CONCERN.

6. **Citations present and honest.**
   Is every validated-envelope entry disk-cited, and is every literature claim
   marked as such (not silently asserted as system-measured)? An invented
   number is a FAIL.

---

## Verdict vocabulary (three outcomes)

- **sign-off** — the card is defensible, complete, and honestly scoped as
  written. No changes required.
- **sign-off-with-amendments** — sound in substance, but specific listed items
  must be corrected first (each amendment names the section and the fix). The
  card is usable only once the amendments are applied.
- **reject-with-reasons** — a load-bearing defect (overclaimed envelope,
  overclaimed diagnostics, invented number, missing critical failure mode). The
  card must be reworked and re-reviewed. Each reason names the section and the
  defect.

An open **TODO-HUMAN** field or unresolved `[CITATION NEEDED]` marker in a
load-bearing section (Validated envelope, Diagnostics, Extraction contract)
blocks **sign-off** — the most such a card can earn is
**sign-off-with-amendments**.

---

## Provenance-field update rule

The reviewer updates the card's Provenance block (§2) on completing a review:

| Reviewer verdict | Provenance state written |
|---|---|
| sign-off | `signed / <reviewer> / <date>` |
| sign-off-with-amendments | `provisional / amendments-pending / <reviewer> / <date>` — stays provisional until the author applies amendments, then re-attests |
| reject-with-reasons | `rejected / <reviewer> / <date>` — card returns to drafting; provisional signature (if any) is void |

A provisionally-signed card grants INTERIM fidelity-gate grounding authority
while its substrate is below mature maturity — a human sits at its trust calls
regardless (the Step-28 hook), which is the covering control. FULL standalone
grounding authority requires Provenance state `signed`. (Aligned with the plan
of record, Step 26 — human pass 2026-07-15.)
