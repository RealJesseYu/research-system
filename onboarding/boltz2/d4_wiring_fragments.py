"""d4_wiring_fragments.py — STAGED runtime surfaces for boltz2 (NOT wired; land
at D.4 on a validated GPU host). Nothing imports this.
  _CONTRACTS['boltz2'] = BOLTZ2_CONTRACT  (from substrates import BOLTZ2_CONTRACT)
  _SIGNATURES['boltz2'] = frozenset(run_boltz2._REQUIRED_FIELDS)  # {protein_sequence, quantity}
      # NOTE: shares {protein_sequence, quantity} with alphafold_db BY DESIGN —
      # they are the Step-41 L1a pair (same signature, DISTINCT regime:
      # structure_affinity_prediction vs predicted_structure_lookup). L1a routes
      # a protein-only spec on the declared regime; this fires only once BOTH are
      # routable (D.4), never at D.2.
  _VOCABS['boltz2'] = FixedSummaryVocab(names=tuple(run_boltz2.QOI_FIELDS),
      regime=StructureAffinityPredictionRegime())  # shape 'structure_affinity_prediction'
  # dispatch adapter: state-key confidence = 1.0 iff validated-weights gate passed.
"""
