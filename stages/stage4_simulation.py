"""
stage4_simulation.py — real Simulation stage (Step 12 chunk 1).

Deterministic control flow, ZERO model calls — the Haiku ack stub retired
here. This stage reads the fidelity verdict already in the payload and acts
on it; it never re-judges anything:

  defer          -> execute nothing (skipped_defer).
  trust | refine -> for each mini-experiment run (1-3, sequential): execute
                    through the SELECTED substrate's adapter
                    (tools/substrate_dispatch, D.4) — for cavity that is
                    build_case + the identical production-wrapper call this
                    stage has always made. A CaseSynthesisError is an honest
                    outcome, not a crash: the stage records halted_synthesis,
                    runs nothing further, and relays onward. refine
                    additionally flags that survivors require downstream
                    confirmation.

The substrate is chosen STRUCTURALLY (D.4): signature-based selection on the
validated spec (tools/substrate_selection, the same function stage 3 uses —
deterministic, D.2 test (d)), never parsed from a payload name (R-28H-1);
the payload gains no substrate field (the key set is locked). An unwired or
unknown id raises at dispatch — never a cavity fallback.

The spec's QoI is translated to a wrapper qoi_request through the SELECTED
substrate's translation (tools/substrate_dispatch.qoi_translation_for, R2
flip) ONLY if the spec's qoi object carries the machine-readable keys of
that substrate's own grammar — cavity: {field, operation, component?};
named-quantity class: {kind, target, reduction[, at]} — with vocabularies
read from the selected substrate's QoI-vocabulary record (tools/qoi_vocab;
every member IS the owning wrapper's object, single source of truth);
otherwise the honest-refusal path records a qoi_error (for cavity, runs
still execute WITHOUT a qoi_request; a named-quantity adapter refuses to
execute without one, loudly). Run entries are built by the selected
substrate's own conclusions-only constructor
(tools/substrate_dispatch.run_entry_constructor_for). Whether the named field actually exists in the case is the
wrapper's own check at extraction time — it reports its own qoi_error rather
than fabricating a number.

Evidence: the FULL per-run wrapper summaries go to runs/<id>/stage4/
results.json. The payload gains execution_results with conclusions ONLY —
{status, refine flag if applicable, runs: [{converged, qoi_value or
qoi_error, wall_clock_s}]} — no residual dicts, no logs, per the baton
invariant. The single history note is code-authored from validated fields.

Substrate note: this stage names no solver and no substrate file format; the
substrate-specific machinery (case builder, wrappers, adapters) sits below
it behind the dispatch seam, and the parameter/QoI content it forwards is
payload DATA, never branched on by name — the substrate id it dispatches on
is obtained structurally from selection, never from the payload.
"""

from __future__ import annotations

import json
from pathlib import Path

from baton import Baton
from stages.stage4_case_builder import CaseSynthesisError
from tools.qoi_vocab import vocab_for
from tools.substrate_dispatch import (
    adapter_for,
    qoi_translation_for,
    run_entry_constructor_for,
)
from tools.substrate_selection import select_substrate

REFINE_FLAG = "refine — survivors require downstream confirmation"


def translate_qoi(spec_qoi, vocab) -> tuple[dict | None, str | None]:
    """Translate a spec's qoi object into a wrapper qoi_request, or refuse.

    Returns (qoi_request, None) when the qoi is contract-extractable, else
    (None, honest_reason). Never raises on qoi content. Extractability is
    signalled by explicit machine-readable keys in the spec qoi — this code
    never guesses from free text.

    D.4: the operation/component re-checks read the QoI-vocabulary RECORD of
    the SELECTED substrate (tools/qoi_vocab.vocab_for — for cavity its
    members ARE run_cfd's own objects, so the checks are unchanged), passed
    in by run(). `vocab` is REQUIRED (G2 guard, owner ruling 2026-07-17):
    the pre-D.4 bare call resolved it via selection on a None spec, which —
    the moment routable_ids() has two entries — silently means "first
    enrolled by vacuous match". A caller must resolve the record itself
    (vocab_for(select_substrate(spec)), or an explicit id); a bare call now
    raises instead of guessing a substrate.
    """
    if not isinstance(spec_qoi, dict):
        return None, "spec has no qoi object"
    field = spec_qoi.get("field")
    operation = spec_qoi.get("operation")
    component = spec_qoi.get("component")
    if not isinstance(field, str) or not field or operation is None:
        return None, (
            "spec qoi carries no machine-readable field/operation keys "
            "(free-text definitions are not translated)"
        )
    if operation not in vocab.operations:
        return None, (
            f"operation {operation!r} is not one of {sorted(vocab.operations)}"
        )
    if component is not None and component not in vocab.components:
        return None, f"component {component!r} is not 'mag' or 0|1|2"
    request = {"field": field, "operation": operation}
    if component is not None:
        request["component"] = component
    return request, None


def extract_parameter_roles(parameters) -> dict:
    """{name: {role, derived_from?}} from the spec's parameters list (Step 16).

    Pure function, never raises: malformed entries are simply omitted — the
    builder treats an absent roles entry exactly like a non-derived
    parameter, so nothing here can invent a role the spec did not declare.
    """
    roles: dict = {}
    if isinstance(parameters, list):
        for p in parameters:
            if isinstance(p, dict) and isinstance(p.get("name"), str) and p["name"]:
                entry = {"role": p.get("role")}
                if "derived_from" in p:
                    entry["derived_from"] = p["derived_from"]
                roles[p["name"]] = entry
    return roles


def _log_line(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt (same path rule as stage 3)."""
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def run_one_point(
    run_id: str,
    index: int,
    total: int,
    params: dict,
    *,
    substrate_id: str,
    adapter,
    entry_constructor,
    parameter_roles: dict,
    qoi_request,
    qoi_error_fallback,
    case_name: str | None = None,
) -> tuple[dict | None, dict | None, str | None]:
    """Execute ONE mini-experiment point through the ALREADY-RESOLVED substrate
    adapter — a PURE extraction of stage 4's per-point loop body.

    Dispatch is hoisted: the caller resolves substrate_id / adapter /
    entry_constructor / parameter_roles / qoi_request / qoi_error_fallback ONCE
    (including the R-23.5-4 agreement check) and passes them in, so this
    function branches on no substrate name and does no re-derivation. The
    campaign controller (Step 29) reuses it to run proposed points beside the
    single-run path.

    Returns (evidence_run, payload_run, halt_reason):
      * on a CaseSynthesisError -> (None, None, halt_reason) — the caller stops;
      * otherwise -> (evidence_run, payload_run, None).
    The caller owns accumulation and the halt break, exactly as the inline loop
    did. Side-effect order (adapter call -> entry constructed -> STAGE4 log) is
    preserved byte-for-byte.
    """
    if case_name is None:
        case_name = f"{run_id}_run{index}"
    try:
        summary = adapter(substrate_id, params, case_name, parameter_roles, qoi_request)
    except CaseSynthesisError as exc:
        halt_reason = f"run {index} of {total}: {exc}"
        _log_line(run_id, f"STAGE4 halted_synthesis at {halt_reason}")
        return None, None, halt_reason
    evidence_run = {
        "run_index": index,
        "case": case_name,
        "params": params,
        "summary": summary,
    }
    payload_run = entry_constructor(summary, qoi_error_fallback, qoi_request)
    # the qoi display tolerates both wrapper shapes: cavity's {value: …}
    # object and ngspice's bare scalar/null (cavity output unchanged)
    raw_qoi = summary.get("qoi")
    if isinstance(raw_qoi, dict):
        qoi_display = raw_qoi.get("value", "n/a")
    else:
        qoi_display = raw_qoi if raw_qoi is not None else "n/a"
    _log_line(
        run_id,
        f"STAGE4 run {index}/{total} case={case_name} "
        f"status={summary.get('status')} converged={summary.get('converged')} "
        f"qoi={qoi_display}",
    )
    return evidence_run, payload_run, None


def run(baton: Baton) -> Baton:
    # Step 29 opt-in (D5): when the RESEARCH_CAMPAIGN flag is set, this stage is
    # the campaign controller (a stage-4-equivalent producing ONE consolidated
    # result). The import is lazy so the default path pays nothing structural
    # and there is no import cycle (campaign_controller imports run_one_point
    # from here). With the flag unset the single-run path below is unchanged.
    from stages.campaign_controller import campaign_enabled, run_campaign

    if campaign_enabled():
        return run_campaign(baton)

    verdict = baton.payload["fidelity_verdict"]
    label = verdict["label"]
    stage_dir = Path("runs") / baton.run_id / "stage4"
    stage_dir.mkdir(parents=True, exist_ok=True)

    if label == "defer":
        reason = 'fidelity verdict label is "defer" — nothing was executed.'
        results = {"status": "skipped_defer", "reason": reason}
        (stage_dir / "results.json").write_text(json.dumps(results, indent=2))
        payload = dict(baton.payload)
        payload["execution_results"] = {"status": "skipped_defer"}
        baton.payload = payload
        baton.add_history("stage4_simulation", "skipped (defer)")
        _log_line(baton.run_id, "STAGE4 skipped_defer: no case built, no solver run")
        return baton

    if label not in ("trust", "refine"):
        raise ValueError(
            f"stage4_simulation: unknown fidelity verdict label {label!r} — "
            "expected trust, refine, or defer"
        )

    spec = baton.payload["experiment_spec"]
    # D.4: the substrate id is RE-DERIVED structurally from the validated
    # spec (the same deterministic selection stage 3 used — the payload key
    # set is locked and carries no substrate field), then dispatch resolves
    # its adapter BEFORE any translation: an unwired or unknown id raises
    # here, escape-failing — never a cavity fallback.
    substrate_id = select_substrate(spec)
    # R-23.5-4 agreement check (owner, 2026-07-17): the spec-derived
    # structural selection must agree with the gate-decided substrate_id
    # the payload carries — a mismatch stops loudly BEFORE execution
    # (nothing built, nothing run). A payload without the key fails loud
    # here too (KeyError), never defaults.
    carried_id = baton.payload["substrate_id"]
    if substrate_id != carried_id:
        raise RuntimeError(
            f"stage4_simulation: substrate agreement check failed — "
            f"spec-derived selection {substrate_id!r} != gate-decided payload "
            f"substrate_id {carried_id!r}; stopping before execution."
        )
    adapter = adapter_for(substrate_id)
    vocab = vocab_for(substrate_id)
    # R2 flip: the spec-QoI translation and the conclusions-only entry
    # constructor are per-substrate glue, resolved structurally at dispatch
    # (fail-loud on an unwired id) — for cavity both ARE the pre-flip code
    # paths (translate_qoi / the moved _cavity_run_entry), fixture-pinned
    # byte-identical.
    translate = qoi_translation_for(substrate_id)
    entry_constructor = run_entry_constructor_for(substrate_id)
    mini_runs = spec["mini_experiment"]["runs"]
    parameter_roles = extract_parameter_roles(spec.get("parameters"))
    qoi_name = spec.get("qoi", {}).get("name") if isinstance(spec.get("qoi"), dict) else None
    qoi_request, refusal = translate(spec.get("qoi"), vocab)
    qoi_error_fallback = (
        None
        if qoi_request is not None
        else f"QoI {qoi_name!r} not extractable by contract: {refusal}"
    )
    if qoi_request is None:
        _log_line(baton.run_id, f"STAGE4 qoi_request=none ({qoi_error_fallback})")

    evidence_runs: list[dict] = []
    payload_runs: list[dict] = []
    halt_reason: str | None = None

    for index, params in enumerate(mini_runs, start=1):
        # PURE extraction (Step 29): the per-point loop body is run_one_point,
        # with dispatch hoisted above. qoi_request joined the uniform
        # constructor signature ADDITIVELY at Packet B Phase 2.0 (ruled option
        # V-A): fixed-summary substrates return several named numbers and the
        # constructor must know which one the spec requested; cavity/ngspice/
        # sympy constructors ignore it — their entries are byte-identical.
        evidence_run, payload_run, halt = run_one_point(
            baton.run_id,
            index,
            len(mini_runs),
            params,
            substrate_id=substrate_id,
            adapter=adapter,
            entry_constructor=entry_constructor,
            parameter_roles=parameter_roles,
            qoi_request=qoi_request,
            qoi_error_fallback=qoi_error_fallback,
        )
        if halt is not None:
            halt_reason = halt
            break
        evidence_runs.append(evidence_run)
        payload_runs.append(payload_run)

    status = "halted_synthesis" if halt_reason else "executed"
    results = {
        "status": status,
        "verdict_label": label,
        "qoi_request": qoi_request,
        "runs": evidence_runs,
    }
    execution_results = {"status": status, "runs": payload_runs}
    if halt_reason:
        results["reason"] = halt_reason
        execution_results["reason"] = halt_reason
    if qoi_error_fallback is not None:
        results["qoi_translation_error"] = qoi_error_fallback
    if label == "refine":
        results["flag"] = REFINE_FLAG
        execution_results["flag"] = REFINE_FLAG
    (stage_dir / "results.json").write_text(json.dumps(results, indent=2))

    payload = dict(baton.payload)
    payload["execution_results"] = execution_results
    baton.payload = payload

    if halt_reason:
        note = f"halted: case synthesis (run {len(evidence_runs) + 1} of {len(mini_runs)})"
    else:
        converged = sum(1 for r in payload_runs if r["converged"])
        extracted = sum(1 for r in payload_runs if "qoi_value" in r)
        note = (
            f"executed {len(payload_runs)} mini-run(s): {converged} converged, "
            f"{extracted} QoI extracted"
        )
    baton.add_history("stage4_simulation", note)
    return baton
