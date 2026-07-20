"""
verification.py — re-execute the artifact, or the claim does not stand.

This is the second half of the autonomy inversion, and it is the half that
makes the first half defensible. The old architecture bought trust with
PERMISSION: a stage could only reach pre-enrolled instruments through typed
contracts, so whatever came back was reproducible by construction. That bought
real safety and cost the project its premise — nothing could be discovered that
had not been anticipated and wired months earlier.

This module buys the same trust with VERIFICATION instead. A stage may search,
read, write code, build an apparatus, do things nobody pre-ordained. But no
number it produces becomes a claim until this pass has independently
regenerated it from a recorded artifact.

WHAT AN ARTIFACT IS. Whatever fully determines a measurement, plus the name of
the value read out of it:

  * a code experiment  -> {kind: "code", code, quantity}
  * a substrate run    -> {kind: "substrate", substrate_id, typed_input, quantity}

Both are re-runnable by deterministic Python with no model in the loop. That is
the requirement: an artifact a model must interpret is not an artifact, it is a
second opinion.

WHY RE-RUN RATHER THAN RE-READ. Re-reading a recorded number proves only that
the number was recorded. Re-running proves the number is a property of the
experiment rather than of the run that happened to produce it — it catches
fabrication, hidden state, unseeded randomness, and the specific failure this
project has already seen live: a value that changed when nothing about the
science changed.

WHAT A MISMATCH MEANS. Not necessarily fraud. Unseeded randomness and genuine
nondeterminism both produce it, and both are things an author must know about
before publishing. The pass reports what it found and never silently repairs;
deciding what an irreproducible number means is the author's job, and the
verdict travels with the claim so a reader can make it too.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

# Relative tolerance for "the same number". Floating-point re-execution of
# identical code is normally bit-identical, so this is slack for legitimate
# platform variation, not a license for drift. A run that needs more than this
# is telling you something about itself.
DEFAULT_REL_TOL = 1e-6


class ArtifactError(ValueError):
    """The artifact is not re-runnable as recorded."""


def _isnum(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def rerun_artifact(artifact: dict) -> dict:
    """Independently re-execute one artifact and return {value, error}.

    Deterministic Python only — no model call anywhere in this path, which is
    what keeps verification from becoming a second opinion about the first
    opinion.
    """
    if not isinstance(artifact, dict):
        raise ArtifactError(f"artifact must be an object, got {type(artifact).__name__}")
    kind = artifact.get("kind")

    if kind == "code":
        from tools.run_python_experiment import run_python_experiment
        for field in ("code", "quantity"):
            if not artifact.get(field):
                raise ArtifactError(f"code artifact is missing {field!r}")
        summary = run_python_experiment({
            "code": artifact["code"],
            "quantity": artifact["quantity"],
        })
        return {"value": summary.get("qoi"), "error": None if summary.get("valid")
                else summary.get("diagnostics")}

    if kind == "substrate":
        from tools.substrate_dispatch import wrapper_callable
        sid = artifact.get("substrate_id")
        typed = artifact.get("typed_input")
        if not sid or not isinstance(typed, dict):
            raise ArtifactError(
                "substrate artifact needs substrate_id and a typed_input object")
        summary = wrapper_callable(sid)(dict(typed))
        return {"value": summary.get("qoi"), "error": None if summary.get("valid")
                else summary.get("diagnostics")}

    raise ArtifactError(
        f"unknown artifact kind {kind!r} — verification can re-run 'code' and "
        "'substrate' artifacts; anything else cannot be independently "
        "reproduced and so cannot support a claim"
    )


def verify_claim(claim: dict, rel_tol: float = DEFAULT_REL_TOL) -> dict:
    """Verify one {value, artifact} claim by re-running its artifact.

    Returns a verdict dict that travels with the claim. Never raises for a
    failed verification — an unverifiable claim is a RESULT of this pass, not
    an error in it. Only a structurally malformed claim raises.
    """
    original = claim.get("value")
    artifact = claim.get("artifact")

    if artifact is None:
        # The load-bearing case. A number with no artifact is exactly what the
        # old permission model made impossible and what tool-bearing stages
        # make easy again: a value that appeared in prose and was never
        # measured by anything.
        return {
            "verified": False,
            "reason": "no_artifact",
            "detail": (
                "this value carries no artifact, so nothing can regenerate it; "
                "it may not be claimed"
            ),
            "original": original,
        }

    try:
        result = rerun_artifact(artifact)
    except ArtifactError as e:
        return {"verified": False, "reason": "unrunnable_artifact",
                "detail": str(e), "original": original}

    if result["error"] is not None:
        return {"verified": False, "reason": "rerun_failed",
                "detail": result["error"], "original": original}

    reproduced = result["value"]
    if not _isnum(original) or not _isnum(reproduced):
        return {"verified": False, "reason": "non_numeric",
                "detail": f"original={original!r} reproduced={reproduced!r}",
                "original": original, "reproduced": reproduced}

    denom = max(abs(original), abs(reproduced), 1e-12)
    rel_error = abs(original - reproduced) / denom
    if not math.isfinite(rel_error) or rel_error > rel_tol:
        return {
            "verified": False, "reason": "mismatch",
            "detail": (
                f"re-running the artifact produced {reproduced!r}, not "
                f"{original!r} (relative error {rel_error:.3g}). The claim is "
                "not reproducible as recorded — check for unseeded randomness "
                "or state carried between runs before treating it as a result."
            ),
            "original": original, "reproduced": reproduced, "rel_error": rel_error,
        }

    return {"verified": True, "reason": "reproduced", "original": original,
            "reproduced": reproduced, "rel_error": rel_error}


def verify_run(claims: list, run_id: str = None, rel_tol: float = DEFAULT_REL_TOL) -> dict:
    """Verify every claim in a run. Writes evidence to
    runs/<run_id>/verification.json when a run_id is given.

    The summary's `publishable` flag is the gate: FALSE when any claim failed,
    because a paper is not partially trustworthy. Which claims failed, and what
    to do about them, is reported rather than decided here.
    """
    verdicts = []
    for i, claim in enumerate(claims):
        verdict = verify_claim(claim, rel_tol=rel_tol)
        verdict["claim_index"] = i
        verdict["label"] = claim.get("label") or f"claim {i + 1}"
        verdicts.append(verdict)

    verified = [v for v in verdicts if v["verified"]]
    failed = [v for v in verdicts if not v["verified"]]
    summary = {
        "total": len(verdicts),
        "verified": len(verified),
        "failed": len(failed),
        "publishable": not failed and bool(verdicts),
        "verdicts": verdicts,
    }
    if not verdicts:
        summary["note"] = (
            "no claims were submitted for verification — a paper with no "
            "verifiable numbers has nothing to stand on"
        )

    if run_id:
        run_dir = Path("runs") / str(run_id)
        if run_dir.is_dir():
            (run_dir / "verification.json").write_text(json.dumps(summary, indent=2))
            line = (
                f"VERIFICATION {summary['verified']}/{summary['total']} claims "
                f"reproduced; publishable={summary['publishable']}"
            )
            print(line)
            with open(run_dir / "log.txt", "a") as f:
                f.write(line + "\n")
    return summary
