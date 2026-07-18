"""d4_wiring_fragments.py — STAGED. The six runtime enrollment surfaces for
rdkit, AUTHORED here but NOT wired. They land at the D.4 PROMOTION ruling
(alongside flipping `routable=True`), never at the D.2 enrollment merge —
Option A, owner-ruled 2026-07-18. Nothing imports this file.

At promotion, the growing fixtures (tests/fixtures/d1/feasibility_nudge.txt,
tests/fixtures/c235/chooser_retry_user_turn_v235.txt) re-capture with rdkit's
contract additive-only, and rdkit becomes a live select_substrate candidate
(its first R-B-1 exposure). None of that happens at D.2.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import RDKIT_DESCRIPTOR_CONTRACT     # moved from
    # onboarding/rdkit/contract.py to substrates.py at promotion (one source)
    _CONTRACTS["rdkit"] = RDKIT_DESCRIPTOR_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_rdkit import _REQUIRED_FIELDS as _RDKIT_REQUIRED_FIELDS
    _SIGNATURES["rdkit"] = frozenset(_RDKIT_REQUIRED_FIELDS)   # {smiles, quantity}
    # Disjoint from every existing signature (physics params vs {smiles,
    # quantity}) — no R-B-1 tie; asserted at promotion, proven inert at D.2.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_rdkit import QOI_FIELDS as _RDKIT_QOI_FIELDS
    DESCRIPTOR_COMPUTATION = "descriptor_computation"

    @dataclass(frozen=True)
    class DescriptorComputationRegime:
        '''rdkit-class regime: a single valid/sanitizable small molecule and a
        2D allowlist descriptor; no per-case numeric regime axis. The spec's
        regime object is {"notes": "..."} — why the molecule sits inside the
        allowlist's 2D-descriptor scope. Alien keys of every other shape are
        rejected by name.'''
        shape: ClassVar[str] = DESCRIPTOR_COMPUTATION
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    # QoI vocab is the fixed_summary shape (like the cantilevers): the wrapper
    # returns a fixed named set every valid run; "quantity" picks THE one,
    # membership-checked against QOI_FIELDS (imported, never pasted).
    _VOCABS["rdkit"] = FixedSummaryVocab(
        names=tuple(_RDKIT_QOI_FIELDS),
        regime=DescriptorComputationRegime(),
    )

--- 5 & 6. DISPATCH: adapter + QoI translation + run-entry (tools/substrate_dispatch.py)
    # adapter: run_rdkit(spec) -> the wrapper's {valid, qoi, diagnostics,
    #   runtime_s}; state-key scalar confidence = 1.0 when valid (deterministic
    #   answer), else 0.0 with qoi None (the `state`-key pattern, scalar only).
    # QoI translation: the spec's fixed_summary {quantity} -> the wrapper's
    #   typed {smiles, quantity}; a quantity off QOI_FIELDS is a translation
    #   error (qoi_error, never a wrong number).
    # run-entry constructor: {state: "valid"|"invalid", qoi_value|qoi_error,
    #   wall_clock_s} mirroring the ngspice/cantilever entries.
"""
# Nothing executable — a staged note, wired by hand at the D.4 promotion ruling.
