# Anomaly scan v0 — read-only report

- run dirs walked: 183
- stage4/results.json parsed: 33
- numeric families collected: 10

_A scanner, not a judge: findings are shapes to look at, not conclusions._

## (a) Outliers (IQR rule, n>=4 per family)
- **max_Courant** (3):
    - `handfeed4-20260704T083221Z_run1` = 0.604011 (fences [0.2691, 0.326])
    - `handfeed4-20260706T045314Z_run1` = 0.604011 (fences [0.2691, 0.326])
    - `validate18-T2-same1-h5_run3` = 0.250173 (fences [0.2691, 0.326])
- **residual:Ux** (3):
    - `20260706T063330Z_run2` = 1.04906e-05 (fences [-2.986e-06, 5.001e-06])
    - `20260706T063330Z_run3` = 2.11716e-05 (fences [-2.986e-06, 5.001e-06])
    - `handfeed4-20260706T075137Z_run3` = 1.25445e-05 (fences [-2.986e-06, 5.001e-06])
- **residual:Uy** (3):
    - `20260706T063330Z_run2` = 1.03881e-05 (fences [-3.063e-06, 5.111e-06])
    - `20260706T063330Z_run3` = 2.08798e-05 (fences [-3.063e-06, 5.111e-06])
    - `handfeed4-20260706T075137Z_run3` = 1.29271e-05 (fences [-3.063e-06, 5.111e-06])
- **residual:p** (4):
    - `20260706T063330Z_run2` = 1.29228e-05 (fences [-3.66e-07, 2.925e-06])
    - `20260706T063330Z_run3` = 2.99397e-05 (fences [-3.66e-07, 2.925e-06])
    - `handfeed4-20260706T075137Z_run3` = 2.68728e-05 (fences [-3.66e-07, 2.925e-06])
    - `validate18-T2-same1-h5_run3` = 3.01568e-06 (fences [-3.66e-07, 2.925e-06])

## (b) Identical values repeated across DISTINCT runs
- **qoi:volAverage(mag(U))**:
    - 0.416835 in 2 runs: handfeed4-20260704T083221Z, handfeed4-20260706T045314Z
    - 0.193007 in 2 runs: handfeed4-20260704T083221Z, handfeed4-20260706T045314Z

## (c) Predicted-vs-actual wall-time gaps
- none — no predicted/estimated wall-time field found on disk (nothing writes one today); actual wall times are collected and IQR-scanned above.

## (d) Structural oddities
- none

## Numeric families collected (name -> point count)
- continuity_global: 16
- max_Courant: 16
- qoi:cellMin(U): 3
- qoi:cellMin(U)[0]: 3
- qoi:volAverage(mag(U)): 7
- residual:Ux: 16
- residual:Uy: 16
- residual:p: 16
- solver_execution_time_s: 16
- wall_clock_s: 16
