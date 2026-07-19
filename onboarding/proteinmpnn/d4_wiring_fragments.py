"""d4_wiring_fragments.py — STAGED runtime surfaces for proteinmpnn (NOT wired;
land at D.4 on a validated GPU host). Nothing imports this.
  _CONTRACTS['proteinmpnn'] = PROTEINMPNN_CONTRACT
  _SIGNATURES['proteinmpnn'] = frozenset(run_proteinmpnn._REQUIRED_FIELDS)  # {backbone, quantity}
  _VOCABS['proteinmpnn'] = FixedSummaryVocab(names=tuple(run_proteinmpnn.QOI_FIELDS),
      regime=BackboneConditionedSequenceDesignRegime())  # shape 'backbone_conditioned_sequence_design'
  # dispatch: state-key confidence = 1.0 iff validated-weights gate passed.
"""
