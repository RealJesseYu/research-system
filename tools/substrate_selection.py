"""
substrate_selection.py — D.2: signature-based substrate selection, retiring
sole_routable_id() from production.

THE RULE. A validated experiment spec declares parameter names. A routable
substrate CAN SERVE the spec iff every declared parameter name is in that
substrate's parameter signature — the set of names its builder/wrapper
actually honors. Selection is:

    candidates = [routable substrates that can serve the spec]
    none serve      -> raise LookupError (contract_for's style); NEVER a
                       cavity fallback — a spec nothing routable can serve
                       is refused loudly at selection, not judged against
                       the wrong instrument.
    among candidates, prefer mature (registry.is_mature); if MORE THAN ONE
    candidate survives that filter, selection STOPS LOUDLY naming all of
    them (R-B-1, owner-delegated, 2026-07-17) — the silent enrollment-order
    pick is RETIRED, maturity is the only tie-breaker, and no further tie
    policy exists or may be invented. Deterministic where determinable:
    same spec, same registry -> same unique pick or the same loud stop,
    always.

STEP 41 — HIERARCHICAL ROUTING (D.1b, owner-ruled 2026-07-18;
docs/memo_step41_routing.md). Serve-ability alone makes near-neighbour
FAMILIES (substrates that share a signature) unroutable: any spec two can
serve stops loudly. Step 41 interposes TASK-CLASS narrowing between
serve-ability and the R-B-1 stop, all structural and reading only the vocab
records each substrate already declares (tools/qoi_vocab.py) — no new source
of truth, no invented tie-break:

    L0  serve-ability (above) — declared names ⊆ signature.
    L1a regime-shape          — keep candidates whose regime grammar admits
                                the spec's regime block.
    L1b QoI-vocab             — keep candidates whose QoI vocabulary admits
                                the spec's requested QoI (routes a family on
                                the quantity it asks for).
    L2  instance tie-break    — among the survivors (true near-neighbours:
                                same params, same regime shape, same admitted
                                QoI), maturity then R-B-1's LOUD STOP. L2 is
                                Option 1 (loud stop, stated reason) — the
                                owner-ruled default; NO per-family preference
                                table is built (a later, explicitly
                                owner-declared add-on if a family needs one).

Every level that empties the set stops loudly with a level-named reason.
L1a/L1b are transparent when the spec declares no regime/qoi. R-B-1 is
PRESERVED, not replaced — its loud stop is simply the L2 default, reached
only on genuine ties instead of on every family.

FAIL LOUD AT SELECTION, not downstream: before serve-ability is even
consulted, every routable substrate must have BOTH a wired fidelity
contract (registry.contract_for — raises for an unwired one) and a wired
parameter signature (signature_for below). Flipping a substrate routable
without wiring both lands here loudly — this is the seam sole_routable_id's
raise used to name, now stated per missing artifact instead of per count.

SINGLE SOURCES, NEVER A THIRD COPY. The signature map wires each substrate
to a vocabulary IMPORTED read-only from the place that already owns it:
  - cavity_2d_cfd: the keys of stage4_case_builder.BUILDABLE_PARAMS plus
    REYNOLDS_KEY (the builder honors reynolds_number by verifying it
    against an explicit U/L/nu decomposition). That module is a known
    unguarded duplicate of contract §5; importing its keys read-only adds
    no new copy and that file is deliberately NOT edited here.
  - ngspice_linear_passive: WIRED at the R2 promotion flip (owner ruling,
    2026-07-17), alongside its routability ruling exactly as this note
    always required: the wrapper's own _REQUIRED_FIELDS
    (tools/run_ngspice.py), imported read-only — the tested wiring shape.
  - sympy_symbolic_exact: WIRED at the Packet B Phase 1 flip (owner
    ruling, 2026-07-17), alongside its routability ruling: the wrapper's
    own re-exported universal + per-operation field constants
    (tools/run_scipy.py), imported read-only and derived structurally.
  - fenicsx/FEA/code et al.: NOT wired — same discipline as the
    registry's _CONTRACTS map (absence is deliberate; a signature is wired
    alongside a routability ruling, never before). Tests construct
    multi-routable registries by patching this map with vocabularies
    imported from THEIR single sources.

WHAT SELECTION READS FROM THE SPEC — and R-28H-1. Serve-ability reads the
spec's declared parameter NAMES only. That is structural matching against
wrapper vocabularies, not substrate-name parsing: the spec never names a
substrate, and no substrate name found in any payload is consulted or
branched on. The QoI request is deliberately NOT part of serve-ability
today: parameter signatures discriminate among enrolled substrates —
pairwise disjoint EXCEPT the ruled cantilever overlap (the FEA seven are
a proper subset of the fenicsx eight, Packet B Phase 2), where a
shared-seven spec stops loudly under R-B-1 — and a QoI the wrapper cannot
extract has an honest downstream path (qoi_error, never a wrong number).
Expand on evidence.

KNOWN LIMITATION (stated, not solved): in production, specs are authored
against the contract stage 2 was shown, so end-to-end mixed-domain routing
additionally binds to the D.1.1 direction (selection point between gate 1
and stage 2, memo P8 option C). See docs/memo_d2_selection.md.
"""

from __future__ import annotations

from stages.stage4_case_builder import BUILDABLE_PARAMS, REYNOLDS_KEY
# Step 41 (D.1b) L1a/L1b: the ONE grammar+admissibility oracle for "does this
# substrate's regime/QoI vocabulary admit this spec's regime/QoI block". Reused
# read-only from stage 2 (the same read-only-internal-import discipline this
# file already applies to the wrapper vocabularies below) so routing and
# authoring share ONE source of truth — never a second copy of the grammar.
# Both dispatch on the vocab record's shape (vocab_for), never on a substrate
# name (R-28H-1). No import cycle: stage2_spec imports only tools.qoi_vocab.
from stages.stage2_spec import _validate_qoi, _validate_regime
from tools import substrate_registry as registry
from tools.qoi_vocab import vocab_for
from tools.run_cobrapy import _REQUIRED_FIELDS as _COBRAPY_REQUIRED_FIELDS
from tools.run_fea import _REQUIRED_FIELDS as _FEA_REQUIRED_FIELDS
from tools.run_fenicsx import _REQUIRED_FIELDS as _FENICSX_REQUIRED_FIELDS
from tools.run_mafft import _REQUIRED_FIELDS as _MAFFT_REQUIRED_FIELDS
from tools.run_ngspice import _REQUIRED_FIELDS as _NGSPICE_REQUIRED_FIELDS
from tools.run_rdkit import _REQUIRED_FIELDS as _RDKIT_REQUIRED_FIELDS
from tools.run_scipy import (
    OP_FIELDS as _SCIPY_OP_FIELDS,
    UNIVERSAL_OPTIONAL_FIELDS as _SCIPY_UNIVERSAL_OPTIONAL_FIELDS,
    UNIVERSAL_REQUIRED_FIELDS as _SCIPY_UNIVERSAL_REQUIRED_FIELDS,
)

# sympy's full typed-key vocabulary, derived STRUCTURALLY from the wrapper's
# own re-exported constants (Packet B Phase 1 flip, owner 2026-07-17):
# the universal fields plus every per-operation required/optional field —
# never a literal name (a literal here would be a forbidden third copy).
_SCIPY_SIGNATURE: frozenset[str] = (
    frozenset(_SCIPY_UNIVERSAL_REQUIRED_FIELDS)
    | frozenset(_SCIPY_UNIVERSAL_OPTIONAL_FIELDS)
    | {
        name
        for fields in _SCIPY_OP_FIELDS.values()
        for group in ("required", "optional")
        for name in fields[group]
    }
)

# substrate_id -> the set of spec parameter names its builder/wrapper honors.
# Values are built from IMPORTED vocabularies only (see module docstring);
# a literal name string in this map would be a forbidden third copy.
_SIGNATURES: dict[str, frozenset[str]] = {
    "cavity_2d_cfd": frozenset(BUILDABLE_PARAMS) | {REYNOLDS_KEY},
    # R2 promotion flip (owner, 2026-07-17): run_ngspice's own typed-key
    # vocabulary, imported — the shape the D.2 tests always wired.
    "ngspice_linear_passive": frozenset(_NGSPICE_REQUIRED_FIELDS),
    # Packet B Phase 1 flip (owner, 2026-07-17): run_scipy's own typed-key
    # vocabulary, imported and derived above. Disjoint from every other
    # wired signature — asserted by test, since the R-B-1 loud stop leans
    # on overlap detection being real.
    "sympy_symbolic_exact": _SCIPY_SIGNATURE,
    # Packet B Phase 2 flip (build chat under the owner's standing
    # delegation, 2026-07-17): each cantilever wrapper's own typed-key
    # vocabulary, imported. THE ONE DELIBERATE OVERLAP among wired
    # signatures: the FEA seven are a proper subset of the fenicsx eight
    # (element_degree is the one extra name), so a spec declaring only the
    # shared seven is served by BOTH — and stops loudly under R-B-1
    # instead of falling to enrollment order.
    "calculix_cantilever_fea": frozenset(_FEA_REQUIRED_FIELDS),
    "fenicsx_cantilever_elastic": frozenset(_FENICSX_REQUIRED_FIELDS),
    # BIO Wave D.4 promotion flip (owner, 2026-07-19): each wrapper's own
    # _REQUIRED_FIELDS, imported. All three are pairwise DISJOINT from each
    # other and from every existing signature (rdkit {smiles,quantity};
    # cobrapy {model,quantity} — min_growth is optional and NOT in
    # _REQUIRED_FIELDS, so it is not part of the serve-ability signature;
    # mafft {sequences,quantity}), so no spec any two can serve — no new
    # R-B-1 tie. Proven by test, not asserted.
    "rdkit": frozenset(_RDKIT_REQUIRED_FIELDS),
    "cobrapy": frozenset(_COBRAPY_REQUIRED_FIELDS),
    "mafft": frozenset(_MAFFT_REQUIRED_FIELDS),
}


def signature_for(substrate_id: str) -> frozenset[str]:
    """The parameter signature for one substrate. FAIL LOUD (contract_for's
    style): a substrate with no wired signature raises LookupError — selection
    must never guess what a substrate can serve. An unknown id raises KeyError
    first (via registry.get), same as contract_for."""
    record = registry.get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _SIGNATURES[substrate_id]
    except KeyError:
        raise LookupError(
            f"no parameter signature wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "selection must NOT guess serve-ability — wire a signature in "
            "tools/substrate_selection.py from the substrate's own vocabulary "
            "under a recorded ruling before routing to this substrate."
        )


def declared_parameter_names(spec: dict | None) -> frozenset[str]:
    """The parameter names a validated spec declares. A None spec (or one
    with no parameters) declares nothing — and since R-B-1 (S1, ruled
    2026-07-17) a nothing-declaring spec is served by EVERY routable
    substrate and therefore stops loudly at selection whenever more than
    one is routable: the old constrains-nothing convenience (bare
    era-proof reads resolving to cavity) is RETIRED, because its residual
    was a silent enrollment-order pick landing on cavity — a cavity
    fallback, forbidden by doctrine. Era proofs pass a minimal
    cavity-declaring spec instead."""
    if not isinstance(spec, dict):
        return frozenset()
    return frozenset(
        p["name"]
        for p in spec.get("parameters", [])
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    )


def _regime_shape_admits(spec: dict, sid: str) -> bool:
    """L1a oracle (Step 41): does substrate `sid`'s regime grammar admit the
    spec's regime block? True iff the shared stage-2 regime check finds no
    errors — the SAME grammar the spec was authored against, read through the
    substrate's own vocab record (vocab_for), never re-implemented. A spec
    with no dict `regime` narrows nothing and admits everywhere (handled by
    the caller)."""
    errors: list[str] = []
    _validate_regime(spec["regime"], vocab_for(sid), errors)
    return not errors


def _qoi_vocab_admits(spec: dict, sid: str) -> bool:
    """L1b oracle (Step 41): does substrate `sid`'s QoI vocabulary admit the
    spec's requested QoI? True iff the shared stage-2 QoI check finds no
    errors. This is what routes a shared-signature family on the QoI it asks
    for: a quantity only one member's vocab admits narrows to that member;
    two members admitting the same quantity are true near-neighbours and fall
    through to L2."""
    errors: list[str] = []
    _validate_qoi(spec["qoi"], vocab_for(sid), errors)
    return not errors


def select_substrate(spec: dict | None) -> str:
    """Pick the ONE substrate this spec routes to — Step 41 hierarchical
    routing (D.1b), task-class first then instance. In brief: routable + wired
    (contract AND signature, both probed loudly up front), then narrow through

        L0  serve-ability   — declared parameter names ⊆ signature (exists);
        L1a regime-shape    — the substrate's regime grammar admits the spec's
                              regime block (new: reads the vocab record);
        L1b QoI-vocab       — the substrate's QoI vocabulary admits the spec's
                              requested QoI (new: reads the vocab record);
        L2  instance        — among true near-neighbours (survivors of L0+L1),
                              maturity is the ONE tie-breaker, then R-B-1's
                              LOUD STOP (Option 1, owner-ruled D.1b default —
                              NO preference table). Never a coin flip.

    Every level that empties the candidate set STOPS LOUDLY with a stated,
    level-named reason — never a cavity fallback, never a silent pick. L1a/L1b
    are transparent when the spec declares no regime/qoi (minimal era-proof
    specs): there is nothing to narrow on, so nothing is dropped. PRECONDITION:
    the spec is stage-2-validated, so its regime/qoi are grammar-valid for its
    intended (L0-surviving) substrate — L1a/L1b therefore never drop that
    substrate; they only drop wrong-grammar near-neighbours.
    """
    routable = registry.routable_ids()
    for sid in routable:
        registry.contract_for(sid)  # LookupError: routable without a contract
        signature_for(sid)          # LookupError: routable without a signature

    # L0 — SERVE-ABILITY (unchanged): declared names ⊆ signature.
    names = declared_parameter_names(spec)
    candidates = [sid for sid in routable if names <= signature_for(sid)]
    if not candidates:
        unserved = {
            sid: sorted(names - signature_for(sid)) for sid in routable
        }
        raise LookupError(
            f"no routable substrate can serve this spec: declared parameters "
            f"{sorted(names)} exceed every routable signature — per substrate, "
            f"the unserved names are {unserved}. Selection must NOT fall back "
            "to cavity (or any substrate) for a spec it cannot serve — route "
            "the spec to a substrate whose vocabulary covers it, or enroll "
            "and wire one under a recorded ruling."
        )

    # L1a — TASK-CLASS by REGIME-SHAPE (Step 41). Narrow a shared-signature
    # family to the candidates whose regime grammar admits this spec's regime.
    if isinstance(spec, dict) and isinstance(spec.get("regime"), dict):
        in_regime = [sid for sid in candidates if _regime_shape_admits(spec, sid)]
        if not in_regime:
            raise LookupError(
                f"substrate selection stops at L1a (Step 41, regime-shape): "
                f"{len(candidates)} substrate(s) serve this spec's parameters "
                f"{sorted(names)} — {', '.join(candidates)} — but NONE has a "
                f"regime grammar that admits the spec's regime block. Selection "
                "must NOT fall back to cavity (or any substrate) whose regime "
                "grammar the spec does not fit — author the regime in the "
                "grammar of a serving substrate, or enroll one under a recorded "
                "ruling; stopping before routing."
            )
        candidates = in_regime

    # L1b — TASK-CLASS by QoI-VOCAB (Step 41). Narrow to candidates whose QoI
    # vocabulary admits the spec's requested QoI — this routes a family on the
    # quantity it asks for.
    if isinstance(spec, dict) and isinstance(spec.get("qoi"), dict):
        in_qoi = [sid for sid in candidates if _qoi_vocab_admits(spec, sid)]
        if not in_qoi:
            raise LookupError(
                f"substrate selection stops at L1b (Step 41, QoI-vocab): "
                f"{len(candidates)} substrate(s) serve this spec's parameters "
                f"and regime — {', '.join(candidates)} — but NONE has a QoI "
                f"vocabulary that admits the requested QoI. Selection must NOT "
                "fall back to a substrate that cannot extract the asked-for "
                "quantity — request a QoI a serving substrate's vocabulary "
                "admits, or enroll one under a recorded ruling; stopping before "
                "routing."
            )
        candidates = in_qoi

    # L2 — INSTANCE TIE-BREAK. Structural narrowing is done; the survivors are
    # true near-neighbours (same params, same regime shape, same admitted QoI).
    # Maturity is the ONE tie-breaker; if more than one survives it, the R-B-1
    # LOUD STOP fires (Option 1, the owner-ruled D.1b default — NO preference
    # table). Text preserved byte-identical: R-B-1's loud stop IS the L2 default.
    mature = [sid for sid in candidates if registry.is_mature(sid)]
    pool = mature or candidates
    if len(pool) > 1:                       # R-B-1 (owner-delegated, 2026-07-17)
        rungs = ", ".join(
            f"{sid}@{registry.maturity_of(sid)}" for sid in pool
        )
        raise LookupError(
            f"substrate selection is ambiguous (R-B-1, owner 2026-07-17): "
            f"{len(pool)} candidates serve this spec after the mature-preferred "
            f"filter — {rungs}; the declared parameters {sorted(names)} sit "
            f"inside every one of their signatures. The enrollment-order pick "
            f"is RETIRED by that ruling and no further tie policy exists — "
            f"author the spec against exactly one instrument (declare a "
            f"parameter only one signature covers), or promote exactly one "
            f"candidate to mature under a recorded ruling; stopping before "
            f"routing."
        )
    return pool[0]                          # unique candidate — the only survivor
