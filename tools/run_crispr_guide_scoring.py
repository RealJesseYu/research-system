"""
run_crispr_guide_scoring — the CRISPR guide-efficiency scoring wrapper
(CRISPOR/CHOPCHOP class, Doench/CFD models). BIO Wave D.2. Plain, deterministic
code. NO AI inside, ever.

**RE-TIERED T2 -> DEFERRED (owner-ruled 2026-07-18):** no VERIFIED py3 Doench/CFD
scorer runs here. Azimuth (the canonical Doench-2016 on-target scorer) is
Python-2 code (`SyntaxError` on Python 3 import) + a compiled sklearn/model
backend; and no standalone CFD package exists (`pip install cfd-score` ->
"No matching distribution"). This is a SOFTWARE-AVAILABILITY deferral (different
from cas_offinder's wrong-kernel and autodock_vina's wrong-architecture): it
needs an ARTIFACT — a verified py3 Doench/CFD scorer, or model files + a
maintained scorer, FROM A TRUSTED SOURCE — not a machine.

*** FORBIDDEN (part of the spec, not a nicety) ***
DO NOT hand-transcribe the Doench/CFD model coefficients or the CFD penalty
matrix from memory or an unverified source. A transcribed model produces
plausible-but-UNVERIFIABLE scores — the silent-wrong failure this wave exists to
prevent (a wrong guide-efficiency score reads as confident and correct). The QoI
is trustworthy ONLY when computed by a verified scorer. Un-deferring means
INSTALLING that verified artifact, exactly as cas_offinder's card says "validate
the kernel first."

Enrolled INERT (`calibrating`/`routable=False`). The pure-Python INPUT gate is
proven now; the scoring §3A is PENDING-PROVISIONING.

REGIME (card unit = (crispr_guide_scoring, guide_activity_scoring)). Score a
guide RNA's on-target efficiency for a target site under a given nuclease.
FILTER-class: the score is a RELATIVE efficiency screen, not measured cutting.

Typed input:
    run_crispr_guide_scoring({
      "guide": "ACGT...(20 nt)",   # the protospacer
      "pam": "AGG",                # must match the enzyme's motif
      "enzyme": "SpCas9",          # a baked allowlist nuclease
      "quantity": "activity_score",
    })

Return (ONLY this leaves the wrapper):
    {"valid": bool, "qoi": float | None, "diagnostics": str, "runtime_s": float}
"""

from __future__ import annotations

import json
import re
import time


class CrisprInputError(ValueError):
    """The typed input is not a runnable guide-scoring request."""


_REQUIRED_FIELDS = ("guide", "pam", "enzyme", "quantity")
GUIDE_LEN = 20
# enzyme -> PAM motif (IUPAC; N = any). SpCas9 = NGG.
ENZYME_MOTIFS = {"SpCas9": "NGG"}
ENZYME_ALLOWLIST = tuple(ENZYME_MOTIFS)
QOI_FIELDS = ("activity_score",)

_DNA_RE = re.compile(r"^[ACGT]+$", re.IGNORECASE)
_IUPAC = {"N": "ACGT", "G": "G", "A": "A", "C": "C", "T": "T"}


def _pam_matches_motif(pam: str, motif: str) -> bool:
    if len(pam) != len(motif):
        return False
    return all(p.upper() in _IUPAC.get(m, "") for p, m in zip(pam, motif))


def _validate_input(spec: dict) -> dict:
    """Return a clean copy, or raise CrisprInputError. THE INPUT GATE — pure,
    proven now (no scorer needed): valid guide, valid PAM matching the enzyme
    motif, sequence in the expected form."""
    if not isinstance(spec, dict):
        raise CrisprInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise CrisprInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise CrisprInputError(f"unsupported field(s): {', '.join(sorted(extra))}")

    if spec["enzyme"] not in ENZYME_ALLOWLIST:
        raise CrisprInputError(
            f"enzyme {spec['enzyme']!r} is not on the allowlist "
            f"(allowed: {', '.join(ENZYME_ALLOWLIST)})")
    motif = ENZYME_MOTIFS[spec["enzyme"]]

    guide = spec["guide"]
    if not isinstance(guide, str) or not _DNA_RE.match(guide or ""):
        raise CrisprInputError("'guide' must be a DNA string over A/C/G/T")
    if len(guide) != GUIDE_LEN:
        raise CrisprInputError(
            f"'guide' must be exactly {GUIDE_LEN} nt (the protospacer length); "
            f"got {len(guide)}")

    pam = spec["pam"]
    if not isinstance(pam, str) or not _DNA_RE.match(pam or ""):
        raise CrisprInputError("'pam' must be a DNA string over A/C/G/T")
    if not _pam_matches_motif(pam, motif):
        raise CrisprInputError(
            f"'pam' {pam!r} does not match the {spec['enzyme']} motif {motif!r}")

    if spec["quantity"] not in QOI_FIELDS:
        raise CrisprInputError(
            f"quantity {spec['quantity']!r} is not an allowlist QoI "
            f"(allowed: {', '.join(QOI_FIELDS)})")
    return {"guide": guide.upper(), "pam": pam.upper(),
            "enzyme": spec["enzyme"], "quantity": spec["quantity"]}


def scorer_available() -> str | None:
    """Return None when a VERIFIED py3 Doench/CFD scorer is installed, else the
    honest DEFERRED reason. On this host none is available (Azimuth is Python-2;
    no standalone CFD package). At provisioning the verified artifact is
    installed and this returns None."""
    return ("no VERIFIED py3 Doench/CFD scorer is installed (Azimuth is "
            "Python-2; no standalone CFD package) — DEFERRED. Install a verified "
            "scorer/model from a trusted source; do NOT hand-transcribe "
            "coefficients (that is the silent-wrong failure this wave prevents).")


def run_crispr_guide_scoring(spec: dict) -> dict:
    """Score a guide's on-target efficiency — but ONLY with a verified scorer.
    On this host the input gate fires (proven) and then the honest DEFERRED
    state is returned; no score is ever produced from an unverified model."""
    wall_start = time.time()

    def fail(msg: str) -> dict:
        return {"valid": False, "qoi": None,
                "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except CrisprInputError as e:
        return fail(f"input rejected: {e}")

    reason = scorer_available()
    if reason:
        return fail(f"substrate not ready: {reason}")

    # AT PROVISIONING (verified scorer installed): compute activity_score via the
    # verified scorer here, gated on a finite result. Intentionally NOT
    # implemented with any transcribed model — the verified artifact IS the
    # implementation, and it is the un-defer requirement.
    raise NotImplementedError(  # pragma: no cover - unreachable until provisioned
        "the verified scorer path is wired at provisioning together with the "
        "trusted scorer artifact; unreachable while scorer_available() defers")


# CLI: venv/bin/python3 tools/run_crispr_guide_scoring.py  (DEFERRED here)
if __name__ == "__main__":
    default = {"guide": "GACGCATAAAGATGAGACGC", "pam": "TGG",
               "enzyme": "SpCas9", "quantity": "activity_score"}
    print(json.dumps(run_crispr_guide_scoring(default), indent=2))
