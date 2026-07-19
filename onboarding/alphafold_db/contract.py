"""contract.py — STAGED. Contract for (alphafold_db, predicted_structure_lookup).
Option A + network-un-deferred (owner 2026-07-19). contract_for('alphafold_db')
MUST raise until the promotion flip. Un-defer WAS reachable AFDB endpoint (done);
promotion is a separate later step on clean gate-track calibration. PERMANENT
never-trust-alone (card A3). INPUT-SHAPE RULING (owner 2026-07-19): keyed by
uniprot_accession, NOT protein_sequence. -> substrates.py as
ALPHAFOLD_DB_CONTRACT at promotion."""

ALPHAFOLD_DB_CONTRACT = """SUBSTRATE CONTRACT — alphafold_db, predicted_structure_lookup

1. WHAT THIS IS. A lookup of a precomputed AlphaFold structure's mean pLDDT for a
UniProt accession. LOOKUP-class: structurally NEVER TRUSTED ALONE — corroboration
required.
2. TYPED INPUT. uniprot_accession; quantity (mean_pLDDT).
3. REGIME. In: an accession resolvable in AFDB via a reachable endpoint. Out:
trusting the value alone; experimental-accuracy claims.
4. RETURNS. mean_pLDDT (from globalMetricValue) via a reachable endpoint —
reported never-trusted-alone.
5. GATE + GAP. Trustworthy as CORROBORATION ONLY, never alone (permanent). KNOWN
GAP: pLDDT is model self-confidence, not experimental accuracy.
"""
