"""
chain_runner.py — v1 chained experiments (Steps 31/32).

A CHAIN is ONE experiment naming TWO ordered nodes. Each node is a
(substrate, sub-spec) pair. Node A routes, executes and receives a verdict;
node B does the same. The CHAIN verdict is the WEAKEST of the two on the
ordering defer < refine < trust — one reduction, computed before any single
verdict is written anywhere.

WHAT v1 DELIBERATELY IS NOT
---------------------------
NO data flows A -> B. A prior spike established that the wrappers emit only a
small scalar summary — there is nothing worth passing — so v1 needs no
inter-node channel, no artifact store, and no baton handle for data (R2,
owner-delegated). Data-passing chains are v2 and are explicitly out of scope.

WHY THE BATON DOES NOT CHANGE
-----------------------------
The two nodes are INDEPENDENT and both are fully specified up front, so
nothing about node A has to survive into node B's execution. The chain is
therefore the EXPERIMENT INPUT, not baton cargo: it lives outside the closed
key sets in `schemas.py` (POST_GATE1_KEYS..POST_STAGE5_KEYS, enforced by
`_check_exact_keys`), and each node's sub-spec is resolved to an ORDINARY
single-node stage-2 spec at run time. `schemas.py` is untouched by this
build, and so is every stage on the single-node path — a plain single-node
run is byte-identical to the era.

R-B-1 AND CHAINS (R1, owner-delegated)
--------------------------------------
R-B-1's loud stop refuses AMBIGUITY — selection cannot tell WHICH single
substrate a spec means. It does not refuse deliberate MULTIPLICITY. A chain
node NAMES its substrate, so there is no ambiguity to resolve and the L2 tie
-break is never consulted for it. That exemption is narrow ON PURPOSE: a
named node is still checked for routability, for wiring, and for
serve-ability, and each of those still stops loudly. An ambiguous SINGLE
spec — a node that names no substrate — still falls through to
`select_substrate` and still hits R-B-1's stop naming its candidates.

Records: per-node evidence goes to runs/<run_id>/chain/node_<i>.json and the
reduction to runs/<run_id>/chain/chain.json — OUTSIDE the baton, the same
pattern the campaign controller uses for runs/<run_id>/campaign/.

No model call is made anywhere in this module. Verdicts arrive through the
caller's `verdict_fn`, which has NO default: this module will not invent,
guess, or stub a verdict, and there is no cavity fallback on any path.
"""

from __future__ import annotations

import json
from pathlib import Path

from stages.stage2_spec import validate_spec
from stages.stage4_case_builder import CaseSynthesisError
from stages.stage4_simulation import extract_parameter_roles, run_one_point
from tools import substrate_registry as registry
from tools.qoi_vocab import vocab_for
from tools.substrate_dispatch import (
    adapter_for,
    qoi_translation_for,
    regime_content_inputs,
    run_entry_constructor_for,
)
from tools.substrate_selection import (
    declared_parameter_names,
    select_substrate,
    signature_for,
)

# v1 is an ORDERED PAIR. Not "at least two", not "N" — the aggregate rule and
# the acceptance evidence are both written for exactly two nodes.
CHAIN_NODE_COUNT = 2

# The verdict lattice. Lower is weaker; the chain takes the minimum.
VERDICT_STRENGTH = {"defer": 0, "refine": 1, "trust": 2}

HALTED = "halted_synthesis"


# --------------------------------------------------------------------------
# P1 — SPEC
# --------------------------------------------------------------------------

def validate_chain_structure(chain) -> list[str]:
    """The SHAPE of a chain input — no routing, no substrate resolution.

    Kept separate from routing on purpose. A malformed chain is a broken
    invariant and stops the caller loudly; an unroutable NODE is an
    experiment outcome and halts the chain honestly (P5). Mixing the two
    would turn a routing failure into a crash.
    """
    errors: list[str] = []
    if not isinstance(chain, dict):
        return ["the chain must be a single JSON object."]

    nodes = chain.get("nodes")
    if not isinstance(nodes, list):
        return ["chain is missing a 'nodes' list of its ordered nodes."]
    if len(nodes) != CHAIN_NODE_COUNT:
        errors.append(
            f"a v1 chain names exactly {CHAIN_NODE_COUNT} ordered nodes; got "
            f"{len(nodes)}. Chains of other lengths are not built."
        )

    for index, node in enumerate(nodes):
        label = f"node {index}"
        if not isinstance(node, dict):
            errors.append(f"{label} must be an object of {{substrate_id, spec}}.")
            continue
        sid = node.get("substrate_id")
        if sid is not None and not (isinstance(sid, str) and sid.strip()):
            errors.append(
                f"{label} substrate_id must be a non-empty string naming the "
                f"instrument this node runs on (or be absent, which routes the "
                f"node structurally); got {sid!r}."
            )
        if not isinstance(node.get("spec"), dict):
            errors.append(f"{label} must carry a 'spec' object — its sub-spec.")

    return errors


def validate_chain(chain) -> list[str]:
    """Full pre-flight: structure, then per-node routing and sub-spec validity.

    Each node's sub-spec is checked by the EXISTING `validate_spec`, against
    the QoI vocabulary of that node's own routed substrate — this module adds
    no second spec grammar and relaxes nothing. A single-node spec's own
    validation is therefore reached through the identical call the pipeline
    makes, which is why the era holds byte-identically.

    This is a REPORTING function for callers who want to check a chain before
    spending anything; `run_chain` does not use it for routing, because a
    routing failure must halt honestly rather than read as a bad input.
    """
    errors = validate_chain_structure(chain)
    if errors:
        return errors

    for index, node in enumerate(chain["nodes"]):
        label = f"node {index}"
        try:
            resolved = route_node(node)
        except LookupError as exc:
            errors.append(f"{label} cannot be routed: {exc}")
            continue
        for message in validate_spec(
            node["spec"], node["spec"].get("hypothesis_id"), vocab_for(resolved)
        ):
            errors.append(f"{label} spec: {message}")

    return errors


# --------------------------------------------------------------------------
# P2 — ROUTE
# --------------------------------------------------------------------------

def route_node(node) -> str:
    """Route ONE node to exactly one substrate.

    A node that NAMES its substrate is unambiguous, so R-B-1's L2 tie-break
    is not consulted (R1). Everything else that protects routing still
    applies to it and still raises LookupError:

      * the named id must be ROUTABLE (an enrolled-but-parked id stops here);
      * it must be WIRED — contract AND signature both probed, as
        `select_substrate` probes them;
      * it must SERVE the sub-spec — the spec's declared parameter names must
        sit inside the substrate's signature.

    A node that names NO substrate falls through to `select_substrate`, which
    still fires R-B-1's loud stop when the spec is genuinely ambiguous.
    """
    if not isinstance(node, dict):
        raise LookupError("a chain node must be an object of {substrate_id, spec}.")
    spec = node.get("spec")
    named = node.get("substrate_id")

    if not (isinstance(named, str) and named.strip()):
        # No name: this is an ordinary single-node routing question. R-B-1
        # applies in full, including its loud stop.
        return select_substrate(spec)

    routable = registry.routable_ids()
    if named not in routable:
        raise LookupError(
            f"chain node names substrate {named!r}, which is not routable — "
            f"the routable set is {', '.join(routable)}. A named node is exempt "
            f"from R-B-1's ambiguity stop (R1), NOT from routability: name a "
            f"routable instrument, or promote this one under a recorded ruling; "
            f"stopping before routing. There is no fallback substrate."
        )
    # Wiring probe — the same two loud lookups select_substrate performs.
    registry.contract_for(named)   # LookupError: routable without a contract
    signature = signature_for(named)  # LookupError: routable without a signature

    declared = declared_parameter_names(spec)
    unserved = sorted(declared - signature)
    if unserved:
        raise LookupError(
            f"chain node names substrate {named!r}, which cannot serve its "
            f"sub-spec: the declared parameters {unserved} are outside that "
            f"substrate's signature. Naming an instrument does not make it able "
            f"to run the spec — author the sub-spec against {named!r}'s "
            f"vocabulary, or name an instrument that covers it; stopping before "
            f"routing. Selection must NOT fall back to cavity (or any other "
            f"substrate)."
        )
    return named


# --------------------------------------------------------------------------
# P3 — EXECUTE
# --------------------------------------------------------------------------

def _hoisted_dispatch(substrate_id: str, spec: dict) -> dict:
    """Resolve everything `run_one_point` needs, ONCE per node — the same
    hoisting stage 4 does before its per-point loop. An unwired or unknown id
    raises here, before anything executes."""
    vocab = vocab_for(substrate_id)
    translate = qoi_translation_for(substrate_id)
    qoi_request, refusal = translate(spec.get("qoi"), vocab)
    qoi_name = spec.get("qoi", {}).get("name") if isinstance(spec.get("qoi"), dict) else None
    qoi_error_fallback = (
        None
        if qoi_request is not None
        else f"QoI {qoi_name!r} not extractable by contract: {refusal}"
    )
    return {
        "substrate_id": substrate_id,
        "adapter": adapter_for(substrate_id),
        "entry_constructor": run_entry_constructor_for(substrate_id),
        "parameter_roles": extract_parameter_roles(spec.get("parameters")),
        "qoi_request": qoi_request,
        "qoi_error_fallback": qoi_error_fallback,
        "regime_inputs": regime_content_inputs(spec, substrate_id),
    }


def execute_node(run_id: str, index: int, node: dict, substrate_id: str,
                 verdict: dict) -> dict:
    """Route-resolved execution of ONE node. Returns its record.

    Verdict-gated exactly as stage 4 gates: a defer executes nothing. A
    CaseSynthesisError inside any point is an honest outcome — the node
    records halted_synthesis and stops — never a raw crash and never a
    fabricated result.
    """
    label = verdict["label"]
    spec = node["spec"]
    record = {
        "node_index": index,
        "substrate_id": substrate_id,
        "verdict": verdict,
    }

    if label == "defer":
        record["status"] = "skipped_defer"
        record["reason"] = 'fidelity verdict label is "defer" — nothing was executed.'
        record["runs"] = []
        return record
    if label not in ("trust", "refine"):
        raise ValueError(
            f"chain_runner: unknown fidelity verdict label {label!r} for node "
            f"{index} — expected trust, refine, or defer"
        )

    dispatch = _hoisted_dispatch(substrate_id, spec)
    regime_inputs = dispatch.pop("regime_inputs")
    points = spec["mini_experiment"]["runs"]

    evidence_runs: list[dict] = []
    payload_runs: list[dict] = []
    halt_reason: str | None = None
    for point_index, params in enumerate(points, start=1):
        evidence_run, payload_run, halt = run_one_point(
            run_id,
            point_index,
            len(points),
            {**regime_inputs, **params},
            case_name=f"{run_id}_chain{index}_run{point_index}",
            **dispatch,
        )
        if halt is not None:
            halt_reason = halt
            break
        evidence_runs.append(evidence_run)
        payload_runs.append(payload_run)

    record["status"] = HALTED if halt_reason else "executed"
    record["runs"] = payload_runs
    record["evidence"] = evidence_runs
    record["qoi_request"] = dispatch["qoi_request"]
    if dispatch["qoi_error_fallback"] is not None:
        record["qoi_translation_error"] = dispatch["qoi_error_fallback"]
    if halt_reason:
        record["reason"] = halt_reason
    return record


# --------------------------------------------------------------------------
# P4 — AGGREGATE
# --------------------------------------------------------------------------

def chain_verdict(node_verdicts) -> dict:
    """The chain's verdict: the WEAKEST node verdict on defer < refine < trust.

    Pure and total over valid labels. Returns the reduction together with the
    per-node labels and which node was weakest, so the record shows WHY the
    chain landed where it did rather than asserting it.
    """
    labels = [v["label"] for v in node_verdicts]
    unknown = [lab for lab in labels if lab not in VERDICT_STRENGTH]
    if unknown:
        raise ValueError(
            f"chain_runner: cannot reduce unknown verdict label(s) {unknown} — "
            f"expected each of {sorted(VERDICT_STRENGTH)}"
        )
    weakest_index = min(range(len(labels)), key=lambda i: VERDICT_STRENGTH[labels[i]])
    return {
        "label": labels[weakest_index],
        "node_labels": labels,
        "weakest_node": weakest_index,
        "rule": "weakest link: defer < refine < trust",
    }


# --------------------------------------------------------------------------
# The chain
# --------------------------------------------------------------------------

def run_chain(run_id: str, chain: dict, *, verdict_fn) -> dict:
    """Route, execute and reduce a two-node chain. Returns the chain record.

    `verdict_fn(index, node, substrate_id) -> verdict` supplies each node's
    fidelity verdict. It has NO default ON PURPOSE: a verdict is a judgment,
    and this module will not manufacture one. No model call happens here.

    Fail-loud policy — the exception TYPE decides. A routing failure
    (LookupError) or a case-synthesis failure (CaseSynthesisError) is an
    HONEST HALT: the chain stops, records halted_synthesis with the reason,
    and runs nothing further. Every other exception propagates uncaught,
    because it is a broken invariant rather than an experiment outcome.
    """
    errors = validate_chain_structure(chain)
    if errors:
        raise ValueError(
            "chain_runner: the chain is malformed — " + "; ".join(errors)
        )

    run_dir = Path("runs") / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    chain_dir = run_dir / "chain"
    chain_dir.mkdir(parents=True, exist_ok=True)

    nodes = chain["nodes"]
    records: list[dict] = []
    halt_reason: str | None = None

    for index, node in enumerate(nodes):
        try:
            substrate_id = route_node(node)
            # The sub-spec is validated against the ROUTED substrate's own
            # vocabulary before anything executes. A sub-spec that does not
            # validate is a broken invariant, not an experiment outcome — it
            # raises loudly (never re-asked, never repaired here).
            spec_errors = validate_spec(
                node["spec"], node["spec"].get("hypothesis_id"),
                vocab_for(substrate_id),
            )
            if spec_errors:
                raise ValueError(
                    f"chain_runner: node {index} sub-spec does not validate "
                    f"against {substrate_id!r} — " + "; ".join(spec_errors)
                )
            record = execute_node(run_id, index, node, substrate_id,
                                  verdict_fn(index, node, substrate_id))
        except (LookupError, CaseSynthesisError) as exc:
            record = {
                "node_index": index,
                "substrate_id": node.get("substrate_id"),
                "status": HALTED,
                "reason": f"node {index}: {exc}",
                "runs": [],
            }
            halt_reason = record["reason"]
        records.append(record)
        (chain_dir / f"node_{index}.json").write_text(json.dumps(record, indent=2))
        if record["status"] == HALTED:
            halt_reason = record.get("reason")
            break

    if halt_reason is not None:
        chain_record = {
            "run_id": run_id,
            "status": HALTED,
            "reason": halt_reason,
            "nodes_attempted": len(records),
            "nodes": records,
        }
    else:
        chain_record = {
            "run_id": run_id,
            "status": "executed",
            "chain_verdict": chain_verdict([r["verdict"] for r in records]),
            "nodes_attempted": len(records),
            "nodes": records,
        }
    (chain_dir / "chain.json").write_text(json.dumps(chain_record, indent=2))
    return chain_record
