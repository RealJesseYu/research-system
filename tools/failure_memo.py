"""
failure_memo.py — code-authored failure memos for non-clean run terminations.

write_failure_memo(run_dir) composes runs/<run_id>/failure_memo.txt purely
from the run's on-disk baton snapshots and stage evidence. NO model call ever
writes a memo (memo-on-failure is deterministic record-keeping). The file name
is chosen to match the R-WIN-1 reader's glob exactly — read_recent_failure_memo
in stages/generation_strategies.py globs runs/<run_id>/*failure_memo*.txt, and
"failure_memo.txt" satisfies that pattern — so a memo written here is the file
a later retried ideation pass will pick up when the feasibility nudge is on.

The memo is byte-stable: every field comes from disk, nothing from the clock,
and iteration order over snapshots is a deterministic filename sort. The
producer never raises — any failure returns None and writes nothing, so a memo
write can never mask or replace the original failure path that called it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

MEMO_FILENAME = "failure_memo.txt"
_RATIONALE_CAP = 240


def _load_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _payload(path: Path) -> dict:
    data = _load_json(path)
    payload = data.get("payload") if isinstance(data, dict) else None
    return payload if isinstance(payload, dict) else {}


def _pass_number(path: Path) -> int:
    m = re.search(r"_pass(\d+)\.json$", path.name)
    return int(m.group(1)) if m else 1


def _one_line(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()[:_RATIONALE_CAP]


def _first_payload_with(run_dir: Path, key: str) -> Any:
    """The value of `key` from the first (deterministic name-sorted) stage
    snapshot whose payload carries it — or None."""
    for path in sorted(run_dir.glob("baton_after_stage_*.json")):
        value = _payload(path).get(key)
        if value is not None:
            return value
    return None


def _build_memo_text(run_dir: Path) -> str:
    run_id = run_dir.name
    stage3 = sorted(run_dir.glob("baton_after_stage_3*.json"), key=lambda p: (_pass_number(p), p.name))
    stage5 = sorted(run_dir.glob("baton_after_stage_5*.json"), key=lambda p: (_pass_number(p), p.name))
    stage4 = sorted(run_dir.glob("baton_after_stage_4*.json"), key=lambda p: (_pass_number(p), p.name))
    all_stage = sorted(run_dir.glob("baton_after_stage_*.json"), key=lambda p: (_pass_number(p), p.name))

    domain = _first_payload_with(run_dir, "domain")
    chosen = _first_payload_with(run_dir, "chosen_hypothesis") or {}
    spec = _first_payload_with(run_dir, "experiment_spec") or {}
    qoi = spec.get("qoi") if isinstance(spec, dict) else {}
    qoi_name = qoi.get("name") if isinstance(qoi, dict) else None

    lines: list[str] = []
    lines.append(f"FAILURE MEMO — run {run_id}")
    lines.append(f"DOMAIN / ASK: {_one_line(domain) if domain else '(unknown)'}")
    if isinstance(chosen, dict) and chosen.get("id"):
        lines.append(
            f"CHOSEN HYPOTHESIS: {chosen.get('id')} — {_one_line(chosen.get('statement'))}"
        )
    else:
        lines.append("CHOSEN HYPOTHESIS: (none reached gate 1)")
    if qoi_name:
        lines.append(f"REQUESTED QoI: {_one_line(qoi_name)}")

    # Fidelity verdicts, one line per pass.
    lines.append("")
    lines.append("FIDELITY VERDICTS (by pass):")
    verdict_classes: list[str] = []
    if stage3:
        for path in stage3:
            v = _payload(path).get("fidelity_verdict") or {}
            label = v.get("label") or "(none)"
            verdict_classes.append(label)
            lines.append(
                f"  pass {_pass_number(path)}: {label} — {_one_line(v.get('rationale')) or '(no rationale)'}"
            )
    else:
        lines.append("  (no fidelity verdict on disk)")

    # Gate-5 iterate decisions, one line per pass.
    lines.append("")
    lines.append("GATE-5 DECISIONS (by pass):")
    if stage5:
        for path in stage5:
            decision = _payload(path).get("iterate_decision") or "(none)"
            lines.append(f"  pass {_pass_number(path)}: {decision}")
    else:
        lines.append("  (stage 5 not reached)")

    # Execution — did any solver run?
    exec_res = {}
    if stage4:
        exec_res = _payload(stage4[-1]).get("execution_results") or {}
    elif stage5:
        exec_res = _payload(stage5[-1]).get("execution_results") or {}
    status = exec_res.get("status") if isinstance(exec_res, dict) else None
    runs = exec_res.get("runs") if isinstance(exec_res, dict) else None
    n_executed = len(runs) if isinstance(runs, list) else 0
    lines.append("")
    lines.append(f"EXECUTION: {status or '(none)'} — {n_executed} solver run(s) executed")

    # QoI / extraction blockers named by defers and by any qoi_error.
    blockers: list[str] = []
    for path in stage3:
        v = _payload(path).get("fidelity_verdict") or {}
        if v.get("label") == "defer":
            ri = _one_line(v.get("right_instrument"))
            blockers.append(
                f"defer (pass {_pass_number(path)}): "
                + (f"QoI '{_one_line(qoi_name)}' " if qoi_name else "")
                + f"unservable — {_one_line(v.get('rationale'))}"
                + (f" [right instrument: {ri}]" if ri else "")
            )
    if isinstance(runs, list):
        for i, r in enumerate(runs, start=1):
            if isinstance(r, dict) and r.get("qoi_error"):
                blockers.append(f"run {i} qoi_error: {_one_line(r['qoi_error'])}")
    lines.append("")
    lines.append("QoI / EXTRACTION BLOCKERS:")
    if blockers:
        lines.extend(f"  - {b}" for b in blockers)
    else:
        lines.append("  (none named)")

    # Loop-bound state, inferred from the highest pass number on disk.
    max_pass = max((_pass_number(p) for p in all_stage), default=1)
    loopbacks = max_pass - 1
    lines.append("")
    lines.append(
        f"LOOP-BOUND STATE: {loopbacks} loop-back(s) observed on disk "
        f"(highest pass = {max_pass})"
    )

    return "\n".join(lines) + "\n"


def write_failure_memo(run_dir) -> Path | None:
    """Write runs/<run_id>/failure_memo.txt from on-disk artifacts. Returns the
    path on success, None on any failure (never raises)."""
    try:
        run_dir = Path(run_dir)
        if not run_dir.is_dir():
            return None
        text = _build_memo_text(run_dir)
        path = run_dir / MEMO_FILENAME
        path.write_text(text)
        return path
    except Exception:
        return None
