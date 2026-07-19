"""d4_wiring_fragments.py — STAGED. The runtime enrollment surfaces for
cas_offinder, AUTHORED but NOT wired. They land at D.4 PROMOTION, never at D.2 —
and for THIS substrate, promotion additionally requires the KNOWN-ANSWER GUARD to
pass on a validated-kernel host (the card §3A re-validation gate). Nothing imports
this file.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import CAS_OFFINDER_CONTRACT
    _CONTRACTS["cas_offinder"] = CAS_OFFINDER_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_cas_offinder import _REQUIRED_FIELDS as _CAS_REQUIRED_FIELDS
    _SIGNATURES["cas_offinder"] = frozenset(_CAS_REQUIRED_FIELDS)
    # {genome, guide, mismatches, quantity} — disjoint from every existing
    # signature; no R-B-1 tie.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_cas_offinder import QOI_FIELDS as _CAS_QOI_FIELDS
    BOUNDED_ENUMERATION = "bounded_enumeration"

    @dataclass(frozen=True)
    class BoundedEnumerationRegime:
        shape: ClassVar[str] = BOUNDED_ENUMERATION
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    _VOCABS["cas_offinder"] = FixedSummaryVocab(
        names=tuple(_CAS_QOI_FIELDS),           # ("off_target_count",)
        regime=BoundedEnumerationRegime(),
    )

--- 5 & 6. DISPATCH (tools/substrate_dispatch.py) ---------------------------
    # adapter: run_cas_offinder(spec) -> {valid, qoi, diagnostics, runtime_s}.
    #   state-key scalar confidence = 1.0 when valid (the KNOWN-ANSWER GUARD
    #   passed AND enumeration returned a finite count), else 0.0 / qoi None.
    #   The guard is the did-it-work signal (exit code and count are unreliable).
    # QoI translation: fixed_summary {quantity:"off_target_count"} -> the wrapper.
    # run-entry constructor: {state, qoi_value|qoi_error, wall_clock_s}.
"""
# Nothing executable — staged; wired by hand at the D.4 promotion ruling, which
# for cas_offinder ALSO requires the known-answer guard to pass on the host.
