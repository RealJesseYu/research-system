"""registry_row_fragment.py — the STAGED note for mafft's registry row. Nothing
imports this.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to `_REGISTRY` AFTER
`homology_search` and BEFORE `web_search`.

    SubstrateRecord(
        substrate_id="mafft",
        wrapper="tools/run_mafft.py",
        card_path="docs/envelope_card_mafft.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2 (T2): MSA alignment. Proven real in mafft-prod "
              "(alignment_identity 94.4444); did-it-work signal is the STRICT "
              "INPUT GATE (>=2 alignable same-alphabet seqs, refused pre-run) — "
              "alignment is near-total so a well-formed alignment of junk is "
              "never trusted; input jails proven by triggering. Narrowest trust "
              "claim: descriptive, not 'correct' (C1-hole M4). Pinned MAFFT "
              "v7.526. Runtime maps STAGED, UNWIRED; contract_for('mafft') raises.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. `contract_for("mafft")` MUST raise.
"""
# Nothing executable.
