"""registry_row_fragment.py — the STAGED note for cas_offinder's registry row.
Nothing imports this.

WHAT LANDS LIVE AT THE D.2 MERGE: the ROW below, appended to `_REGISTRY` AFTER
`cobrapy` and BEFORE `web_search`.

    SubstrateRecord(
        substrate_id="cas_offinder",
        wrapper="tools/run_cas_offinder.py",
        card_path="docs/envelope_card_cas_offinder.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="BIO Wave D.2: re-tiered T1 -> DEFERRED (owner-ruled 2026-07-18) "
              "— Cas-OFFinder's OpenCL kernel does not compute correctly on "
              "colima/aarch64 (pocl exits 0 with 0 matches). Wrapper built with "
              "a KNOWN-ANSWER GUARD (refuses unless a known-present probe site "
              "is found — proven to fire here); input jails proven. Card "
              "skeleton, section 3A PENDING-PROVISIONING. Pinned: cas-offinder "
              "2.4.1 + pocl 7.1. Runtime maps STAGED, UNWIRED; contract_for "
              "raises. Un-defer requires the guard to pass on a validated host.",
    ),

ROW ONLY — NO _CONTRACTS ENTRY. `contract_for("cas_offinder")` MUST raise.
"""
# Nothing executable.
