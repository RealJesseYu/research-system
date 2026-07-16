"""
substrate_registry.py — STEP 28: the substrate maturity registry.

A typed, code-authored table of every substrate the system knows about, and
how far each one has climbed the trust ladder. This is the single source of
truth the supervisor consults before it lets a fidelity "trust decision"
(a trust/refine verdict) route to real execution.

THE MATURITY LADDER (low -> high), for routable substrates:
    calibrating  -- a card exists / a battery is being assembled, but the
                    substrate has not earned unattended trust. Never routable.
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

from substrates import CAVITY_2D_CONTRACT

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
            "real runs accruing, mini-21 pending; the SOLE routable substrate "
            "(current pipeline behavior)"
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


def sole_routable_id() -> str:
    """The one routable substrate id — the single-node pipeline's structural
    answer to 'which substrate does this run execute/verdict against'. Read
    from the registry, never guessed. RAISES if the routable set is not exactly
    one: multi-substrate node selection (which node runs on which substrate) is
    Step 35 (task typing), and this session promotes nothing, so today the
    routable set is exactly ('cavity_2d_cfd',). A future promotion that makes a
    second substrate routable without building selection lands here loudly,
    which is the intended seam — it names the missing work rather than silently
    picking one."""
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
    (that would violate the substrate-agnostic invariant). Today: exactly
    ('cavity_2d_cfd',)."""
    return tuple(r.substrate_id for r in _REGISTRY if r.routable)
