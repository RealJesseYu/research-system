"""
gate_bets.py — Phase-1 Lane-1 gate-bets machinery (Brier scoring over the
fidelity ledger).

The idea: every fidelity-gate verdict is an implicit *bet* on whether the run,
as designed, will yield a faithful, usable answer. This module turns that bet
into an explicit probability and scores it with the Brier score once a
real-world outcome is known — so the gate's calibration can be measured
instead of asserted.

WHAT IT READS: memory/fidelity_ledger.jsonl (READ-ONLY). Its real schema, as
found at build time (2026-07-14), is one object per line with fields:
    run_id, verdict, substrate, rationale, outcome, timestamp
`verdict` is the gate's own vocabulary (trust | refine | defer). `outcome` is
a RESERVED slot — always written null today; a later real-world result fills
it (Step 21). See memory/ledgers.py.

THE BINARY EVENT scored against (stated plainly for the debrief):
    y = 1  iff the run as designed yielded a FAITHFUL, USABLE answer
    y = 0  iff it did not (unfaithful / unusable / wrong-instrument in hindsight)
The predicted probability p is the gate's bet that y == 1. Brier = (p - y)**2,
lower is better; cumulative Brier is the mean over RESOLVED entries only.

LIVE-LEDGER BLOCKER (honest, unpatched): every entry's `outcome` is currently
null, so NO entry is resolvable and the cumulative Brier is undefined. The
machinery + fixtures below are built and tested anyway; the live read reports
0 resolved / 18 excluded rather than inventing a fake event. This module does
NOT write outcomes and does NOT touch the ledger — it only reads.

This is a LEAF module: it imports nothing project-local, so any layer may use
it without inverting layer order. It never calls a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

FIDELITY_LEDGER_PATH = Path(__file__).resolve().parent.parent / "memory" / "fidelity_ledger.jsonl"
GATE_BETS_REPORT_PATH = Path(__file__).resolve().parent / "gate_bets_report.json"

# Verdict-class -> default probability that the run yields a faithful, usable
# answer. These are DEFAULTS (a class prior); an entry carrying an explicit
# `probability` field overrides them (the seam below). Deliberately coarse —
# they are priors to be corrected by measured outcomes, not tuned constants.
VERDICT_PRIORS: dict[str, float] = {
    "trust": 0.90,
    "refine": 0.50,
    "defer": 0.10,
}

# Outcome tokens that resolve to a faithful/usable answer (y = 1) vs not
# (y = 0). Anything else (incl. None / missing) is UNRESOLVED and excluded.
_TRUE_OUTCOMES = {True, 1, "faithful", "usable", "success", "confirmed", "true", "yes"}
_FALSE_OUTCOMES = {False, 0, "unfaithful", "unusable", "failure", "refuted", "false", "no"}


def entry_probability(entry: dict) -> Optional[float]:
    """The gate's bet p for one ledger entry.

    Seam: an explicit numeric `probability` field wins (clamped to [0, 1]).
    Otherwise the verdict-class prior. Returns None if the verdict is unknown
    and no explicit probability is present (an unpredictable entry).
    """
    if "probability" in entry and entry["probability"] is not None:
        try:
            p = float(entry["probability"])
        except (TypeError, ValueError):
            p = None
        if p is not None:
            return max(0.0, min(1.0, p))
    verdict = entry.get("verdict")
    return VERDICT_PRIORS.get(verdict)


def resolve_outcome(entry: dict) -> Optional[int]:
    """Map an entry's `outcome` to the binary event y in {0, 1}, or None if
    unresolved (the reserved-null state, a missing key, or an unrecognized
    token — all excluded from scoring)."""
    if "outcome" not in entry:
        return None
    val = entry["outcome"]
    if val is None:
        return None
    key = val.lower() if isinstance(val, str) else val
    if key in _TRUE_OUTCOMES:
        return 1
    if key in _FALSE_OUTCOMES:
        return 0
    return None


def brier(p: float, y: int) -> float:
    """Single-event Brier score for a binary outcome: (p - y)**2."""
    return (p - y) ** 2


def score_ledger(entries: list[dict]) -> dict:
    """Score a list of ledger entries.

    Returns a report dict:
      {
        binary_event: <str description>,
        n_total, n_resolved, n_excluded, n_unpredictable,
        cumulative_brier: <float|None>,       # mean over resolved, None if 0
        per_entry: [ {run_id, verdict, p, y, brier} ... ],   # resolved only
        excluded: [ {run_id, verdict, reason} ... ],
        calibration: [ {verdict, predicted_p, observed_frequency, n} ... ],
      }
    Unresolved / unpredictable entries are counted, never scored.
    """
    per_entry: list[dict] = []
    excluded: list[dict] = []
    # calibration buckets keyed by (verdict, predicted_p)
    buckets: dict[tuple, dict] = {}

    for e in entries:
        rid = e.get("run_id")
        verdict = e.get("verdict")
        p = entry_probability(e)
        y = resolve_outcome(e)
        if p is None:
            excluded.append({"run_id": rid, "verdict": verdict, "reason": "unpredictable (unknown verdict, no explicit probability)"})
            continue
        if y is None:
            excluded.append({"run_id": rid, "verdict": verdict, "reason": "unresolved outcome (null/missing/unrecognized)"})
            continue
        b = brier(p, y)
        per_entry.append({"run_id": rid, "verdict": verdict, "p": p, "y": y, "brier": b})
        key = (verdict, p)
        bk = buckets.setdefault(key, {"verdict": verdict, "predicted_p": p, "_ys": []})
        bk["_ys"].append(y)

    calibration = []
    for _key, bk in sorted(buckets.items(), key=lambda kv: (-kv[1]["predicted_p"], str(kv[1]["verdict"]))):
        ys = bk["_ys"]
        calibration.append({
            "verdict": bk["verdict"],
            "predicted_p": bk["predicted_p"],
            "observed_frequency": (sum(ys) / len(ys)) if ys else None,
            "n": len(ys),
        })

    n_resolved = len(per_entry)
    cumulative = (sum(pe["brier"] for pe in per_entry) / n_resolved) if n_resolved else None
    n_unpredictable = sum(1 for x in excluded if x["reason"].startswith("unpredictable"))

    return {
        "binary_event": "y=1 iff the run as designed yielded a faithful, usable answer; p = the gate's bet on y==1",
        "n_total": len(entries),
        "n_resolved": n_resolved,
        "n_excluded": len(excluded),
        "n_unpredictable": n_unpredictable,
        "cumulative_brier": cumulative,
        "per_entry": per_entry,
        "excluded": excluded,
        "calibration": calibration,
    }


def load_ledger(path: Path = FIDELITY_LEDGER_PATH) -> list[dict]:
    """Read a JSONL ledger into a list of dicts. Missing file -> []."""
    if not path.exists():
        return []
    entries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(json.loads(line))
    return entries


def format_report(report: dict) -> str:
    """Render a short human-readable table for stdout."""
    lines = []
    lines.append("=== gate-bets: Brier calibration over the fidelity ledger ===")
    lines.append(f"binary event: {report['binary_event']}")
    lines.append(f"priors: {VERDICT_PRIORS}")
    lines.append("")
    lines.append(f"entries total:      {report['n_total']}")
    lines.append(f"entries resolved:   {report['n_resolved']}")
    lines.append(f"entries excluded:   {report['n_excluded']}  "
                 f"(unpredictable: {report['n_unpredictable']}, "
                 f"unresolved: {report['n_excluded'] - report['n_unpredictable']})")
    cb = report["cumulative_brier"]
    lines.append(f"cumulative Brier:   {cb if cb is not None else 'UNDEFINED (0 resolved entries)'}")
    lines.append("")
    lines.append("calibration table (predicted p vs observed frequency):")
    lines.append(f"  {'verdict':<10} {'pred_p':>7} {'obs_freq':>9} {'n':>4}")
    if report["calibration"]:
        for row in report["calibration"]:
            of = row["observed_frequency"]
            of_s = f"{of:.3f}" if of is not None else "  n/a"
            lines.append(f"  {str(row['verdict']):<10} {row['predicted_p']:>7.2f} {of_s:>9} {row['n']:>4}")
    else:
        lines.append("  (empty — no resolved entries to calibrate)")
    if report["n_resolved"] == 0:
        lines.append("")
        lines.append("BLOCKER: no entry carries a resolved `outcome` (all null — the")
        lines.append("reserved Step-21 slot). Machinery is exercised by fixtures; the live")
        lines.append("read is a calibration of ZERO events. No fake event was invented.")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Brier calibration over the fidelity ledger.")
    parser.add_argument("--ledger", default=str(FIDELITY_LEDGER_PATH), help="path to fidelity_ledger.jsonl")
    parser.add_argument("--report", default=str(GATE_BETS_REPORT_PATH), help="path to write the JSON report")
    args = parser.parse_args(argv)

    entries = load_ledger(Path(args.ledger))
    report = score_ledger(entries)
    print(format_report(report))
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(f"\nreport written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
