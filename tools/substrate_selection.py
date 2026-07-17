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
    among candidates, prefer mature (registry.is_mature); tie-break is
    ENROLLMENT ORDER — routable_ids() preserves the registry's enrollment
    order, and the first candidate in that order wins. Deterministic: same
    spec, same registry -> same pick, always.

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
  - ngspice_linear_passive et al.: NOT wired in production — same
    discipline as the registry's _CONTRACTS map (absence is deliberate; a
    signature is wired alongside a routability ruling, never before).
    Tests construct multi-routable registries by patching this map with
    vocabularies imported from THEIR single sources (e.g.
    tools/run_ngspice.py's _REQUIRED_FIELDS).

WHAT SELECTION READS FROM THE SPEC — and R-28H-1. Serve-ability reads the
spec's declared parameter NAMES only. That is structural matching against
wrapper vocabularies, not substrate-name parsing: the spec never names a
substrate, and no substrate name found in any payload is consulted or
branched on. The QoI request is deliberately NOT part of serve-ability
today: parameter signatures already fully discriminate among enrolled
substrates (the vocabularies are disjoint), and a QoI the wrapper cannot
extract has an honest downstream path (qoi_error, never a wrong number).
Expand on evidence.

KNOWN LIMITATION (stated, not solved): in production, specs are authored
against the contract stage 2 was shown, so end-to-end mixed-domain routing
additionally binds to the D.1.1 direction (selection point between gate 1
and stage 2, memo P8 option C). See docs/memo_d2_selection.md.
"""

from __future__ import annotations

from stages.stage4_case_builder import BUILDABLE_PARAMS, REYNOLDS_KEY
from tools import substrate_registry as registry

# substrate_id -> the set of spec parameter names its builder/wrapper honors.
# Values are built from IMPORTED vocabularies only (see module docstring);
# a literal name string in this map would be a forbidden third copy.
_SIGNATURES: dict[str, frozenset[str]] = {
    "cavity_2d_cfd": frozenset(BUILDABLE_PARAMS) | {REYNOLDS_KEY},
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
    with no parameters) declares nothing and so constrains nothing — every
    routable substrate can serve it; the era proofs rely on this for their
    bare _selected_contract() reads."""
    if not isinstance(spec, dict):
        return frozenset()
    return frozenset(
        p["name"]
        for p in spec.get("parameters", [])
        if isinstance(p, dict) and isinstance(p.get("name"), str)
    )


def select_substrate(spec: dict | None) -> str:
    """Pick the ONE substrate this spec routes to. See the module docstring
    for the full rule; in brief: routable + wired (contract AND signature,
    both probed loudly up front) + can-serve, mature preferred, tie-break =
    enrollment order (routable_ids() order), deterministic."""
    routable = registry.routable_ids()
    for sid in routable:
        registry.contract_for(sid)  # LookupError: routable without a contract
        signature_for(sid)          # LookupError: routable without a signature

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

    mature = [sid for sid in candidates if registry.is_mature(sid)]
    pool = mature or candidates
    return pool[0]
