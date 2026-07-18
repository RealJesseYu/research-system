"""
substrate_registry.py — STEP 28: the substrate maturity registry.

A typed, code-authored table of every substrate the system knows about, and
how far each one has climbed the trust ladder. This is the single source of
truth the supervisor consults before it lets a fidelity "trust decision"
(a trust/refine verdict) route to real execution.

THE MATURITY LADDER (low -> high), for routable substrates:
    calibrating  -- a card exists / a battery is being assembled, but the
                    substrate has not earned unattended trust. Not routable
                    by default; AMENDED by ruling R3 (owner, 2026-07-17): a
                    calibrating substrate whose battery has run MAY be ruled
                    routable — every trust decision touching it stays
                    human-required via the supervisor's maturity hook
                    (NEEDS_HUMAN_SIGNOFF; auto-mode trust/refine downgrades
                    to defer), so it is never silently trusted.
    provisional  -- real runs are accruing and the wrapper behaves, but the
                    calibration is not complete (e.g. cavity_2d_cfd: real runs
                    accruing, mini-21 pending). Routable, but a trust decision
                    that touches it is human-required (see the supervisor hook).
    mature       -- calibration complete; trust decisions may proceed
                    unattended. NO substrate is 'mature' today.

web_search sits in its OWN class, retrieval-provisional, deliberately OUTSIDE
the routable ladder: it is a retrieval source that is structurally never
trusted alone, so it is never routable and never the target of a trust
decision.

changes only by recorded ruling — maturity and routable are trust-bearing
facts. Editing a row (promoting a rung, flipping routable) is a governance
act: it happens by editing THIS file under a recorded ruling, never at
runtime, never from a prompt, never inferred from a run. That is why the
table is plain Python data and not read from a mutable store.

Registration-for-routing of the FEA and code substrates is a SEPARATE future
ruling; enrolling them here as calibrating/unroutable does NOT authorize the
pipeline to route to them.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrates import (
    CAVITY_2D_CONTRACT,
    NGSPICE_LINEAR_PASSIVE_CONTRACT,
    SYMPY_SYMBOLIC_EXACT_CONTRACT,
)

# --- maturity rungs -------------------------------------------------------
CALIBRATING = "calibrating"
PROVISIONAL = "provisional"
MATURE = "mature"
# web_search's own class — outside the routable ladder, never trusted alone.
RETRIEVAL_PROVISIONAL = "retrieval-provisional"

# The routable ladder, low -> high. RETRIEVAL_PROVISIONAL is intentionally NOT
# a member: a retrieval source is not on the execute-and-trust path at all.
MATURITY_LADDER = (CALIBRATING, PROVISIONAL, MATURE)

# The one and only maturity a trust decision may proceed on unattended.
TRUSTWORTHY = MATURE


@dataclass(frozen=True)
class SubstrateRecord:
    """One row of the registry. Frozen: a runtime caller can read it but can
    never mutate a trust-bearing fact in place."""

    substrate_id: str
    wrapper: str
    card_path: str
    maturity: str
    routable: bool
    cost_tier: str
    notes: str


# The registry itself. Order is the enrollment order and is preserved by
# all_substrates(). changes only by recorded ruling (see module docstring).
_REGISTRY: tuple[SubstrateRecord, ...] = (
    SubstrateRecord(
        substrate_id="cavity_2d_cfd",
        wrapper="tools/run_cfd.py",
        card_path="docs/envelope_card_cavity2d.md",
        maturity=PROVISIONAL,
        routable=True,
        cost_tier="low",
        notes=(
            "real runs accruing, mini-21 pending; first-enrolled routable "
            "substrate (sole-routable note retired at the R2 flip, owner "
            "2026-07-17)"
        ),
    ),
    SubstrateRecord(
        substrate_id="calculix_cantilever_fea",
        wrapper="tools/run_fea.py",
        card_path="docs/envelope_card_calculix_cantilever.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="battery pending owner OK",
    ),
    SubstrateRecord(
        substrate_id="code_sklearn_eval",
        wrapper="tools/run_code.py",
        card_path="docs/envelope_card_code_sklearn_eval.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="battery not on the run manifest — owner decision pending",
    ),
    SubstrateRecord(
        substrate_id="fenicsx_cantilever_elastic",
        wrapper="tools/run_fenicsx.py",
        card_path="docs/envelope_card_fenicsx_cantilever_elastic.md",
        maturity=CALIBRATING,
        routable=False,
        cost_tier="low",
        notes="slate drafted (15 cases); battery pending owner OK on the slate ruling",
    ),
    SubstrateRecord(
        substrate_id="sympy_symbolic_exact",
        wrapper="tools/run_scipy.py",
        card_path="docs/envelope_card_sympy_symbolic_exact.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "sci-Python Regime A (exact symbolic CAS); card provisionally "
            "signed (owner, 2026-07-16), S1-S6 + S2a/S4a/S4b all RULED (owner, "
            "2026-07-16); battery executed 2026-07-17 (28/30 draws in-band, "
            "8/10 cases unanimous, hook witnessed 16/16 zero-silent-trust, "
            "wrapper self-checks 5/5 — harness/"
            "calibration_sympy_symbolic_exact_20260717T115450Z.json); "
            "routable=True RULED Packet B Phase 1 (owner 'start phase 1' + "
            "Phase-1.0 ruling line, 2026-07-17: OperationSetRegime regime "
            "shape, item 1), maturity CALIBRATING unchanged — every trust "
            "decision human-required via the maturity hook until a separate "
            "maturity ruling. Regime B (scipy_numeric_quad) is QUEUED and "
            "has no row."
        ),
    ),
    SubstrateRecord(
        substrate_id="ngspice_linear_passive",
        wrapper="tools/run_ngspice.py",
        card_path="docs/envelope_card_ngspice_linear_passive.md",
        maturity=CALIBRATING,
        routable=True,
        cost_tier="low",
        notes=(
            "battery executed 2026-07-17 (30/30 draws in-band, 10/10 cases "
            "unanimous, hook witnessed 18/18 zero-silent-trust — harness/"
            "calibration_ngspice_linear_passive_20260717T123935Z.json); "
            "routable=True RULED R2, maturity CALIBRATING unchanged RULED R3 "
            "(owner, 2026-07-17) — every trust decision human-required via "
            "the maturity hook until a separate maturity ruling"
        ),
    ),
    SubstrateRecord(
        substrate_id="web_search",
        wrapper="tools/web_search_stub.py",
        card_path="docs/substrate_registry.md",
        maturity=RETRIEVAL_PROVISIONAL,
        routable=False,
        cost_tier="minimal",
        notes="structurally never trusted alone",
    ),
)

_BY_ID: dict[str, SubstrateRecord] = {r.substrate_id: r for r in _REGISTRY}

# --- the model-visible fidelity contract, keyed by substrate id ------------
# R-S3-1: the ONE place "which contract does the gate judge against" is
# answered, replacing stage3's hardcoded module constant. Registry-driven and
# structural — a caller passes a substrate_id it obtained STRUCTURALLY from
# this registry (routable_ids / sole_routable_id), never parsed from a payload
# name (R-28H-1). cavity's value IS the imported substrates.CAVITY_2D_CONTRACT
# (never a pasted copy — substrates.py stays the single source of truth, same
# discipline as the R-WIN-1 prompt blocks). A substrate absent from this map
# has NO wired contract: contract_for RAISES rather than substitute cavity.
# Enrolling FEA/code here is a SEPARATE future ruling (they are unroutable and
# uncalibrated today) — their absence from this map is deliberate, not an
# oversight, and is the fail-loud escape the Part-A tests prove.
_CONTRACTS: dict[str, str] = {
    "cavity_2d_cfd": CAVITY_2D_CONTRACT,
    # R2 promotion flip (owner, 2026-07-17): the IMPORTED runtime constant,
    # graduated to substrates.py — never a pasted copy, and never the
    # battery's compact SUBSTRATE_TEXT (a different artifact; see
    # onboarding/ngspice_linear_passive/contract.py).
    "ngspice_linear_passive": NGSPICE_LINEAR_PASSIVE_CONTRACT,
    # Packet B Phase 1 flip (owner, 2026-07-17): the IMPORTED runtime
    # constant, AUTHORED AT GRADUATION in substrates.py (the sympy
    # onboarding module had no 5-section text to move — its structured
    # allowlists stay the wrapper's source of truth; see the onboarding
    # module's STAGING NOTE) — never a pasted copy, and never the
    # battery's substrate_text/envelope_text (different artifacts).
    "sympy_symbolic_exact": SYMPY_SYMBOLIC_EXACT_CONTRACT,
}


def contract_for(substrate_id: str) -> str:
    """The model-visible fidelity-contract text for one substrate, read
    STRUCTURALLY from the registry (R-28H-1: never parsed from a payload name).

    THE CHAIN SEAM (Steps 31/32). A chain of N nodes needs N contracts — each
    node verdicted against its OWN card, chain trust capped at the weakest link.
    This function is that seam: call it once per node with the node's own
    substrate_id. It is keyed on substrate_id ALONE so a multi-node chain drops
    in without rework; it does NOT decide which substrate a node runs on (that
    is Stage 3 / task-typing's job — Step 35 — and is deliberately not built
    here).

    FAIL LOUD (R-S3-1): a substrate with no wired contract raises LookupError.
    The gate NEVER falls back to cavity for a substrate it has no contract for —
    an unroutable FEA/code substrate has no routing contract here by design, and
    a run that reached this point for one is a broken invariant, not a case to
    paper over with the wrong contract. An unknown id raises KeyError first (via
    get) — an unenrolled substrate is never silently treated as anything.
    """
    record = get(substrate_id)  # KeyError on an unknown id — never silent
    try:
        return _CONTRACTS[substrate_id]
    except KeyError:
        raise LookupError(
            f"no fidelity contract wired for substrate {substrate_id!r} "
            f"(maturity={record.maturity}, routable={record.routable}); "
            "the gate must NOT fall back to cavity — wire a contract in "
            "_CONTRACTS under a recorded ruling before routing to this "
            "substrate."
        )


def routable_contracts_block() -> str:
    """R5 (owner, 2026-07-17): the ALL-ROUTABLE contract block for Stage-1
    surfaces. Stage 1 sits BEFORE any hypothesis is chosen, so its honest
    grounding is every instrument the run could route to — never a selected
    one (the D.1.1 direction: all routable contracts at Stage-1 surfaces,
    task-typed selection at Stage-2/Step-35).

    Deterministic pure function of the registry: loops routable_ids() in
    enrollment order and emits, per substrate, a minimal fixed header naming
    the substrate_id and then contract_for(id) VERBATIM — never a paraphrase,
    never a pasted copy. No timestamps, fixed separators, byte-stable.
    FAIL LOUD inherits from contract_for: a routable substrate without a
    wired contract cannot compose — the LookupError escapes."""
    return "\n\n".join(
        "ROUTABLE SUBSTRATE: " + sid + "\n" + contract_for(sid)
        for sid in routable_ids()
    )


def sole_routable_id() -> str:
    """RETIRED FROM PRODUCTION (D.2, 2026-07-17): zero production call sites —
    stage 3 now selects via tools/substrate_selection.select_substrate
    (signature-based serve-ability, mature preferred, enrollment-order
    tie-break), and that module's fail-loud probes (contract AND signature
    wired for every routable substrate) replace this function's
    exactly-one-routable raise as the promotion seam. The body stays for
    tests/history (tests/test_contract_registry.py exercises it); no new call
    site may use it.

    Original contract, still honored: the one routable substrate id, read from
    the registry, never guessed; RAISES if the routable set is not exactly
    one."""
    routable = routable_ids()
    if len(routable) != 1:
        raise RuntimeError(
            f"substrate selection is ambiguous: routable set is {list(routable)}; "
            "the single-node pipeline requires exactly one routable substrate. "
            "Multi-substrate node selection is Step 35 (task typing) — it must "
            "not be silently guessed here."
        )
    return routable[0]


def all_substrates() -> tuple[SubstrateRecord, ...]:
    """Every enrolled substrate, in enrollment order."""
    return _REGISTRY


def get(substrate_id: str) -> SubstrateRecord:
    """The record for one substrate. Raises KeyError on an unknown id — an
    unknown substrate is never silently treated as anything."""
    return _BY_ID[substrate_id]


def maturity_of(substrate_id: str) -> str:
    """The maturity rung of one substrate."""
    return _BY_ID[substrate_id].maturity


def is_mature(substrate_id: str) -> bool:
    """True only when the substrate is fully 'mature' — the one rung a trust
    decision may proceed on unattended. provisional / calibrating /
    retrieval-provisional all return False (non-mature)."""
    return _BY_ID[substrate_id].maturity == MATURE


def routable_ids() -> tuple[str, ...]:
    """The substrate ids the pipeline may route execution to, in enrollment
    order. This is the registry's answer to 'what can a run execute on' — it
    is consulted structurally, NOT parsed from a payload's substrate names
    (that would violate the substrate-agnostic invariant). Since the
    Packet B Phase 1 flip (owner, 2026-07-17): ('cavity_2d_cfd',
    'sympy_symbolic_exact', 'ngspice_linear_passive') — sympy sits in the
    middle because enrollment order is preserved and its row precedes
    ngspice's."""
    return tuple(r.substrate_id for r in _REGISTRY if r.routable)
