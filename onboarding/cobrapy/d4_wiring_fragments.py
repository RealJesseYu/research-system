"""d4_wiring_fragments.py — STAGED. The six runtime enrollment surfaces for
cobrapy, AUTHORED here but NOT wired. They land at the D.4 PROMOTION ruling
(with `routable=True`), never at the D.2 enrollment merge — Option A. Nothing
imports this file. At promotion the growing fixtures re-capture with cobrapy's
contract additive-only, and cobrapy becomes a live select_substrate candidate.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import COBRAPY_FBA_CONTRACT   # moved from
    # onboarding/cobrapy/contract.py to substrates.py at promotion
    _CONTRACTS["cobrapy"] = COBRAPY_FBA_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_cobrapy import _REQUIRED_FIELDS as _COBRAPY_REQUIRED_FIELDS
    _SIGNATURES["cobrapy"] = frozenset(_COBRAPY_REQUIRED_FIELDS)  # {model, quantity}
    # Disjoint from every existing signature (physics params, {smiles,quantity})
    # — no R-B-1 tie; asserted at promotion.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_cobrapy import QOI_FIELDS as _COBRAPY_QOI_FIELDS
    FBA_STEADY_STATE = "fba_steady_state"

    @dataclass(frozen=True)
    class FbaSteadyStateRegime:
        '''cobrapy-class regime: a baked allowlist model solved at steady state
        for its max biomass flux. No per-case numeric regime axis; the spec's
        regime object is {"notes": "..."} — why the FBA screen fits the case.
        Alien keys of every other shape rejected by name.'''
        shape: ClassVar[str] = FBA_STEADY_STATE
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    # QoI vocab is the fixed_summary shape: "quantity" picks from QOI_FIELDS
    # (currently the single growth_rate), membership-checked against the
    # wrapper's own imported constant.
    _VOCABS["cobrapy"] = FixedSummaryVocab(
        names=tuple(_COBRAPY_QOI_FIELDS),
        regime=FbaSteadyStateRegime(),
    )

--- 5 & 6. DISPATCH: adapter + QoI translation + run-entry (tools/substrate_dispatch.py)
    # adapter: run_cobrapy(spec) -> {valid, qoi, diagnostics, runtime_s}.
    #   state-key scalar confidence = 1.0 when valid (an OPTIMAL LP solve), else
    #   0.0 with qoi None. THE STATUS GATE means qoi is None for any non-optimal
    #   solve — the confidence is the LP feasibility, not the bare objective.
    # QoI translation: the spec's fixed_summary {quantity} -> the wrapper's
    #   {model, quantity[, min_growth]}; a quantity off QOI_FIELDS or a model off
    #   MODEL_ALLOWLIST is a translation error (qoi_error, never a wrong number).
    # run-entry constructor: {state: "valid"|"invalid", qoi_value|qoi_error,
    #   wall_clock_s}, mirroring the ngspice/rdkit entries.
"""
# Nothing executable — a staged note, wired by hand at the D.4 promotion ruling.
