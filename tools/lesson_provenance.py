"""
lesson_provenance.py — Phase-1 Lane-1 lesson-provenance sidecar.

The system's learned summaries (memory/journal.jsonl, kind="learned_summary")
mix two very different kinds of claim: some REST ON measured, on-disk numeric
output from an executed solver run; others are re-scope / limitation lessons
the model reasoned to WITHOUT ever measuring anything ("testing X needs an
instrument this substrate lacks"). Downstream, both look identical. This
sidecar tags each one measured|said so their provenance stops being invisible.

OUTPUT: an append-only sidecar memory/lesson_provenance.jsonl, one object per
learned summary:
    {key, provenance, source_run, basis}
  - key:        stable id of the journal entry -> "<run_id>|<hypothesis_id>|<timestamp>"
  - provenance: "measured" | "said"
  - source_run: the run id (or null)
  - basis:      one line explaining the tag

CONSERVATIVE RULE (the whole point):
  "measured" ONLY if the claim is traceable to an executed run's on-disk
  numeric artifact. Concretely, BOTH must hold:
    (1) HARD GATE: runs/<run_id>/stage4/results.json exists with
        status == "executed" AND at least one run carries a numeric
        summary.qoi.value (a solver actually produced a number).
    (2) the lesson text RESTS ON that measurement — it states an empirical
        trend/result (a trend verb such as grows/saturates/monotonic/dips/
        slope/steeper/insensitive, alongside a numeric token). A lesson from
        an executed run that is only a re-scope/limitation claim stays "said".
  Everything else defaults to "said".

The journal itself is NEVER modified (read-only). Tags are NOT wired into
retrieval or any injected memory block — that is a separately scheduled
ruling. This module never calls a model. It is a tools/ leaf: it imports
nothing project-local.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_PATH = _ROOT / "memory" / "journal.jsonl"
RUNS_ROOT = _ROOT / "runs"
PROVENANCE_PATH = _ROOT / "memory" / "lesson_provenance.jsonl"

# Empirical-result markers: a lesson that "rests on measured output" describes
# a trend/relationship in the numbers, not merely what an instrument lacks.
_TREND_TERMS = re.compile(
    r"\b(grows?|growing|saturat\w*|monoton\w*|dips?|scal\w*|slope|steeper|"
    r"insensitive|decreas\w*|increas\w*|superlinear\w*|sublinear\w*|"
    r"non-?monoton\w*|plateau\w*|dominat\w*|extremum)\b",
    re.IGNORECASE,
)
_NUMERIC_TOKEN = re.compile(r"\d")


def stable_key(entry: dict) -> str:
    """Compose a stable id for a journal entry. run_id alone is not unique
    (a run journals one learned summary per surviving hypothesis), so the key
    joins run_id, hypothesis_id, and the unique timestamp."""
    return f"{entry.get('run_id')}|{entry.get('hypothesis_id')}|{entry.get('timestamp')}"


def executed_numeric_qois(run_id: Optional[str], runs_root: Path = RUNS_ROOT) -> Optional[list[float]]:
    """The HARD GATE. Returns the list of numeric QoI values on disk for an
    EXECUTED run, or None if the run did not execute a solver / wrote no
    numeric QoI / has no results.json. Read-only."""
    if not run_id:
        return None
    results = runs_root / str(run_id) / "stage4" / "results.json"
    if not results.exists():
        return None
    try:
        data = json.loads(results.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if data.get("status") != "executed":
        return None
    vals: list[float] = []
    for run in (data.get("runs") or []):
        qoi = (run.get("summary") or {}).get("qoi")
        if isinstance(qoi, dict) and isinstance(qoi.get("value"), (int, float)):
            vals.append(float(qoi["value"]))
    return vals or None


def classify_provenance(entry: dict, runs_root: Path = RUNS_ROOT) -> tuple[str, Optional[str], str]:
    """Classify one learned-summary entry -> (provenance, source_run, basis).

    Conservative: default "said"; "measured" only when the hard gate passes
    AND the text states an empirical trend/result.
    """
    run_id = entry.get("run_id")
    source_run = str(run_id) if run_id else None
    text = entry.get("text") or ""

    if not run_id:
        return ("said", None, "no run_id — not traceable to any executed run")

    qois = executed_numeric_qois(run_id, runs_root)
    if not qois:
        return ("said", source_run, "run did not execute a solver with a numeric QoI on disk (defer/halt/skip or no results.json)")

    has_trend = bool(_TREND_TERMS.search(text))
    has_number = bool(_NUMERIC_TOKEN.search(text))
    if has_trend and has_number:
        preview = ", ".join(f"{v:.4g}" for v in qois[:3])
        return ("measured", source_run, f"rests on executed run's measured QoI [{preview}...]; lesson states an empirical trend")
    return ("said", source_run, "executed run, but lesson is a re-scope/limitation claim, not resting on the measured numbers")


def load_learned_summaries(journal_path: Path = JOURNAL_PATH) -> list[dict]:
    """Read journal.jsonl (READ-ONLY) and return kind=='learned_summary'
    entries in file order."""
    out = []
    if not journal_path.exists():
        return out
    with open(journal_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            if d.get("kind") == "learned_summary":
                out.append(d)
    return out


def backfill(
    journal_path: Path = JOURNAL_PATH,
    runs_root: Path = RUNS_ROOT,
    out_path: Path = PROVENANCE_PATH,
) -> list[dict]:
    """Classify every learned summary and WRITE the sidecar fresh (this is the
    one-time backfill, so it overwrites rather than appends). Returns the
    records written. Journal untouched."""
    records = []
    for entry in load_learned_summaries(journal_path):
        provenance, source_run, basis = classify_provenance(entry, runs_root)
        records.append({
            "key": stable_key(entry),
            "provenance": provenance,
            "source_run": source_run,
            "basis": basis,
        })
    with open(out_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return records


def append_provenance(
    key: str,
    provenance: str,
    source_run: Optional[str],
    basis: str,
    out_path: Path = PROVENANCE_PATH,
) -> dict:
    """Append one provenance record for a FUTURE learned summary. Append-only,
    same discipline as the ledgers. Not wired into retrieval."""
    if provenance not in ("measured", "said"):
        raise ValueError(f"provenance must be 'measured' or 'said', got {provenance!r}")
    rec = {"key": key, "provenance": provenance, "source_run": source_run, "basis": basis}
    with open(out_path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill the lesson-provenance sidecar from the journal.")
    parser.add_argument("--journal", default=str(JOURNAL_PATH))
    parser.add_argument("--runs", default=str(RUNS_ROOT))
    parser.add_argument("--out", default=str(PROVENANCE_PATH))
    args = parser.parse_args(argv)

    records = backfill(Path(args.journal), Path(args.runs), Path(args.out))
    measured = sum(1 for r in records if r["provenance"] == "measured")
    said = len(records) - measured
    print(f"=== lesson-provenance backfill ===")
    print(f"learned summaries classified: {len(records)}  (measured={measured}, said={said})")
    print()
    print(f"  {'provenance':<9} {'source_run':<28} basis")
    for r in records:
        print(f"  {r['provenance']:<9} {str(r['source_run']):<28} {r['basis']}")
    print(f"\nsidecar written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
