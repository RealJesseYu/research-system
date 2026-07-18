"""registry_row_fragment.py — the STAGED note for rdkit's registry row.
Nothing imports this. Mirrors onboarding/ngspice_linear_passive/
registry_row_fragment.py.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to
tools/substrate_registry.py `_REGISTRY` AFTER `ngspice_linear_passive` and
BEFORE `web_search` (web_search stays last — outside the routable ladder;
enrollment order is asserted by tests/test_substrate_registry.py).

    SubstrateRecord(
        substrate_id="rdkit",
        wrapper="tools/run_rdkit.py",
        card_path="docs/envelope_card_rdkit.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2 enrollment (Option A): descriptor_computation "
              "wrapper proven real in rdkit-prod; card signed from real runs; "
              "battery pending owner-OK'd slot. Runtime maps staged (contract/"
              "signature/vocab in onboarding/rdkit/), UNWIRED until a D.4 "
              "promotion ruling — contract_for('rdkit') must keep raising.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. Exactly like FEA/code/ngspice-at-birth: an
enrolled `routable=False` substrate is absent from `_CONTRACTS`, `_SIGNATURES`,
and `_VOCABS`; `contract_for("rdkit")` MUST raise LookupError. That raise is the
invariant, not a gap to fill. tests/test_contract_registry.py derives the
contractless set as every enrolled substrate except cavity and asserts the
raise — adding rdkit to `_CONTRACTS` would turn it red. The runtime wiring is in
d4_wiring_fragments.py and lands at promotion, not here.
"""
# Nothing executable. The registry is plain Python data, edited by hand under a
# recorded ruling — never assembled from a fragment at runtime.
