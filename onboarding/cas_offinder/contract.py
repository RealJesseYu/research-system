"""contract.py — STAGED. The model-visible fidelity contract for the
(cas_offinder, bounded_enumeration) substrate. NOTHING imports this today.

Option A enrollment (owner-ruled 2026-07-18): enrolls `calibrating`/
`routable=False` and INERT — NOT in `_CONTRACTS`; `contract_for("cas_offinder")`
MUST keep raising until a D.4 ruling. Additionally DEFERRED: un-deferring
requires the known-answer guard to pass on a validated-kernel host (see the
card §3A re-validation gate). At promotion the text moves to substrates.py as
`CAS_OFFINDER_CONTRACT`.
"""

CAS_OFFINDER_CONTRACT = """SUBSTRATE CONTRACT — cas_offinder, bounded_enumeration

1. WHAT THIS IS.
A deterministic CRISPR off-target enumerator (Cas-OFFinder). Given a guide RNA
protospacer, a PAM, and a mismatch budget, it exhaustively enumerates every
near-match site in a reference genome. It is an ANSWER-class instrument: the
count IS its exact enumeration — no scoring model, no prediction.

2. TYPED INPUT.
    genome      : a baked allowlist reference genome.
    guide       : the 20-nt protospacer (A/C/G/T).
    mismatches  : the max mismatches allowed in the protospacer.
    quantity    : the QoI (the off-target count).

3. REGIME (bounded_enumeration).
In-regime: a 20-nt guide, SpCas9 NGG PAM, a baked genome, a bounded mismatch
budget. Out of regime: other PAMs/guide lengths (v1), non-allowlist genomes, and
any functional-relevance judgment about the sites found.

4. WHAT IT RETURNS.
One scalar QoI — the off-target count — returned ONLY behind a known-answer
guard (below). It never returns a count from an unvalidated search.

5. THE KNOWN-ANSWER GUARD AND THE KNOWN GAP.
Cas-OFFinder's search runs in an OpenCL kernel that can exit 0 and return 0
matches WITHOUT computing (a broken/absent kernel). A fabricated "0 off-targets"
is the dangerous wrong answer for CRISPR. So the count is trustworthy ONLY when
a baked known-present probe site is first FOUND; otherwise the substrate refuses.
THE KNOWN GAP (uncheckable): a sequence match is NOT a functional off-target —
chromatin accessibility and actual cutting efficiency are not modelled. Trust the
count as a sequence-match enumeration, not a functional off-target set.
"""
