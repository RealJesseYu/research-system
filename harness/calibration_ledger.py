"""harness/calibration_ledger.py — R-CAL-3: the CALIBRATION ledger.

A SEPARATE append-only JSONL record for calibration-battery and probe gate
verdicts. It is DISTINCT from and NEVER pooled with the production fidelity
ledger (memory/fidelity_ledger.jsonl):

  * Physically separate file, in harness/ (evidence-class, like runs/), NOT in
    memory/ where the production decision ledgers live. A calibration/probe
    verdict is a TEST MEASUREMENT against a planted answer key, not a real
    experiment's decision — pooling the two populations is exactly what let the
    tonight 13/5/0 trust/refine/defer mix be misread as a "conservative gate"
    (R6, now REJECTED). Keeping the populations in different files makes that
    pooling impossible by construction.
  * This module imports NOTHING project-local (leaf module, like cost_meter /
    ledgers): any layer can import it without inverting layer order.
  * It writes ONLY to CALIBRATION_LEDGER_PATH. It has no handle to the fidelity
    or override ledger paths — it cannot write there even by mistake. A test
    asserts the path is neither production ledger.

Each entry is one gate verdict (calibration battery case OR probe repeat):
  {source, batch_id, substrate_id, case_id, cell, repeat, expected_class,
   acceptable_labels, raw_verdict, routed_outcome, hook_fired, passed,
   rationale, timestamp}
`cell`/`repeat` are null for battery cases (one verdict per case) and set for
probe repeats (P-0..P-C x repeat index).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CALIBRATION_LEDGER_PATH = Path(__file__).resolve().parent / "calibration_ledger.jsonl"

# Defensive backstop only — callers pass an already-short rationale.
RATIONALE_CAP = 300


def _cap(text: Any) -> str:
    s = str(text).strip()
    if len(s) > RATIONALE_CAP:
        s = s[:RATIONALE_CAP].rstrip() + "…"
    return s


def append_entry(
    *,
    source: str,
    batch_id: Optional[str],
    substrate_id: str,
    case_id: str,
    expected_class: str,
    acceptable_labels: list,
    raw_verdict: str,
    routed_outcome: str,
    hook_fired: bool,
    passed: bool,
    rationale: str = "",
    cell: Optional[str] = None,
    repeat: Optional[int] = None,
    path: Optional[Path] = None,
) -> dict:
    """Append one calibration/probe gate verdict. Returns the entry written."""
    if source not in ("battery", "probe"):
        raise ValueError(f"source must be 'battery' or 'probe', got {source!r}")
    entry = {
        "source": source,
        "batch_id": batch_id,
        "substrate_id": substrate_id,
        "case_id": case_id,
        "cell": cell,
        "repeat": repeat,
        "expected_class": expected_class,
        "acceptable_labels": list(acceptable_labels),
        "raw_verdict": raw_verdict,
        "routed_outcome": routed_outcome,
        "hook_fired": bool(hook_fired),
        "passed": bool(passed),
        "rationale": _cap(rationale),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    target = Path(path) if path is not None else CALIBRATION_LEDGER_PATH
    with open(target, "a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def count_entries(path: Optional[Path] = None) -> int:
    """Count entries (non-empty lines); 0 if absent."""
    target = Path(path) if path is not None else CALIBRATION_LEDGER_PATH
    if not target.exists():
        return 0
    with open(target) as f:
        return sum(1 for line in f if line.strip())


def read_all(path: Optional[Path] = None) -> list:
    """Read every entry back as a list of dicts (test/report read-side)."""
    target = Path(path) if path is not None else CALIBRATION_LEDGER_PATH
    if not target.exists():
        return []
    out = []
    with open(target) as f:
        for line in f:
            if line.strip():
                out.append(json.loads(line))
    return out


def seed_from_battery_report(report_path: Path, path: Optional[Path] = None) -> int:
    """Append every gate-case verdict from a calibration-battery report JSON.

    IDEMPOTENT per (source='battery', batch_id, case_id): a batch already
    present is skipped, so re-running the seeder never double-writes. Returns the
    number of entries newly appended. Wrapper-behavior cases are NOT recorded —
    they carry no gate verdict.
    """
    report = json.loads(Path(report_path).read_text())
    batch_id = report.get("batch_id")
    substrate_id = report.get("substrate_id")
    existing = {
        (e["batch_id"], e["case_id"])
        for e in read_all(path)
        if e.get("source") == "battery"
    }
    appended = 0
    for c in report["gate"]["cases"]:
        key = (batch_id, c["case_id"])
        if key in existing:
            continue
        append_entry(
            source="battery",
            batch_id=batch_id,
            substrate_id=substrate_id,
            case_id=c["case_id"],
            expected_class=c["expected_class"],
            acceptable_labels=c["acceptable_labels"],
            raw_verdict=c["raw_verdict"],
            routed_outcome=c["routed_outcome"],
            hook_fired=c["hook_fired"],
            passed=c["passed"],
            rationale=c.get("rationale", ""),
            path=path,
        )
        appended += 1
    return appended
