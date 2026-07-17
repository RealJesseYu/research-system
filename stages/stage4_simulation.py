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

The spec's QoI is translated to a wrapper qoi_request ONLY if the spec's qoi
object carries machine-readable {field, operation, component?} keys that the
substrate contract can extract (operation/component vocabularies read from
the selected substrate's QoI-vocabulary record, tools/qoi_vocab — for cavity
its members ARE the wrapper's own objects, single source of truth);
otherwise every run executes WITHOUT a qoi_request and records an honest
qoi_error. Whether the named field actually exists in the case is the
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
from tools.substrate_dispatch import adapter_for
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


def _payload_run_entry(summary: dict, qoi_error_fallback: str | None) -> dict:
    """Conclusions only: {converged, qoi_value | qoi_error, wall_clock_s}."""
    entry = {
        "converged": bool(summary.get("converged")),
        "wall_clock_s": summary.get("runtime", {}).get("wall_clock_s"),
    }
    if "qoi" in summary:
        entry["qoi_value"] = summary["qoi"]["value"]
    elif "qoi_error" in summary:
        entry["qoi_error"] = summary["qoi_error"]
    elif qoi_error_fallback is not None:
        entry["qoi_error"] = qoi_error_fallback
    return entry


def run(baton: Baton) -> Baton:
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
    adapter = adapter_for(substrate_id)
    vocab = vocab_for(substrate_id)
    mini_runs = spec["mini_experiment"]["runs"]
    parameter_roles = extract_parameter_roles(spec.get("parameters"))
    qoi_name = spec.get("qoi", {}).get("name") if isinstance(spec.get("qoi"), dict) else None
    qoi_request, refusal = translate_qoi(spec.get("qoi"), vocab)
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
        case_name = f"{baton.run_id}_run{index}"
        try:
            # the selected substrate's adapter: for cavity, build_case + the
            # identical wrapper call this loop always made (D.4 dispatch)
            summary = adapter(
                substrate_id, params, case_name, parameter_roles, qoi_request
            )
        except CaseSynthesisError as exc:
            halt_reason = f"run {index} of {len(mini_runs)}: {exc}"
            _log_line(baton.run_id, f"STAGE4 halted_synthesis at {halt_reason}")
            break
        evidence_runs.append(
            {
                "run_index": index,
                "case": case_name,
                "params": params,
                "summary": summary,
            }
        )
        payload_runs.append(_payload_run_entry(summary, qoi_error_fallback))
        _log_line(
            baton.run_id,
            f"STAGE4 run {index}/{len(mini_runs)} case={case_name} "
            f"status={summary.get('status')} converged={summary.get('converged')} "
            f"qoi={summary.get('qoi', {}).get('value', 'n/a')}",
        )

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
