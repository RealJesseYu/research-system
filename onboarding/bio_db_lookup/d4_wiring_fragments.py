"""d4_wiring_fragments.py — STAGED runtime surfaces for bio_db_lookup (NOT wired;
land at D.4 with reachable endpoints; per-endpoint partial availability). Nothing
imports this.
  _CONTRACTS['bio_db_lookup'] = BIO_DB_LOOKUP_CONTRACT
  _SIGNATURES['bio_db_lookup'] = frozenset(run_bio_db_lookup._REQUIRED_FIELDS)  # {database, record_id, quantity}
  _VOCABS['bio_db_lookup'] = NamedQuantityVocab(kinds=('record_field',), target_re=_ANY,
      reductions=('value',), regime=RecordDbLookupRegime())  # shape 'record_db_lookup'
  # dispatch: lookup class — maturity hook keeps it never-trusted-alone.
"""
