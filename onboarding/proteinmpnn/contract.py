"""contract.py — STAGED. Contract for (proteinmpnn, backbone_conditioned_sequence_design).
Option A + DEFERRED (no GPU). contract_for('proteinmpnn') MUST raise. Un-defer needs
a validated GPU + pinned official weights (card). Moves to substrates.py as
PROTEINMPNN_CONTRACT at D.4."""

PROTEINMPNN_CONTRACT = """SUBSTRATE CONTRACT — proteinmpnn, backbone_conditioned_sequence_design

1. WHAT THIS IS. A neural inverse-folding model (ProteinMPNN): a sequence for a
fixed backbone. FILTER-class: sequence-recovery is a RELATIVE design screen, not
proof the sequence folds/functions.
2. TYPED INPUT. backbone (a baked allowlist backbone); quantity (seq_recovery).
3. REGIME. In: a backbone within the model's scope, scored by validated weights.
Out: fold/function claims, OOD backbones.
4. RETURNS. One scalar (seq_recovery) from validated weights only.
5. GATE + GAP. Trustworthy ONLY from PINNED official weights that passed a
known-answer run. KNOWN GAP: high recovery != folds/functions; OOD unknowable.
Relative screen only.
"""
