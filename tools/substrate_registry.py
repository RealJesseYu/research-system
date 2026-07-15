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
