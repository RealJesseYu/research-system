"""d4_wiring_fragments.py — STAGED. The runtime enrollment surfaces for mafft,
AUTHORED but NOT wired. They land at D.4 PROMOTION, never at D.2. Nothing
imports this file.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import MAFFT_CONTRACT
    _CONTRACTS["mafft"] = MAFFT_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_mafft import _REQUIRED_FIELDS as _MAFFT_REQUIRED_FIELDS
    _SIGNATURES["mafft"] = frozenset(_MAFFT_REQUIRED_FIELDS)   # {sequences, quantity}
    # Disjoint from every existing signature — no R-B-1 tie.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_mafft import QOI_FIELDS as _MAFFT_QOI_FIELDS
    MSA_ALIGNMENT = "msa_alignment"

    @dataclass(frozen=True)
    class MsaAlignmentRegime:
        shape: ClassVar[str] = MSA_ALIGNMENT
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    _VOCABS["mafft"] = FixedSummaryVocab(
        names=tuple(_MAFFT_QOI_FIELDS),           # ("alignment_identity",)
        regime=MsaAlignmentRegime(),
    )

--- 5 & 6. DISPATCH (tools/substrate_dispatch.py) ---------------------------
    # adapter: run_mafft(spec) -> {valid, qoi, diagnostics, runtime_s}.
    #   state-key scalar confidence = 1.0 when valid (the STRICT INPUT GATE passed
    #   AND a well-formed alignment was produced), else 0.0. The did-it-work
    #   signal is the INPUT gate, not the output (alignment is near-total).
    # QoI translation: fixed_summary {quantity:"alignment_identity"} -> the wrapper.
    # run-entry constructor: {state, qoi_value|qoi_error, wall_clock_s}.
"""
# Nothing executable — staged; wired by hand at the D.4 promotion ruling.
