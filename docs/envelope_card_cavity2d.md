# Envelope Card — (cavity_2d, laminar incompressible 2D)

> **STATUS: SKELETON / PROVISIONAL — Step 20.5 START (2026-07-13).**
> Drafted by agent from on-disk evidence. Every judgment-requiring field is
> marked **TODO-HUMAN** and must be filled by the human pass before this card
> carries any authority. Literature-derived numbers are marked
> `[CITATION NEEDED - V&V pass Wednesday]` and are NOT to be treated as
> established. Finalization: Wednesday's V&V pass.

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
| Signature | **TODO-HUMAN — provisional signature required before use** |
| Reviewer sign-off | **TODO-HUMAN — see `docs/reviewer_rubric.md`** |
| Provenance state | `drafted-by-agent / awaiting-human` — updated per the reviewer rubric's provenance rule |

---

## 3. Validated envelope

Two tables, deliberately separate. **Nothing enters Table 3A without an on-disk
citation.** Table 3B (believed-but-not-exercised) is entirely TODO-HUMAN.

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

### 3B. Ranges BELIEVED valid but NOT exercised — **all TODO-HUMAN**

| Question | Draft answer | Status |
|---|---|---|
| True validated Reynolds ceiling for the *laminar 2D* regime | Spike names Re≈200 as *validated*; convergence seen to Re=1000–1600, but convergence ≠ validation | **TODO-HUMAN** — needs V&V decision; Re_c literature `[CITATION NEEDED - V&V pass Wednesday]` |
| Mesh resolution range certified mesh-independent | 64×64 is the only exercised resolution at scale; mesh-independence unestablished at any Re | **TODO-HUMAN** |
| `cavity_length` range beyond 1.0 m | untested | **TODO-HUMAN** |
| `lid_velocity` upper bound within laminar regime | untested above 2.0 m/s | **TODO-HUMAN** |
| Aspect ratios other than 1:1 (square) | untested; builder scales uniformly only | **TODO-HUMAN** |
| Multi-moving-wall / non-standard BC configurations | contract allows "one or more moving walls"; only single-lid exercised | **TODO-HUMAN** |

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
  error bites." (Ghia et al. 129×129 is a literature benchmark:
  `[CITATION NEEDED - V&V pass Wednesday]`.)
- **Coarse-mesh high bias, converged.** Evidence: triage fixture
  `harness/triage_cases/2_coarse_mesh.json` (**hand-authored, NOT a real run**):
  an 8×8 cavity at Re=200 that *converges* but returns volAverage(mag(U)) =
  0.71 m/s, ~1.7× the ~0.42 benchmark — a resolution artifact, not a discovery.

### 4D. Out-of-envelope use → spurious steady state (out_of_envelope class)
Running the instrument outside its validated laminar 2D envelope can produce a
"converged steady" result that is a numerical artifact.

- **Signature: max Courant ≫ 1.** Evidence: triage fixture
  `harness/triage_cases/4_envelope_drift.json` (**hand-authored, NOT a real
  run**): lid 25 m/s, ν=0.01, L=1 → Re=2500, above the Re_c≈1914 Hopf
  bifurcation `[CITATION NEEDED - V&V pass Wednesday]` and far outside the
  substrate's validated Re≈200 laminar envelope. The solver reports "converged
  steady" but max Courant = 6.2 — the out-of-envelope tell. `more_data` is the
  one *wrong* response (finer runs of an out-of-envelope instrument do not
  help).

### 4E. Turbulent physics silently mis-simulated
No turbulence models exist. A case whose physics is actually turbulent will not
be simulated correctly **and the wrapper cannot detect that.** Evidence:
contract §4 (declared limit; no run exercises it — this is a declared, not
observed, mode).

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
**TODO-HUMAN:** decide which rate the cost model should quote, and whether to
characterize the Re-dependence.

---

## 8. Open questions for the human pass

Explicit list — to be resolved Wednesday (V&V pass) or by human ruling:

1. **True validated Reynolds ceiling.** Convergence is observed to Re=1000
   (Run C) and claimed reliable to Re≈1600 (journal); the spike validated only
   Re≈200. Where is the *validated* (not merely converged) ceiling? Requires
   the Re_c≈1914 Hopf-bifurcation literature `[CITATION NEEDED]`.
2. **Mesh-independence policy.** 64×64 is the only exercised resolution; two
   refine verdicts flag it as under-resolved at Re=1000 vs Ghia et al. 129×129.
   What is the policy — a required mesh-independence sweep above some Re? A
   fixed certified (Re, mesh) grid?
3. **Do finer-mesh claims (e.g. 128×128) need a Ghia et al. cross-check** before
   the card certifies them? `[CITATION NEEDED - Ghia et al.]`.
4. **Cost-model rate to quote** (2.3 ms/step low-Re vs 3.6–4.1 ms/step at higher
   endTime/Re) and whether to publish the Re-dependence (§7).
5. **out_of_envelope vs setup_error labeling** at the coarse-mesh boundary — the
   triage battery treats both as defensible for the same case; does the card
   take a position?
6. **Aspect-ratio and multi-wall envelope** — the contract allows "one or more
   moving walls" and the builder scales uniformly; neither is exercised. In or
   out of the validated envelope?
7. **Provisional → signed transition** — who signs, and does sign-off require
   the Wednesday V&V numbers to be filled first? (See reviewer rubric.)
