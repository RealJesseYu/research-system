# FEniCSx V&V / benchmark sources — LOCATED, not applied

Mirrors `tools/fea_env/vv_sources.md` in shape and in discipline: this is a
**list only**, captured so a later card/validation session does not have to
re-find them. **Nothing here has been run.** No card text is written here, and
locating a NAFEMS case is explicitly not the same as executing one — running one
is a separate, later, owner-gated task.

Verification & validation references for the FEniCSx linear-elastic cantilever
family v1 (and its planned growth):

1. **Euler-Bernoulli beam theory** — closed-form tip deflection
   δ = P·L³/(3·E·I), I = w·h³/12. This wrapper's own `analytic_tip_deflection`
   (its OWN copy — deliberately not imported from the sibling CalculiX wrapper,
   so the two substrates' agreement is evidence rather than a tautology).
   **Applied this session**: see the card §3A (degree-2 gaps 1.31% → 0.31%
   across mesh 8 → 32).
2. **Timoshenko & Goodier, _Theory of Elasticity_** — the exact end-loaded
   cantilever elasticity solution including the shear-deformation correction.
   This is the reference that governs the G1 slenderness bound: it is what a
   stubby (L/h < 10) beam must be judged against, because Euler-Bernoulli is
   then the wrong reference, not merely an imprecise one.
3. **Roark's _Formulas for Stress and Strain_** — tabulated closed-form beam
   deflection and max-bending-stress formulas across load/support cases. The
   **max-bending-stress** tables are the candidate route to validating
   `max_von_mises`, which this card holds reported-only (G4).
4. **NAFEMS linear-elastic benchmark suite** — standardized LE static tests with
   published target values (e.g. LE1 elliptic membrane, LE10 thick plate); the
   community reference set for FEA solver validation. **LOCATED, NOT APPLIED** —
   a NAFEMS case is a different geometry and therefore a different card unit;
   running one is out of scope for this session by construction.
5. **The locking literature (the G5 bound's grounding).** Standard FE texts
   (Hughes, _The Finite Element Method_; Bathe, _Finite Element Procedures_)
   establish that fully-integrated low-order Lagrange elements exhibit **shear
   locking** in bending, and that the error is governed by element aspect ratio
   rather than element count — which is why refining a locked mesh through the
   thickness does not rescue it. **This session measured that directly** rather
   than citing it (card §3A/§3B, ruling G5): thickness-only refinement at
   nx=8 moved the degree-1 answer from 0.2800× to 0.2894× of the closed form —
   essentially nothing — while degree 2 sat at 0.987× on the very same 8×1×1
   mesh.
6. **Volumetric locking (a DIFFERENT disease — do not conflate).** ν → 0.5
   near-incompressibility causes volumetric locking, which degree-2 displacement
   elements do **not** fix (the standard remedies are mixed/`u-p` formulations,
   selective reduced integration, or F-bar). Referenced by card §4 (4D-analog)
   and case X10. **Not measured this session.**
7. **DOLFINx demo `demo_elasticity.py`** — the project's own linear-elasticity
   demo (indexed in `retrieval/fenicsx_docs_corpus/`), usable as an independent
   check that `dolfinx-prod` reproduces upstream behavior.
8. **The FEniCSx test suite** — DOLFINx's own regression tests, the solver's
   internal verification set.

**Cross-substrate note.** The strongest V&V asset this project has for family v1
is not in this list: it is the **sibling CalculiX card**
(`docs/envelope_card_calculix_cantilever.md`), whose §3A exercises the *same
beam* against the *same closed form* through an entirely independent solver,
element technology, and wrapper. Two independent instruments agreeing on one
reference beam is a stronger statement than either card alone — and this session
kept them independent on purpose (no shared helper, no copied contract text) so
that the agreement means something. Comparing them is a later, deliberate act,
not an assumption baked into either wrapper.
