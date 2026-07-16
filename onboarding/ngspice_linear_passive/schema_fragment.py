"""schema_fragment.py — STAGED. The Wave Guide merges this; nothing imports it.

LANDS IN: stages/stage2_spec.py.

READ THIS FIRST: THIS ONE IS NOT A PASTE. IT IS A DESIGN DECISION.
=============================================================================
The brief asked for "the Stage-2 vocabulary/QoI-key extension exactly as it
would sit in the schema, with a comment naming its insertion point". Written out
honestly, there is no such snippet, because the Stage-2 schema is not
substrate-neutral today — it is CFD-PINNED at the import line:

    stages/stage2_spec.py:22
        from tools.run_cfd import (QOI_COMPONENTS, QOI_OPERATIONS, MASK_TYPES,
                                   _QOI_FIELD_RE)

_validate_qoi then checks a spec's machine-readable keys against exactly that
one wrapper's vocabulary:

    field      -> _QOI_FIELD_RE      (an OpenFOAM field name the case writes)
    operation  -> QOI_OPERATIONS     {max, min, volAverage, volIntegrate}
    component  -> QOI_COMPONENTS     ("mag", 0, 1, 2)
    mask       -> MASK_TYPES

ngspice's QoI vocabulary is not a superset, a subset, or a renaming of that. It
is a DIFFERENT SHAPE:

    kind       -> {node_voltage, vsource_current}     (no CFD analogue)
    target     -> a node or voltage-source name       (no CFD analogue)
    reduction  -> {op_value, final, max, min, value_at, corner_3db}
    at         -> float, REQUIRED for value_at and FORBIDDEN otherwise

Only `max` and `min` even collide, and they collide by accident of English:
CFD's operate over a spatial field, ngspice's over a solved sweep. There is no
`field`, no `component`, and no `mask` in a circuit; there is no `kind`,
`target`, or `at` in the cavity. Adding ngspice's terms to QOI_OPERATIONS would
make `volAverage` a legal ngspice reduction and `corner_3db` a legal cavity
operation, and validate_spec would wave both through. That is worse than no
extension: it converts a loud pre-solve rejection into a spec the gate believes.

WHAT ACTUALLY HAS TO HAPPEN (a ruling, not a merge)
---------------------------------------------------------------------------
_validate_qoi must dispatch on the spec's substrate before it picks a
vocabulary. The seam already half-exists one layer up: substrate_registry
.contract_for(substrate_id) is the "which contract does this node judge
against" answer (R-S3-1), and this is the same question one level down — "which
QoI vocabulary does this node's spec validate against". Sketch, NOT ratified:

    # stages/stage2_spec.py — replacing the tools.run_cfd import at line 22
    _QOI_VOCABULARIES = {
        "cavity_2d_cfd":         _CAVITY_QOI_RULES,
        "ngspice_linear_passive": _NGSPICE_QOI_RULES,
    }
    # ...and _validate_qoi takes the substrate_id it validates against, keyed
    # STRUCTURALLY from the registry (R-28H-1: never parsed from a payload).

That change touches a FROZEN file, needs its own tests, and — most importantly
— is a decision about whether Stage 2 becomes multi-substrate at all, which is
entangled with Step 35 (task typing) and with sole_routable_id()'s deliberate
RAISE on a second routable substrate. It is not this session's call and it is
not a paste the Wave Guide should make unattended.

DOES ANYTHING BLOCK ON IT TODAY? NO.
---------------------------------------------------------------------------
ngspice is `calibrating` / unroutable. Stage 2 never authors an ngspice spec,
because nothing routes there. The calibration battery does not touch
stage2_spec at all — it builds its own stage_input from the case file and calls
the Stage-3 gate directly. So this fragment is a NOTE FOR THE RECORD: the
vocabulary gap is named, sized, and deliberately unbuilt. It wakes when ngspice
is proposed for routing, not before. (Expand on evidence; no gold-plating.)

THE VOCABULARY, FOR WHOEVER BUILDS IT
---------------------------------------------------------------------------
Below is ngspice's side of that future table, stated once so the eventual
builder does not re-derive it from the wrapper. These are the wrapper's OWN
constants — import them, never retype them:

    from tools.run_ngspice import _QOI_KINDS, _REDUCTIONS, _NAME_RE

        _QOI_KINDS  = ("node_voltage", "vsource_current")
        _REDUCTIONS = ("op_value", "final", "max", "min", "value_at",
                       "corner_3db")
        _NAME_RE    = r"^[A-Za-z0-9_#\\.\\-\\+]+$"   # target, shell-locked

    Cross-field rules the wrapper already enforces pre-solve, which any schema
    extension must NOT re-implement loosely (one runtime source of truth):
      - reduction "op_value"    requires analysis.type == "op"
      - reduction "corner_3db"  requires analysis.type == "ac"
      - reduction "value_at"    requires `at`; every other reduction forbids it
      - qoi.target must exist as a solved vector, or the run returns
        valid=False with a named reason and NO number

    The honest framing for a Stage-2 prompt, when one is ever written: a
    circuit's QoI is (kind, target, reduction[, at]) — "which quantity, at which
    node, reduced how" — not (field, operation, component).
"""

# Nothing executable, deliberately. Importing this file must never be how the
# schema learns a vocabulary; that would be a second source of truth for the
# wrapper's own constants.
