"""d4_wiring_fragments.py — STAGED. Runtime enrollment surfaces for
autodock_vina, AUTHORED but NOT wired. Land at D.4 PROMOTION — and for THIS tool,
promotion additionally requires the card's un-defer requirement (an x86 host
where Vina installs + real 3A + determinism + convergence jail). Nothing imports
this.

--- 1 & 4a. CONTRACT (tools/substrate_registry.py) --------------------------
    from substrates import AUTODOCK_VINA_CONTRACT
    _CONTRACTS["autodock_vina"] = AUTODOCK_VINA_CONTRACT

--- 2. SIGNATURE (tools/substrate_selection.py) -----------------------------
    from tools.run_autodock_vina import _REQUIRED_FIELDS as _VINA_REQUIRED_FIELDS
    _SIGNATURES["autodock_vina"] = frozenset(_VINA_REQUIRED_FIELDS)
    # {receptor, ligand, box, quantity} — disjoint from every existing signature.

--- 3. VOCAB + REGIME (tools/qoi_vocab.py) ----------------------------------
    from tools.run_autodock_vina import QOI_FIELDS as _VINA_QOI_FIELDS
    RIGID_POCKET_DOCK = "rigid_pocket_dock"

    @dataclass(frozen=True)
    class RigidPocketDockRegime:
        shape: ClassVar[str] = RIGID_POCKET_DOCK
        alien_keys: ClassVar[tuple] = (
            "reynolds_min", "reynolds_max", "analysis_type", "operation",
        )

    _VOCABS["autodock_vina"] = FixedSummaryVocab(
        names=tuple(_VINA_QOI_FIELDS),            # ("docking_score",)
        regime=RigidPocketDockRegime(),
    )

--- 5 & 6. DISPATCH (tools/substrate_dispatch.py) ---------------------------
    # adapter: run_autodock_vina(spec) -> {valid, qoi, diagnostics, runtime_s}.
    #   state-key scalar confidence = 1.0 when valid (V2 convergence gate passed:
    #   a scored pose with the fixed seed), else 0.0. NOTE the C1-hole: a
    #   converged score does NOT validate the receptor/box setup (upstream).
    # QoI translation: fixed_summary {quantity:"docking_score"} -> the wrapper.
    # run-entry constructor: {state, qoi_value|qoi_error, wall_clock_s}.
"""
# Nothing executable — staged; wired at D.4 promotion on an x86 host.
