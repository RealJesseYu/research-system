"""contract.py — STAGED. Contract for (boltz2, structure_affinity_prediction).
Option A + DEFERRED (no GPU). contract_for('boltz2') MUST raise. Un-defer needs a
validated GPU + pinned official weights (see the card). Moves to substrates.py as
BOLTZ2_CONTRACT at D.4."""

BOLTZ2_CONTRACT = """SUBSTRATE CONTRACT — boltz2, structure_affinity_prediction

1. WHAT THIS IS. A neural predictor (Boltz-2) of protein structure + binding
affinity from sequence(+ligand). FILTER-class: predicted RMSD/affinity is a
RELATIVE screen within the model's training distribution, not absolute Kd.
2. TYPED INPUT. protein_sequence; ligand (optional SMILES); quantity (affinity|rmsd).
3. REGIME. In: a sequence within the model's scope, scored by validated weights.
Out: absolute affinity, OOD targets, "the structure is correct".
4. RETURNS. One scalar (affinity or rmsd) from validated weights only.
5. GATE + GAP. Trustworthy ONLY from PINNED official weights that passed a
known-answer run (mismatched weights produce confident garbage). KNOWN GAP: the
prediction is not experimental; OOD generalization is unknowable. Relative screen only.
"""
