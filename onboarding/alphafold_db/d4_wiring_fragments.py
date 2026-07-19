"""d4_wiring_fragments.py — STAGED runtime surfaces for alphafold_db (NOT wired;
land at D.4 with a reachable endpoint). Nothing imports this.
  _CONTRACTS['alphafold_db'] = ALPHAFOLD_DB_CONTRACT
  _SIGNATURES['alphafold_db'] = frozenset(run_alphafold_db._REQUIRED_FIELDS)  # {protein_sequence, quantity}
      # shares {protein_sequence, quantity} with boltz2 BY DESIGN (the Step-41
      # L1a pair; distinct regimes predicted_structure_lookup vs
      # structure_affinity_prediction). L1a routes a protein-only spec on the
      # declared regime once BOTH are routable (D.4) — the live L1a proof.
  _VOCABS['alphafold_db'] = FixedSummaryVocab(names=tuple(run_alphafold_db.QOI_FIELDS),
      regime=PredictedStructureLookupRegime())  # shape 'predicted_structure_lookup'
  # dispatch: lookup class — maturity hook keeps it never-trusted-alone.
"""
