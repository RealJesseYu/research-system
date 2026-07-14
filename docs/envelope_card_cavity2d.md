# Envelope Card — (cavity_2d, laminar incompressible 2D)

> **STATUS: FINALIZED — human pass 2026-07-15 (Step 20.5 CLOSE).**
> Judgment fields ruled by owner (rulings D1–D7, strategy session 2026-07-15).
> Provenance: provisionally signed; external expert review pending
> (dispatch scheduled 2026-07-17 together with docs/reviewer_rubric.md).

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `cavity_2d` |
| Physics regime | 2D incompressible **laminar** cavity-class flow (closed box, one or more moving walls) |
| Solver | OpenFOAM v12, `foamRun`/incompressibleFluid, in container `of12-prod` |
| Wrapper | `tools/run_cfd.py` (deterministic Python, no AI), graduated Step 11 |
| Wrapper commit (last touch) | `6e4796b` (17-fix-A close) — component-carrying QoI names |
| Contract text (last touch) | `substrates.py` `CAVITY_2D_CONTRACT`, commit `4634a1d` (Step 13) |
| Card drafted against repo HEAD | `2f421bd` |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, doc-only session) |
| Drafted date | 2026-07-13 |
| Sources | repo run evidence (richest), substrate contract in code, solver V&V literature (placeholder-cited only — no web calls this session) |
| Signature | `provisionally-signed / owner / 2026-07-15` |
| Reviewer sign-off | `pending — dispatch to external reviewers 2026-07-17` |
| Provenance state | `provisionally-signed / awaiting-external-review` |

---

## 3. Validated envelope

Two sections, deliberately separate. **Nothing enters Table 3A without an
on-disk citation.** §3B (the believed-but-not-exercised region) is ruled by the
human pass 2026-07-15 (rulings D2–D4).

### 3A. Ranges actually exercised (disk-cited)

Every row below is a parameter value the system has actually run and observed.
"Converged" here means the wrapper's exact definition (end time reached AND all
start-of-final-step residuals < 1e-3) — it is **not** a claim of physical
validity or mesh-independence (see §4 and §5).

| Parameter | Exercised value(s) | Outcome | Evidence (file / run id) |
|---|---|---|---|
| `cavity_length` | 1.0 m | converged | Run C `20260713T020121Z` (3 runs); Step-11/12 baseline |
| `mesh_resolution` | 64 (i.e. 64×64×1) | converged | Run C `20260713T020121Z`; `cases/cavity_baseline`; Step-11 live proof |
| `kinematic_viscosity` | 0.1, 0.01, 0.001 m²/s | converged | Run C `20260713T020121Z` runs 1/2/3 |
| `lid_velocity` | 1.0 m/s | converged | Run C `20260713T020121Z`; Step-12 run2 (`handfeed4-20260704T083221Z`) |
| `lid_velocity` | 2.0 m/s | converged | Step-11 live proof; Step-12 run1 |
| `end_time` | 20 s | converged | Step-11/12 baseline runs |
| `end_time` | 100 s | converged | Run C `20260713T020121Z` |
| `time_step` | 0.002 s | converged | Step-11 baseline (qoi 0.4168179) |
| `time_step` | 0.005 s | converged | Step-12 + Run C |
| Reynolds (derived) | Re=10, 100, 1000 | converged, residuals ~1e-8 to ~1e-6, max Courant < 0.31 | Run C `20260713T020121Z` |
| Reynolds (derived) | Re=200 | converged (the spike's original validated point) | Step-11 live proof; contract §1 |
| Reynolds (derived, **converged not validated**) | "Re=100–1600 on 64×64 converges reliably" | learned summary, single-run observations | journal `handfeed4-20260706T075137Z` |

**Calibration points (executed QoI values, disk-cited):**

| Re | lid | mesh | QoI | value | Evidence |
|---|---|---|---|---|---|
| 200 | 2.0 | 64 | volAverage(mag(U)) @ t=20 | 0.4168179 m/s | Step-11 live proof (determinism-checked) |
| 10 | 1.0 | 64 | cellMin(U)[0] @ t=100 | −0.207748 m/s | Run C run1 |
| 100 | 1.0 | 64 | cellMin(U)[0] @ t=100 | −0.241654 m/s | Run C run2 |
| 1000 | 1.0 | 64 | cellMin(U)[0] @ t=100 | −0.368362 m/s | Run C run3 |

> **Anchor benchmark:** volAverage(mag(U)) ≈ 0.42 m/s for the Re=200, lid=2.0,
> 64×64 baseline is the system's own reproduced reference value (Step-11,
> determinism-checked). It is the number the coarse-mesh failure case (§4) is
> measured against.

### 3B. Ruled envelope (human pass 2026-07-15)

**Reynolds ruling (D2), four tiers:**

- **Re ≤ 200 — VALIDATED CORE (trust class).** Anchored by the
  determinism-checked Re=200 calibration point (§3A).
- **200 < Re ≤ 1000 — EXERCISED, CONVERGED;** calibration points at Re=100 and
  Re=1000. Known caveat: the 64×64 grid marginally under-resolves near
  Re=1000 vs the Ghia et al. (1982) 129×129 benchmark (two refine verdicts
  on record). Verdict guidance: trust for qualitative claims; refine for
  threshold-sensitive quantitative claims near the top of this band.
- **1000 < Re ≤ 1600 — CONVERGED-NOT-VALIDATED** (journal handfeed4: converges
  reliably; zero calibration points). Verdict ceiling: refine.
- **Re > 1600 — OUT OF ENVELOPE.** Verdict: defer (out_of_envelope).

**Physical-realizability scope:**

Real cavity flow develops three-dimensional instabilities near Re ≈ 786
(Albensoeder, Kuhlmann & Rath 2001, Physics of Fluids); the 2D steady solution
remains mathematically well-defined far beyond (first 2D Hopf bifurcation
≈ Re 8000 — Bruneau & Saad 2006, Computers & Fluids; other published
localizations fall between ≈7,300 and 10,000). Above Re ≈ 800, results from
this substrate are claims about the idealized 2D system, not predictions of a
physical cavity; papers must scope such claims explicitly as 2D-system
results. [Citations verified by live search 2026-07-15.]

**Mesh policy (D3):**

64×64 is the standard operating grid. Mesh-independence is certified at NO
resolution. Standing rule: the first use of any new resolution must reproduce
one Ghia et al. (1982) benchmark point before its numbers are treated as
validated. A mesh-independence sweep is a queued calibration item, not a
blocker.

**Geometry ruling (D4):**

Validated configuration = square cavity, side 1.0 m, single moving lid,
uniform mesh — exactly as exercised. Aspect ratios ≠ 1:1, multiple moving
walls, cavity_length ≠ 1.0 m: unvalidated configuration → defer/refine with
the configuration named.

**Re-similarity (D4):**

Re = lid_velocity × cavity_length / kinematic_viscosity is the governing
parameter; parameter decompositions yielding the same Re are physically
equivalent experiments and acceptable at in-envelope Re, PROVIDED time_step is
scaled to hold max Courant < ~0.5. [JUDGMENT 2026-07-15 — dimensional-similarity
grounds, not disk-exercised.]

---

## 4. Known failure modes

Each mode below is backed by disk evidence — a fidelity verdict, an executed
run, or a hand-authored triage fixture (marked as such).

### 4A. Un-buildable geometry / boundary conditions → builder halts (defer class)
The case builder honors exactly six canonical parameters (§6). Anything else
halts loudly, by name. Two observed sub-classes:

- **Spatially-varying / non-uniform lid profiles** (codedFixedValue, mapped,
  bimodal/cosine/double-Gaussian). Evidence: fidelity ledger, Run B
  `20260712T212952Z` — two defers ("no `profile_amplitude`… scalar
  `lid_velocity` cannot express the spatially-varying cosine lid"; "double-
  Gaussian… requires codedFixedValue and non-canonical parameters
  `profile_sigma`, `profile_peak_velocity`"). Learned summary same run:
  "supports only a uniform scalar lid velocity."
- **Non-canonical geometry** (central obstacle, per-axis dimensions, S-shaped
  walls). Evidence: fidelity ledger, Run C `20260713T020121Z` defer ("cannot
  build the central-obstacle geometry — non-canonical parameters halt the
  builder"); journal `handfeed4-20260706T045429Z` (S-shaped staircase mesh).

### 4B. Un-extractable QoI → defer class
The QoI path is a single volume reduction over a field the case already wrote
(§6). Derived/gradient fields and sub-domain integrals are outside it.

- **Vorticity / enstrophy** (a velocity-gradient derivation) is never written
  and cannot be reduced. Evidence: fidelity ledger `handfeed3-20260707T183101Z`
  ("cannot compute ∂v/∂x−∂u/∂y"); Run C `20260713T020121Z` defer ("enstrophy…
  a two-step vorticity/squared-magnitude derivation outside the single-
  operation QoI path"); Run A `20260712T194452Z` defer (sub-domain circulation
  ratio; vorticity never written, sub-domain integration unsupported).
- **Concentration / tracer mixing QoIs** — no scalar-transport physics, so no
  concentration field exists. Evidence: contract §4; journal
  `20260705T214035Z`, `20260706T023653Z` (passive-scalar transport absent).
- **Spatially-masked / line-sampled QoIs** (corner-vortex KE, centerline
  ratios, vortex-core position). Evidence: journal `20260706T030119Z`,
  `053329Z`, `083542Z`, `090043Z`.

### 4C. Mesh under-resolution near threshold values → **converged-but-wrong** (refine class, and the diagnostics-blind case)
A run can converge cleanly yet return a physically biased number when the mesh
under-resolves the flow. This is the failure the diagnostics cannot see on
their own (§5).

- **Threshold-adjacent under-resolution.** Evidence: fidelity ledger, TWO
  refine verdicts — Run A `20260712T194452Z` and Run C `20260713T020121Z`:
  "64×64 mesh at Re=1000 is marginally under-resolved versus the Ghia et al.
  129×129 benchmark… the trust-critical −0.35 threshold sits exactly where that
  error bites." (Ghia et al. 129×129 is a literature benchmark: Ghia, U.,
  Ghia, K.N. & Shin, C.T. (1982), 'High-Re Solutions for Incompressible Flow
  Using the Navier-Stokes Equations and a Multigrid Method,' Journal of
  Computational Physics 48, 387–411 (Re=1000 solution on the 129×129 grid;
  solutions to Re=10,000 on grids up to 257×257). [Verified by live search
  2026-07-15.])
- **Coarse-mesh high bias, converged.** Evidence: triage fixture
  `harness/triage_cases/2_coarse_mesh.json` (**hand-authored, NOT a real run**):
  an 8×8 cavity at Re=200 that *converges* but returns volAverage(mag(U)) =
  0.71 m/s, ~1.7× the ~0.42 benchmark — a resolution artifact, not a discovery.

### 4D. Out-of-envelope use → spurious steady state (out_of_envelope class)
Running the instrument outside its validated laminar 2D envelope can produce a
"converged steady" result that is a numerical artifact.

- **Signature: max Courant ≫ 1.** Evidence: triage fixture
  `harness/triage_cases/4_envelope_drift.json` (hand-authored, NOT a real run):
  lid 25 m/s, ν=0.01, L=1 → Re=2500 — far above this card's validated ceiling
  (Re=1600), with a time step violating numerical stability (max Courant = 6.2,
  the out-of-envelope tell). The solver reports 'converged steady'; the result
  is a numerical artifact. `more_data` remains the one wrong response.
  NOTE (human pass 2026-07-15): an earlier draft justified this fixture via a
  claimed Hopf bifurcation at Re_c≈1914; a live literature check found no such
  value (2D onset ≈7,300–8,000). The claim is struck; the fixture's planted
  correct answer (out_of_envelope) stands on the ceiling-and-Courant grounds
  above; the fixture file itself is unchanged.

### 4E. Turbulent physics silently mis-simulated
No turbulence models exist. A case whose physics is actually turbulent will not
be simulated correctly **and the wrapper cannot detect that.** Evidence:
contract §4 (declared limit; no run exercises it — this is a declared, not
observed, mode).

### 4F. Labeling convention (ruling D6, 2026-07-15)
`setup_error` = the case deviates from card-standard configuration (e.g., an
8×8 mesh where the standard is 64×64). `out_of_envelope` = card-standard
configuration applied beyond its supported regime (e.g., 64×64 at Re=2500).
The §4C coarse-mesh fixture is setup_error primary, out_of_envelope defensible
secondary; the triage battery continues to accept both.

---

## 5. What the diagnostics CAN and CANNOT see

The wrapper returns: `converged` (bool), per-field `residuals`, `final_time`,
`max_Courant`, `continuity_global`, `runtime`. What that buys:

**CAN detect (from the returned summary alone):**
- Failure to reach end time / non-convergence (residuals ≥ 1e-3).
- Solver blow-up or stall (600 s timeout → reported failure).
- **Out-of-envelope instability signature** when it shows in `max_Courant ≫ 1`
  (§4D, envelope_drift fixture: Courant 6.2) or in elevated residuals
  (envelope_drift residuals ~8e-5 to ~7e-4 vs Run C's ~1e-8).

**CANNOT detect without an external benchmark:**
- **Converged-but-wrong.** A converged run with clean residuals and a benign
  Courant number can still return a physically biased QoI. The coarse_mesh
  fixture (§4C) is the canonical evidence: converged=true, residuals ~4e-8,
  yet 0.71 vs the ~0.42 benchmark — invisible to every internal diagnostic. The
  ONLY way to catch it is comparison to an independent benchmark value.
- **Mesh-independence.** "Convergence is judged from residuals and end time
  only; it says the solver settled, not that the physics is resolved" (contract
  §4). Mesh-independence is nobody's promise here.
- **Regime-assumption certainty** — whether the assumption that places a case
  "in-envelope" is itself correct. Explicitly NOT checked anywhere (contract
  §4; a carried open axis for the fidelity gate's future work).

---

## 6. Extraction contract (verbatim)

**Canonical parameter vocabulary** (`substrates.py` §5) — the builder honors
exactly these; anything else halts loudly, by name:

| Name | Units | Meaning |
|---|---|---|
| `kinematic_viscosity` | m²/s | fluid kinematic viscosity |
| `lid_velocity` | m/s | moving-wall speed |
| `cavity_length` | m | side length (uniform scaling) |
| `mesh_resolution` | cells/side | N, meshed as N×N×1 |
| `end_time` | s | simulated end time |
| `time_step` | s | solver time step |

Reynolds number is never buildable directly: specify `lid_velocity`,
`cavity_length`, `kinematic_viscosity`; Re may be stated only as a derived
quantity (verified against that decomposition within 1%, not honored on its
own).

**QoI extraction path** (`substrates.py` §3, `tools/run_cfd.py`) — verbatim
capability:
- ONE quantity of interest per run, from a field the case **already wrote**, at
  the **latest written time only**.
- Operations: `volAverage | min | max | volIntegrate` over one existing field.
- Optional component: `mag` (magnitude) or `0|1|2` (single vector component).
- Precondition: the run must have **reached its declared end time**.
  Convergence is reported separately; a QoI from an unconverged run is returned
  **without endorsement** — usability is downstream judgment.
- On success: `qoi {name, field, operation, value, time}` (name carries the
  component, e.g. `cellMin(U)[0]`).
- On ANY failure (missing field, post-processing error, unparseable output):
  `qoi_error` with an honest reason and **NO qoi block** — the instrument never
  fabricates a number.
- Single-shot only: no time-series, no probes, no field sampling beyond these
  volume reductions.
- Velocity/pressure-field statistics YES; concentration/tracer fields NO (no
  scalar-transport physics; no field the case didn't write).

---

## 7. Cost model (measured rates)

| Regime | Measured rate | Evidence |
|---|---|---|
| endTime 20 s, Δt 0.005 (4000 steps), transient, 64×64 | solver ExecutionTime **9.2–9.3 s/run**; wall-clock **11.4–11.6 s/run** | contract §3 (measured Step 12, two production mini-runs) |
| endTime 100 s, Δt 0.005 (20000 steps), 64×64, Re 10/100/1000 | solver **71.5 / 72.2 / 81.0 s**; wall-clock **91.3 / 90.6 / 101.6 s** | Run C `20260713T020121Z` |
| Hard kill limit | 600 s wall-clock → reported failure | `tools/run_cfd.py` `TIMEOUT_SECONDS` |

**Per-step rate (derived, NOT constant):** Step-12 runs give ≈2.3 ms
solver-time/step (9.25 s / 4000). Run C gives ≈3.6–4.1 ms/step (71–81 s /
20000). The higher-endTime / higher-Re runs cost more per step — the ~2.3
ms/step figure is the low-Re short-run rate, not a universal constant.

**Ruling (D5, 2026-07-15):** Both measured operating points stay quoted as
tabulated above. Per-step rate is published as a RANGE — 2.3–4.1 ms
solver-time/step — NOT a constant; it rises with Re and run length. No
single-number per-step rate may be quoted from this card.

---

## 8. Resolved questions (human pass 2026-07-15)

Each Step-20.5-START open question, with its ruling:

1. **True validated Reynolds ceiling → D2.** Resolved by the four-tier ruling
   (§3B): validated core Re ≤ 200; exercised-converged to Re ≤ 1000;
   converged-not-validated to Re ≤ 1600; out of envelope above.
2. **Mesh-independence policy → D3.** Resolved by the mesh policy (§3B): 64×64
   standard grid, mesh-independence certified at no resolution, new-resolution
   Ghia-benchmark reproduction rule, sweep queued not blocking.
3. **Finer-mesh Ghia cross-check → D3.** Same mesh policy: the first use of any
   new resolution must reproduce one Ghia et al. (1982) point before its
   numbers are treated as validated.
4. **Cost-model rate to quote → D5.** Resolved (§7): both measured operating
   points stay tabulated; per-step rate published as the 2.3–4.1 ms/step range,
   never a single number.
5. **out_of_envelope vs setup_error labeling → D6.** Resolved by the labeling
   convention (§4F): configuration deviation = setup_error; card-standard
   configuration beyond regime = out_of_envelope; coarse-mesh fixture is
   setup_error primary, out_of_envelope defensible secondary.
6. **Aspect-ratio and multi-wall envelope → D4.** Resolved by the geometry
   ruling (§3B): validated configuration is the square, single-lid,
   uniform-mesh, L=1.0 m case exactly as exercised; all others → defer/refine
   with the configuration named.
7. **Provisional → signed transition → D1.** Owner provisionally signs
   2026-07-15; external review dispatched 2026-07-17; the provisional signature
   grants interim authority per the amended reviewer rubric.
