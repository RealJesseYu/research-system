"""models.py — one place to choose which model plays which role.

Every stage/agent in the system draws its model from one of THREE tiers, and
each tier is a single knob you set once:

    heavy   — the smart / hard-judgment model: the free experimenter, the PI
              director, the paper writer, hypothesis ranking, meta-review.
              Default: Opus.
    light   — the workhorse: hypothesis generation, the review chain, evolution.
              Default: Sonnet.
    triage  — cheap, low-stakes passes: the sealed-stage default, web search.
              Default: Haiku.

Set a tier with an env var (an alias — opus/sonnet/haiku — or a full model id):

    RESEARCH_MODEL_HEAVY=opus  RESEARCH_MODEL_LIGHT=opus   # an all-Opus run
    RESEARCH_MODEL_HEAVY=sonnet                            # a cheaper heavy tier

or, on the supervisor, the friendlier flags --model-heavy / --model-light /
--model-triage (which set these env vars for you before the run starts).

Unset => the historical mix, byte-identical to the pinned constants. Resolved
at call time, so a knob set before the run takes effect everywhere.
"""

from __future__ import annotations

import os

# Claude 5 family (2026-07-25). These pins were claude-opus-4-8 / claude-sonnet-4-6
# — the PREVIOUS generation — so every agent in the system was running a model
# older than the plain chat it was being compared against, which is a direct
# PRIME-DIRECTIVE problem: the comparison chat was Claude 5, the system was not.
OPUS = "claude-opus-5"
SONNET = "claude-sonnet-5"
HAIKU = "claude-haiku-4-5-20251001"  # current; Haiku has no 5 release

_ALIASES = {"opus": OPUS, "sonnet": SONNET, "haiku": HAIKU}

_TIER_ENV = {
    "heavy": "RESEARCH_MODEL_HEAVY",
    "light": "RESEARCH_MODEL_LIGHT",
    "triage": "RESEARCH_MODEL_TRIAGE",
}
# OWNER RULING 2026-07-25: every tier defaults to OPUS.
#
# The prior defaults (light=Sonnet, triage=Haiku) meant hypothesis GENERATION and
# the whole review chain — the creative and screening work — ran on Sonnet, while
# only ranking and meta-review got Opus. Measured on study-20260725T073215Z: 119
# of 140 ideation calls were Sonnet. A plain Opus/Fable chat given the same prompt
# produced markedly better ideas, better selection reasoning, and an honest mixed
# result; the PRIME DIRECTIVE says the system must never be weaker than a chat, so
# the tier split was violating it at the exact stage where quality matters most.
#
# Cost is the deliberate trade. Both knobs remain, so a cheap run is one env var
# away (RESEARCH_MODEL_LIGHT=sonnet RESEARCH_MODEL_TRIAGE=haiku restores the old
# mix exactly).
_TIER_DEFAULT = {"heavy": OPUS, "light": OPUS, "triage": OPUS}


def model_for(tier: str) -> str:
    """Resolve a tier ('heavy' | 'light' | 'triage') to a model id, honoring the
    tier's env override — an alias (opus/sonnet/haiku) or a full model id. Unset
    => the tier default, byte-identical to the historical pin. Raises on an
    unknown tier (a typo in the code, not a user error)."""
    if tier not in _TIER_DEFAULT:
        raise ValueError(
            f"unknown model tier {tier!r}; expected one of {sorted(_TIER_DEFAULT)}")
    raw = os.environ.get(_TIER_ENV[tier], "").strip()
    if not raw:
        return _TIER_DEFAULT[tier]
    return _ALIASES.get(raw.lower(), raw)


def set_tier(tier: str, value: str) -> None:
    """Set a tier's env knob (used by the supervisor's --model-* flags). `value`
    is an alias or a full model id; empty/None clears the override."""
    if tier not in _TIER_ENV:
        raise ValueError(f"unknown model tier {tier!r}")
    if value:
        os.environ[_TIER_ENV[tier]] = value
    else:
        os.environ.pop(_TIER_ENV[tier], None)
