"""registry_row.py — the STAGED substrate-registry row for fenicsx_cantilever_elastic.

STAGING ONLY — THIS SESSION DOES NOT MERGE. `tools/substrate_registry.py` is
frozen to this build; the Wave Guide merges these rows serially. This file exists
so that merge is a mechanical paste of a shape that was written against the
registry code as it actually is (read at HEAD 07816ba), not a guess.

HOW THE REGISTRY IS CONSUMED (read structurally from tools/substrate_registry.py
and supervisor.apply_substrate_maturity_hook — never by parsing names, R-28H-1):
  * `_REGISTRY` is a tuple of frozen SubstrateRecord dataclasses; enrollment
    order is preserved by all_substrates().
  * `routable_ids()` returns the ids with routable=True. The maturity hook reads
    THAT set structurally to decide whether a trust decision needs a human.
  * `_CONTRACTS` maps substrate_id -> model-visible contract text. A substrate
    ABSENT from that map has NO wired contract and `contract_for` RAISES
    LookupError rather than fall back to cavity's.

WHAT THIS ROW ASKS FOR — AND DELIBERATELY DOES NOT:
  * maturity=CALIBRATING, routable=False. Everything enters at calibrating =
    UNROUTABLE. Promotion is a separate owner ruling, not this session's.
  * NO `_CONTRACTS` ENTRY. This is deliberate and load-bearing, mirroring the
    FEA and code substrates: an unroutable, uncalibrated substrate has no routing
    contract, and its absence from `_CONTRACTS` is the fail-loud escape that the
    Part-A tests prove. The contract TEXT exists (contract.py) for the
    calibration battery, which passes it as `substrate_text`/`envelope_text`
    directly — it does NOT reach the gate through `contract_for`. Wiring
    `_CONTRACTS` is a separate future ruling.
  * cost_tier="low" — MEASURED, not assumed: 0.45 s warm to 3.6 s cold wall-clock
    on the family-v1 ladder (card §7), the same tier as its CalculiX sibling.

THE ROW (paste into `_REGISTRY` in enrollment order, after code_sklearn_eval):

    SubstrateRecord(
        substrate_id="fenicsx_cantilever_elastic",
        wrapper="tools/run_fenicsx.py",
        card_path="docs/envelope_card_fenicsx_cantilever_elastic.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="slate drafted (15 cases); battery pending owner OK on the slate ruling",
    ),
"""

from __future__ import annotations

# The row as DATA, so the merge can assert against it rather than re-type it.
# Field names match tools.substrate_registry.SubstrateRecord exactly.
REGISTRY_ROW = {
    "substrate_id": "fenicsx_cantilever_elastic",
    "wrapper": "tools/run_fenicsx.py",
    "card_path": "docs/envelope_card_fenicsx_cantilever_elastic.md",
    "maturity": "calibrating",   # registry.CALIBRATING
    "routable": False,           # UNROUTABLE — promotion is a separate ruling
    "cost_tier": "low",          # measured: 0.45 s warm — 3.6 s cold (card §7)
    "notes": "slate drafted (15 cases); battery pending owner OK on the slate ruling",
}

# Deliberately absent: any `_CONTRACTS[...]` entry. See the module docstring.
WIRE_CONTRACT_ENTRY = False
