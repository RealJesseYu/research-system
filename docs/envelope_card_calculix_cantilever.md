# Envelope Card — (calculix_cantilever, linear-elastic small-deflection static)

> **STATUS: PROVISIONALLY SIGNED 2026-07-15 (owner). External review pending.**
> Provenance: `provisionally-signed (owner)` (see §2). Judgment fields (§3B,
> F1–F4) are owner-RULED and filled; external reviewer dispatch is pending
> Sunday 2026-07-19.
> This card is **HUMAN-FACING ONLY** (R-20.5-1 doctrine): no code reads it, no
> model sees it. The substrate is **UNREGISTERED** — nothing in `stages/`, the
> supervisor, `substrates.py`, or any schema imports `tools/run_fea.py`.

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `calculix_cantilever` (family-v1 typed input; **UNREGISTERED** — no router/`substrates.py` entry exists) |
| Physics regime | linear-elastic **isotropic small-deflection static** cantilever beam; single tip point-load, one clamped end |
| Solver | CalculiX **2.17** (`calculix-ccx`, Ubuntu 22.04 universe) in container `ccx-prod` |
| Element | `C3D8I` — 8-node incompatible-modes hex (bending-capable) |
| Wrapper | `tools/run_fea.py` (deterministic Python, no AI), graduated Step 27 DRY |
| Wrapper commit (last touch) | `a07f939` (Packet B Phase 2 flip — the additive `QOI_FIELDS` constant, ruled option V-A; was `c82cfda` STEP27-DRY) |
| Contract text | **none** — substrate is UNREGISTERED; the typed input lives only in `run_fea.py` `_REQUIRED_FIELDS`, not in `substrates.py` |
| Docs index | CalculiX manual **v2.23** (`retrieval/fea_docs_index.pkl`) — **note the skew: docs v2.23 vs solver v2.17**; the manual is a superset reference, not a version-matched one |
| Card drafted against repo HEAD | `c82cfda` |
| Maturity | **calibrating** (pre-registration; judgment slots open) |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, doc-only measurement-capture session) |
| Drafted date | 2026-07-15 |
| Sources | wrapper run evidence captured this session (mesh 8/16/32 self-checks); the wrapper's built-in analytic self-check; `tools/fea_env/vv_sources.md` (V&V references, located not yet applied) |
| Signature | `provisionally signed — owner, 2026-07-15` (was `unsigned`). **A provisional signature grants interim authority; a human sits at every trust call on this substrate regardless — it is UNREGISTERED and would enter at calibrating maturity.** (mirrors the CFD card) |
| Reviewer sign-off | `pending — external expert-review dispatch planned Sunday 2026-07-19` |
| **Provenance state** | `provisionally-signed` (2026-07-15) — history: `drafted-by-agent` → `provisionally-signed` |

*Provenance state is the load-bearing field. It has advanced from
`drafted-by-agent` to `provisionally-signed` (owner, 2026-07-15): the four §3B
judgment slots (F1–F4) are now owner-RULED bounds, not suggestions. The
provisional signature grants interim authority only — a human sits at every
trust call on this UNREGISTERED substrate, which would enter at `calibrating`
maturity; final grounding authority still awaits the Sunday 2026-07-19 reviewer
sign-off.*

---

## 3. Validated envelope

Two sections, deliberately separate. §3A is the disk-cited evidence actually
exercised this session; §3B is the set of envelope bounds left as TODO-HUMAN
judgment slots — **none pre-filled as decided.**

### 3A. Analytic self-check (disk-cited, this session)

Reference: **Euler-Bernoulli beam theory** — tip deflection
δ = P·L³/(3·E·I), with I = w·h³/12 (`analytic_tip_deflection` in
`tools/run_fea.py`). Beam exercised: L=1.0 m, w=h=0.05 m, E=210e9 Pa, ν=0.3,
P=1000 N (L/h = 20; analytic δ = 0.0030476190 m).

| mesh_density | mesh (nx×ny×nz) / elems | tip_displacement (m) | gap vs Euler-Bernoulli | max_von_mises (Pa) | runtime_s |
|---|---|---|---|---|---|
| 8 | 8×1×1 / 8 | 0.003002929 | **1.466%** | 2.521e7 | 0.201 |
| 16 | 16×1×1 / 16 | 0.003029264 | **0.602%** | 2.609e7 | 0.108 |
| 32 | 32×2×2 / 128 | 0.003030861 | **0.550%** | 3.848e7 | 0.160 |

**Convergence direction:** the tip-deflection gap shrinks **monotonically with
refinement** (1.466% → 0.602% → 0.550%); the mesh-16 point sits between the
mesh-8 and mesh-32 gaps, as expected for h-refinement converging toward the
analytic reference from below (FEA displacement stiffer than the beam limit).
The tip-displacement QoI is **validated within family v1** against its own
Euler-Bernoulli closed form.

> **Contrast — max_von_mises does NOT converge:** the pointwise stress maximum
> *rises* with refinement (2.521e7 → 2.609e7 → 3.848e7). It is tracking the
> clamped-corner stress concentration, not a settling physical value. See §6.

### 3B. Envelope bounds — TODO-HUMAN judgment slots

Each slot carries an agent-SUGGESTED value and a one-line reason. **None is a
decided bound** — each awaits an owner ruling (mirrors the CFD card's D-rulings).

- **(F1) Slenderness bound `L/h` for trusting the Euler-Bernoulli reference.**
  `RULED (owner, 2026-07-15)` — **L/h ≥ 10.**
  *Reason:* Euler-Bernoulli neglects shear deformation; the shear correction is
  ≲1–2% for L/h ≥ 10 and grows rapidly below it (a stubby beam needs the
  Timoshenko/elasticity solution, not this reference). The exercised beam is
  L/h = 20, comfortably inside.

- **(F2) Linearity bound (max tip-deflection/length ratio counted as in-envelope).**
  `RULED (owner, 2026-07-15)` — **δ_tip / L ≤ 0.10.**
  *Reason:* the small-deflection static solve assumes deflections small vs
  length; past ~10% geometric nonlinearity (stiffening / follower effects)
  invalidates the linear result. The exercised case is δ/L ≈ 0.003 (0.3%), deep
  in the linear regime.

- **(F3) Mesh-reproduction tolerance any new mesh must hit on the analytic point.**
  `RULED (owner, 2026-07-15)` — **within 2.0% of Euler-Bernoulli δ** (equivalently,
  no worse than the mesh-8 gap of 1.466%).
  *Reason:* mirrors the CFD card's standing rule that a new resolution must
  reproduce a benchmark point before its numbers are trusted; the exercised
  meshes land at 0.550–1.466%, so a 2% acceptance band admits a valid mesh yet
  still flags a broken one.

- **(F4) `max_von_mises` status pending screening.**
  `RULED (owner, 2026-07-15)` — **reported-only (NOT validated).**
  *Reason:* the pointwise maximum sits at the clamped-corner stress
  concentration/singularity and rises with refinement (mesh-suspect); it cannot
  be validated until a benchmark or a masked/sampled alternative clears it
  (see the §6 screening entry).

---

## 4. Known failure modes

Calibrating — this section is thin by design; the full failure catalogue is
populated once the labeled calibration battery (`docs/fea_calibration_cases_v1.md`)
is actually executed under an owner-OK'd run. Modes anticipated / partially
evidenced:

- **4A. Non-buildable / nonphysical typed input → input rejection (setup_error).**
  `_validate_input` rejects missing/extra fields, non-positive L/w/h/E/tip_load,
  ν ∉ (−1, 0.5), and mesh_density < 1 — the wrapper returns `valid=False` with a
  named reason and **never fabricates a QoI**. (Evidence: `run_fea.py`
  `_validate_input`; unit tests `tests/test_run_fea.py`. Labeled cases C10–C14.)
- **4B. Out-of-slenderness use (stubby beam) → EB reference invalid (out_of_envelope).**
  Below the F1 bound the Euler-Bernoulli self-check is no longer the right
  reference; a converged solve can still return a number, but validated-against-EB
  no longer holds. (Anticipated; labeled cases C06–C07 — not yet executed.)
- **4C. Large-deflection use → linear small-deflection assumption broken (out_of_envelope).**
  Past the F2 ratio the linear static solve is physically wrong though it still
  converges. (Anticipated; labeled case C08.)
- **4D. Near-incompressible ν → volumetric locking risk (out_of_envelope / numerics).**
  ν → 0.5 with C3D8I risks element locking; the result is suspect though the
  input is *valid*. (Anticipated; labeled case C09.)
- **4E. `max_von_mises` contaminated by the clamped-corner singularity → converged-but-misleading.**
  Measured this session: the pointwise max rises with refinement rather than
  settling. No internal diagnostic flags it. (Evidence: §3A; screened in §6.)

---

## 5. What the diagnostics CAN and CANNOT see

The wrapper returns: `valid` (bool), `qoi` (or None), a bounded `diagnostics`
string (mesh size, node/element counts, error tail), and `runtime_s`.

| CAN see | CANNOT see |
|---|---|
| Input rejected before any solve (nonphysical typed input, §4A) | Whether a *converged* displacement is mesh-independent |
| Solver hard failure: no `.dat`, `*ERROR` in the log, 600 s timeout | Whether `max_von_mises` is a physical value or the clamped-corner singularity (§6) |
| Missing displacement/stress rows in output → `valid=False`, no number | Whether a case is inside the slenderness (F1) or linearity (F2) envelope — no regime check exists |
| Analytic self-check gap **when the caller computes it** (not automatic) | Regime-assumption certainty — whether the "linear-elastic small-deflection" assumption itself holds for the input |

*Overclaiming diagnostic reach is the most dangerous error a card can make: the
wrapper checks that the solver **ran and produced parseable output**, not that
the physics is resolved or in-regime.*

---

## 6. Extraction contract + QoI status

**Typed input vocabulary** (`tools/run_fea.py` `_REQUIRED_FIELDS`) — the builder
honors exactly these; anything else is rejected by name:

| Name | Units | Meaning |
|---|---|---|
| `length` | m | beam length (X; clamped at x=0) |
| `width` | m | section width (Y) |
| `height` | m | section height (Z; load direction) |
| `E` | Pa | Young's modulus |
| `nu` | — | Poisson's ratio, ∈ (−1, 0.5) |
| `tip_load` | N | total transverse tip load (−Z), distributed over the tip face |
| `mesh_density` | int ≥ 1 | element count along the length; width/height scale by aspect ratio |

**QoI-name single source (Packet B Phase 2 flip, ruled option V-A):** the two
QoI names below are now the wrapper's own constant `run_fea.QOI_FIELDS`
(`summarize_dat` derives its keys from it; the fixed-summary vocabulary
record imports it — never a pasted copy). Deliberately NOT shared with the
sibling fenicsx wrapper: the two share no code, by design.

**QoI status table** — one summary per run, extracted from the `.dat`; the raw
deck/log NEVER leaves the wrapper:

| QoI | field | status | basis |
|---|---|---|---|
| `tip_displacement` | max \|u₃\| over printed nodes | **VALIDATED within family v1** | monotone convergence to Euler-Bernoulli δ, 0.550–1.466% across mesh 8–32 (§3A) |
| `max_von_mises` | max von Mises over integration points | **REPORTED, NOT VALIDATED** | pointwise max sits at the clamped-corner stress concentration/singularity; observed **rising 2.521e7 → 3.848e7 with refinement** (§3A) — a mesh-suspect trend |

**QoI screening entry (`max_von_mises`).** Applying the CFD card's standing
QoI-screening rule, quoted verbatim from `docs/envelope_card_cavity2d.md` §6:

> "every extremum QoI must be screened for boundary-singularity contamination at
> design vet, not merely for contract fit."

`max_von_mises` is an extremum QoI that passes the extraction contract's
mechanical fit yet fails this screen: its maximum is located at the
clamped-corner stress singularity, and its value **rises monotonically with mesh
refinement** (2.521e7 at mesh 8 → 2.609e7 at mesh 16 → 3.848e7 at mesh 32)
instead of settling — the diagnostic signature of a boundary singularity, not a
physical stress. **Pointwise-max stress trends on this substrate are
mesh-suspect until a benchmark or a masked/sampled alternative (e.g. stress
sampled away from the clamped corner, or a Roark/NAFEMS reference value) clears
them.** Until then `max_von_mises` is reported-only (F4).

---

## 7. Cost model (measured this session)

Per the D5 doctrine (never a single rate): the three measured runtimes are
published as a **range plus per-mesh points**, not a per-element constant.

| Operating point | Measured wall-clock `runtime_s` | Evidence |
|---|---|---|
| mesh_density 8 (8×1×1, 8 elems) | **0.201 s** | this session |
| mesh_density 16 (16×1×1, 16 elems) | **0.108 s** | this session |
| mesh_density 32 (32×2×2, 128 elems) | **0.160 s** | this session |
| **Range (family v1, mesh 8–32)** | **0.108 – 0.201 s / run** | this session |
| Hard kill limit | 600 s → reported failure | `tools/run_fea.py` `TIMEOUT_SECONDS` |

**Note (honest):** at these tiny mesh sizes runtime is dominated by
`docker exec` / solver-startup overhead, not element compute — which is why the
wall-clock is **non-monotonic** in mesh_density (mesh 16 measured faster than
mesh 8). No per-element rate is quoted; the range above is the honest cost
statement for family v1 at these resolutions.

---

## 8. Negative space + open watches

**What this card does NOT cover** (out of scope for family v1 as drafted):

- Other geometries or boundary conditions — only a single-tip-point-load
  cantilever clamped at one end; no distributed loads, multi-span, other
  supports, or non-rectangular sections.
- Geometric **nonlinearity** (large deflection, follower loads).
- **Dynamics** — modal, transient, harmonic, or any time-dependent response.
- **Contact** between bodies.
- **Buckling** / stability.
- **Plasticity** or any nonlinear material; only linear-elastic isotropic.
- Other materials beyond a single isotropic (E, ν) pair per run; no anisotropy,
  no temperature dependence, no composites.

**Open watches:**

1. **Judgment slots F1–F4 (§3B) are undecided.** Each needs an owner ruling
   before the card can advance past `drafted-by-agent`.
2. **`max_von_mises` validation path (F4/§6).** Requires a Roark/NAFEMS
   benchmark or a masked/sampled stress alternative before it can move from
   reported-only to validated.
3. **Docs/solver version skew (§1).** Manual index is v2.23; solver is v2.17. A
   worked-example reproduction from the manual should be version-checked before
   its reference numbers are trusted.
4. **Registration.** Substrate stays UNREGISTERED at this step; no code reads
   this card and no model sees it (R-20.5-1). Registration is a later, separate
   decision after calibration.
5. **Calibration battery unexecuted.** `docs/fea_calibration_cases_v1.md`
   defines the labeled cases; running them is a later ⚙ task needing owner OK.
