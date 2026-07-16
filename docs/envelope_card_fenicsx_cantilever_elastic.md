# Envelope Card — (fenicsx_cantilever_elastic, linear-elastic small-deflection static)

> **STATUS: DRAFT — not yet reviewed.** Provenance: `drafted-by-agent` (§2).
> §3B judgment slots (G1–G5) are agent-SUGGESTED, **none decided**. This card is
> **HUMAN-FACING ONLY** (R-20.5-1): no code reads it, no model sees it. The
> substrate is **UNREGISTERED** — nothing in `stages/`, the supervisor,
> `substrates.py`, or any schema imports `tools/run_fenicsx.py`.

---

## 1. Identity

| Field | Value |
|---|---|
| Card unit | (substrate, physics-regime) pair |
| Substrate | `fenicsx_cantilever_elastic` (family-v1 typed input; **UNREGISTERED**, enters at `calibrating` = unroutable) |
| Physics regime | linear-elastic **isotropic small-deflection static** cantilever; single tip load, one clamped end |
| Solver | FEniCSx / DOLFINx **`0.11.0.post0`** — **as printed by the container**, not from docs |
| **(G0) Project choice** | **FEniCSx (`import dolfinx`), NOT legacy FEniCS.** Two projects share the name; legacy (`from dolfin import *`) last released **2019**, is absent from this image, and is what most open-web cantilever tutorials use — choosing it would ground the build in code that cannot run here. |
| Container | `dolfinx-prod`, image `dolfinx/dolfinx:stable`, digest `sha256:2ae4bfbc0d9077268880faf04c72750528bee986c94ab223a2c159969bd56fa8` (arm64, native under colima) |
| **Real-mode pin** | `float64` **asserted in code** at solve startup; a complex build raises and refuses to solve. **Proven by failing the escape**: under `dolfinx-complex-mode` the pin fires (`complex128`); same input in real mode solves. Fixture: `tests/fixtures/fenicsx_realmode_pin_failure.out` |
| Element | Lagrange, degree = **typed input** (`element_degree`). Validated at **degree 2**. **No `C3D8I` analog exists** — see G5 |
| Wrapper | `tools/run_fenicsx.py` (deterministic, no AI). Carries its OWN Euler-Bernoulli copy; imports nothing from the sibling |
| Docs index | DOLFINx **v0.11.0.post0** docs + tutorials (`retrieval/fenicsx_docs_index.pkl`, 17 pages → 325 chunks) — **version-matched, NO skew** (contrast FEA: docs v2.23 vs solver v2.17) |
| Card drafted against repo HEAD | `07816ba` (branch `build-fenicsx`) |
| Maturity | **calibrating** |

---

## 2. Provenance

| Field | Value |
|---|---|
| Drafted by | agent (Claude Code, `build-fenicsx` session) |
| Drafted date | 2026-07-16 |
| Sources | this session's run evidence (§3A, §3B, all disk-cited); `tools/fenicsx_env/vv_sources.md` (V&V references — **literature, LOCATED not applied**) |
| Signature | `unsigned` |
| Reviewer sign-off | `pending` |
| **Provenance state** | `drafted-by-agent` |

*Provenance state sets how much grounding authority the card carries. This card
carries none yet — every §3B bound is a suggestion.*

**License watch (does NOT block).** FEniCSx is **LGPL**; this wrapper makes an
**out-of-process container call** — no linking, no redistribution of the library.
Confirm at the IP-lawyer hour.

---

## 3. Validated envelope

### 3A. Analytic self-check (disk-cited, this session)

Reference: **Euler-Bernoulli** δ = P·L³/(3·E·I), I = w·h³/12
(`analytic_tip_deflection`, this wrapper's own copy). Beam: **the FEA card §3A
beam, read off disk** — L=1.0 m, w=h=0.05 m, E=210e9 Pa, ν=0.3, P=1000 N
(L/h = 20; analytic δ = 0.0030476190 m). **`element_degree = 2`.**

| mesh_density | grid / elems | tip_displacement (m) | gap vs Euler-Bernoulli | max_von_mises (Pa) | runtime_s |
|---|---|---|---|---|---|
| 8 | 8×1×1 / 8 | 0.003007857 | **−1.305%** | 4.246e7 | 0.705 |
| 16 | 16×1×1 / 16 | 0.003029079 | **−0.608%** | 4.492e7 | 0.615 |
| 32 | 32×2×2 / 128 | 0.003038334 | **−0.305%** | 4.670e7 | 0.754 |

**Convergence:** the gap shrinks **monotonically** (1.305% → 0.608% → 0.305%),
approaching the reference **from below** (the 3D solve is stiffer than the beam
limit). `tip_displacement` is **validated within family v1 at element_degree ≥ 2**.
Values are byte-identical across repeat runs and a container rebuild.

> **Independent agreement (evidence, not tautology).** The sibling CalculiX card
> §3A runs the *same beam* and *same closed form* through a different solver,
> element, and wrapper: 1.466 / 0.602 / 0.550% vs 1.305 / 0.608 / 0.305% here —
> both monotone, both from below. They share **no code**, by design.

> **Contrast — `max_von_mises` does NOT converge:** it *rises* with refinement
> (4.246e7 → 4.670e7), tracking the clamped-corner singularity. See §6.

### 3B. Envelope bounds — TODO-HUMAN judgment slots

Agent-SUGGESTED. **None is a decided bound.** G1–G4 **transplant** the sibling
card's F1–F4 (same beam, closed form, regime), F-reasons quoted verbatim below;
**G5 is this substrate's own.**

| Ruling | Suggested value | Class | Criterion (what the gate evaluates, and where it reads it) | Consequence (verdict/action on each side) |
|---|---|---|---|---|
| **G1** slenderness | **L/h ≥ 10** | CHECKABLE:numeric | `length / height` from the spec's typed fields, vs 10 | inside → eligible for trust (other gates permitting); outside → **defer** — the EB reference does not apply; route to a Timoshenko/elasticity reference |
| **G2** linearity | **δ_tip / L ≤ 0.10** | CHECKABLE:numeric | δ predicted from the spec by the closed form ÷ `length`, vs 0.10 | inside → eligible for trust; outside → **defer** — small-deflection physics is broken; no re-run of THIS instrument fixes it |
| **G3** mesh reproduction | **within 2.0% of EB δ** | CHECKABLE:numeric | the analytic gap on the case's mesh, vs 2.0% (coarsest validated rung: 1.305%) | inside → eligible for trust; outside → **refine** — re-run finer before the number is used |
| **G4** `max_von_mises` | **reported-only (NOT validated)** | CHECKABLE:membership | is the requested QoI `max_von_mises`? (QoI-name test) | requested → **trust excluded**; report the number, **defer the claim resting on it** — a masked/benchmarked alternative is the right instrument. `tip_displacement` unaffected |
| **G5** element order | **element_degree ≥ 2** | CHECKABLE:numeric | the spec's `element_degree` field, vs 2 | **≥ 2 → eligible for trust** (other gates permitting); **< 2 on a converged solve → refine** (converged-but-wrong: reliable filter, human validates) — the fix is this same instrument at a higher degree, on the same mesh |

**F-reasons, verbatim from `docs/envelope_card_calculix_cantilever.md`:**
- **F1→G1:** *"Euler-Bernoulli neglects shear deformation; the shear correction is ≲1–2% for L/h ≥ 10 and grows rapidly below it (a stubby beam needs the Timoshenko/elasticity solution, not this reference)."*
- **F2→G2:** *"the small-deflection static solve assumes deflections small vs length; past ~10% geometric nonlinearity (stiffening / follower effects) invalidates the linear result."*
- **F3→G3:** *"mirrors the CFD card's standing rule that a new resolution must reproduce a benchmark point before its numbers are trusted."*
- **F4→G4:** *"the pointwise maximum sits at the clamped-corner stress concentration/singularity and rises with refinement (mesh-suspect); it cannot be validated until a benchmark or a masked/sampled alternative clears it."* — **independently reproduced here** (§3A) on a different solver; G4 is suggested from this session's measurement, not inherited on faith.

**G5's reason (this substrate's own, measured this session).** DOLFINx has no
incompatible-modes element; a fully-integrated degree-1 Lagrange hex **shear-locks**
in bending. On the reference beam: **0.2800×** the closed form at 8×1×1, still
**0.9446× (5.5% too stiff) at mesh_density 64**, vs **0.9870× for degree 2 on the
coarsest 8×1×1 mesh**. Degree 1 never enters the G3 band on this ladder. The typed
input **accepts** degree 1 (§4A); whether it becomes a hard reject is an **owner
ruling**.

**THE G1↔G5 TENSION — a card fact, both halves true.** G1 demands **slender** beams
because that is where the EB reference is trustworthy; shear locking is **worst**
for slender beams. *The regime where the reference is most valid is the regime
where a naive element is most wrong.* Not a conflict — jointly binding, and G5 is
what makes G1's regime safely usable.

---

## 4. Known failure modes

- **4A. Nonphysical/non-buildable typed input → rejection (setup_error).**
  `_validate_input` rejects missing/extra fields, non-positive L/w/h/E/tip_load,
  ν ∉ (−1, 0.5), mesh_density < 1, **element_degree < 1**; returns `valid=False`
  with a named reason, **never fabricates a QoI**. *CHECKABLE:membership (in code).*
  Cases X11–X15.
- **4B. Degree-1 shear locking → converged-but-wrong (refine).** *(4C-analog)*
  Clean solve, confident number, **tens of percent too stiff**, geometry fully
  in-envelope, **no diagnostic flags it**. Fixed by degree ≥ 2 on the same mesh.
  *CHECKABLE:numeric — the `element_degree` field (G5).* Measured §3B. Cases X06/X07.
- **4C. Refinement does not rescue a locked element** — severity is governed by
  **element aspect ratio**, not element count. Measured: refining **only through
  the thickness** (8 along the length, nz 1→8) moved degree 1 from **0.2800× to
  0.2894×** — essentially nothing across an 8× increase. *KNOWN GAP: no diagnostic
  sees mesh-independence (§5).*
- **4D. Near-incompressible ν → VOLUMETRIC locking (out_of_envelope/numerics).**
  ν → 0.5; input *valid*, solve converges, result suspect. **A DIFFERENT DISEASE
  from 4B — degree 2 does NOT fix it** (remedies: mixed/u-p, selective reduced
  integration, F-bar; none present). *JUDGMENT — **KNOWN GAP**: no ν threshold is
  ruled or measured; advisory only.* Anticipated, **not measured**. Case X10.
- **4E. Out-of-slenderness / large-deflection use → EB reference or linear physics
  invalid (out_of_envelope).** *CHECKABLE:numeric (G1, G2).* Cases X08/X09.
- **4F. `max_von_mises` contaminated by the clamped-corner singularity →
  converged-but-misleading.** *(4G stress-singularity slot)* Rises with refinement
  rather than settling; belongs to the **continuum problem**, not to a solver —
  independently reproduced on a second solver this session.
  *CHECKABLE:membership (QoI-name test, G4).* Measured §3A. See §6.
- **4G. Degree-1 `max_von_mises` is additionally corrupted by its OWN extraction.**
  The DG0 sample points sit at **cell centres**, which on a one-element-thick mesh
  lie **exactly on the neutral axis** where bending stress vanishes. Measured:
  **6.93e5 Pa at 8×1×1 vs 5.80e6 Pa at 8×1×2** — an 8× swing from a mesh change
  that should barely matter. *CHECKABLE:numeric (G5 excludes degree 1 anyway).*
  A second, independent reason G4 holds.

---

## 5. What the diagnostics CAN and CANNOT see

| CAN see | CANNOT see |
|---|---|
| Input rejected before any solve (§4A) | Whether a *converged* displacement is mesh-independent |
| Substrate unreachable — **daemon AND container checked separately**, each named | **Whether the element is locking** (§4B) — the wrapper echoes the degree it was handed, never a judgment on it |
| Solver failure / no result line / unparseable output → `valid=False`, no number | Whether `max_von_mises` is physical or the clamped-corner singularity (§6) |
| Scalar type — **the real-mode pin fires and refuses to solve** (§1) | Whether a case is inside slenderness (G1) or linearity (G2) — **no regime check exists anywhere** |
| 600 s hard kill | Regime-assumption certainty — whether "linear-elastic small-deflection" holds at all |

*Overclaiming diagnostic reach is the most dangerous error a card can make: the
wrapper checks that the solve **ran and parsed**, not that the physics is resolved,
the mesh converged, or the element appropriate. **A degree-1 run is
indistinguishable from a degree-2 run in every field this wrapper returns except
the degree it echoes back.***

---

## 6. Extraction contract + QoI status

**The contract text lives in ONE place and is not pasted here:**
**`onboarding/fenicsx_cantilever_elastic/contract.py`**
(`FENICSX_CANTILEVER_ELASTIC_CONTRACT`) — canonical vocabulary, QoI keys,
extraction semantics. The battery case file is **generated** from it
(`generate_cases.py`; byte-identity asserted by `tests/test_run_fenicsx.py`). No
second copy exists to drift. *(Staged under `onboarding/` because `substrates.py`
is frozen to this build.)*

**Typed input** (`_REQUIRED_FIELDS` — all REQUIRED, no defaults): `length` (m),
`width` (m), `height` (m), `E` (Pa), `nu` (−, in (−1, 0.5)), `tip_load` (N, total,
over the tip face), `mesh_density` (int ≥ 1, along the length; width/height scale
by aspect ratio), **`element_degree`** (int ≥ 1 typed / ≥ 2 validated). The first
seven match the sibling FEA family v1's units and semantics by design, so one beam
can be posed to both instruments.

| QoI | field | status | basis |
|---|---|---|---|
| `tip_displacement` | max \|u_z\| over the displacement dofs | **VALIDATED within family v1 — at element_degree ≥ 2 only** | monotone convergence to EB δ, 0.305–1.305% across mesh 8–32 (§3A) |
| `max_von_mises` | pointwise max von Mises, interpolated into DG(degree−1) | **REPORTED, NOT VALIDATED** | rises 4.246e7 → 4.670e7 with refinement (§3A); plus the degree-1 neutral-axis artifact (§4G) |

**Semantic difference from the sibling, stated not glossed:** CalculiX takes
max |u₃| over **printed nodes**; this takes max |u_z| over the **space's dof
values** — point evaluations at dof coordinates (nodes at degree 1; nodes **plus
edge/face/interior points**, a superset, at degree ≥ 2). Both land at the tip for a
monotonically-deflecting cantilever: same measurement in intent, not byte-identical
in construction.

**QoI screening rule**, quoted verbatim from `docs/envelope_card_cavity2d.md` §6:

> "every extremum QoI must be screened for boundary-singularity contamination at
> design vet, not merely for contract fit."

`max_von_mises` passes contract fit and **fails this screen twice**: its maximum
sits at the clamped-corner singularity and **rises monotonically with refinement**
instead of settling, and at degree 1 its extraction additionally samples the
neutral axis (§4G). The singularity belongs to the **continuum problem**, not any
solver — the sibling measured the same rise on CalculiX; this session reproduced it
independently. **Pointwise-max stress here is mesh-suspect until a benchmark or a
masked/sampled alternative clears it** (G4) — and per the mask-insensitivity
doctrine, such an alternative is unsafe until shown **insensitive to the mask**.

---

## 7. Cost model (measured this session)

Never a single rate — a **range**, and here a **cold/warm** one: FEniCSx compiles
kernels on first use and caches them.

| Operating point | Measured | Evidence |
|---|---|---|
| **Cold** (JIT cache cleared), degree 2, 8×1×1 | **2.61 s** wall (1.823 s in-script solve) | this session |
| **Warm**, degree 2, 8×1×1 | **0.45 s** wall (0.024 s in-script solve) | this session |
| Warm ladder, degree 2, mesh 8 / 16 / 32 | 0.705 / 0.615 / 0.754 s | §3A |
| Warm, degree 2, mesh 64 (64×3×3) | 2.272 s | this session |
| **Range (family v1, mesh 8–64)** | **0.45 – 3.6 s / run** | this session |
| Hard kill limit | 600 s → reported failure | `run_fenicsx.TIMEOUT_SECONDS` |

**Honest notes:** the cold/warm gap on *solve time* is ~**76×** (1.823 vs 0.024 s);
wall-clock hides it behind `docker exec` overhead. Each new **kernel variant** pays
its own JIT cost (the first degree-1 run: 2.806 s; later ones 0.561 s). At these
sizes wall-clock is dominated by container-exec and JIT, **not** element compute,
so runtime is **non-monotonic** in mesh_density. No per-element rate is quoted.

---

## 8. Negative space + open watches

**NOT covered** (family v1): any other PDE, geometry, boundary condition, or
material law; distributed/multiple loads; non-rectangular sections; anisotropy,
temperature dependence, composites; geometric **nonlinearity**; **plasticity**;
**dynamics**; **contact**; **buckling**.

**Open watches:**

1. **G1–G5 (§3B) are undecided.** Each needs an owner ruling before this card
   advances past `drafted-by-agent`. **G5 is the consequential one** — the only
   bound with no sibling precedent, and what stands between a caller and a clean,
   converged, 16%-wrong number.
2. **Should `element_degree = 1` become a hard reject?** The wrapper accepts it and
   the card rules it out-of-envelope — a deliberate split between the **typed floor
   (≥ 1)** and the **validated floor (≥ 2)**. **Owner ruling:** enforcing a physics
   judgment in the wrapper is not its to make, and would destroy X06/X07.
3. **`max_von_mises` validation path (G4/§6).** Needs a Roark/NAFEMS benchmark or a
   masked/sampled alternative, itself proven mask-insensitive.
4. **The ν→0.5 volumetric-locking bound (4D) is UNMEASURED** — physics-grounded
   anticipation only, and the one JUDGMENT/KNOWN-GAP ruling here. Case X10's label
   is the weakest-grounded on the slate.
5. **Orphaned solver on timeout** — inherited watch, unfixed, same as the sibling:
   the 600 s kill terminates the `docker exec` **client**; a solver inside the
   container may run on as an orphan. Neither wrapper reaps it.
6. **Calibration battery unexecuted, and it cannot run yet.**
   `docs/fenicsx_calibration_cases_v1.md` defines 15 labeled cases; the slate is an
   **owner ruling** first (R-CAL-2), and three battery amendments are staged in
   `onboarding/.../battery_wiring.py` — one a **merge blocker** (`_ANSWER_KEY_KEYS`
   must learn `label_provenance`/`label_rationale` or the drift guard fails).
7. **Registration.** UNREGISTERED and unroutable; no code reads this card, no model
   sees it. A later, separate decision — and `onboarding/.../router_entry.md` §7
   records why these two cantilever substrates are **not** drop-in equivalents.
8. **Version skew: none today** (docs and solver both 0.11.0.post0). `stable` is a
   **moving tag** — a future `docker pull` can silently move the solver out from
   under this card. The §1 digest is the pin that makes such a move detectable.
