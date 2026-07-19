"""contract.py — STAGED. Contract for (retrosynthesis, retrosynthetic_route_search).
Option A + DEFERRED. contract_for('retrosynthesis') MUST raise. Un-defer needs the
models AND the reaction route DB/backend (card). -> substrates.py as
RETROSYNTHESIS_CONTRACT at D.4."""

RETROSYNTHESIS_CONTRACT = """SUBSTRATE CONTRACT — retrosynthesis, retrosynthetic_route_search

1. WHAT THIS IS. A retrosynthetic route planner (AiZynth/ASKCOS): a route to
purchasable building blocks. FILTER-class: a found route is TEMPLATE-feasible, a
relative screen, not experimentally validated.
2. TYPED INPUT. target_smiles; backend (aizynth|askcos); quantity (synthesizability).
3. REGIME. In: a target within the template library, searched with a validated
backend. Out: yields/conditions/selectivity, chemistry outside the templates.
4. RETURNS. One scalar (synthesizability) from a validated models+backend only.
5. GATE + GAP. Trustworthy ONLY from validated models + the reaction route
DB/backend that passed a known-answer run. KNOWN GAP: template-feasible !=
experimentally validated. Relative screen only.
"""
