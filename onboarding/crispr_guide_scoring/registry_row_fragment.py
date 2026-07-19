"""registry_row_fragment.py — STAGED note for crispr_guide_scoring's registry
row. Nothing imports this.

LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to _REGISTRY AFTER
`autodock_vina` and BEFORE `web_search`.

    SubstrateRecord(
        substrate_id="crispr_guide_scoring",
        wrapper="tools/run_crispr_guide_scoring.py",
        card_path="docs/envelope_card_crispr_guide_scoring.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2: re-tiered T2 -> DEFERRED (no verified py3 scorer — "
              "Azimuth is Python-2; no standalone CFD package). SOFTWARE-"
              "availability defer. Input jails proven pure-Python; card "
              "skeleton, 3A PENDING. Un-defer = a verified py3 Doench/CFD "
              "scorer/model from a trusted source; hand-transcription FORBIDDEN "
              "(silent-wrong). Runtime maps STAGED, UNWIRED; contract_for raises.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. contract_for('crispr_guide_scoring') MUST raise.
"""
# Nothing executable.
