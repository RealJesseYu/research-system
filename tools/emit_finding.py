"""emit_finding.py — persist a producer the MOMENT it is named (T0.2).

THE FAILURE THIS EXISTS FOR, re-derived from `studies/study-20260730T034915Z/`
rather than from its write-up:

    m15  34 findings, 0 with an artifact, 0 verified
    m16  26 findings, 0 with an artifact, 0 verified

Both moves did the expensive work, computed every number for real, and died
before writing a single producer file. m15's own `blocked_on` names the nine
files it never emitted; its workspace contains `make_producers.py`, the script
written to emit them all at the end, never run. m16's says it plainly: *"the
budget ran out ... before the producer files were written."*

**This is not a shape failure.** `free_experimenter.SYSTEM_PROMPT` already
teaches ONE SCALAR, ONE FILE, and m15 planned exactly that shape — as ONE batch,
at the end. The gap is WHEN, not HOW, and the batch is the whole defect: a batch
of N producers is one all-or-nothing event, so a move cut off anywhere before it
loses all N. `emit()` makes the unit of loss ONE number instead of all of them.

WHY A PROMPT SENTENCE CANNOT CLOSE IT. This project has twice watched a
requested-but-unenforced structure simply not happen (the paper skeleton, which
needed `study_lint.py`; units, which is still only asked). Worse, the sentence is
already there — `WRITE EACH ONE AS YOU GO` — and m15/m16 ran with it. What was
missing was a REASON to pay the cost now rather than later, and that reason is
mechanical: what `emit()` writes is picked up by
`stages/free_experimenter.py::_merge_emitted` whether or not the agent survives
to mention it in its final JSON. Emitting early is the only way a number is safe.

WHY NOT THE WIND-UP MESSAGE (`model_call._WIND_UP_MESSAGE`), the one moment the
agent is guaranteed to be listening: **because the same mechanism that sends it
denies the Write that would create the file.** `_wrap_can_use_tool_with_allowance`
and `_wrap_hook_with_allowance` deny EVERY tool call once the tracker winds up,
and m16's session transcript shows the proof — a denied `Write` at 09:56:08Z,
carrying that exact message, immediately before its final JSON
(docs/finding_m16_stopping_mechanism.md). Asking for producers there would ask
for something the harness has just forbidden. The wind-up message is amended for
what it CAN do without a tool call: name a file already on disk.

WHAT IT DOES. `emit("m_b_sn.py", "b_sn")`:

1. runs that workspace file through the SAME sandbox the verification wall
   re-runs artifacts in (`tools.run_python_experiment`, --network=none, same
   ceilings) and reads `metrics["b_sn"]` — so the check is not a smoke test that
   resembles the wall, it IS the wall's re-run path;
2. on success appends ONE line to `emitted_findings.jsonl` in the workspace,
   already shaped as a finding with its `artifact` filled in;
3. on failure appends NOTHING and returns the sandbox's own diagnostics, so a
   producer that needs the network, imports a missing library, or never sets its
   metric is discovered NOW — while there is still budget to fix it — instead of
   at the wall, or never.

The value of record is the SANDBOX's, never the caller's. A `value=` argument, if
given, is only cross-checked; a disagreement is recorded as a note and the file's
number wins. Nothing here can manufacture a verified number: the artifact is a
real file that really recomputed, and the wall re-runs it again independently.

ADDITIVE, ABSOLUTELY. Nothing calls this; the agent may ignore it entirely. A run
that never calls it writes no `emitted_findings.jsonl`, and every downstream path
behaves exactly as it did before this file existed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

#: The workspace-local emission channel. Read back by
#: stages/free_experimenter.py::_read_emitted after the call returns — including
#: after a cut-off or a crash, which is the entire point.
EMITTED_FILENAME = "emitted_findings.jsonl"

#: A line longer than this is refused rather than written: the channel is read
#: back with json.loads per line, and one enormous line is one unreadable line.
MAX_RECORD_BYTES = 64 * 1024


class EmitError(ValueError):
    """The emission could not be made. Raised only for a caller mistake that no
    amount of re-running fixes (no quantity name, a path outside the workspace).
    A producer that simply did not work is NOT an error — it comes back as a
    result with `emitted: False` and the sandbox's diagnostics, because that is
    information the agent should act on, not an exception it must catch."""


def _workspace(explicit) -> Path:
    return Path(explicit).resolve() if explicit else Path(os.getcwd()).resolve()


def _resolve_in_workspace(file: str, workspace: Path) -> Path:
    """The producer must live in THIS run's workspace or it is not this run's
    evidence — the same containment rule `_finding_artifact` applies, applied
    here so the failure lands at emit time with a name, instead of silently
    becoming `no_artifact` at the wall."""
    resolved = (workspace / str(file)).resolve()
    if not resolved.is_relative_to(workspace):
        raise EmitError(
            f"producer file {file!r} resolves outside the run workspace "
            f"({workspace}) — an artifact must be a file this run owns")
    return resolved


def emit(file: str,
         quantity: str,
         *,
         label: Optional[str] = None,
         units: Optional[str] = None,
         value=None,
         tolerance: Optional[float] = None,
         reproduce: Optional[str] = None,
         profile: Optional[str] = None,
         compares: Optional[list] = None,
         workspace=None,
         runner=None) -> dict:
    """Run `file` in the verification sandbox, and if it produces
    `metrics[quantity]`, persist that finding immediately.

    Returns a plain dict — never raises for a producer that failed:

        {"emitted": True,  "quantity": ..., "value": <the file's number>,
         "file": ..., "note": <str or None>}
        {"emitted": False, "quantity": ..., "value": None,
         "error": "<why, from the sandbox itself>"}

    `runner` is injected by tests; production uses
    tools.run_python_experiment.run_python_experiment, the same callable the
    wall uses.
    """
    quantity = str(quantity or "").strip()
    if not quantity:
        raise EmitError("emit() needs a 'quantity' — the metrics key the "
                        "producer sets, and the name this value registers under")
    ws = _workspace(workspace)
    path = _resolve_in_workspace(file, ws)
    if not path.is_file():
        return {"emitted": False, "quantity": quantity, "value": None,
                "error": f"no such producer file {file!r} in this workspace — "
                         "write the file first, then emit it"}
    try:
        source = path.read_text()
    except OSError as e:
        return {"emitted": False, "quantity": quantity, "value": None,
                "error": f"could not read {file!r}: {e}"}

    summary = _run(source, quantity, profile, runner)
    if not summary.get("valid"):
        return {
            "emitted": False, "quantity": quantity, "value": None,
            "error": (
                f"{file!r} did not produce metrics[{quantity!r}] in the "
                f"verification sandbox: {summary.get('diagnostics')}. Nothing "
                "was emitted — fix the file and emit again. (The sandbox has NO "
                "network and a bounded time/memory budget, so a producer that "
                "downloads or reloads a large input must embed or cache the "
                "small slice it needs.)"),
        }

    produced = summary.get("qoi")
    note = None
    if value is not None and _disagrees(value, produced):
        note = (f"caller reported {value!r}; the producer computed {produced!r} "
                "and the producer is the artifact of record")

    record = {
        "label": label or f"{quantity} (emitted from {path.name})",
        "value": produced,
        "verified": True,
        "reproduce": reproduce or f"python3 {path.name} in this run's workspace",
        "artifact": {"file": path.name, "quantity": quantity},
        "quantity": quantity,
        "emitted": True,
        "emitted_at": datetime.now(timezone.utc).isoformat(),
    }
    if units is not None:
        record["units"] = units
    if tolerance is not None:
        record["tolerance"] = tolerance
    if compares is not None:
        record["compares"] = compares
    if profile is not None:
        record["artifact"]["profile"] = profile
    if note:
        record["emit_note"] = note

    _append(ws / EMITTED_FILENAME, record)
    return {"emitted": True, "quantity": quantity, "value": produced,
            "file": path.name, "note": note}


def _run(source: str, quantity: str, profile, runner) -> dict:
    """One sandbox execution, through the SAME entry point the wall uses. Any
    exception becomes an invalid summary: emit() reports, it never crashes the
    agent's turn."""
    if runner is None:
        from tools.run_python_experiment import run_python_experiment as runner
    spec = {"code": source, "quantity": quantity}
    if profile is not None:
        spec["profile"] = profile
    try:
        out = runner(spec)
    except Exception as e:  # noqa: BLE001
        return {"valid": False, "diagnostics": f"{type(e).__name__}: {e}"}
    return out if isinstance(out, dict) else {
        "valid": False, "diagnostics": "the sandbox returned no summary"}


def _disagrees(a, b) -> bool:
    """Cross-check only, and deliberately loose: this exists to catch a
    transcription slip, not to adjudicate — the wall does that."""
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return str(a) != str(b)
    scale = max(abs(fa), abs(fb))
    return abs(fa - fb) > (1e-9 if scale == 0 else 1e-6 * scale)


def _append(path: Path, record: dict) -> None:
    line = json.dumps(record)
    if len(line.encode()) > MAX_RECORD_BYTES:
        raise EmitError(
            f"this emission is {len(line.encode())} bytes, over the "
            f"{MAX_RECORD_BYTES}-byte line limit — a finding carries a scalar "
            "and a short label, not a payload")
    with open(path, "a") as fh:
        fh.write(line + "\n")
        fh.flush()


def read_emitted(workspace) -> list:
    """Every well-formed record in a workspace's emission channel, in order.

    TOLERATES A TORN LINE, and counts nothing on it — the same discipline as
    `journal._read_entries`. A move killed mid-write leaves a partial last line,
    and that line must not take down the fifteen good ones above it: losing the
    record to a crash is the exact failure this whole mechanism exists to stop."""
    ws = _workspace(workspace)
    path = ws / EMITTED_FILENAME
    if not path.is_file():
        return []
    out = []
    try:
        text = path.read_text()
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("quantity"):
            out.append(rec)
    return out
