"""
positional_analysis.py — offline positional-bias analysis over accumulated
stage-1 tournament states (deferred-queue item 14, QUEUE-14).

Read-only and deterministic: ZERO model/API calls, ZERO writes to any run
dir. Scans runs/*/stage1/**/tournament_state.json, and for every REAL
(non-trivial) tournament state measures whether the Opus judge favours the
hypothesis it is shown SECOND ("position 2").

GROUND TRUTH for "position 2" (do not assume from array order):
  * The judge input dict inserts hypothesis_a (h_a) BEFORE hypothesis_b (h_b)
    — stages/stage1_ideation.py:294-295 (single-turn), :346-347 / :376-377
    (debate). model_call.py:294 serialises it with json.dumps(stage_input)
    and NO sort_keys, so h_a's text precedes h_b's in the prompt string.
  * The `orderings` entry recorded for that call is [h_a.id, h_b.id]
    (stage1_ideation.py:597 for the debate's two swapped orderings, :604 for
    the single-turn ordering).
  => ordering[0] is presented FIRST, ordering[1] is presented SECOND.
     "position 2" == ordering[1] == presented-second. A verdict favours
     position 2 iff winner_id == ordering[1].

An IDENTITY worth stating (drives the honest reporting below): a debate is
run at both swapped orderings and the two orderings share the same id pair.
  * If the two verdicts AGREE (same winner), that winner necessarily sits at
    position 1 in one ordering and position 2 in the other — so every agreed
    debate contributes exactly one position-1 win and one position-2 win.
    Agreed debates therefore carry NO positional signal (position-2 rate is
    exactly 0.5 by construction).
  * If the two verdicts DISAGREE (a "split"), the two winners are the two
    distinct ids, so BOTH verdicts land on the same presentation position —
    a split is always either "both position 1" or "both position 2". All the
    debate positional signal lives in the splits, and each split is ONE
    independent directional outcome (its two verdicts are perfectly
    correlated — counting them as 2 double-counts).

Single-turn matches (J2 non-top-2) are the named exposure: one ordering, no
swap/draw protection. For those we compare the observed position-2 win count
to the Elo-EXPECTED count using elo_before.

Usage:  python3 harness/positional_analysis.py [--runs-dir DIR]
Output: harness/positional_last_run.json (uncommitted) + a printed banner.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RUNS_DIR = os.path.join(REPO_ROOT, "runs")
REPORT_PATH = os.path.join(REPO_ROOT, "harness", "positional_last_run.json")


# --------------------------------------------------------------------------
# Pure helpers (unit-tested directly against canned data)
# --------------------------------------------------------------------------

def is_trivial(state: dict) -> bool:
    """A k=1 round writes a trivial-marker state (stage1_ideation.py:535):
    {"trivial": True, ...} with no match_log. Recognised so it is skipped
    gracefully."""
    return bool(state.get("trivial")) or "match_log" not in state


def winner_position(ordering: list, winner: str) -> int:
    """1 if the winner was presented FIRST, 2 if presented SECOND. Raises on
    a winner outside the ordering (enum-pinned upstream; a violation here is a
    corrupt state, surfaced not swallowed)."""
    if winner == ordering[0]:
        return 1
    if winner == ordering[1]:
        return 2
    raise ValueError(f"winner {winner!r} not in ordering {ordering!r}")


def classify_debate(match: dict) -> dict:
    """Classify one debate match (two swapped orderings, two verdicts).
    Returns {is_split, split_position: 1|2|None, pos2_verdicts, pos1_verdicts}
    where the verdict counts sum to 2 (one per ordering)."""
    orderings, verdicts = match["orderings"], match["verdicts"]
    positions = [winner_position(o, v) for o, v in zip(orderings, verdicts)]
    pos2 = sum(1 for p in positions if p == 2)
    pos1 = sum(1 for p in positions if p == 1)
    is_split = verdicts[0] != verdicts[1]
    # A split is always both-same-position (see module docstring identity).
    split_position = None
    if is_split:
        split_position = 2 if pos2 == 2 else 1
    return {
        "is_split": is_split,
        "split_position": split_position,
        "pos2_verdicts": pos2,
        "pos1_verdicts": pos1,
    }


def elo_expected(r_first: float, r_second: float) -> float:
    """Expected score for the SECOND-presented (position-2) hypothesis under
    standard Elo: 1/(1+10^((R_first - R_second)/400))."""
    return 1.0 / (1.0 + 10.0 ** ((r_first - r_second) / 400.0))


def single_turn_expectation(match: dict) -> dict:
    """One single-turn match: observed position-2 win (0/1) and the
    Elo-expected position-2 win probability from elo_before."""
    ordering = match["orderings"][0]
    verdict = match["verdicts"][0]
    elo_before = match["elo_before"]
    observed = 1 if winner_position(ordering, verdict) == 2 else 0
    expected = elo_expected(elo_before[ordering[0]], elo_before[ordering[1]])
    return {"observed_pos2": observed, "expected_pos2": expected}


def binomial_two_sided_all_one_way(n: int) -> float:
    """Two-sided p for n independent fair-coin trials landing ALL one way:
    2 * 0.5^n, capped at 1.0. n==0 -> 1.0 (no evidence)."""
    if n <= 0:
        return 1.0
    return min(1.0, 2.0 * (0.5 ** n))


def analyze_state(state: dict) -> dict:
    """Per-state census: split debates, agreed debates, and single-turn
    Elo-expectation accumulation. Returns raw counts only (pooling is done by
    the caller so per-run and pooled totals stay consistent)."""
    debates_total = debates_split = debates_agree = 0
    split_pos2 = split_pos1 = 0          # split debates by direction
    split_verdicts_pos2 = split_verdicts_pos1 = 0  # verdict-instances (2/split)
    st_n = 0
    st_observed = 0.0
    st_expected = 0.0
    for m in state["match_log"]:
        if m["tier"] == "debate":
            debates_total += 1
            c = classify_debate(m)
            if c["is_split"]:
                debates_split += 1
                split_verdicts_pos2 += c["pos2_verdicts"]
                split_verdicts_pos1 += c["pos1_verdicts"]
                if c["split_position"] == 2:
                    split_pos2 += 1
                else:
                    split_pos1 += 1
            else:
                debates_agree += 1
        elif m["tier"] == "single_turn":
            e = single_turn_expectation(m)
            st_n += 1
            st_observed += e["observed_pos2"]
            st_expected += e["expected_pos2"]
    return {
        "debates_total": debates_total,
        "debates_split": debates_split,
        "debates_agree": debates_agree,
        "split_pos2": split_pos2,
        "split_pos1": split_pos1,
        "split_verdicts_pos2": split_verdicts_pos2,
        "split_verdicts_pos1": split_verdicts_pos1,
        "single_turn_n": st_n,
        "single_turn_observed_pos2": st_observed,
        "single_turn_expected_pos2": st_expected,
    }


# --------------------------------------------------------------------------
# Disk scan (deterministic selection: round dirs when present, else canonical)
# --------------------------------------------------------------------------

def select_state_paths(runs_dir: str) -> list[str]:
    """Every real per-round tournament state, exactly once. The canonical
    stage1/tournament_state.json is a byte-copy of the last successful round,
    so when a run has round dirs we take ONLY the round files and drop the
    canonical (double-count guard); a run with no round dirs contributes its
    canonical file. Returns paths sorted for reproducibility."""
    by_run: dict[str, dict] = {}
    pattern = os.path.join(runs_dir, "*", "stage1", "**", "tournament_state.json")
    for path in glob.glob(pattern, recursive=True):
        rel = os.path.relpath(path, runs_dir)
        run_id = rel.split(os.sep)[0]
        m = re.search(r"round(\d+)", rel)
        key = ("round", int(m.group(1))) if m else ("canonical", 0)
        by_run.setdefault(run_id, {})[key] = path
    selected: list[str] = []
    for run_id, paths in by_run.items():
        round_keys = sorted(k for k in paths if k[0] == "round")
        if round_keys:
            selected.extend(paths[k] for k in round_keys)
        else:
            selected.append(paths[("canonical", 0)])
    return sorted(selected)


def state_label(path: str, runs_dir: str) -> str:
    """A stable human label: '<run_id>' or '<run_id>/round<N>'."""
    rel = os.path.relpath(path, runs_dir)
    run_id = rel.split(os.sep)[0]
    m = re.search(r"round(\d+)", rel)
    return f"{run_id}/round{m.group(1)}" if m else run_id


# --------------------------------------------------------------------------
# Report assembly
# --------------------------------------------------------------------------

def build_report(runs_dir: str = DEFAULT_RUNS_DIR) -> dict:
    """Scan runs_dir and pool per-state censuses into the machine report."""
    paths = select_state_paths(runs_dir)
    per_run = []
    skipped_trivial = []
    pool = {
        "debates_total": 0, "debates_split": 0, "debates_agree": 0,
        "split_pos2": 0, "split_pos1": 0,
        "split_verdicts_pos2": 0, "split_verdicts_pos1": 0,
        "single_turn_n": 0,
        "single_turn_observed_pos2": 0.0, "single_turn_expected_pos2": 0.0,
    }
    for path in paths:
        label = state_label(path, runs_dir)
        with open(path) as f:
            state = json.load(f)
        if is_trivial(state):
            skipped_trivial.append(label)
            continue
        a = analyze_state(state)
        a["state"] = label
        per_run.append(a)
        for key in pool:
            pool[key] += a[key]

    split_total = pool["split_pos2"] + pool["split_pos1"]
    st_excess = pool["single_turn_observed_pos2"] - pool["single_turn_expected_pos2"]

    return {
        "runs_dir": os.path.relpath(runs_dir, REPO_ROOT),
        "states_included": [r["state"] for r in per_run],
        "states_skipped_trivial": skipped_trivial,
        "per_state": per_run,
        "pooled": pool,
        "split_debate_census": {
            "split_debates": pool["debates_split"],
            "total_debates": pool["debates_total"],
            "agreed_debates": pool["debates_agree"],
            "splits_favoring_pos2": pool["split_pos2"],
            "splits_favoring_pos1": pool["split_pos1"],
            # verdict-instance framing (2 per split) — matches the watch's
            # "N/N verdicts" phrasing, but the two verdicts in a split are
            # perfectly correlated, so this DOUBLE-COUNTS the evidence.
            "verdict_instances_pos2": pool["split_verdicts_pos2"],
            "verdict_instances_pos1": pool["split_verdicts_pos1"],
            # honest independent unit = the split itself
            "binomial_two_sided_p_on_splits": binomial_two_sided_all_one_way(
                split_total
            ) if (pool["split_pos2"] == 0 or pool["split_pos1"] == 0) else None,
        },
        "agreed_debate_note": (
            "Agreed debates carry NO positional signal: each contributes "
            "exactly one position-1 and one position-2 win by construction "
            "(the two orderings are exact swaps). Position-2 win rate across "
            "agreed-debate verdicts is exactly 0.5 identically."
        ),
        "single_turn": {
            "n": pool["single_turn_n"],
            "observed_pos2_wins": pool["single_turn_observed_pos2"],
            "elo_expected_pos2_wins": round(pool["single_turn_expected_pos2"], 4),
            "excess_over_elo": round(st_excess, 4),
        },
        "limitations": [
            "SMALL-n on splits: the independent unit is the split "
            f"({split_total} split(s) total), not the "
            f"{pool['split_verdicts_pos2'] + pool['split_verdicts_pos1']} "
            "verdict instances. With all splits one direction the two-sided "
            "binomial p is 2*0.5^(#splits) — reported above; do not overclaim.",
            "ELO CIRCULARITY: elo_before ratings were themselves updated by "
            "these same verdicts within each tournament (online/sequential "
            "expectation). The single-turn excess is measured against ratings "
            "the verdicts helped set — a standard online-expectation caveat, "
            "not an independent prior.",
        ],
    }


def format_banner(report: dict) -> str:
    c = report["split_debate_census"]
    st = report["single_turn"]
    lines = []
    lines.append("=" * 70)
    lines.append("POSITIONAL-BIAS ANALYSIS (QUEUE-14) — offline, deterministic")
    lines.append("=" * 70)
    lines.append(
        f"states included: {len(report['states_included'])}  "
        f"(trivial skipped: {len(report['states_skipped_trivial'])})"
    )
    lines.append("")
    lines.append("SPLIT-DEBATE CENSUS")
    lines.append(
        f"  debates: {c['total_debates']} total | "
        f"{c['split_debates']} split | {c['agreed_debates']} agreed"
    )
    lines.append(
        f"  splits favoring position 2: {c['splits_favoring_pos2']} / "
        f"{c['split_debates']}  "
        f"(position 1: {c['splits_favoring_pos1']})"
    )
    lines.append(
        f"  verdict-instance framing (2/split, correlated): "
        f"pos2 {c['verdict_instances_pos2']} / "
        f"{c['verdict_instances_pos2'] + c['verdict_instances_pos1']}"
    )
    p = c["binomial_two_sided_p_on_splits"]
    lines.append(
        f"  binomial two-sided p on splits: "
        + (f"{p:.4f}  (small-n; not conclusive)" if p is not None
           else "n/a (splits go both ways)")
    )
    lines.append("")
    lines.append("  " + report["agreed_debate_note"])
    lines.append("")
    lines.append("SINGLE-TURN (named exposure: one ordering, no swap protection)")
    lines.append(f"  n = {st['n']} matches")
    lines.append(
        f"  observed position-2 wins: {st['observed_pos2_wins']:.0f}  |  "
        f"Elo-expected: {st['elo_expected_pos2_wins']:.4f}  |  "
        f"excess: {st['excess_over_elo']:+.4f}"
    )
    lines.append("")
    lines.append("LIMITATIONS (disclosed)")
    for lim in report["limitations"]:
        lines.append(f"  - {lim}")
    lines.append("")
    lines.append("states included:")
    for s in report["states_included"]:
        lines.append(f"  {s}")
    lines.append("=" * 70)
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    runs_dir = DEFAULT_RUNS_DIR
    if "--runs-dir" in argv:
        runs_dir = os.path.abspath(argv[argv.index("--runs-dir") + 1])
    report = build_report(runs_dir)
    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)
    print(format_banner(report))
    print(f"\nmachine report: {os.path.relpath(REPORT_PATH, REPO_ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
