"""d4_wiring_fragments.py — STAGED. Runtime enrollment surfaces for
crispr_guide_scoring, AUTHORED but NOT wired. Land at D.4 PROMOTION — and for
THIS tool, promotion additionally requires a VERIFIED scorer artifact (never a
transcribed model). Nothing imports this.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import CRISPR_GUIDE_SCORING_CONTRACT
    _CONTRACTS["crispr_guide_scoring"] = CRISPR_GUIDE_SCORING_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_crispr_guide_scoring import _REQUIRED_FIELDS as _CGS
    _SIGNATURES["crispr_guide_scoring"] = frozenset(_CGS)
    # {guide, pam, enzyme, quantity} — disjoint from every existing signature.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_crispr_guide_scoring import QOI_FIELDS as _CGS_QOI
    GUIDE_ACTIVITY_SCORING = "guide_activity_scoring"

    @dataclass(frozen=True)
    class GuideActivityScoringRegime:
        shape: ClassVar[str] = GUIDE_ACTIVITY_SCORING
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    _VOCABS["crispr_guide_scoring"] = FixedSummaryVocab(
        names=tuple(_CGS_QOI),                    # ("activity_score",)
        regime=GuideActivityScoringRegime(),
    )

--- 5 & 6. DISPATCH (tools/substrate_dispatch.py) ---------------------------
    # adapter: run_crispr_guide_scoring(spec) -> {valid, qoi, diagnostics,
    #   runtime_s}. state-key scalar confidence = 1.0 when valid (G1 verified-
    #   scorer gate passed AND a finite score), else 0.0. NEVER a transcribed
    #   model. QoI translation: fixed_summary {quantity:"activity_score"}.
    # run-entry constructor: {state, qoi_value|qoi_error, wall_clock_s}.
"""
# Nothing executable — staged; wired at D.4 promotion with a verified scorer.
