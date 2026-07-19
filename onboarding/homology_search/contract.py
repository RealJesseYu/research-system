"""contract.py — STAGED. The model-visible fidelity contract for the
(homology_search, homology_search) substrate (the BLAST+HMMER bundle). NOTHING
imports this today.

Option A: enrolls `calibrating`/`routable=False`, INERT — NOT in `_CONTRACTS`;
`contract_for("homology_search")` MUST keep raising until a D.4 ruling. At
promotion the text moves to substrates.py as `HOMOLOGY_SEARCH_CONTRACT`.
"""

HOMOLOGY_SEARCH_CONTRACT = """SUBSTRATE CONTRACT — homology_search

1. WHAT THIS IS.
A local sequence-homology search (BLAST; HMMER as a second backend) that scores
how significantly a query sequence resembles entries in a reference database,
via Karlin-Altschul e-value statistics. It is a FILTER-class instrument: the
e-value is the SIGNIFICANCE of similarity — a relative screen, not homology or
function.

2. TYPED INPUT.
    database  : a baked allowlist reference database.
    query     : a protein sequence.
    tool      : the backend, one of {blast, hmmer} (an explicit choice).
    quantity  : the QoI (the best-hit e-value).

3. REGIME (homology_search).
In-regime: a protein query, a baked database, a similarity search returning an
e-value. Out of regime: databases outside the allowlist, non-sequence inputs, and
any homology/orthology/function claim beyond similarity significance.

4. WHAT IT RETURNS.
One scalar QoI — the best (minimum) e-value — returned ONLY when the search
provably ran (a valid database, no search error). A clean run that finds nothing
is a real 'no significant homolog' result (no e-value), DISTINCT from a search
that could not run.

5. THE DID-IT-WORK GATE AND THE KNOWN GAP.
BLAST exits 0 even when the database is missing/malformed — so exit code is not
trusted; a search error on stderr means the search could NOT run (defer), never
a '0 hits'. THE KNOWN GAP (uncheckable): a significant e-value is the significance
of SIMILARITY, not homology, orthology, or function; low-complexity and
composition bias also inflate significance. Trust the e-value as a
similarity-significance screen, not as a homology/function determination.
"""
