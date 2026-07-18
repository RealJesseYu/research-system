"""
qoi_vocab.py — D.3: the per-substrate QoI-vocabulary lookup, retiring
stage2_spec.py's direct run_cfd imports.

THE TWO-SHAPE FACT (D.3 registered prediction, confirmed from disk). A
substrate's structured QoI vocabulary is per-substrate in SHAPE, not just in
contents — one table keyed the same way for every substrate would be a lie:

  field-reduction shape (cavity class): a QoI request is a REDUCTION OVER A
    FIELD — operations x components x a field-name grammar x spatial mask
    types. The structured source is tools/run_cfd.py (QOI_OPERATIONS,
    QOI_COMPONENTS, _QOI_FIELD_RE, MASK_TYPES).

  named-quantity shape (ngspice/FEA class): a QoI request NAMES A QUANTITY —
    enumerated kinds x a target-name grammar x enumerated reductions. The
    structured source is tools/run_ngspice.py (_QOI_KINDS, _NAME_RE,
    _REDUCTIONS). NOTE the packet correction: the ngspice onboarding
    contract.py is PROSE; the structured vocabulary lives in the wrapper,
    mirroring how cavity's lives in tools/run_cfd.py.

So the record is TAGGED — one frozen dataclass per shape, and a validator
dispatches on the shape, never on a substrate name (R-28H-1 discipline).

SINGLE SOURCES, NEVER A THIRD COPY (the _CONTRACTS/_SIGNATURES precedent).
The cavity record's members ARE run_cfd's objects — imported, assertIs-
provable, never a pasted copy. ngspice's record was WIRED at the R2
promotion flip (owner ruling, 2026-07-17), alongside its routability ruling
exactly as the discipline requires, from tools/run_ngspice.py's own
constants — its single source. sympy's record was wired the same way at
the Packet B Phase 1 flip (owner, 2026-07-17), from tools/run_scipy.py's
re-exported operation allowlist. The still-unrouted substrates (fenicsx/
FEA/code) remain unwired: absence is deliberate; a vocabulary is wired
alongside a routability ruling, never before.

FAIL LOUD (contract_for's style): a substrate with no wired vocabulary
raises LookupError — validation must never guess a vocabulary, and NEVER
falls back to cavity's. An unknown id raises KeyError first (via
registry.get) — an unenrolled substrate is never silently treated as
anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Pattern

from tools import substrate_registry as registry
from tools.run_cfd import MASK_TYPES, QOI_COMPONENTS, QOI_OPERATIONS, _QOI_FIELD_RE
from tools.run_ngspice import _ANALYSIS_FIELDS, _NAME_RE, _QOI_KINDS, _REDUCTIONS
from tools.run_scipy import OPERATIONS as _SCIPY_OPERATIONS

FIELD_REDUCTION = "field_reduction"
NAMED_QUANTITY = "named_quantity"
SYMBOLIC_RESULT = "symbolic_result"

# Regime-semantics shapes (R-23.5-5, owner 2026-07-17): "regime" remains
# REQUIRED in every spec; its MEANING is per-substrate. The semantics ride
# the same per-substrate record family as the QoI vocabulary — vocab_for is
# the one lookup, and _validate_regime dispatches on the regime record's
# shape, never on a substrate name (R-28H-1 discipline). Unknown/unwired
# substrates hit vocab_for's existing loud raises before any regime check.
REYNOLDS_BAND = "reynolds_band"
ANALYSIS_TYPE = "analysis_type"
OPERATION_SET = "operation_set"


@dataclass(frozen=True)
class ReynoldsBandRegime:
    """Cavity-class regime semantics (R-23.5-5): today's Reynolds bounds —
    an object {reynolds_min, reynolds_max, notes} with numeric bounds
    satisfying 0 < min <= max. The validation behavior and rejection text
    are the pre-R-23.5-5 _validate_regime body byte-equal (pinned by
    tests/test_r2355_captures.py's exact-string captures)."""

    shape: ClassVar[str] = REYNOLDS_BAND


@dataclass(frozen=True)
class AnalysisTypeRegime:
    """ngspice-class regime semantics (R-23.5-5): DERIVED FROM THE WRAPPER'S
    typed input on disk, never invented — the regime axis of a linear
    passive network is which analysis it lives in, and the wrapper's own
    typed-input vocabulary already enumerates exactly that:
    tools/run_ngspice.py's _ANALYSIS_FIELDS keys (op | dc | ac | tran, the
    same set the contract's "out of this regime by ruling" sentence draws
    from). `analysis_types` is derived from that imported object at import
    time — a structural view, never a pasted copy."""

    shape: ClassVar[str] = ANALYSIS_TYPE

    analysis_types: tuple  # run_ngspice._ANALYSIS_FIELDS keys, in wrapper order

    # The OTHER shapes' keys, rejected by name so a wrong-grammar regime
    # block in a named-analysis spec fails loudly with a per-substrate
    # reason instead of a bare missing-key complaint (mirrors alien_keys).
    # "operation" joined ADDITIVELY under the Packet B Phase 1.0 ruling
    # (item 2, owner, 2026-07-17): the operation-set shape's key, so a
    # CAS-shaped regime block in an ngspice-class spec rejects by name in
    # the reverse direction too. Existing rejection strings for Reynolds
    # inputs are byte-identical (per-key rendering; pinned exact by
    # tests/test_r2355_regime.py).
    alien_keys: ClassVar[tuple] = ("reynolds_min", "reynolds_max", "operation")


# ngspice's regime record, constructed from the wrapper's typed input
# (R-23.5-5: each field cited — _ANALYSIS_FIELDS is run_ngspice's own
# analysis-type table, imported at the top of this module; tuple(...) reads
# its keys live at import).
NGSPICE_REGIME = AnalysisTypeRegime(analysis_types=tuple(_ANALYSIS_FIELDS))


@dataclass(frozen=True)
class OperationSetRegime:
    """CAS-class regime semantics (Packet B Phase 1.0 ruling item 1, owner
    2026-07-17): DERIVED FROM THE WRAPPER'S own closed operation allowlist,
    never invented — the regime of an exact symbolic instrument is which
    operation it performs on the expression as typed. `operations` is
    derived from the owning wrapper's imported allowlist (for sympy:
    tools/run_scipy.py's OPERATIONS, which IS the onboarding contract's S1
    tuple, bound at run_scipy.py's own import) — a structural view, never
    a pasted copy."""

    shape: ClassVar[str] = OPERATION_SET

    operations: tuple  # the wrapper's closed operation allowlist, in order

    # The OTHER shapes' keys, rejected by name so a Reynolds-shaped or
    # analysis-shaped regime block in an operation-set spec fails loudly
    # with a per-substrate reason instead of a bare missing-key complaint.
    alien_keys: ClassVar[tuple] = ("reynolds_min", "reynolds_max", "analysis_type")


# sympy's regime record, constructed from the wrapper's own closed operation
# allowlist (Packet B Phase 1.0 ruling item 1 + packet rule D.1: derived from
# run_scipy's own operation allowlist, NEVER invented — run_scipy.OPERATIONS
# IS the onboarding contract's ruled S1 tuple, bound at the wrapper's own
# import; tuple(...) reads it live at import, a structural view).
SYMPY_REGIME = OperationSetRegime(operations=tuple(_SCIPY_OPERATIONS))


@dataclass(frozen=True)
class FieldReductionVocab:
    """A reduction-over-a-field vocabulary (cavity class). Members are the
    wrapper's own objects — the record adds structure, never content."""

    shape: ClassVar[str] = FIELD_REDUCTION

    operations: dict     # allowed operations (mapping; sorted(...) -> keys)
    components: tuple    # allowed components
    field_re: Pattern    # the field-name grammar
    mask_types: tuple    # allowed spatial-mask types
    regime: Any          # the substrate's regime-semantics record (R-23.5-5)

    # The OTHER shape's machine keys, rejected by this shape's validator so a
    # request in the wrong grammar fails loudly instead of passing silently
    # as "not extractable".
    alien_keys: ClassVar[tuple] = ("kind", "target", "reduction", "at")


@dataclass(frozen=True)
class NamedQuantityVocab:
    """A named-quantity vocabulary (ngspice/FEA class): enumerated kinds,
    a target-name grammar, enumerated reductions."""

    shape: ClassVar[str] = NAMED_QUANTITY

    kinds: tuple         # allowed quantity kinds
    target_re: Pattern   # the target-name grammar
    reductions: tuple    # allowed reductions
    regime: Any          # the substrate's regime-semantics record (R-23.5-5)

    alien_keys: ClassVar[tuple] = ("field", "operation", "component", "mask")


@dataclass(frozen=True)
class SymbolicResultVocab:
    """A symbolic-result vocabulary (exact-CAS class, Packet B Phase 1.0):
    the QoI IS the operation's own verified result — the wrapper takes no
    QoI request (its typed input has no `qoi` field; unknown fields are
    rejected by name), so this shape carries NO machine-readable extraction
    keys. A spec's qoi under this shape is the four prose fields only;
    machine keys from EITHER other grammar are rejected by name via
    alien_keys. The record still carries the substrate's regime-semantics
    member — the regime rides the vocab record in every shape (R-23.5-5)."""

    shape: ClassVar[str] = SYMBOLIC_RESULT

    regime: Any          # the substrate's regime-semantics record

    # BOTH other shapes' machine keys, rejected by name: a request in any
    # foreign grammar fails loudly instead of passing silently as prose.
    alien_keys: ClassVar[tuple] = (
        "field", "operation", "component", "mask",   # field-reduction grammar
        "kind", "target", "reduction",                # named-quantity grammar
    )


# substrate_id -> its QoI-vocabulary record, mirroring _CONTRACTS (registry)
# and _SIGNATURES (selection): wired only alongside a routability ruling —
# ngspice entered at the R2 flip (owner, 2026-07-17); the still-unrouted
# substrates are deliberately absent. Every member IS the owning wrapper's
# object (see module docstring) — a literal here would be a forbidden third
# copy.
_VOCABS: dict[str, Any] = {
    "cavity_2d_cfd": FieldReductionVocab(
        operations=QOI_OPERATIONS,
        components=QOI_COMPONENTS,
        field_re=_QOI_FIELD_RE,
        mask_types=MASK_TYPES,
        regime=ReynoldsBandRegime(),
    ),
    # R-23.5-5 (owner, 2026-07-17): ngspice's regime semantics are its own —
    # NGSPICE_REGIME, derived above from the wrapper's typed analysis set —
    # enrolled at Phase 3 of the R-23.5-5 build together with the c235
    # placeholder-fixture supersession (the Phase-2 commit carried a
    # disclosed transitional ReynoldsBandRegime so every commit stayed
    # green while the placeholder was still the pinned fixture).
    "ngspice_linear_passive": NamedQuantityVocab(
        kinds=_QOI_KINDS,
        target_re=_NAME_RE,
        reductions=_REDUCTIONS,
        regime=NGSPICE_REGIME,
    ),
    # Packet B Phase 1 flip (owner, 2026-07-17): sympy's vocabulary is the
    # symbolic-result shape — the wrapper takes no QoI request (its typed
    # input has no qoi field; the QoI IS the operation's verified result),
    # so the record carries no machine-key vocabulary, only the regime
    # record derived above from the wrapper's own operation allowlist.
    "sympy_symbolic_exact": SymbolicResultVocab(regime=SYMPY_REGIME),
}


def vocab_for(substrate_id: str):
    """The QoI-vocabulary record for one substrate, read STRUCTURALLY from
    this map keyed by substrate_id (R-28H-1: never parsed from a payload
    name). FAIL LOUD (contract_for's style): a substrate with no wired
    vocabulary raises LookupError — the validator must NOT fall back to
    cavity's vocabulary for a substrate that has none. An unknown id raises
    KeyError first (via registry.get) — an unenrolled substrate is never
    silently treated as anything."""
    record = registry.get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _VOCABS[substrate_id]
    except KeyError:
        raise LookupError(
            f"no QoI vocabulary wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "spec validation must NOT fall back to cavity's vocabulary — "
            "wire a record in tools/qoi_vocab.py from the substrate's own "
            "wrapper vocabulary under a recorded ruling before routing to "
            "this substrate."
        )
