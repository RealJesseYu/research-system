"""contract.py — STAGED. Contract for (bio_db_lookup, record_db_lookup).
Option A + DEFERRED (network). contract_for('bio_db_lookup') MUST raise. Un-defer =
ALL FOUR endpoints reachable (one down = partial); PERMANENT never-trust-alone
(card). -> substrates.py as BIO_DB_LOOKUP_CONTRACT at D.4."""

BIO_DB_LOOKUP_CONTRACT = """SUBSTRATE CONTRACT — bio_db_lookup, record_db_lookup

1. WHAT THIS IS. A record lookup by id from an authoritative biological database
(PDB/PubChem/UniProt/ChEMBL; the database field selects which). LOOKUP-class:
structurally NEVER TRUSTED ALONE — corroboration required.
2. TYPED INPUT. database (pdb|pubchem|uniprot|chembl); record_id (well-formed for
that namespace); quantity (round_trip_id).
3. REGIME. In: a well-formed id resolvable via a reachable endpoint. Out: trusting
the record alone; assuming its curation is current/correct.
4. RETURNS. round_trip_id (resolved=1) from a reachable endpoint — never-trusted-alone.
5. GATE + GAP. Trustworthy as CORROBORATION ONLY, never alone (permanent). KNOWN
GAP: the DB's own curation currency/correctness is unverifiable from inside.
"""
