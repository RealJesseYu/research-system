"""contract.py — STAGED. The model-visible fidelity contract for the
(mafft, msa_alignment) substrate. NOTHING imports this today.

Option A: enrolls `calibrating`/`routable=False`, INERT — NOT in `_CONTRACTS`;
`contract_for("mafft")` MUST keep raising until a D.4 ruling. At promotion the
text moves to substrates.py as `MAFFT_CONTRACT`.
"""

MAFFT_CONTRACT = """SUBSTRATE CONTRACT — mafft, msa_alignment

1. WHAT THIS IS.
A multiple sequence alignment tool (MAFFT): it arranges two or more sequences
into columns of putative homology. It carries the NARROWEST trust claim of the
instruments here — an alignment it produces is a heuristic hypothesis about how
sequences relate, not a determination that the alignment is correct.

2. TYPED INPUT.
    sequences : a list of >= 2 sequences, all over the SAME alphabet (all
                protein OR all nucleotide), each non-empty and valid.
    quantity  : the QoI (the alignment-identity statistic).

3. REGIME (msa_alignment).
In-regime: >= 2 alignable same-alphabet sequences, aligned, summarized by a
descriptive identity statistic. Out of regime: alignment CORRECTNESS or
phylogenetic inference; mixed-alphabet or single-sequence input; scores beyond
average pairwise identity.

4. WHAT IT RETURNS.
One scalar QoI — the average pairwise percent identity over the computed
alignment (DESCRIPTIVE). It returns nothing for un-alignable input (refused
before running) or a malformed alignment.

5. THE INPUT GATE AND THE KNOWN GAP.
Alignment is near-total: garbage in yields a well-formed alignment OF the
garbage. So "an alignment was produced" is NOT evidence it means anything; the
trustworthiness gate is on the INPUT (>= 2 valid same-alphabet sequences),
checked before running. THE KNOWN GAP (uncheckable, and it is the whole
scientific question): a well-formed alignment is a HEURISTIC homology hypothesis,
guide-tree-dependent — a different tool or setting gives a different alignment.
Trust the alignment DESCRIPTIVELY, never as the biologically correct one.
"""
