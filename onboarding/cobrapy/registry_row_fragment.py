"""registry_row_fragment.py — the STAGED note for cobrapy's registry row.
Nothing imports this. Mirrors onboarding/rdkit/registry_row_fragment.py.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to
tools/substrate_registry.py `_REGISTRY` AFTER `rdkit` and BEFORE `web_search`
(web_search stays last — outside the routable ladder; enrollment order asserted
by tests/test_substrate_registry.py).

    SubstrateRecord(
        substrate_id="cobrapy",
        wrapper="tools/run_cobrapy.py",
        card_path="docs/envelope_card_cobrapy.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2 enrollment (Option A): fba_steady_state wrapper "
              "proven real in cobrapy-prod (e_coli_core + iML1515), STATUS-GATE "
              "jail proven by triggering infeasible on both; card from real "
              "runs; battery pending. Runtime maps staged (onboarding/cobrapy/), "
              "UNWIRED until D.4 — contract_for('cobrapy') must keep raising.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. Exactly like rdkit/FEA/code: an enrolled
`routable=False` substrate is absent from `_CONTRACTS`/`_SIGNATURES`/`_VOCABS`;
`contract_for("cobrapy")` MUST raise LookupError. That raise is the invariant.
The runtime wiring is in d4_wiring_fragments.py and lands at promotion.
"""
# Nothing executable. The registry is plain Python data, edited by hand under a
# recorded ruling.
