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

    if kind == "composition":
        return _execute_composition(artifact)

    raise ArtifactError(
        f"unknown artifact kind {kind!r} — verification can re-run 'code', "
        "'substrate', and 'composition' artifacts; anything else cannot be "
        "independently reproduced and so cannot support a claim"
    )


# ---------------------------------------------------------------------------
# Composition — one experiment that CALLS several tools and combines their
# scalars (Phase 1, R-COMP-1..5; docs/memo_phase1_composition.md).
#
# A composition is a recipe of primitive steps plus a combine. Running it and
# RE-running it are the same code path (this function), so verification cannot
# drift from execution: the number a composition produces is the number
# verification regenerates, by construction. The recipe records the WIRING, not
# the intermediate values — every step is re-executed and every reference is
# re-resolved from the RE-RUN scalars, so a nondeterministic step is caught
# rather than masked. No model anywhere in here (verification purity); the only
# model-authored code is the sealed `code` steps, run in the --network=none
# sandbox exactly as a standalone code artifact is.
# ---------------------------------------------------------------------------
def _validate_recipe(artifact: dict) -> tuple:
    """Structurally check a composition recipe, or raise ArtifactError. Returns
    (steps, combine). A malformed recipe is a broken artifact, not a failed
    experiment — it raises, like every other unrunnable-artifact case."""
    steps = artifact.get("steps")
    combine = artifact.get("combine")
    if not isinstance(steps, list) or not steps:
        raise ArtifactError(
            "composition artifact needs a non-empty 'steps' list")
    seen = set()
    emits_by_step: dict = {}
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ArtifactError(f"composition step {i} is not an object")
        sid = step.get("step_id")
        if not isinstance(sid, str) or not sid:
            raise ArtifactError(f"composition step {i} has no string 'step_id'")
        if sid in seen:
            raise ArtifactError(f"composition step_id {sid!r} is not unique")
        prior = set(seen)  # steps declared BEFORE this one (for consume ordering)
        seen.add(sid)
        kind = step.get("kind")
        if kind not in ("code", "substrate"):
            raise ArtifactError(
                f"composition step {sid!r} must be a 'code' or 'substrate' "
                f"step, got kind {kind!r}")

        # Phase 4 (R-ART-5): file-artifact emits/consumes. Only code steps may
        # move files (a substrate emitting a file is R-ART-6, deferred). A
        # consume must name a bare file an EARLIER step actually emits, so a
        # malformed hand-off is re-asked, never run.
        emits = step.get("emits")
        if emits is not None:
            if not isinstance(emits, list) or not all(_is_bare_name(n) for n in emits):
                raise ArtifactError(
                    f"composition step {sid!r} 'emits' must be a list of bare "
                    "filenames (no path parts)")
            # Both a code step and an emitting substrate (R-ART-7) may emit; a
            # substrate that does not support emitting simply returns no
            # artifact and the completeness check below fails it loudly.
        emits_by_step[sid] = set(emits or [])

        consumes = step.get("consumes")
        if consumes is not None:
            if not isinstance(consumes, list):
                raise ArtifactError(
                    f"composition step {sid!r} 'consumes' must be a list")
            for c in consumes:
                if (not isinstance(c, dict) or not _is_bare_name(c.get("name"))
                        or not isinstance(c.get("step_id"), str)):
                    raise ArtifactError(
                        f"composition step {sid!r} each 'consumes' entry needs a "
                        "'step_id' and a bare 'name'")
                if c["step_id"] not in prior:
                    raise ArtifactError(
                        f"composition step {sid!r} consumes from {c['step_id']!r}, "
                        "which is not an earlier step")
                if c["name"] not in emits_by_step.get(c["step_id"], set()):
                    raise ArtifactError(
                        f"composition step {sid!r} consumes {c['name']!r} from "
                        f"{c['step_id']!r}, which does not emit it")
                # A CODE step injects the file as-is (optional 'as' rename, no
                # 'resolve'); a SUBSTRATE step reduces the file to a typed field
                # via a known 'resolve' {into, method} — R-ART-8.
                resolve = c.get("resolve")
                if kind == "substrate":
                    if (not isinstance(resolve, dict)
                            or not _is_bare_name(resolve.get("into"))
                            or resolve.get("method") not in _ARTIFACT_RESOLVERS):
                        raise ArtifactError(
                            f"composition step {sid!r} a substrate consume needs a "
                            "'resolve' {into, method} with a known method (one of "
                            f"{sorted(_ARTIFACT_RESOLVERS)})")
                else:  # code step
                    if resolve is not None:
                        raise ArtifactError(
                            f"composition step {sid!r} a code consume injects the "
                            "file as-is and takes no 'resolve'")
                    if "as" in c and not _is_bare_name(c.get("as")):
                        raise ArtifactError(
                            f"composition step {sid!r} 'consumes' rename 'as' must "
                            "be a bare filename")
    if not isinstance(combine, dict):
        raise ArtifactError("composition artifact needs a 'combine' object")
    if combine.get("kind") != "code":
        raise ArtifactError(
            "composition 'combine' must be a 'code' step — the combine is the "
            "one place the recipe's step scalars are reduced to a final number")
    if not combine.get("code") or not combine.get("quantity"):
        raise ArtifactError("composition 'combine' needs 'code' and 'quantity'")
    refs = combine.get("inputs")
    if not isinstance(refs, list) or not all(isinstance(r, str) for r in refs):
        raise ArtifactError(
            "composition 'combine' needs an 'inputs' list of step_id strings")
    unknown = [r for r in refs if r not in seen]
    if unknown:
        raise ArtifactError(
            f"composition combine references unknown step(s) {unknown} — the "
            f"declared steps are {sorted(seen)}")
    return steps, combine


def _resolve_fasta_first_ungapped(artifact_bytes: bytes) -> str:
    """Reduce an aligned FASTA to the FIRST record's UNGAPPED sequence — the
    natural query for a homology search (R-ART-8). Deterministic, no model;
    gaps ('-') are stripped so the result is a bare residue string the consumer
    accepts. Raises ArtifactError if the artifact holds no sequence."""
    text = artifact_bytes.decode("utf-8", errors="replace")
    seq_lines, started = [], False
    for line in text.splitlines():
        if line.startswith(">"):
            if started:
                break            # end of the first record
            started = True
        elif started and line.strip():
            seq_lines.append(line.strip())
    seq = "".join(seq_lines).replace("-", "")
    if not seq:
        raise ArtifactError(
            "resolver 'fasta_first_ungapped' found no sequence in the artifact")
    return seq


# The deterministic artifact reducers (R-ART-8). name -> bytes->typed value.
# Added on evidence; the registry is the single place a substrate-consume method
# is looked up, so an unknown method is refused at recipe validation.
_ARTIFACT_RESOLVERS = {
    "fasta_first_ungapped": _resolve_fasta_first_ungapped,
}


def _is_bare_name(name) -> bool:
    """A file-artifact name is a bare filename: non-empty, no path separators,
    not a directory dot-name. The recipe-side guard that mirrors the sandbox's
    _safe_artifact_name, so a bad name is caught at recipe validation."""
    return (isinstance(name, str) and name != "" and "/" not in name
            and "\\" not in name and name not in (".", ".."))


def _run_one_step(step: dict, consumed: list) -> tuple:
    """Run one composition step, wiring any consumed artifacts in, and return
    ({value, error}, {name: bytes} emitted). `consumed` is a list of
    {as, bytes, resolve} descriptors. A code step gets the files injected as-is;
    a substrate step reduces each via its resolver into a typed field (R-ART-8).
    Every non-file step is the existing per-artifact runner, byte-identical. No
    model."""
    kind = step.get("kind")
    if kind == "code" and (consumed or step.get("emits")):
        from tools.run_python_experiment import run_python_experiment
        for field in ("code", "quantity"):
            if not step.get(field):
                raise ArtifactError(f"code artifact is missing {field!r}")
        spec = {"code": step["code"], "quantity": step["quantity"]}
        if consumed:
            spec["input_files"] = {c["as"]: c["bytes"] for c in consumed}
        emits = step.get("emits") or []
        if emits:
            spec["output_files"] = list(emits)
        summary = run_python_experiment(spec)
        result = {"value": summary.get("qoi"),
                  "error": None if summary.get("valid") else summary.get("diagnostics")}
        return result, (summary.get("artifacts") or {})

    if kind == "substrate" and (step.get("emits") or consumed):
        # An emitting/consuming substrate (R-ART-7/8). Same mechanical read as
        # rerun_artifact's substrate branch (the scalar is taken by the
        # substrate's OWN run-entry constructor, never a second reader here);
        # consumed files are reduced by their resolver into typed fields, and
        # the wrapper's returned artifacts are captured for downstream steps.
        from tools.substrate_dispatch import (
            CALL_CASE_BUILD,
            run_entry_constructor_for,
            wrapper_callable,
        )
        sid = step.get("substrate_id")
        typed = step.get("typed_input")
        if not sid or not isinstance(typed, dict):
            raise ArtifactError(
                "substrate artifact needs substrate_id and a typed_input object")
        if step.get("call_style") == CALL_CASE_BUILD:
            raise ArtifactError(
                f"case-build substrate step {sid!r} cannot emit or consume a file "
                "artifact yet (R-ART-6)")
        request = dict(typed)
        for c in consumed:
            reduce = _ARTIFACT_RESOLVERS[c["resolve"]["method"]]  # validated present
            request[c["resolve"]["into"]] = reduce(c["bytes"])
        if step.get("emits"):
            request["emit_artifacts"] = list(step["emits"])
        summary = wrapper_callable(sid)(request)
        try:
            entry = run_entry_constructor_for(sid)(
                summary, None, step.get("qoi_request"))
        except (ValueError, LookupError, KeyError) as e:
            return {"value": None, "error": f"could not read the summary: {e}"}, {}
        if "qoi_value" in entry:
            return {"value": entry["qoi_value"], "error": None}, (summary.get("artifacts") or {})
        return {"value": None,
                "error": entry.get("qoi_error") or "the step produced no value"}, {}

    return rerun_artifact(step), {}


def _run_steps(steps: list) -> tuple:
    """Run every step in order, threading file artifacts between them, and
    return (scalars, error). The SAME executor runs a composition and re-runs it
    under verification, so every consumed file is RE-DERIVED from the re-run
    producer — never a recorded or stored copy (R-ART-3/4). A step that fails,
    goes non-numeric, or does not emit what it declared fails the whole
    composition — a composed number standing on a step that did not deliver is
    exactly the fabrication this pass exists to catch."""
    scalars: dict = {}
    artifacts: dict = {}  # step_id -> {name: bytes}, held in-memory this run only
    for step in steps:
        sid = step["step_id"]
        consumed: list = []  # [{as, bytes, resolve}] — descriptors for this step
        for c in step.get("consumes") or []:
            up, name = c["step_id"], c["name"]
            if up not in artifacts or name not in artifacts[up]:
                return scalars, (f"composition step {sid!r} consumes artifact "
                                 f"{name!r} from step {up!r}, which did not "
                                 "produce it")
            consumed.append({"as": c.get("as", name),
                             "bytes": artifacts[up][name],
                             "resolve": c.get("resolve")})
        result, emitted = _run_one_step(step, consumed)
        if result["error"] is not None:
            return scalars, (f"composition step {sid!r} did not produce a value: "
                             f"{result['error']}")
        if not _isnum(result["value"]):
            return scalars, (f"composition step {sid!r} produced a non-numeric "
                             f"value {result['value']!r}")
        for name in step.get("emits") or []:
            if name not in emitted:
                return scalars, (f"composition step {sid!r} declared it emits "
                                 f"{name!r} but did not write it")
        scalars[sid] = result["value"]
        artifacts[sid] = emitted
    return scalars, None


def _run_combine(combine: dict, scalars: dict) -> dict:
    """Resolve the combine's inputs from the step scalars and run it. The one
    place the recipe's step scalars are reduced to a final number."""
    resolved = {ref: scalars[ref] for ref in combine["inputs"]}
    return rerun_artifact({
        "kind": "code",
        "code": _combine_code(combine, resolved),
        "quantity": combine["quantity"],
    })


def _combine_code(combine: dict, resolved: dict) -> str:
    """Assemble the combine's sealed code: a deterministic `inputs = {...}`
    literal of the (re-run) upstream scalars, then the author's combine body.
    json.dumps of floats is round-trip exact, so the injected literal carries
    the reproduced numbers without loss."""
    return "inputs = " + json.dumps(resolved) + "\n" + combine["code"]


def _execute_composition(artifact: dict) -> dict:
    """Run every step (threading file artifacts between them), resolve the
    combine's inputs from the step scalars, run the combine. Returns
    {value, error} like every other artifact re-runner. A step that fails to
    produce a number — or to emit a file it declared — fails the whole
    composition."""
    steps, combine = _validate_recipe(artifact)
    scalars, error = _run_steps(steps)
    if error is not None:
        return {"value": None, "error": error}
    return _run_combine(combine, scalars)


def run_composition(recipe: dict) -> dict:
    """Execute a composition recipe and hand back everything a caller needs to
    record it as a verifiable claim: the final value, the recipe itself as the
    re-runnable artifact, and the intermediate step scalars (which an
    experimenter reads to decide its next move). Deterministic, no model.

    The returned `artifact` IS the recipe, unchanged — so verify_claim later
    re-runs the identical thing. Intermediate scalars are surfaced for the
    caller but are NOT stored in the artifact: the recipe records wiring, not
    values, so verification re-derives them (R-COMP-3/4). File artifacts thread
    between steps in-memory for this one execution (R-ART-5); they are never
    stored in the recipe, so a re-run re-derives every file too."""
    steps, combine = _validate_recipe(recipe)
    scalars, error = _run_steps(steps)
    if error is not None:
        return {"value": None, "artifact": recipe, "steps": scalars, "error": error}
    final = _run_combine(combine, scalars)
    return {"value": final["value"], "artifact": recipe, "steps": scalars,
            "error": final["error"]}


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

    # A composition's combine is model-authored code too — the same tripwire
    # applies to it. A combine that only ever writes its final metric as a
    # compile-time constant reproduces perfectly while measuring nothing about
    # the steps it claims to compose.
    if artifact.get("kind") == "composition":
        combine = artifact.get("combine") or {}
        planted = hardcoded_metric_reason(
            combine.get("code") or "", combine.get("quantity") or "")
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
