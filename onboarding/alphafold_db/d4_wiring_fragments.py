"""d4_wiring_fragments.py — STAGED runtime surfaces for alphafold_db (NOT wired;
land at the promotion flip on clean gate-track calibration). Nothing imports this.
Network un-deferred 2026-07-19 (wrapper wired, §3A filled); promotion pending.
  _CONTRACTS['alphafold_db'] = ALPHAFOLD_DB_CONTRACT
  _SIGNATURES['alphafold_db'] = frozenset(run_alphafold_db._REQUIRED_FIELDS)  # {uniprot_accession, quantity}
      # INPUT-SHAPE RULING (owner 2026-07-19): keyed by uniprot_accession, NOT
      # protein_sequence — AFDB is accession-keyed. This signature is UNIQUE /
      # disjoint from every routable signature (and from boltz2's
      # {protein_sequence, quantity}), so it routes to itself with NO R-B-1 tie.
      # The former boltz2 L1a pairing is DROPPED (boltz2 stays deferred, GPU).
  _VOCABS['alphafold_db'] = FixedSummaryVocab(names=tuple(run_alphafold_db.QOI_FIELDS),
      regime=PredictedStructureLookupRegime())  # shape 'predicted_structure_lookup'
      # fixed-summary THREADED family (the D.4 bio recipe): 'quantity' selects
      # mean_pLDDT; the wrapper returns the one scalar qoi.
  # dispatch: lookup class — the run entry maps a resolved lookup to a scalar
  # qoi and an unreachable/not-found to qoi_error (never a fabricated pLDDT).
  # maturity hook keeps it never-trusted-alone.
"""
