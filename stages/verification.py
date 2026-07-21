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

import ast
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


def _rhs_is_constant(node) -> bool:
    """True if an expression node is a compile-time constant — a literal or
    arithmetic on literals, with no name, call, or subscript feeding it. A
    computed metric fails this (it reaches for data through a Name or Call); a
    number written straight into the source passes it."""
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError):
        return False


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _iter_metric_rhs(tree, quantity: str):
    """Classify every place the code sets metrics[quantity] as 'const' (its RHS
    is a compile-time constant) or 'computed' (anything else). Covers the two
    idioms that actually occur — metrics['q'] = ... and metrics = {'q': ...} —
    and counts augmented assignment (metrics['q'] += ...) as computed, since it
    derives from a prior value."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if (isinstance(tgt, ast.Subscript)
                        and isinstance(tgt.value, ast.Name)
                        and tgt.value.id == "metrics"
                        and _const_str(tgt.slice) == quantity):
                    yield "const" if _rhs_is_constant(node.value) else "computed"
                if (isinstance(tgt, ast.Name) and tgt.id == "metrics"
                        and isinstance(node.value, ast.Dict)):
                    for k, v in zip(node.value.keys, node.value.values):
                        if _const_str(k) == quantity:
                            yield "const" if _rhs_is_constant(v) else "computed"
        elif isinstance(node, ast.AugAssign):
            tgt = node.target
            if (isinstance(tgt, ast.Subscript)
                    and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "metrics"
                    and _const_str(tgt.slice) == quantity):
                yield "computed"


def hardcoded_metric_reason(code: str, quantity: str):
    """Return a reason string when the claimed metric is only ever set to a
    compile-time constant — a number written into the source rather than
    computed — or None when at least one assignment computes it (benefit of the
    doubt) or the code cannot be parsed.

    THIS IS A TRIPWIRE, NOT A PROOF, and deliberately model-free (verification
    holds no second opinion). It catches the blatant fabrication a re-run cannot
    — a constant reproduces perfectly — but an obfuscated constant (float(0.99),
    a constant hidden behind a helper) still passes here; judging whether code
    genuinely computes what a hypothesis claims is a judgment this pass does not
    make. What it guarantees is narrow and real: a bare hardcoded number is not
    recorded as a measurement.
    """
    if not isinstance(code, str) or not isinstance(quantity, str):
        return None
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    kinds = list(_iter_metric_rhs(tree, quantity))
    if kinds and all(k == "const" for k in kinds):
        return (
            f"the reported metric {quantity!r} is assigned a compile-time "
            "constant in the code — it reproduces because the number is written "
            "into the source, not because it was computed. A hardcoded value is "
            "not a measurement."
        )
    return None


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
        from tools.substrate_dispatch import (
            CALL_CASE_BUILD,
            adapter_for,
            run_entry_constructor_for,
            wrapper_callable,
        )
        sid = artifact.get("substrate_id")
        typed = artifact.get("typed_input")
        if not sid or not isinstance(typed, dict):
            raise ArtifactError(
                "substrate artifact needs substrate_id and a typed_input object")

        if artifact.get("call_style") == CALL_CASE_BUILD:
            # The measurement came from a wrapper reading a case that was
            # SYNTHESIZED above the wrapper call. Re-running the wrapper against
            # the case still on disk would re-read that case, not regenerate it
            # — it would reproduce a build error as faithfully as a good build.
            # So regeneration re-invokes the ADAPTER, which rebuilds the case
            # from the recorded inputs, into a case name of its own so the
            # original run's evidence is never overwritten.
            adapter_input = artifact.get("adapter_input")
            if not isinstance(adapter_input, dict):
                raise ArtifactError(
                    f"substrate artifact for {sid!r} is case-build style but "
                    "carries no adapter_input, so the case it measured cannot "
                    "be rebuilt")
            summary = adapter_for(sid)(
                sid,
                adapter_input.get("params"),
                f"{adapter_input.get('case_name')}_verify",
                adapter_input.get("roles"),
                adapter_input.get("qoi_request"),
            )
        else:
            summary = wrapper_callable(sid)(dict(typed))

        # THE INSTRUMENT READ STAYS MECHANICAL. The reproduced number is taken
        # from the summary by the substrate's OWN run-entry constructor — the
        # same code that read the original measurement — rather than by reaching
        # for summary["qoi"] here. Those differ: cavity returns {value: ...},
        # the cantilevers return a dict of named numbers the request selects
        # from, and homology_search's clean no-hit is a None that is a result
        # rather than a failure. A second, simpler reader in this file would be
        # a second opinion about what the instrument said.
        try:
            entry = run_entry_constructor_for(sid)(
                summary, None, artifact.get("qoi_request"))
        except (ValueError, LookupError, KeyError) as e:
            return {"value": None, "error": f"could not read the re-run summary: {e}"}
        if "qoi_value" in entry:
            return {"value": entry["qoi_value"], "error": None}
        return {"value": None,
                "error": entry.get("qoi_error") or "the re-run produced no value"}

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

    # THE NUMBER REPRODUCES — but a hardcoded constant reproduces perfectly too.
    # For a code artifact, reject a claim whose metric is only ever written as a
    # compile-time constant: re-running proves recording, not computation, and a
    # number planted in the source is the one fabrication re-execution cannot
    # catch. Tripwire only (see hardcoded_metric_reason); substrate artifacts,
    # whose typed inputs run a real instrument, are unaffected.
    if artifact.get("kind") == "code":
        planted = hardcoded_metric_reason(
            artifact.get("code") or "", artifact.get("quantity") or "")
        if planted:
            return {"verified": False, "reason": "hardcoded_constant",
                    "detail": planted, "original": original,
                    "reproduced": reproduced, "rel_error": rel_error}

    return {"verified": True, "reason": "reproduced", "original": original,
            "reproduced": reproduced, "rel_error": rel_error}


def claims_from_run(run_id: str) -> list:
    """Collect the run's measured claims as [{value, artifact, label}], read
    from stage-4 evidence on disk.

    WHY DISK RATHER THAN THE BATON. The payload schema is locked and cumulative
    — a key added at one boundary is required at every later one — so claims
    cannot ride the baton without a recorded ruling, and they do not need to:
    stage 4 already writes the full wrapper summary (results.json) and the
    artifact that regenerates it (artifacts.json, kept separate so results.json
    keeps its pinned shape). The two are joined here on run_index.

    The VALUE is taken through the substrate's own run-entry constructor, so the
    number verified is the number the run recorded, not a second reading of the
    summary taken here.

    A measured value whose artifact is missing is still returned, deliberately,
    carrying artifact None: verify_claim reports it as `no_artifact`. Dropping it
    would quietly shrink the denominator and let an unverifiable measurement pass
    by never being counted — the "unscreened must never be recorded as passed"
    failure in a different costume.
    """
    from tools.substrate_dispatch import run_entry_constructor_for

    stage_dir = Path("runs") / str(run_id) / "stage4"
    results_path = stage_dir / "results.json"
    if not results_path.is_file():
        return []
    try:
        results = json.loads(results_path.read_text())
    except (ValueError, OSError):
        return []

    artifacts_by_index = {}
    artifacts_path = stage_dir / "artifacts.json"
    if artifacts_path.is_file():
        try:
            for record in json.loads(artifacts_path.read_text()).get("runs") or []:
                if isinstance(record, dict):
                    artifacts_by_index[record.get("run_index")] = record.get("artifact")
        except (ValueError, OSError):
            artifacts_by_index = {}

    claims = []
    for run in results.get("runs") or []:
        if not isinstance(run, dict):
            continue
        artifact = artifacts_by_index.get(run.get("run_index"))
        summary = run.get("summary")
        value = None
        if isinstance(artifact, dict) and artifact.get("substrate_id"):
            try:
                entry = run_entry_constructor_for(artifact["substrate_id"])(
                    summary, None, artifact.get("qoi_request"))
                value = entry.get("qoi_value")
            except (ValueError, LookupError, KeyError, TypeError):
                value = None
        if value is None:
            # No number was measured here (a failed or valueless run). There is
            # nothing to claim, so there is nothing to verify.
            continue
        quantity = artifact.get("quantity") or "qoi"
        claims.append({
            "value": value,
            "artifact": artifact,
            "label": f"run {run.get('run_index', '?')} {quantity}",
        })
    return claims


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
