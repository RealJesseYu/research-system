"""registry_row_fragment.py — STAGED note for autodock_vina's registry row.
Nothing imports this.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to _REGISTRY AFTER
`mafft` and BEFORE `web_search`.

    SubstrateRecord(
        substrate_id="autodock_vina",
        wrapper="tools/run_autodock_vina.py",
        card_path="docs/envelope_card_autodock_vina.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2: re-tiered T2 -> DEFERRED (no aarch64 build — "
              "bioconda 'No entries matching', pip 'No matching distribution'). "
              "Wrapper written with fixed-seed + convergence-gate + input "
              "validation; input jails proven pure-Python; card skeleton, 3A "
              "PENDING-PROVISIONING. Un-defer needs a DIFFERENT ARCHITECTURE "
              "(x86 host) — not just a validated environment (cf cas_offinder). "
              "Runtime maps STAGED, UNWIRED; contract_for raises.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. contract_for('autodock_vina') MUST raise.
"""
# Nothing executable.
