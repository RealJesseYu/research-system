"""contract.py — STAGED. The model-visible fidelity contract for the
(cobrapy, fba_steady_state) substrate. NOTHING imports this today.

Option A enrollment (owner-ruled 2026-07-18): at D.2 this substrate enrolls
`calibrating` / `routable=False` and is INERT — its contract is NOT in
tools/substrate_registry.py `_CONTRACTS`, and `contract_for("cobrapy")` MUST
keep raising LookupError until a D.4 promotion ruling. At promotion the text
below moves to substrates.py as `COBRAPY_FBA_CONTRACT` and is wired into
`_CONTRACTS` (never a pasted copy — one runtime source of truth).
"""

COBRAPY_FBA_CONTRACT = """SUBSTRATE CONTRACT — cobrapy, fba_steady_state

1. WHAT THIS IS.
A constraint-based flux-balance analysis (FBA) calculator (COBRApy + an LP
solver) that computes the maximum steady-state biomass flux ("growth rate") of a
genome-scale metabolic model. It is a FILTER-class instrument: the growth it
reports is a feasible steady-state optimum — a RELATIVE screen for comparing
models/conditions — NOT a measured in-vivo growth rate. It is a deterministic
linear program: no kinetics, no regulation, no dynamics.

2. TYPED INPUT.
    model      : one of the baked allowlist models (a small textbook model and a
                 genome-scale model of the same organism).
    quantity   : the QoI to return (the fixed-summary vocabulary; the growth
                 rate).
    min_growth : OPTIONAL. A biomass lower-bound feasibility constraint; a value
                 the network cannot support makes the solve INFEASIBLE.

3. REGIME (the (substrate, regime) card unit — fba_steady_state).
In-regime: a baked allowlist model, solved at steady state for its maximum
biomass flux. Out of regime, by construction: kinetics/dynamics (dFBA),
regulation, transient behaviour, any model outside the allowlist, and any claim
about an absolute measured growth rate.

4. WHAT IT RETURNS.
One scalar QoI — the optimal growth rate — gated on the SOLVER STATUS. It never
returns a growth number for a non-optimal (infeasible / unbounded / errored)
solve; on any non-optimal status the QoI is absent.

5. THE STATUS GATE AND THE KNOWN GAP.
The QoI is trustworthy ONLY when the LP status is `optimal`. An FBA solver
exposes a stale objective value even after an infeasible solve; this substrate
NEVER surfaces it — non-optimal status yields no number. THE KNOWN GAP
(uncheckable by the gate): the FBA optimum is a feasible steady-state upper bound
under the model's stoichiometry and media, NOT a measured growth rate. Trust it
as a relative feasibility/growth screen; do NOT read it as an experimental
measurement, and do not assume the model/media/objective suit the question.
"""
