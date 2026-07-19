"""d4_wiring_fragments.py — STAGED. The runtime enrollment surfaces for
homology_search, AUTHORED but NOT wired. They land at D.4 PROMOTION, never at
D.2. Nothing imports this file. At promotion the growing fixtures re-capture
with this contract additive-only and homology_search becomes a live
select_substrate candidate.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import HOMOLOGY_SEARCH_CONTRACT
    _CONTRACTS["homology_search"] = HOMOLOGY_SEARCH_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_homology_search import _REQUIRED_FIELDS as _HS_REQUIRED_FIELDS
    _SIGNATURES["homology_search"] = frozenset(_HS_REQUIRED_FIELDS)
    # {database, query, tool, quantity} — disjoint from every existing signature.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_homology_search import QOI_FIELDS as _HS_QOI_FIELDS
    HOMOLOGY_SEARCH = "homology_search"

    @dataclass(frozen=True)
    class HomologySearchRegime:
        shape: ClassVar[str] = HOMOLOGY_SEARCH
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    # QoI vocab: the e-value is a NAMED quantity. Modelled as named_quantity
    # (kind=evalue, target=<query-vs-db>, reduction=min); the bundle's tool field
    # rides the spec.
    _VOCABS["homology_search"] = NamedQuantityVocab(
        kinds=("evalue",), target_re=_ANY_NAME_RE, reductions=("min",),
        regime=HomologySearchRegime(),
    )

--- 5 & 6. DISPATCH (tools/substrate_dispatch.py) ---------------------------
    # adapter: run_homology_search(spec) -> {valid, qoi, diagnostics, runtime_s}.
    #   state-key scalar confidence = 1.0 when valid (the DID-IT-WORK gate passed:
    #   a valid DB, the search ran, no stderr error), else 0.0. A clean 0-hits run
    #   is valid=True with qoi None (a real 'no homolog'), NOT an error.
    # QoI translation: named_quantity {kind:evalue,...} + tool field -> the wrapper.
    # run-entry constructor: {state, qoi_value|qoi_error, wall_clock_s}.

NOTE: BOTH backends (blast + hmmer) of this bundle are now wired in
tools/run_homology_search.py's `tool` dispatch (blast: sequence query vs BLAST
DB; hmmer: baked profile vs target FASTA, with its own profile+target integrity
gate). One substrate, one row, one signature {database, query, tool, quantity}.
"""
# Nothing executable — staged; wired by hand at the D.4 promotion ruling.
