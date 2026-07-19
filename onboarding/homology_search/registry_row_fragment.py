"""registry_row_fragment.py — the STAGED note for homology_search's registry row.
Nothing imports this.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to `_REGISTRY` AFTER
`cas_offinder` and BEFORE `web_search`.

    SubstrateRecord(
        substrate_id="homology_search",
        wrapper="tools/run_homology_search.py",
        card_path="docs/envelope_card_homology_search.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2 (T2): the BLAST+HMMER bundle (tool field). BLAST "
              "backend proven real in homology-search-prod (known hit e-value "
              "4.36e-58); DID-IT-WORK/DB-integrity gate proven by triggering "
              "(broken DB -> search-could-not-run, distinct from 0-hits). HMMER "
              "backend wired next increment (same substrate). Card from real "
              "runs. Pinned BLAST 2.16.0+. Runtime maps STAGED, UNWIRED; "
              "contract_for('homology_search') raises.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. `contract_for("homology_search")` MUST raise.
"""
# Nothing executable.
