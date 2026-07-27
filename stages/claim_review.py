"""claim_review.py — does the code do what the words say? Advisory, BESIDE the wall.

WHY THIS EXISTS. The wall (stages/verification.py) re-executes an artifact and
proves the NUMBER is a property of the experiment. It cannot prove the WORDS
around the number are true of the code: a run whose label says "swept e
adaptively" while the code hardcodes e=2 reproduces perfectly; so does a
"baseline k-fold" that is secretly the proposed method; so does "16-bit integer
quantization" implemented as float16. These are exactly the highest-severity
failures documented in the AI-Scientist audit (Beel et al., arXiv:2502.14297)
and measured in the side-project experiment of 2026-07-26
(~/ai-scientist-reviewer/RESULTS.md): an artifact-reading reviewer caught this
class at 88% with zero false alarms, and no text-only reader caught it at all.

WHAT THIS IS NOT. It is not part of the wall and must never move into it: the
wall's character is deterministic, no model in the loop, and that stays pure.
This pass is a model's opinion, so its verdict travels as a CAVEAT on the
finding (`mechanism_review`), never as a change to `verified` or `publishable`.
It can add honesty; it cannot subtract results. Kill switch: CLAIM_REVIEW=0.

ONE SEALED CALL for the whole run's claims (bounded), not one per claim: the
comparison needs only the code text and the label, both already in hand — a
tooled profile would buy nothing and cost reproducibility of the review itself.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from model_call import call_stage_model
from models import model_for

CLAIM_REVIEW_MODEL = model_for("light")
CLAIM_REVIEW_STAGE_NAME = "claim_mechanism_review"

# Bounds so a claim-heavy run cannot grow the prompt without limit; claims past
# the cap are honestly skipped (absent from the returned map), never guessed at.
MAX_CLAIMS = 16
MAX_CODE_CHARS = 6_000
MAX_NOTE_CHARS = 500

SYSTEM_PROMPT = """You are a mechanism reviewer. You are given experimental claims, each as {claim_index, label, code}. The numbers themselves have ALREADY been independently re-executed and reproduced — that is settled. Your ONE question, per claim: does the code actually implement the mechanism its label describes?

Flag ONLY real mismatches of the kind that invalidate a conclusion:
- a parameter the label says is swept/adapted/varied that the code fixes or never uses;
- a labeled baseline or comparison condition whose code is not that condition;
- a named method the code does not implement (e.g. "integer quantization" done in floating point, "cross-validation" without folds);
- a labeled measurement read from something other than what the label names.

Do NOT flag style, efficiency, missing error handling, or anything that does not change what the label asserts. When the code plausibly matches the label, say so — a false alarm here costs more than a miss, because this note travels on a result that already reproduced.

For every flagged claim, `note` MUST quote the specific line(s) of code that contradict the label. A flag without a quoted line is worthless — do not emit it.

Return ONLY JSON: {"reviews": [{"claim_index": <int>, "mechanism_ok": <bool>, "note": "<empty when ok; quoted-code explanation when flagged>"}, ...]} — one entry per claim you were given, no other fields."""

SCHEMA = {"required": ["reviews"]}


def _enabled() -> bool:
    return os.environ.get("CLAIM_REVIEW", "1") != "0"


def _claim_code(art: dict) -> str:
    """The model-authored code behind one artifact, whatever shape carries it.

    THIS PASS WAS INERT IN PRODUCTION. It filtered for artifact kind "code", but
    the only production claim builder (free_experimenter._finding_artifact) never
    emits that kind: a saved code file becomes "workspace_file" (the code is in
    the file on disk) and everything else becomes "substrate". So
    review_claim_mechanisms returned {} on every real run, and the documented
    88%-catch / 0%-false-alarm safeguard could never attach a caveat to anything.
    Its tests only ever built kind "code" artifacts, which is why the suite was
    green over a pass that never fired.

    The question this reviewer asks — does the code actually implement what the
    label claims — applies wherever a MODEL wrote the code, so that is what the
    lookup keys on now:

      code           inline source on the artifact (the original shape; tests)
      workspace_file the file the agent saved; read back off disk
      substrate      only python_experiment, whose typed_input.code IS
                     model-authored. Every other substrate's typed input drives
                     a real instrument and is already a contract, so those stay
                     out — same boundary verification.py's planted-constant
                     tripwire draws.

    Returns "" when there is nothing model-authored to review.
    """
    kind = art.get("kind")
    if kind == "code":
        return str(art.get("code") or "")
    if kind == "workspace_file":
        try:
            return Path(art.get("path") or "").read_text(errors="replace")
        except OSError:
            # The file is gone or unreadable. Not reviewable, and not an error
            # worth surfacing: the WALL already reports an artifact it cannot
            # re-run, and this pass is advisory.
            return ""
    if kind == "substrate" and art.get("substrate_id") == "python_experiment":
        return str((art.get("typed_input") or {}).get("code") or "")
    return ""


def _payload_from_claims(claims: list) -> list:
    """The bounded, model-authored-code subset a reviewer can act on. A claim
    whose number came from a real instrument, or that has nothing re-runnable at
    all (the wall's 'no_artifact' case), is skipped — words about absent code are
    not reviewable."""
    payload = []
    for i, c in enumerate(claims[:MAX_CLAIMS]):
        art = c.get("artifact") if isinstance(c, dict) else None
        if not isinstance(art, dict):
            continue
        code = _claim_code(art)
        if not code.strip():
            continue
        payload.append({
            "claim_index": i,
            "label": str(c.get("label") or "")[:400],
            "code": code[:MAX_CODE_CHARS],
        })
    return payload


def review_claim_mechanisms(claims: list, *, call=None) -> dict:
    """One sealed pass over the run's claims -> {claim_index: {mechanism_ok,
    note}}. Returns {} when disabled, when nothing is reviewable, or on ANY
    failure — an advisory pass may never take down or delay a run. Never raises."""
    if not _enabled():
        return {}
    call = call or call_stage_model
    payload = _payload_from_claims(claims or [])
    if not payload:
        return {}
    try:
        data, _timing = call(
            CLAIM_REVIEW_STAGE_NAME, SYSTEM_PROMPT, {"claims": payload}, SCHEMA,
            model=CLAIM_REVIEW_MODEL)
    except Exception:  # noqa: BLE001 — advisory: silence over crash
        return {}
    out = {}
    reviewable = {p["claim_index"] for p in payload}
    for r in (data.get("reviews") or []):
        if not isinstance(r, dict):
            continue
        idx = r.get("claim_index")
        if idx not in reviewable:  # ignore invented indices
            continue
        out[idx] = {
            "mechanism_ok": bool(r.get("mechanism_ok")),
            "note": str(r.get("note") or "")[:MAX_NOTE_CHARS],
        }
    return out


def attach_mechanism_reviews(findings: list, claimed: list, reviews: dict) -> int:
    """Attach a `mechanism_review` caveat to each flagged finding, in place.

    `claimed` is the same (finding_index, finding) list the wall consumed, so
    claim_index i corresponds to claimed[i] — the exact pairing the wall used.
    Only FLAGS are attached (mechanism_ok False): a passing review adds nothing,
    because absence of a caveat is the default state of a finding and writing
    "reviewed OK" on results would lend this advisory pass an authority it has
    not earned. Never touches `verified` or any other field. Returns the number
    of findings flagged. Pure; never raises on well-formed inputs."""
    flagged = 0
    for claim_i, (finding_i, _f) in enumerate(claimed):
        r = reviews.get(claim_i)
        if not r or r.get("mechanism_ok"):
            continue
        if not (r.get("note") or "").strip():
            continue  # a flag without quoted evidence does not travel
        findings[finding_i]["mechanism_review"] = {
            "mechanism_ok": False,
            "note": r["note"],
        }
        flagged += 1
    return flagged
