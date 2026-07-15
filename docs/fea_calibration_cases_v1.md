# FEA Calibration Cases — v1 (calculix_cantilever, family-v1 typed input)

> **SPECS ONLY — NO EXECUTION.** This document defines labeled calibration cases
> for the CalculiX linear-elastic cantilever substrate. Running the battery is a
> **later ⚙ task that needs owner OK** — nothing here has been executed. The
> substrate is UNREGISTERED; these cases pre-register what a correct gate verdict
> should look like so the calibration run has an answer key.
>
> Companion card: `docs/envelope_card_calculix_cantilever.md` (bounds F1–F4).
> Base beam (in-envelope reference): L=1.0, w=h=0.05 m, E=210e9 Pa, ν=0.3,
> P=1000 N, L/h = 20.

## Class counts

| expected_class | count | case ids |
|---|---|---|
| `in` (in-envelope) | 5 | C01, C02, C03, C04, C05 |
| `out` (out-of-envelope) | 4 | C06, C07, C08, C09 |
| `setup_error` (nonphysical input) | 5 | C10, C11, C12, C13, C14 |
| **Total** | **14** | |

The three envelope bounds referenced below are the card's *suggested* values
(F1 slenderness L/h ≥ 10; F2 linearity δ_tip/L ≤ 0.10; F3 mesh reproduction
≤ 2%). They are TODO-HUMAN and may move; the labels here follow the suggestions.

---

## In-envelope cases (expected_class: `in`)

### C01 — base beam, coarse mesh
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 8}`
- **why:** the validated reference beam (L/h = 20, δ/L ≈ 0.3%); both F1 and F2 satisfied with wide margin.
- **correct verdict:** trust — `tip_displacement` validated within family (≈1.47% gap vs Euler-Bernoulli at this mesh, inside the F3 band).

### C02 — base beam, refined mesh
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 16}`
- **why:** same beam, finer mesh; tests mesh-reproduction (F3) — gap should drop toward ~0.6%.
- **correct verdict:** trust — validated; gap well inside F3.

### C03 — long slender beam, light load
- **params:** `{length: 2.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 500.0, mesh_density: 16}`
- **why:** very slender (L/h = 40), small deflection; deep inside F1 and F2.
- **correct verdict:** trust — validated within family.

### C04 — moderate beam at the slenderness boundary
- **params:** `{length: 1.0, width: 0.10, height: 0.10, E: 210e9, nu: 0.3, tip_load: 2000.0, mesh_density: 16}`
- **why:** L/h = 10, exactly at the suggested F1 bound; a boundary in-envelope case to test where the gate draws the slenderness line.
- **correct verdict:** trust, with a note that the case sits at the F1 boundary — shear correction is marginal here (~1–2%); acceptable but the closest in-envelope case to `out`.

### C05 — aluminium beam, larger section
- **params:** `{length: 2.0, width: 0.10, height: 0.10, E: 70e9, nu: 0.33, tip_load: 5000.0, mesh_density: 8}`
- **why:** different material (aluminium E, ν) and section, still slender (L/h = 20) and small-deflection; confirms the envelope is material-agnostic within linear-elastic isotropic.
- **correct verdict:** trust — validated within family.

---

## Out-of-envelope cases (expected_class: `out`)

### C06 — stubby beam, shear-dominated
- **params:** `{length: 0.2, width: 0.05, height: 0.10, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 16}`
- **why:** L/h = 2 — below the F1 slenderness bound; shear deformation dominates and the Euler-Bernoulli self-check is no longer the correct reference (3D FEA will deflect more than the EB limit).
- **correct verdict:** refine or defer (out_of_envelope), naming L/h = 2 shear-dominated; `tip_displacement` may be returned but is NOT validated against Euler-Bernoulli here — a Timoshenko/elasticity reference is required.

### C07 — very stubby beam
- **params:** `{length: 0.1, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 16}`
- **why:** L/h = 2, second shear-dominated point at a different absolute scale; confirms the F1 violation is about the ratio, not the size.
- **correct verdict:** refine/defer (out_of_envelope), shear-dominated, EB reference invalid.

### C08 — large load, geometric nonlinearity
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 50000.0, mesh_density: 16}`
- **why:** at this load the linear prediction gives δ_tip ≈ 0.15 m → δ/L ≈ 15%, above the F2 linearity bound (0.10). The linear small-deflection solve is physically wrong (geometric stiffening ignored) though it still converges.
- **correct verdict:** refine/defer (out_of_envelope), naming δ/L > 0.10 — large-deflection regime; the linear static result over-predicts deflection and must not be trusted.

### C09 — near-incompressible, locking risk
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.4999, tip_load: 1000.0, mesh_density: 16}`
- **why:** ν = 0.4999 is a *valid* input (passes `_validate_input`, < 0.5) but near-incompressible; C3D8I hex elements risk volumetric locking, so the result is numerically suspect even though the solver converges.
- **correct verdict:** refine/defer (out_of_envelope / numerics), flagging near-incompressible locking risk with C3D8I; NOT a setup_error (the input is well-formed) — the envelope violation is physical/numerical.

---

## Setup-error cases (expected_class: `setup_error`)

These are rejected by `_validate_input` before any solve; the wrapper returns
`valid=False` with a named reason and **no QoI**.

### C10 — negative Young's modulus
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: -210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 8}`
- **why:** negative stiffness is nonphysical; violates the "E must be positive" input rule.
- **correct verdict:** setup_error — input rejected at validation ("field 'E' must be positive"); nothing runs, no number fabricated.

### C11 — zero thickness
- **params:** `{length: 1.0, width: 0.05, height: 0.0, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 8}`
- **why:** a beam with zero height has no cross-section; violates "height must be positive".
- **correct verdict:** setup_error — input rejected ("field 'height' must be positive").

### C12 — Poisson's ratio out of range
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.6, tip_load: 1000.0, mesh_density: 8}`
- **why:** ν ≥ 0.5 is nonphysical for an isotropic elastic solid; violates the ν ∈ (−1, 0.5) rule.
- **correct verdict:** setup_error — input rejected ("nu must be in (-1, 0.5)").

### C13 — zero mesh density
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 0}`
- **why:** mesh_density < 1 yields no elements; violates the "mesh_density must be >= 1" rule.
- **correct verdict:** setup_error — input rejected ("mesh_density must be >= 1").

### C14 — unsupported extra field
- **params:** `{length: 1.0, width: 0.05, height: 0.05, E: 210e9, nu: 0.3, tip_load: 1000.0, mesh_density: 8, material: "steel"}`
- **why:** `material` is not a family-v1 field; the typed input rejects unknown keys by name rather than silently ignoring them.
- **correct verdict:** setup_error — input rejected ("unsupported field(s) for cantilever v1: material").

---

## Notes for the future battery run

- Cases C01–C09 are executable decks; C10–C14 are expected to halt at input
  validation before any `ccx` call (fast, no container work).
- C04 (F1 boundary) and C09 (near-incompressible) are the most informative
  *edge* cases — where the gate must draw a line the wrapper itself cannot see.
- The `out` cases share a theme: the solver **converges and returns a number**,
  but the number is outside what family-v1's Euler-Bernoulli reference or the
  linear/small-deflection/well-conditioned assumptions can validate. That is the
  converged-but-out-of-envelope class the fidelity gate must catch, since no
  internal diagnostic will.
