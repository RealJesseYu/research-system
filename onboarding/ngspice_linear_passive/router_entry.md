# Router entry — `ngspice_linear_passive` (STAGED)

The Wave Guide merges this. Nothing reads it today.

**Lands in:** the router card / cost-tier table (`docs/substrate_registry.md`),
alongside the `cost_tier` field carried by the `SubstrateRecord` row that
`registry_row_fragment.py` stages.

**Substrate-agnostic by construction:** no solver name, no container name, and
no netlist syntax appears below. Upper layers see capability, cost, and
maturity — nothing else. (The solver *is* named in the wrapper, the contract,
and the card; those all sit at or below the tool-wrapper line.)

---

| Field | Value |
|---|---|
| Substrate id | `ngspice_linear_passive` |
| Capability summary | Solves idealized lumped linear passive electrical networks and returns one scalar per run: a steady operating-point value, a swept response, a frequency response, or a time response. |
| Physics regime | Ideal linear passive networks — energy storage and dissipation with no nonlinearity, no device physics, and no physical-assembly effects. |
| Question shapes it answers | "What does this idealized network do?" — a steady value, a slope across a sweep, a corner frequency, a value at a stated time, or a screened extremum of a transient. |
| Question shapes it does NOT answer | Anything about a physical assembly (tolerance, parasitics, ESR, grounding); anything resting on device-model fidelity; anything nonlinear or behavioural; any analysis outside the four offered. |
| QoI cardinality | ONE scalar per run. No vector, no time series, no second quantity from the same solve. |
| Cost tier | **low** |
| Measured rate | **0.19 – 0.85 s** wall-clock per run (range, never a constant — see below) |
| Hard kill | 600 s → reported failure |
| Maturity | **`calibrating`** |
| Routable | **No** |

---

## Cost tier — the basis

`low`, on the same rung as `cavity_2d_cfd`, `calculix_cantilever_fea`, and
`code_sklearn_eval`.

Measured range **0.19 – 0.85 s per run** (median 0.26 s, n=31), from two on-disk
evidence files: `selfcheck_evidence.json` (9 single runs, 0.253 – 0.667 s) and
`coarse_extremum_evidence.json` (22 single runs, 0.19 – 0.848 s). Published as a
**range with its per-point evidence**, never as a per-run constant, per the D5
doctrine. (Note: `selfcheck_evidence.json` check b reports `runtime_s_total`
1.535 s — that is a six-run sweep total, not a single run, and is excluded from
the range.)

**Why the range is nearly flat and does not scale with the problem:** the cost
is container-exec overhead, not solve time. The networks in this regime solve in
milliseconds; a 30,023-row transient and a 3-element steady solve differ by well
under 3x. Do not model this substrate's cost as
proportional to circuit size or simulated duration — over the whole exercised
envelope it is close to a fixed per-invocation toll. If a future case ever does
approach the 600 s kill, that is a signal the case has left this regime, not a
cost-model refinement.

## Routing status

**Unroutable, deliberately.** Enrolling a row does not authorize routing (see
`substrate_registry.py`'s module docstring). Three things are true today and
each independently blocks routing:

1. **Maturity is `calibrating`.** The 15-case battery is assembled and
   pre-registered but **UNEXECUTED** — no calibration result exists.
2. **No fidelity contract is wired.** `contract_for("ngspice_linear_passive")`
   RAISES `LookupError` by design; the substrate has a registry row but no
   `_CONTRACTS` entry, exactly like FEA and code. See
   `registry_row_fragment.py` for why that raise is the invariant.
3. **Selection does not exist.** `sole_routable_id()` RAISES if the routable set
   is not exactly one. Promoting this substrate to routable without building
   multi-substrate node selection (Step 35, task typing) lands there loudly —
   which is the intended seam.

Promotion is a separate recorded ruling, after the battery runs and after an
external reviewer signs the card.
