"""pi_agent/cost_report.py — the offline per-phase cost report (roadmap item 1).

WHY. A study currently reports one spend number per move and nothing about
where the tokens went; the next roadmap decision (proportional verification)
rests on a belief about that distribution which has never been measured. This
module reads what is already on disk — arc.jsonl's per-entry cost
{calls, tokens} and `at` timestamps — into a per-phase table, so that decision
can rest on a measured distribution instead of a belief.

A READER, NEVER A PARTICIPANT. This is a measuring instrument over evidence
files: it never writes, never calls a model, and NEVER RAISES on a bad study.
Several studies on disk are truncated or malformed (no arc.jsonl, no
report.json, torn lines); every one of them must produce a report, degrading
to "unknown" per row or field. The tolerant-reader discipline and the
recursive tree roll-up follow liveview/reader.py (read_jsonl / _sum_cost /
totals) — same semantics, no import, so this stays usable even if liveview
moves.

WHAT THE NUMBERS MEAN — read before quoting them:
- A row's cost is the move's own persisted spend. Experiment moves
  (single/campaign) carry it from the run subprocess. Capability rows
  (call_ideation, call_validation, ...) carry it only for studies recorded
  after capability metering landed (2026-07-28); before that they read as
  unknown, NOT zero.
- A spawn row owns no measured cost: the child's spend lives in the CHILD's
  arc and report. The row shows the child's recursive arc roll-up, explicitly
  marked as derived rather than measured.
- Wall-clock per row is the delta between successive arc timestamps. `at` is
  written when a move is RECORDED (finished); there is no per-move start
  field. So each row's wall-clock includes the director's deciding turn that
  preceded the move, and the first row is measured from the study's
  created_at. This is stated in the output rather than presented as a
  per-move runtime.
- The tree total is the recursive sum of the arc cost column over this study
  and every descendant found on disk. It excludes process-side (director)
  spend, which is reported separately from report.json and never summed
  across the tree: child directors run in the parent's process, so their
  spend deltas NEST — summing them would double-count.

CLI:  venv/bin/python3 -m pi_agent.cost_report <study_id> [--json]
      venv/bin/python3 -m pi_agent.cost_report --all
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pi_agent.study import STUDIES_ROOT

# The move types whose cost is measured in a SUBPROCESS and persisted per-run.
# Everything else in the arc is an in-process action (capability, decide, ...).
EXPERIMENT_MOVE_TYPES = ("single", "campaign")

# Recursion backstop for the tree roll-up — far above any real study tree
# (spawn depth is capped at 5 by pi_agent/budget.py).
_MAX_TREE_DEPTH = 12


# --------------------------------------------------------------------------- #
# Tolerant readers. None of these raise; a bad file reads as absent.
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Optional[Any]:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001 — missing, partial, or malformed
        return None


def _read_jsonl(path: Path) -> tuple[list, int]:
    """(entries, skipped) — a torn or half-written line is skipped and counted,
    never raised (a study mid-write is a normal state, not an error)."""
    entries: list = []
    skipped = 0
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except Exception:  # noqa: BLE001 — torn line
                    skipped += 1
                    continue
                if isinstance(parsed, dict):
                    entries.append(parsed)
                else:
                    skipped += 1
    except Exception:  # noqa: BLE001 — no file is a normal early state
        return [], 0
    return entries, skipped


def _parse_at(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None


def _cost_of(entry: Any) -> tuple[Optional[int], Optional[int]]:
    """(calls, tokens) as recorded on an arc entry, or (None, None) when the
    move carries no measurement. None means UNKNOWN — never coerced to 0,
    because 'unmeasured' and 'measured zero' are different facts."""
    if not isinstance(entry, dict):
        return None, None
    cost = entry.get("cost")
    if not isinstance(cost, dict):
        return None, None
    calls = cost.get("calls")
    tokens = cost.get("tokens")
    calls = calls if isinstance(calls, int) and not isinstance(calls, bool) else None
    tokens = tokens if isinstance(tokens, int) and not isinstance(tokens, bool) else None
    if calls is None and tokens is None:
        return None, None
    return calls, tokens


def _usd_turns_of(entry: Any) -> tuple[Optional[float], Optional[int]]:
    """(usd, turns) as recorded on an arc entry's cost dict, or (None, None).
    Item C (2026-07-28): both fields exist only for studies recorded after
    per-call cost recording landed; None means UNKNOWN — never coerced to 0,
    because a run that predates the recording did not cost nothing."""
    if not isinstance(entry, dict):
        return None, None
    cost = entry.get("cost")
    if not isinstance(cost, dict):
        return None, None
    usd = cost.get("usd")
    turns = cost.get("turns")
    usd = float(usd) if isinstance(usd, (int, float)) and not isinstance(usd, bool) else None
    turns = turns if isinstance(turns, int) and not isinstance(turns, bool) else None
    return usd, turns


def _tokens_by_field_of(entry: Any) -> Optional[dict]:
    """The per-field usage breakdown ({input_tokens, output_tokens,
    cache_read_input_tokens, ...}) on an arc entry's cost, or None. This is
    what lets a reader separate cache re-reads (~10% the price of input) from
    real input — the summed `tokens` figure destroys that distinction."""
    if not isinstance(entry, dict):
        return None
    cost = entry.get("cost")
    if not isinstance(cost, dict):
        return None
    fields = cost.get("tokens_by_field")
    if isinstance(fields, dict) and fields:
        return {k: v for k, v in fields.items()
                if isinstance(v, int) and not isinstance(v, bool)}
    return None


# --------------------------------------------------------------------------- #
# Loading a study's arc and finding its children.
# --------------------------------------------------------------------------- #

def _load_arc(study_dir: Path) -> tuple[list, int, Optional[str]]:
    """(entries, torn_lines, source). arc.jsonl is the source of truth; when it
    is missing but report.json embeds the arc, that copy is used and named as
    the source so a reader knows the provenance."""
    entries, torn = _read_jsonl(study_dir / "arc.jsonl")
    if entries or (study_dir / "arc.jsonl").exists():
        return entries, torn, "arc.jsonl"
    report = _read_json(study_dir / "report.json")
    if isinstance(report, dict) and isinstance(report.get("arc"), list):
        arc = [e for e in report["arc"] if isinstance(e, dict)]
        return arc, 0, "report.json (arc.jsonl missing)"
    return [], 0, None


def _child_study_ids(study_id: str, entries: list, studies_root: Path) -> tuple[list, list]:
    """(linked, unlinked): children named by spawn entries in the arc, plus
    children present on disk by the spawn naming convention (<id>-sub<N>) that
    no arc entry links — a spawn still in flight, or a truncated arc. Both
    belong in the tree total; the unlinked ones are additionally reported so a
    reader knows the arc under-describes the tree."""
    linked = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        tool_output = e.get("tool_output")
        cid = tool_output.get("child_study_id") if isinstance(tool_output, dict) else None
        if isinstance(cid, str) and cid and cid not in linked:
            linked.append(cid)
    unlinked = []
    try:
        pattern = re.compile(re.escape(study_id) + r"-sub\d+$")
        for d in sorted(Path(studies_root).iterdir()):
            if d.is_dir() and pattern.fullmatch(d.name) and d.name not in linked:
                unlinked.append(d.name)
    except Exception:  # noqa: BLE001 — an unreadable root just yields no extras
        pass
    return linked, unlinked


def _own_arc_spend(entries: list) -> dict:
    """This study's own arc cost sum — same semantics as liveview's _sum_cost,
    plus coverage so 'how much of the arc is even measured' is visible.
    usd/turns (item C) carry their own coverage counters: 0 there means no
    entry recorded them (a pre-item-C study), which readers report as unknown,
    never as $0."""
    calls = tokens = covered = 0
    usd = 0.0
    turns = usd_covered = turns_covered = 0
    by_field: dict = {}
    for e in entries:
        c, t = _cost_of(e)
        if c is not None or t is not None:
            covered += 1
        calls += c or 0
        tokens += t or 0
        u, n = _usd_turns_of(e)
        if u is not None:
            usd += u
            usd_covered += 1
        if n is not None:
            turns += n
            turns_covered += 1
        fields = _tokens_by_field_of(e)
        if fields:
            for k, v in fields.items():
                by_field[k] = by_field.get(k, 0) + v
    return {"calls": calls, "tokens": tokens,
            "moves_with_cost": covered, "moves": len(entries),
            "usd": round(usd, 6), "moves_with_usd": usd_covered,
            "turns": turns, "moves_with_turns": turns_covered,
            "tokens_by_field": by_field}


def tree_arc_spend(
    study_id: str,
    studies_root: Path = STUDIES_ROOT,
    *,
    _seen: Optional[set] = None,
    _depth: int = 0,
) -> dict:
    """Recursive arc-cost roll-up over a study and every descendant on disk:
    {calls, tokens, studies, moves_with_cost, moves}. The same roll-up
    liveview's totals() performs. Cycle-safe, depth-capped, never raises.
    Process-side (director) spend is deliberately NOT in this number — see the
    module docstring."""
    seen = _seen if _seen is not None else set()
    out = {"calls": 0, "tokens": 0, "studies": 0, "moves_with_cost": 0, "moves": 0,
           "usd": 0.0, "moves_with_usd": 0, "turns": 0, "moves_with_turns": 0}
    if study_id in seen or _depth > _MAX_TREE_DEPTH:
        return out
    seen.add(study_id)
    try:
        study_dir = Path(studies_root) / study_id
        if not study_dir.is_dir():
            return out
        entries, _torn, _source = _load_arc(study_dir)
        own = _own_arc_spend(entries)
        for key in out:
            if key != "studies":
                out[key] += own[key]
        out["studies"] = 1
        linked, unlinked = _child_study_ids(study_id, entries, studies_root)
        for cid in linked + unlinked:
            child = tree_arc_spend(cid, studies_root, _seen=seen, _depth=_depth + 1)
            for key in out:
                out[key] += child[key]
        out["usd"] = round(out["usd"], 6)
    except Exception:  # noqa: BLE001 — a bad study degrades, never raises
        pass
    return out


# --------------------------------------------------------------------------- #
# The per-phase report.
# --------------------------------------------------------------------------- #

def _intent_of(entry: dict) -> Optional[str]:
    """The phase's intent, best available: the director's going-in rationale
    (`finding`), else the tool's own detail sentence, else the outcome label."""
    for candidate in (
        entry.get("finding"),
        (entry.get("tool_output") or {}).get("detail")
        if isinstance(entry.get("tool_output"), dict) else None,
        entry.get("outcome"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def _row(entry: dict, prev_at: Optional[datetime], studies_root: Path,
         seen: set) -> tuple[dict, Optional[datetime]]:
    """One arc entry -> one report row. Returns (row, this entry's timestamp)
    so the caller can chain wall-clock deltas."""
    at = _parse_at(entry.get("at"))
    wall = None
    if at is not None and prev_at is not None:
        delta = (at - prev_at).total_seconds()
        wall = delta if delta >= 0 else None  # clock skew reads as unknown

    calls, tokens = _cost_of(entry)
    cost_source = "measured" if (calls is not None or tokens is not None) else "unknown"
    usd, turns = _usd_turns_of(entry)

    tool_output = entry.get("tool_output")
    child_id = tool_output.get("child_study_id") if isinstance(tool_output, dict) else None
    if isinstance(child_id, str) and child_id and cost_source == "unknown":
        # A spawn's spend lives in the child's own records; roll it up and say
        # the number is derived, not measured on this row.
        child = tree_arc_spend(child_id, studies_root, _seen=seen)
        if child["studies"] > 0:
            calls, tokens = child["calls"], child["tokens"]
            cost_source = "derived_from_child"
            # usd/turns derive only where the child actually recorded them —
            # a child predating item C keeps them None (unknown, never 0).
            if child.get("moves_with_usd"):
                usd = child.get("usd")
            if child.get("moves_with_turns"):
                turns = child.get("turns")

    results = entry.get("results") if isinstance(entry.get("results"), list) else []
    verified = sum(1 for r in results if isinstance(r, dict) and r.get("verified"))
    claims = sum(1 for r in results if isinstance(r, dict))
    tokens_per_verified = None
    if isinstance(tokens, int) and verified > 0:
        tokens_per_verified = round(tokens / verified)

    row = {
        "seq": entry.get("seq"),
        "move_type": entry.get("move_type") or "?",
        "intent": _intent_of(entry),
        "wall_seconds": wall,
        "calls": calls,
        "tokens": tokens,
        # Item C: the SDK's own dollar figure and the summed agentic-loop turn
        # count for this phase. None = unknown (a study recorded before
        # 2026-07-28, or a row whose run reported neither) — never 0.
        "usd": usd,
        "turns": turns,
        "cost_source": cost_source,
        "verified": verified,
        "claims": claims,
        "tokens_per_verified": tokens_per_verified,
        "child_study_id": child_id if isinstance(child_id, str) else None,
    }
    return row, (at if at is not None else prev_at)


def study_cost_report(study_id: str, studies_root: Path = STUDIES_ROOT) -> dict:
    """The full per-phase cost picture of one study, as a plain dict. Never
    raises: a missing/truncated/malformed study reads as a report that says so."""
    node = {
        "study_id": study_id,
        "exists": False,
        "goal": None,
        "arc_source": None,
        "torn_lines": 0,
        "rows": [],
        "own_spend": _own_arc_spend([]),
        "tree_spend": {"calls": 0, "tokens": 0, "studies": 0,
                       "moves_with_cost": 0, "moves": 0,
                       "usd": 0.0, "moves_with_usd": 0,
                       "turns": 0, "moves_with_turns": 0},
        "report_present": False,
        "report_total_spend": None,
        "report_process_spend": None,
        "report_tree_spend": None,
        "process_residual": None,
        "grand_total_tokens": None,
        "unlinked_children": [],
        "notes": [],
    }
    try:
        study_dir = Path(studies_root) / study_id
        node["exists"] = study_dir.is_dir()
        if not node["exists"]:
            node["notes"].append("no such study directory on disk")
            return node

        identity = _read_json(study_dir / "study.json") or {}
        node["goal"] = identity.get("goal") if isinstance(identity, dict) else None

        entries, torn, source = _load_arc(study_dir)
        node["arc_source"] = source
        node["torn_lines"] = torn
        if source is None:
            node["notes"].append("no arc.jsonl and no report.json arc — nothing recorded")
        elif source != "arc.jsonl":
            node["notes"].append(f"arc read from {source}")
        if torn:
            node["notes"].append(f"{torn} unreadable arc line(s) skipped")

        prev_at = _parse_at(identity.get("created_at") if isinstance(identity, dict) else None)
        if entries and prev_at is None:
            node["notes"].append(
                "study created_at missing/unparsable — first row's wall-clock unknown")
        seen = {study_id}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            row, prev_at = _row(entry, prev_at, studies_root, seen)
            node["rows"].append(row)

        node["own_spend"] = _own_arc_spend(entries)
        node["tree_spend"] = tree_arc_spend(study_id, studies_root)
        _linked, unlinked = _child_study_ids(study_id, entries, studies_root)
        node["unlinked_children"] = unlinked
        if unlinked:
            node["notes"].append(
                "child stud(ies) on disk not linked from the arc (spawn in flight, "
                "or arc truncated): " + ", ".join(unlinked)
                + " — included in the tree total")

        report = _read_json(study_dir / "report.json")
        if isinstance(report, dict):
            node["report_present"] = True
            node["report_total_spend"] = report.get("total_spend")
            # process_spend is the honest name; decider_spend the historical one.
            node["report_process_spend"] = (
                report.get("process_spend") or report.get("decider_spend"))
            node["report_tree_spend"] = report.get("tree_spend")
        else:
            node["notes"].append("no report.json — process-side (director) spend unknown")

        # Process residual: the report's process-side delta minus whatever part
        # of it the arc already attributes to in-process capability rows (the
        # meter is process-global, so those overlap for studies recorded after
        # capability metering). For older studies the subtraction is a no-op.
        proc = node["report_process_spend"]
        if isinstance(proc, dict):
            cap_calls = cap_tokens = 0
            for row in node["rows"]:
                if row["move_type"] not in EXPERIMENT_MOVE_TYPES \
                        and row["cost_source"] == "measured":
                    cap_calls += row["calls"] or 0
                    cap_tokens += row["tokens"] or 0
            residual = {
                "calls": max(0, (proc.get("calls") or 0) - cap_calls),
                "tokens": max(0, (proc.get("tokens") or 0) - cap_tokens),
            }
            node["process_residual"] = residual
            node["grand_total_tokens"] = node["tree_spend"]["tokens"] + residual["tokens"]
        else:
            node["grand_total_tokens"] = node["tree_spend"]["tokens"] or None
            if node["tree_spend"]["tokens"]:
                node["notes"].append(
                    "grand total is the arc tree only — process-side spend unknown")
    except Exception as e:  # noqa: BLE001 — the instrument must never crash on evidence
        node["notes"].append(f"report degraded — {type(e).__name__}: {e}")
    return node


# --------------------------------------------------------------------------- #
# Rendering.
# --------------------------------------------------------------------------- #

def _fmt_wall(seconds: Optional[float]) -> str:
    if seconds is None:
        return "?"
    s = int(round(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _fmt_n(value: Optional[int], mark: str = "") -> str:
    if value is None:
        return "?"
    return f"{value:,}{mark}"


def _fmt_usd(value: Optional[float], mark: str = "") -> str:
    """Dollars, or '?' for unknown — a pre-item-C study must never render $0."""
    if value is None:
        return "?"
    if value >= 0.995:
        return f"${value:,.2f}{mark}"
    return f"${value:.3f}{mark}"


def render_text(node: dict) -> str:
    lines = []
    title = node["study_id"]
    if node.get("goal"):
        goal = node["goal"]
        title += " — " + (goal[:100] + "…" if len(goal) > 100 else goal)
    lines.append(title)
    if not node["exists"]:
        lines.append("  no such study directory on disk")
        return "\n".join(lines)

    header = (f"{'seq':>4}  {'move_type':<24} {'wall':>8} {'calls':>6} "
              f"{'tokens':>13} {'usd':>9} {'turns':>6} {'tok/verified':>12}  intent")
    lines.append(header)
    lines.append("-" * len(header))
    derived = False
    for row in node["rows"]:
        mark = "*" if row["cost_source"] == "derived_from_child" else ""
        derived = derived or bool(mark)
        intent = row["intent"] or ""
        if len(intent) > 70:
            intent = intent[:69] + "…"
        lines.append(
            f"{row['seq'] if row['seq'] is not None else '?':>4}  "
            f"{row['move_type']:<24} "
            f"{_fmt_wall(row['wall_seconds']):>8} "
            f"{_fmt_n(row['calls'], mark):>6} "
            f"{_fmt_n(row['tokens'], mark):>13} "
            f"{_fmt_usd(row.get('usd'), mark):>9} "
            f"{_fmt_n(row.get('turns'), mark):>6} "
            f"{_fmt_n(row['tokens_per_verified']):>12}  "
            f"{intent}"
        )
    if not node["rows"]:
        lines.append("  (no arc entries)")
    if derived:
        lines.append("  * derived from the child study's arc roll-up, not measured on this row")

    own = node["own_spend"]
    tree = node["tree_spend"]
    lines.append("")
    lines.append(
        f"own arc spend:      {own['tokens']:>13,} tokens / {own['calls']} calls "
        f"({own['moves_with_cost']}/{own['moves']} arc entries carry a cost)")
    # Item C: real dollars and turns, when any arc entry recorded them.
    # "unknown" for a study predating per-call cost recording — never $0.
    if own.get("moves_with_usd"):
        usd_line = (f"real cost (USD):    {_fmt_usd(own['usd']):>13} "
                    f"({own['moves_with_usd']}/{own['moves']} arc entries "
                    "carry a dollar figure")
        if own.get("moves_with_turns"):
            usd_line += f"; {own['turns']:,} agentic turns"
        lines.append(usd_line + ")")
    elif own["moves"]:
        lines.append(
            "real cost (USD):    unknown — no arc entry carries a dollar figure "
            "(recorded before per-call cost recording, 2026-07-28, or no "
            "experiment move completed); the token sums above mix four "
            "differently-priced quantities")
    by_field = own.get("tokens_by_field") or {}
    if by_field:
        total_bf = sum(by_field.values())
        breakdown = ", ".join(f"{k}={v:,}" for k, v in sorted(by_field.items()))
        lines.append(f"token breakdown:    {breakdown}")
        cache = by_field.get("cache_read_input_tokens", 0)
        if total_bf:
            lines.append(
                f"                    cache reads are {cache / total_bf:.0%} of "
                "the summed token figure (priced at ~10% of input tokens)")
    if tree.get("studies", 0) > 1:
        tree_line = (
            f"tree total (arc):   {tree['tokens']:>13,} tokens / {tree['calls']} calls "
            f"across {tree['studies']} studies "
            f"({tree['moves_with_cost']}/{tree['moves']} entries measured)")
        if tree.get("moves_with_usd"):
            tree_line += f"; {_fmt_usd(tree['usd'])} real cost on the measured entries"
        lines.append(tree_line)
    proc = node["report_process_spend"]
    if isinstance(proc, dict):
        lines.append(
            f"process-side spend: {proc.get('tokens') or 0:>13,} tokens / "
            f"{proc.get('calls') or 0} calls "
            "(report.json: director decisions + in-process capability calls "
            "+ in-process child directors)")
    residual = node["process_residual"]
    if isinstance(residual, dict) and node["grand_total_tokens"] is not None:
        lines.append(
            f"grand total:        {node['grand_total_tokens']:>13,} tokens "
            "(arc tree + process-side spend not already attributed to arc rows)")
    elif node["grand_total_tokens"] is not None:
        lines.append(f"grand total:        {node['grand_total_tokens']:>13,} tokens (arc tree only)")
    rts = node.get("report_total_spend")
    if isinstance(rts, dict):
        lines.append(
            f"report.json total_spend: {rts.get('tokens') or 0:,} tokens "
            "(this study's process delta + its own arc runs; a root with "
            "children under-counts the tree — use the tree total above)")
    for note in node["notes"]:
        lines.append(f"note: {note}")
    lines.append(
        "note: wall-clock is the delta between successive arc timestamps (each "
        "includes the deciding turn before the move; there is no per-move start "
        "field). First row measured from the study's created_at.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #

def main(argv: Optional[list] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m pi_agent.cost_report",
        description="Offline per-phase cost report over a study's on-disk arc.")
    parser.add_argument("study_id", nargs="?", help="the study to report on")
    parser.add_argument("--json", action="store_true",
                        help="emit the report as JSON instead of a table")
    parser.add_argument("--all", action="store_true",
                        help="one summary line per study in studies-root")
    parser.add_argument("--studies-root", default=str(STUDIES_ROOT))
    args = parser.parse_args(argv)
    root = Path(args.studies_root)

    if args.all:
        try:
            ids = sorted(d.name for d in root.iterdir() if d.is_dir())
        except Exception:  # noqa: BLE001
            ids = []
        print(f"{'study':<42} {'moves':>5} {'measured':>8} {'own tokens':>13} "
              f"{'tree tokens':>13} {'tree usd':>10} {'proc tokens':>13}")
        for sid in ids:
            n = study_cost_report(sid, root)
            own, tree = n["own_spend"], n["tree_spend"]
            proc = n["report_process_spend"] or {}
            tree_usd = tree.get("usd") if tree.get("moves_with_usd") else None
            print(f"{sid:<42} {own['moves']:>5} "
                  f"{own['moves_with_cost']:>8} {own['tokens']:>13,} "
                  f"{tree['tokens']:>13,} "
                  f"{_fmt_usd(tree_usd):>10} "
                  f"{_fmt_n(proc.get('tokens') if isinstance(proc, dict) else None):>13}")
        return 0

    if not args.study_id:
        parser.print_usage()
        return 2
    node = study_cost_report(args.study_id, root)
    if args.json:
        print(json.dumps(node, indent=2))
    else:
        print(render_text(node))
    return 0 if node["exists"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
