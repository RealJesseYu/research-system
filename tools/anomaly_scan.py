"""
anomaly_scan.py — Phase-1 Lane-1 anomaly scanner v0. STRICTLY READ-ONLY.

Walks runs/ (and harness/*.json report files if present), collects the numeric
and structural facts that already sit on disk, and reports oddities. It is a
SCANNER, NOT A JUDGE: it flags shapes a human should look at, offers NO
interpretation of why, and NEVER calls a model. It writes nothing except its
own report (tools/anomaly_scan_report.md) and touches no run.

What it collects, per run, from stage4/results.json:
  - QoI values         (summary.qoi.value, grouped by QoI name)
  - convergence        (summary.converged, final_time vs end_time,
                        residuals Ux/Uy/p, key_result max_Courant / continuity)
  - wall times         (summary.runtime.wall_clock_s, solver_execution_time_s)
  - verdict class      (results.verdict_label / status)

What it reports:
  (a) OUTLIERS         per numeric family, by the IQR rule (needs n>=4)
  (b) REPEATED VALUES  identical numeric values across DISTINCT runs
  (c) WALL-TIME GAPS   predicted vs actual, where a predicted field exists
  (d) STRUCTURAL       empty files, unparseable/truncated json

This is a tools/ leaf: it imports nothing project-local and never calls a model.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

_ROOT = Path(__file__).resolve().parent.parent
RUNS_ROOT = _ROOT / "runs"
HARNESS_ROOT = _ROOT / "harness"
REPORT_PATH = _ROOT / "tools" / "anomaly_scan_report.md"

# Keys anywhere in a report that might hold a PREDICTED wall time, to pair
# against an actual. None are known to exist today — the check reports honestly
# when it finds none.
_PREDICTED_WALL_KEYS = {"predicted_wall_s", "estimated_wall_s", "predicted_wall_clock_s",
                        "estimated_wall_clock_s", "expected_wall_s", "eta_s"}


def _iqr_outliers(values: list[tuple[str, float]]) -> list[dict]:
    """values = [(label, x), ...]. Returns outliers by the 1.5*IQR rule.
    Needs at least 4 points; fewer -> no call (returns [])."""
    xs = sorted(v for _, v in values)
    n = len(xs)
    if n < 4:
        return []

    def _quantile(sorted_xs: list[float], q: float) -> float:
        pos = q * (len(sorted_xs) - 1)
        lo = math.floor(pos)
        hi = math.ceil(pos)
        if lo == hi:
            return sorted_xs[lo]
        frac = pos - lo
        return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac

    q1 = _quantile(xs, 0.25)
    q3 = _quantile(xs, 0.75)
    iqr = q3 - q1
    if iqr == 0:
        return []  # a spread of zero -> repeated-value territory, not an outlier
    lo_fence = q1 - 1.5 * iqr
    hi_fence = q3 + 1.5 * iqr
    out = []
    for label, x in values:
        if x < lo_fence or x > hi_fence:
            out.append({"label": label, "value": x, "q1": q1, "q3": q3,
                        "lo_fence": lo_fence, "hi_fence": hi_fence})
    return out


def collect(runs_root: Path = RUNS_ROOT) -> dict:
    """Walk runs/ and gather the numeric families + structural facts.
    Read-only; unparseable/empty files are recorded, never fatal."""
    families: dict[str, list[tuple[str, float]]] = defaultdict(list)
    # for repeated-value detection: value -> set of distinct run ids (per family)
    value_index: dict[str, dict[float, set]] = defaultdict(lambda: defaultdict(set))
    wall_pairs: list[dict] = []  # predicted-vs-actual, if a predicted field appears
    structural: list[dict] = []
    n_runs_seen = 0
    n_results_seen = 0

    if not runs_root.exists():
        return {"families": {}, "value_index": {}, "wall_pairs": [], "structural": [],
                "n_runs_seen": 0, "n_results_seen": 0}

    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        rid = run_dir.name
        n_runs_seen += 1
        results = run_dir / "stage4" / "results.json"
        if not results.exists():
            continue
        n_results_seen += 1
        try:
            raw = results.read_text()
        except OSError:
            structural.append({"file": str(results), "issue": "unreadable"})
            continue
        if not raw.strip():
            structural.append({"file": str(results), "issue": "empty file"})
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            structural.append({"file": str(results), "issue": f"unparseable/truncated json ({e})"})
            continue

        for run in (data.get("runs") or []):
            case = run.get("case") or f"{rid}:{run.get('run_index')}"
            summ = run.get("summary") or {}
            # QoI values, keyed by qoi name so unlike quantities never mix
            qoi = summ.get("qoi")
            if isinstance(qoi, dict) and isinstance(qoi.get("value"), (int, float)):
                fam = f"qoi:{qoi.get('name')}"
                families[fam].append((case, float(qoi["value"])))
                value_index[fam][float(qoi["value"])].add(rid)
            # wall times
            rt = summ.get("runtime") or {}
            for wk in ("wall_clock_s", "solver_execution_time_s"):
                if isinstance(rt.get(wk), (int, float)):
                    families[wk].append((case, float(rt[wk])))
                    value_index[wk][float(rt[wk])].add(rid)
            # convergence diagnostics
            kr = summ.get("key_result") or {}
            for kk in ("max_Courant", "continuity_global"):
                if isinstance(kr.get(kk), (int, float)):
                    families[kk].append((case, float(kr[kk])))
            res = summ.get("residuals") or {}
            for rk in ("Ux", "Uy", "p"):
                if isinstance(res.get(rk), (int, float)):
                    families[f"residual:{rk}"].append((case, float(res[rk])))
            # final vs end time mismatch (converged runs should reach endTime)
            ft, et = summ.get("final_time"), summ.get("end_time")
            if isinstance(ft, (int, float)) and isinstance(et, (int, float)) and ft != et:
                structural.append({"file": str(results),
                                   "issue": f"final_time {ft} != end_time {et} (case {case})"})
            # predicted-vs-actual wall time, if any predicted field is present
            for pk in _PREDICTED_WALL_KEYS:
                if isinstance(run.get(pk), (int, float)) and isinstance(rt.get("wall_clock_s"), (int, float)):
                    wall_pairs.append({"case": case, "predicted": run[pk], "actual": rt["wall_clock_s"],
                                       "gap": rt["wall_clock_s"] - run[pk], "source": pk})

    return {"families": dict(families), "value_index": {k: dict(v) for k, v in value_index.items()},
            "wall_pairs": wall_pairs, "structural": structural,
            "n_runs_seen": n_runs_seen, "n_results_seen": n_results_seen}


def scan_harness_reports(harness_root: Path = HARNESS_ROOT) -> list[dict]:
    """Structural-only pass over harness/*.json (empty / truncated)."""
    structural = []
    if not harness_root.exists():
        return structural
    for jf in sorted(harness_root.glob("*.json")):
        try:
            raw = jf.read_text()
        except OSError:
            structural.append({"file": str(jf), "issue": "unreadable"})
            continue
        if not raw.strip():
            structural.append({"file": str(jf), "issue": "empty file"})
            continue
        try:
            json.loads(raw)
        except json.JSONDecodeError as e:
            structural.append({"file": str(jf), "issue": f"unparseable/truncated json ({e})"})
    return structural


def analyze(collected: dict) -> dict:
    """Turn collected facts into findings. No interpretation — just shapes."""
    outliers = {}
    for fam, vals in collected["families"].items():
        found = _iqr_outliers(vals)
        if found:
            outliers[fam] = found

    repeated = {}
    for fam, vmap in collected["value_index"].items():
        for value, run_ids in vmap.items():
            if len(run_ids) >= 2:
                repeated.setdefault(fam, []).append({"value": value, "run_ids": sorted(run_ids), "n_runs": len(run_ids)})
        if fam in repeated:
            repeated[fam].sort(key=lambda r: -r["n_runs"])

    return {
        "outliers": outliers,
        "repeated_values": repeated,
        "wall_time_gaps": collected["wall_pairs"],
        "structural": collected["structural"],
        "n_runs_seen": collected["n_runs_seen"],
        "n_results_seen": collected["n_results_seen"],
        "families_summary": {fam: len(vals) for fam, vals in sorted(collected["families"].items())},
    }


def format_report(findings: dict) -> str:
    L = ["# Anomaly scan v0 — read-only report", ""]
    L.append(f"- run dirs walked: {findings['n_runs_seen']}")
    L.append(f"- stage4/results.json parsed: {findings['n_results_seen']}")
    L.append(f"- numeric families collected: {len(findings['families_summary'])}")
    L.append("")
    L.append("_A scanner, not a judge: findings are shapes to look at, not conclusions._")
    L.append("")

    L.append("## (a) Outliers (IQR rule, n>=4 per family)")
    if findings["outliers"]:
        for fam, items in sorted(findings["outliers"].items()):
            L.append(f"- **{fam}** ({len(items)}):")
            for it in items:
                L.append(f"    - `{it['label']}` = {it['value']:.6g} "
                         f"(fences [{it['lo_fence']:.4g}, {it['hi_fence']:.4g}])")
    else:
        L.append("- none")
    L.append("")

    L.append("## (b) Identical values repeated across DISTINCT runs")
    if findings["repeated_values"]:
        for fam, items in sorted(findings["repeated_values"].items()):
            L.append(f"- **{fam}**:")
            for it in items:
                L.append(f"    - {it['value']:.6g} in {it['n_runs']} runs: {', '.join(it['run_ids'])}")
    else:
        L.append("- none")
    L.append("")

    L.append("## (c) Predicted-vs-actual wall-time gaps")
    if findings["wall_time_gaps"]:
        for g in findings["wall_time_gaps"]:
            L.append(f"- `{g['case']}` predicted {g['predicted']} actual {g['actual']} "
                     f"gap {g['gap']:+.4g}s (field `{g['source']}`)")
    else:
        L.append("- none — no predicted/estimated wall-time field found on disk "
                 "(nothing writes one today); actual wall times are collected and IQR-scanned above.")
    L.append("")

    L.append("## (d) Structural oddities")
    if findings["structural"]:
        for s in findings["structural"]:
            L.append(f"- `{s['file']}` — {s['issue']}")
    else:
        L.append("- none")
    L.append("")

    L.append("## Numeric families collected (name -> point count)")
    for fam, n in findings["families_summary"].items():
        L.append(f"- {fam}: {n}")
    return "\n".join(L)


def run_scan(runs_root: Path = RUNS_ROOT, harness_root: Path = HARNESS_ROOT) -> dict:
    collected = collect(runs_root)
    findings = analyze(collected)
    findings["structural"] = findings["structural"] + scan_harness_reports(harness_root)
    return findings


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Read-only anomaly scan of runs/ + harness reports.")
    parser.add_argument("--runs", default=str(RUNS_ROOT))
    parser.add_argument("--harness", default=str(HARNESS_ROOT))
    parser.add_argument("--report", default=str(REPORT_PATH))
    args = parser.parse_args(argv)

    findings = run_scan(Path(args.runs), Path(args.harness))
    report = format_report(findings)
    print(report)
    Path(args.report).write_text(report + "\n")
    print(f"\nreport written to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
