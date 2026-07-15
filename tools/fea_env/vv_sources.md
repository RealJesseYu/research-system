# FEA V&V / benchmark sources — located for the LATER card session

Step 27 is DRY (wrapper + docs index only). This is a **list only**, captured so
the later substrate-card session does not have to re-find them. No card text is
written here.

Verification & validation references for the linear-elastic cantilever family v1
(and its planned growth):

1. **Euler-Bernoulli beam theory** — closed-form tip deflection
   δ = P·L³/(3·E·I), I = w·h³/12. This wrapper's built-in analytic self-check
   (see the Step-27 smoke: 1.47% gap at 8×1×1, 0.55% at 32×2×2).
2. **Timoshenko & Goodier, _Theory of Elasticity_** — the exact end-loaded
   cantilever elasticity solution, including the shear-deformation correction
   that separates a stubby beam's 3D result from Euler-Bernoulli.
3. **Roark's _Formulas for Stress and Strain_** — tabulated closed-form beam
   deflection and max-bending-stress formulas for a range of load/support cases
   (a broader validation set as the family grows beyond a tip point load).
4. **NAFEMS linear-elastic benchmark suite** — standardized LE static tests
   (e.g. the cantilever/beam and elliptic-membrane LE benchmarks) with published
   target values; the community reference set for FEA solver validation.
5. **CalculiX manual worked examples** — "Simple example problems" (node6.html)
   and the "Cantilever beam" example (node7.html) in the indexed manual, which
   carry the author's own reference numbers.
6. **CalculiX structural test suite** — `ccx_2.23.structest.tar.bz2` from
   www.dhondt.de: the solver's own regression/verification cases, usable as an
   independent check that ccx-prod reproduces upstream results.
