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
provable, never a pasted copy. ngspice's record is NOT wired in production:
same discipline as the registry's _CONTRACTS map and selection's _SIGNATURES
map (absence is deliberate; a vocabulary is wired alongside a routability
ruling, never before). Tests construct the ngspice record from
tools/run_ngspice.py's own constants — THEIR single source.

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

FIELD_REDUCTION = "field_reduction"
NAMED_QUANTITY = "named_quantity"


@dataclass(frozen=True)
class FieldReductionVocab:
    """A reduction-over-a-field vocabulary (cavity class). Members are the
    wrapper's own objects — the record adds structure, never content."""

    shape: ClassVar[str] = FIELD_REDUCTION

    operations: dict     # allowed operations (mapping; sorted(...) -> keys)
    components: tuple    # allowed components
    field_re: Pattern    # the field-name grammar
    mask_types: tuple    # allowed spatial-mask types

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

    alien_keys: ClassVar[tuple] = ("field", "operation", "component", "mask")


# substrate_id -> its QoI-vocabulary record. cavity ALONE in production,
# mirroring _CONTRACTS (registry) and _SIGNATURES (selection): absence is
# deliberate, wired only alongside a routability ruling. The cavity members
# ARE run_cfd's objects (see module docstring) — a literal here would be a
# forbidden third copy.
_VOCABS: dict[str, Any] = {
    "cavity_2d_cfd": FieldReductionVocab(
        operations=QOI_OPERATIONS,
        components=QOI_COMPONENTS,
        field_re=_QOI_FIELD_RE,
        mask_types=MASK_TYPES,
    ),
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
