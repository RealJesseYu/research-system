"""
desk_review.py — the virtual desk-rejection screen (owner-ruled 2026-07-20).

ONE Opus call standing where a journal editor stands: not a peer reviewer
weighing contribution, but the editor deciding whether a submission is sent
out for review at all. The owner set the bar explicitly and deliberately low
— "no desk rejections" — because that bar is checkable. An editor desk-rejects
for defects that need no subject expertise to see: conclusions with no data
behind them, citations unrelated to the subject, a method too vague to
reproduce, internal contradiction, claims exceeding the evidence.

WHY THIS IS NOT THE BARREN GATE. The barren gate (supervisor.is_barren) stops
a run BEFORE the paper exists, when the experiment measured nothing. This gate
reads a finished paper and asks whether it is publishable-shaped. They catch
different failures and both are needed: a run can produce real data and still
be written up badly.

WHAT IT DELIBERATELY DOES NOT DO. It does not judge novelty, significance, or
whether the finding is interesting — those are peer review's job, they need
the literature, and a system that reruns itself until a model calls the result
exciting would be optimizing for a model's approval rather than for truth. A
correct, dull, honestly-reported negative result MUST pass this gate. The
prompt says so in as many words.
"""

from __future__ import annotations

import json
from pathlib import Path

from model_call import call_stage_model, log_stage_call
from models import model_for  # model-tier resolver

DESK_REVIEW_MODEL = model_for("heavy")

# Bounded so a paper the reviewer keeps disliking cannot spin forever. Two
# rewrites is the same budget the lint loop gets.
MAX_DESK_REWRITES = 2

SCHEMA = {"required": ["ack_run_id", "desk_reject", "reasons", "remedy"]}

SYSTEM_PROMPT = (
    "You are the handling editor of a peer-reviewed journal performing a DESK "
    "SCREEN on a submitted manuscript. You are not the peer reviewer. Your one "
    "question is whether this manuscript is in good enough shape to send out "
    "for review, or whether it must be returned to the authors immediately.\n\n"
    "Desk-reject ONLY for defects an editor can see without subject expertise:\n"
    "  - a conclusion or claim with no data behind it in the manuscript;\n"
    "  - numbers, results, or apparatus that appear in the text but are not "
    "supported by the reported measurements;\n"
    "  - references that are not about the subject of the paper, or that are "
    "listed but never used;\n"
    "  - a method described too vaguely for another group to repeat it;\n"
    "  - internal contradiction between sections;\n"
    "  - a paper that reports only its own configuration or tooling failure "
    "and draws no scientific conclusion.\n\n"
    "DO NOT desk-reject for: an unexciting, incremental, or negative result; a "
    "narrow scope; a small number of runs; or a finding you personally doubt. "
    "A correct, dull, honestly-reported negative result PASSES this screen — "
    "honest reporting of a limitation is a virtue here, never a defect. "
    "Novelty and significance belong to peer review, not to you.\n\n"
    "Reply ONLY with JSON of the form "
    '{"ack_run_id": "<the run_id you were given>", '
    '"desk_reject": <true | false>, '
    '"reasons": ["<one specific, quotable defect>", ...], '
    '"remedy": "<rewrite | redesign | none>"} '
    "— no other fields anywhere, no prose outside the JSON, no markdown "
    "fences. reasons is [] exactly when desk_reject is false. remedy is "
    '"rewrite" when the underlying work is sound and only the manuscript is '
    'at fault, "redesign" when the experiment itself cannot support any '
    'paper, and "none" exactly when desk_reject is false.'
)


def _log(run_id: str, line: str) -> None:
    print(line)
    run_dir = Path("runs") / str(run_id)
    if run_dir.is_dir():
        with open(run_dir / "log.txt", "a") as f:
            f.write(line + "\n")


def desk_review(run_id: str, paper_markdown: str, execution_results: dict) -> dict:
    """Screen one paper. Returns {desk_reject, reasons, remedy}.

    execution_results is passed so the editor can check the manuscript's
    claims against what the run actually measured — the single most common
    desk-reject cause is a conclusion the data does not carry.

    NEVER raises. A transport or schema failure degrades to a PASS that is
    logged loudly and marked `checked: False`, because a screen that cannot
    run must not silently destroy a completed run's paper — but the run record
    must never imply the paper was screened when it was not.
    """
    stage_input = {
        "run_id": run_id,
        "manuscript_markdown": paper_markdown,
        "measurements_actually_obtained": execution_results,
    }
    try:
        data, timing = call_stage_model(
            "stage6_desk_review", SYSTEM_PROMPT, stage_input, SCHEMA,
            model=DESK_REVIEW_MODEL,
        )
        log_stage_call(run_id, "stage6_desk_review", timing)
    except Exception as e:  # noqa: BLE001 — deliberate: never kill a finished run
        _log(run_id, f"DESK_REVIEW FAILED (paper NOT screened, run proceeds): {e}")
        return {"desk_reject": False, "reasons": [], "remedy": "none",
                "checked": False}

    result = {
        "desk_reject": bool(data.get("desk_reject")),
        "reasons": list(data.get("reasons") or []),
        "remedy": data.get("remedy") or "none",
        "checked": True,
    }
    if result["desk_reject"]:
        _log(
            run_id,
            f"DESK_REVIEW REJECT (remedy={result['remedy']}): "
            + json.dumps(result["reasons"]),
        )
    else:
        _log(run_id, "DESK_REVIEW PASS — manuscript would be sent for review")
    return result
