"""
stage3_fidelity_gate.py — real Fidelity-Gate stage: ONE isolated Opus call
places the stage-2 experiment spec in one of three zones — trust / refine /
defer — judged against the substrate contract. Opus, per CLAUDE.md's model
roles: the fidelity call is a hard judgment.

The judgment text in SYSTEM_PROMPT is FROZEN. It is the spike's Step-6
PROMPT_V2, ported verbatim from ~/research-spike/run_fidelity_test.py (a
read-only provenance reference only — this stage never reads the spike at
runtime; the text lives here). The three zone definitions, the v2
trust-vs-refine (resolve-vs-approximate) paragraph, and the "judge only
from what you are given" guard are byte-identical to the spike's wording.
The ONLY change: the old three-line LABEL/RATIONALE/RIGHT_INSTRUMENT
output-format block and the case-fill tail were replaced by instructions
to return the JSON envelope this pipeline's schema enforcement expects —
the three field descriptions inside it are carried over word-for-word.
No new judgment language was added; the third axis (regime-assumption
certainty) is deliberately absent, per CLAUDE.md's pointers to the spike.

The reply is enforced in Python, not trusted: a shallow envelope schema,
then _validate_verdict as call_stage_model's extra_validator (label
enum-locked to trust | refine | defer; rationale and right_instrument
non-empty strings) inside the same bounded 3-attempt loop. On success the
full verdict object becomes evidence at runs/<run_id>/stage3/verdict.json,
the payload gains fidelity_verdict (no existing field is removed or
rewritten), and the single history note is written by code from
already-validated fields — never model-authored narration.
"""

from __future__ import annotations

import json
from pathlib import Path

from baton import Baton
from memory.ledgers import fidelity_append
from model_call import call_stage_model, log_stage_call
from tools import substrate_registry as registry
from tools import substrate_selection

OPUS_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You are a fidelity gate for an autonomous research system. Before any simulation runs, your job is to judge whether the proposed instrument can faithfully model the proposed experiment, and to place the experiment in exactly one of three zones:

- trust — The instrument, within its stated validity, fully models this experiment. The result can be taken as the real answer with no downstream confirmation.
- refine — The instrument is a reliable filter but not a final verdict. Its result is useful to narrow or screen, but a survivor must be confirmed by a human or a real-world test. (This does not mean "fix the experiment design.")
- defer — The instrument cannot faithfully model this experiment at all. It should not be trusted here; the experiment must be routed to a human or a real experiment.

A note on trust vs refine, since this is the distinction most easily gotten wrong: being used within a validated range is necessary but not sufficient for trust. Trust is warranted only when the instrument's in-range output effectively IS the real-world answer — because it directly reads or measures the quantity, or fully resolves the governing physics for this regime, or its specific prediction for this quantity has itself been directly validated against reality (which closes the model-to-reality gap). Refine is the right call whenever the instrument, even fully in-range, yields only an approximate or predicted estimate with a residual gap to reality that has not itself been confirmed — for example because it models physics it cannot fully resolve, because it is a learned or statistical predictor, or because it forecasts an inherently uncertain or chaotic outcome. So ask not only 'is it in-envelope?' but 'is this output the real answer, or a reliable estimate that reality could still correct?'

You will be given the instrument, its validated envelope, and the experiment's regime. Judge only from what you are given plus your own knowledge of the science. Do not assume facts you were not told.

Reply ONLY with JSON of the form {"ack_run_id": "<the run_id you were given>", "verdict": {"label": "<trust | refine | defer>", "rationale": "<one sentence: the single most decisive reason for this label>", "right_instrument": "<the instrument actually appropriate for this experiment; if the named one fits, repeat it; if none fits, write \\"none — route to human/real experiment\\">"}} — no other fields anywhere."""

SCHEMA = {"required": ["ack_run_id", "verdict"]}

ENVELOPE_FIELDS = ("ack_run_id", "verdict")
VERDICT_FIELDS = ("label", "rationale", "right_instrument")
VALID_LABELS = ("trust", "refine", "defer")


def _validate_verdict(parsed: dict) -> list[str]:
    """Deep validator handed to call_stage_model: the reply envelope must be
    exactly {ack_run_id, verdict}, and the verdict exactly {label, rationale,
    right_instrument} with label enum-locked and both strings non-empty.
    Returns plain-language error strings, empty = valid.
    """
    errors = [
        f"reply field '{key}' is not allowed — reply with exactly "
        '"ack_run_id" and "verdict", nothing else.'
        for key in parsed
        if key not in ENVELOPE_FIELDS
    ]
    verdict = parsed.get("verdict")
    if not isinstance(verdict, dict):
        errors.append(
            "verdict must be an object with label, rationale, and right_instrument."
        )
        return errors
    for key in verdict:
        if key not in VERDICT_FIELDS:
            errors.append(
                f"verdict field '{key}' is not allowed — the verdict carries exactly "
                "label, rationale, and right_instrument."
            )
    if verdict.get("label") not in VALID_LABELS:
        errors.append(
            f'verdict label must be exactly one of "trust", "refine", or "defer"; '
            f"got {verdict.get('label')!r}."
        )
    for field in ("rationale", "right_instrument"):
        value = verdict.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"verdict {field} must be a non-empty string.")
    return errors


def _contract_substrate_name(contract_text: str) -> str | None:
    """Read the substrate's name off the contract's own header line
    ("SUBSTRATE CONTRACT: <name>"). Pure function, no I/O; returns None if
    the header isn't there. Stage code stays substrate-agnostic: the name is
    data read from the contract it was handed, never hardcoded or branched
    on — it goes into the fidelity ledger, not into stage logic.
    """
    first_line = contract_text.strip().splitlines()[0] if contract_text.strip() else ""
    prefix = "SUBSTRATE CONTRACT:"
    if first_line.startswith(prefix):
        name = first_line[len(prefix):].strip()
        return name or None
    return None


def _selected_contract(spec: dict | None = None) -> tuple[str, str]:
    """R-S3-1 + D.2: the substrate this gate judges against, chosen
    STRUCTURALLY by signature-based selection (tools/substrate_selection —
    routable substrates that can serve the spec's declared parameter names,
    mature preferred, enrollment-order tie-break; sole_routable_id is retired
    from production). Returns (substrate_id, contract_text). Today the
    registry's one routable substrate is cavity_2d_cfd, so contract_text is
    byte-identical to the substrates.CAVITY_2D_CONTRACT the gate used before —
    era 862531b holds (d2 fixture-pinned). A spec of None declares no
    parameters and constrains nothing — the era proofs call this bare; run()
    always passes the real spec. A spec no routable substrate can serve, or a
    routable substrate missing its contract or signature, RAISES at selection;
    the gate never falls back to cavity. Extracted so the byte-identity proof
    exercises the exact text the model will see without spending a model call."""
    substrate_id = substrate_selection.select_substrate(spec)
    return substrate_id, registry.contract_for(substrate_id)


def _log_line(run_id: str, line: str) -> None:
    """Append one line to runs/<run_id>/log.txt (same path rule as log_stage_call)."""
    print(line)
    with open(Path("runs") / run_id / "log.txt", "a") as f:
        f.write(line + "\n")


def run(baton: Baton) -> Baton:
    _substrate_id, substrate_contract = _selected_contract(
        baton.payload["experiment_spec"]
    )
    stage_input = {
        "run_id": baton.run_id,
        "spec": baton.payload["experiment_spec"],
        "substrate_contract": substrate_contract,
    }
    data, timing = call_stage_model(
        "stage3_fidelity_gate",
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=OPUS_MODEL,
        extra_validator=_validate_verdict,
    )

    if data["ack_run_id"] != baton.run_id:
        raise RuntimeError(
            f"stage3_fidelity_gate: ack_run_id mismatch — got "
            f"{data['ack_run_id']!r}, expected {baton.run_id!r}"
        )
    _log_line(
        baton.run_id,
        f"ECHO_CHECK stage=stage3_fidelity_gate ack_run_id={data['ack_run_id']} "
        "matches run_id",
    )

    verdict = data["verdict"]
    stage_dir = Path("runs") / baton.run_id / "stage3"
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / "verdict.json").write_text(json.dumps(verdict, indent=2))

    # Step 16.6 chunk 2: observing hook — one fidelity-ledger entry per
    # rendered verdict. The rationale is already the gate's one-sentence
    # summary (summarize-at-the-source); outcome stays null until Step 21.
    # Purely observational: nothing about the returned baton changes.
    fidelity_append(
        run_id=baton.run_id,
        verdict=verdict["label"],
        substrate=_contract_substrate_name(substrate_contract),
        rationale=verdict["rationale"],
    )

    rationale = verdict["rationale"].strip()
    excerpt = rationale if len(rationale) <= 100 else rationale[:100].rstrip() + "…"
    note = f"fidelity verdict {verdict['label']}: {excerpt}"

    payload = dict(baton.payload)
    payload["fidelity_verdict"] = verdict
    baton.payload = payload
    baton.add_history("stage3_fidelity_gate", note)
    log_stage_call(baton.run_id, "stage3_fidelity_gate", timing)
    return baton
