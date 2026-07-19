"""d4_wiring_fragments.py — STAGED runtime surfaces for retrosynthesis (NOT wired;
land at D.4 with models + route DB). Nothing imports this.
  _CONTRACTS['retrosynthesis'] = RETROSYNTHESIS_CONTRACT
  _SIGNATURES['retrosynthesis'] = frozenset(run_retrosynthesis._REQUIRED_FIELDS)  # {target_smiles, backend, quantity}
  _VOCABS['retrosynthesis'] = FixedSummaryVocab(names=tuple(run_retrosynthesis.QOI_FIELDS),
      regime=RetrosyntheticRouteSearchRegime())  # shape 'retrosynthetic_route_search'
  # dispatch: state-key confidence = 1.0 iff models+backend gate passed.
"""
