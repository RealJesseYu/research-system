"""stages/reusable_artifacts.py — cross-run file hand-off, the reproducible way.

THE PROBLEM. A sub-investigation (a child run) can produce a FILE — a FASTA
sequence, a multiple alignment, a structure, a dataset — that a parent needs to
ASSEMBLE with other subsystems' files (e.g. an integration run that consumes a
designed sequence AND its homolog alignment). Today only verified SCALARS bubble
up between runs; files stay in each run's workspace. This module is the honest
bridge.

THE RULE IT KEEPS. A kept number re-proves by re-running its recipe — never a
stored blob. A file that crosses a run boundary must obey the same rule: it travels
as its reproducible PRODUCER (a recipe step that re-derives it), not as bytes. The
parent's integration inlines the producer as a composition step; because a
composition re-runs every step (verification's running==re-running), verifying the
parent re-runs the child's producer too, and the joint number re-proves down the
whole chain. So the verification engine needs NO change — this module only (1)
defines the reusable-artifact shape and (2) GATES it: a producer that does not
actually re-emit its file is refused, exactly as an un-reproducible scalar is.

A reusable artifact is {name, producer}:
  - name     — a bare filename the producer emits (the thing others consume).
  - producer — a composition step (kind 'code' or 'substrate') that declares
               emits:[name] and, when run, actually writes it. Like every
               composition step it also yields a scalar (the step contract), so the
               same executor runs it here as in a real recipe.

No model anywhere (verification purity). The reproducibility gate runs the producer
through verification's OWN step executor, so this can never be a second opinion
about what a producer does.
"""

from __future__ import annotations

from typing import Callable

from stages.verification import ArtifactError, _is_bare_name, _run_one_step

# A producer is a composition step that emits a file. Same kinds a recipe step may
# be; a step that emits a file is exactly the R-ART-5/7 machinery, reused.
_PRODUCER_KINDS = ("code", "substrate")


def structural_errors(desc: dict) -> list:
    """The CHEAP half of the gate — shape only, NO execution. Safe inside a model
    re-ask loop (where running a producer per attempt would be wasteful). A reusable
    artifact is {name, producer} where producer is a code|substrate step that
    declares it emits the file. Returns plain-language errors, [] = shaped."""
    if not isinstance(desc, dict):
        return ["reusable artifact must be an object with 'name' and 'producer'."]
    errors = []
    name = desc.get("name")
    if not _is_bare_name(name):
        errors.append("reusable artifact 'name' must be a bare filename (no path parts).")

    producer = desc.get("producer")
    if not isinstance(producer, dict):
        errors.append(
            "reusable artifact needs a 'producer' — a recipe step (kind code|substrate) "
            "that emits the file.")
        return errors  # nothing more to check without a producer

    if producer.get("kind") not in _PRODUCER_KINDS:
        errors.append(f"producer 'kind' must be one of {list(_PRODUCER_KINDS)}.")
    emits = producer.get("emits")
    if not isinstance(emits, list) or (name not in (emits or [])):
        errors.append(
            f"producer must declare it emits {name!r} in its 'emits' list (a producer "
            "is a step that writes the file it hands off).")
    # A code producer also needs a scalar quantity (the composition step contract).
    if producer.get("kind") == "code" and not producer.get("quantity"):
        errors.append(
            "a code producer needs a 'quantity' (every composition step yields a "
            "scalar too; set metrics[quantity] and also write the emitted file).")
    return errors


def validate_reusable_artifact(desc: dict, *, run: Callable = None) -> list:
    """Structurally check a reusable file-artifact AND prove it REPRODUCES: run its
    producer and confirm it re-emits the named file. A producer that does not
    re-derive its file is refused — the same discipline a scalar gets (a kept
    artifact must re-run), applied to a file so it can cross a run boundary as a
    RECIPE, never as an un-reproducible blob. Returns plain-language errors,
    [] = valid. `run` (verification._run_one_step) is injected for offline tests.

    NEVER raises on a bad producer — a malformed or failing producer is a rejection
    (a returned error), not a crash, because this gate is called in-loop where its
    errors are re-sent to the authoring model."""
    run = run or _run_one_step
    errors = structural_errors(desc)
    if errors:
        return errors
    producer = desc["producer"]
    name = desc["name"]

    # THE REPRODUCIBILITY GATE. Run the producer through verification's own step
    # executor and confirm it actually emits the file. This is what makes a
    # handed-off file trustworthy: it re-derives, it is not a stored artifact.
    step = dict(producer)
    step.setdefault("step_id", "producer")
    try:
        result, emitted = run(step, [])
    except ArtifactError as e:
        return [f"producer is not a runnable recipe step: {e}"]
    except Exception as e:  # noqa: BLE001 — a failing producer is a rejection
        return [f"producer raised while reproducing its file: {type(e).__name__}: {e}"]

    if result.get("error") is not None:
        return [f"producer did not run cleanly: {result['error']}"]
    if name not in emitted:
        return [f"producer ran but did not emit {name!r} — it cannot be handed off."]
    if not emitted.get(name):
        return [f"producer emitted {name!r} but it was empty — nothing to hand off."]
    return []


def as_producer_step(desc: dict, step_id: str) -> dict:
    """Turn a validated reusable artifact into a composition STEP the parent's
    integration recipe can carry, so the file is regenerated inside the parent's
    own re-runnable recipe (the hand-off is the recipe, never the bytes). Pure —
    validation happens separately; this only stamps a step_id."""
    step = dict(desc["producer"])
    step["step_id"] = step_id
    return step
