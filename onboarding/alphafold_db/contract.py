"""contract.py — STAGED. Contract for (alphafold_db, predicted_structure_lookup).
Option A + DEFERRED (network). contract_for('alphafold_db') MUST raise. Un-defer =
reachable AFDB endpoint; PERMANENT never-trust-alone (card). -> substrates.py as
ALPHAFOLD_DB_CONTRACT at D.4."""

ALPHAFOLD_DB_CONTRACT = """SUBSTRATE CONTRACT — alphafold_db, predicted_structure_lookup

1. WHAT THIS IS. A lookup of a precomputed AlphaFold structure's mean pLDDT for a
sequence. LOOKUP-class: structurally NEVER TRUSTED ALONE — corroboration required.
2. TYPED INPUT. protein_sequence; quantity (mean_pLDDT).
3. REGIME. In: a sequence resolvable in AFDB via a reachable endpoint. Out:
trusting the value alone; experimental-accuracy claims.
4. RETURNS. mean_pLDDT from a reachable endpoint — reported never-trusted-alone.
5. GATE + GAP. Trustworthy as CORROBORATION ONLY, never alone (permanent). KNOWN
GAP: pLDDT is model self-confidence, not experimental accuracy.
"""
