"""harness/triage_battery.py — Step 20.7: the Stage-5 triage battery.

Four PLANTED, hand-authored, known-diagnosis cavity-flow cases run through the
REAL Stage-5 thought layer (stages.stage5_thought_layer.run_thought_model — the
same single door the live stage and handfeed_stage5 use), scored deterministically
per case against a mapped expectation. This battery TESTS the existing Stage 5; it
never modifies it.

The four cases and their mapped homes in Stage 5's real vocabulary
(TRIAGE_VALUES = none | setup_error | genuine_surprise | out_of_envelope;
DECISION_VALUES = back_to_ideation | back_to_design | more_data | exit):

  1. broken boundary condition        -> setup_error   (the run broke; nothing learned)
  2. coarse-mesh converged-but-wrong   -> "caught": out_of_envelope (preferred) or
                                          setup_error, decision more_data|back_to_design
                                          (recognized as an untrustworthy number, NOT
                                          accepted as none nor mistaken for genuine_surprise)
  3. genuine surprise                  -> genuine_surprise (trustworthy instrument,
                                          result strongly contradicts the prediction)
  4. out-of-envelope drift             -> out_of_envelope (instrument used outside its
                                          validated envelope; the number reflects limits)

There are three problem-triage values (setup_error, genuine_surprise,
out_of_envelope) but four problem cases, so one triage value is shared by design:
cases 2 and 4 both live in out_of_envelope, distinguished by decision. `none` is
deliberately never an expected home (all four are problem cases).

A case PASSES iff its Stage-5 surprise_triage is in triage_allowed AND its
iterate_decision is in decision_allowed. The battery is GREEN iff all four pass.

Unlike the fidelity-case battery (bare calls, no run dirs), Stage 5's door REQUIRES
a run_id (its answer-key tripwire enforces exactly the six prompt-input keys) and
echoes it, so each scored case writes its mandatory write-only transcript to
runs/triage-<UTC>-<case_id>/transcripts/ — append-only evidence, the handfeed_stage5
precedent. The machine report OVERWRITES harness/triage_last_run.json (like the
fidelity battery's last_run.json); runs/ stays the only append-only store.

This mode is NOT part of FAST's hard gate — it is a separate --mode triage and
becomes Step-24's gate-3 evidence.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from stages.stage5_thought_layer import (  # noqa: E402
    DECISION_VALUES,
    TRIAGE_VALUES,
    run_thought_model,
)

TRIAGE_CASES_DIR = Path(__file__).resolve().parent / "triage_cases"
TRIAGE_LAST_RUN_PATH = Path(__file__).resolve().parent / "triage_last_run.json"

CASE_KEYS = ("case_id", "plan_case", "provenance", "prompt_inputs", "expectation")
PROMPT_INPUT_KEYS = frozenset(
    ("run_id", "chosen_hypothesis", "experiment_spec", "fidelity_verdict",
     "execution_results", "stage4_summaries")
)


def load_cases(cases_dir: Path = TRIAGE_CASES_DIR) -> list[dict]:
    """Load the triage case files (sorted by filename). Validates the sealed
    shape and the mapped expectation up front so a malformed fixture fails
    loudly here, before any model call."""
    cases = []
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text())
        missing = [k for k in CASE_KEYS if k not in case]
        if missing:
            raise ValueError(f"{path.name} missing {missing} — not a triage case file")
        if set(case["prompt_inputs"]) != PROMPT_INPUT_KEYS:
            raise ValueError(
                f"{path.name} prompt_inputs keys must be exactly {sorted(PROMPT_INPUT_KEYS)}; "
                f"got {sorted(case['prompt_inputs'])}"
            )
        exp = case["expectation"]
        bad_t = [t for t in exp["triage_allowed"] if t not in TRIAGE_VALUES]
        bad_d = [d for d in exp["decision_allowed"] if d not in DECISION_VALUES]
        if bad_t:
            raise ValueError(f"{path.name} expectation triage_allowed has non-vocabulary values {bad_t}")
        if bad_d:
            raise ValueError(f"{path.name} expectation decision_allowed has non-vocabulary values {bad_d}")
        if not exp["triage_allowed"] or not exp["decision_allowed"]:
            raise ValueError(f"{path.name} expectation lists must be non-empty")
        case["_file"] = path.name
        cases.append(case)
    if not cases:
        raise ValueError(f"no triage case files found in {cases_dir}")
    return cases


def score_thought(case: dict, thought: dict, timing: dict) -> dict:
    """Pure: score one Stage-5 thought against a case's mapped expectation.
    Kept separate from the model call so tests can score canned thoughts."""
    exp = case["expectation"]
    triage = thought["surprise_triage"]
    decision = thought["iterate_decision"]
    triage_pass = triage in exp["triage_allowed"]
    decision_pass = decision in exp["decision_allowed"]
    return {
        "case_id": case["case_id"],
        "plan_case": case["plan_case"],
        "triage": triage,
        "decision": decision,
        "triage_allowed": list(exp["triage_allowed"]),
        "decision_allowed": list(exp["decision_allowed"]),
        "triage_pass": triage_pass,
        "decision_pass": decision_pass,
        "passed": triage_pass and decision_pass,
        "assessment": thought["assessment"],
        "justification": thought["justification"],
        "learned_summary": thought["learned_summary"],
        "attempts": timing.get("attempts"),
        "fence_stripped": timing.get("fence_stripped"),
    }


def run_case(case: dict, batch_ts: str) -> dict:
    """Drive ONE case through the real Stage-5 door and score it. The run_id is
    overridden to a batch-scoped, per-case id so the mandatory transcript lands
    in a fresh append-only run dir each invocation (handfeed_stage5 precedent)."""
    run_id = f"triage-{batch_ts}-{case['case_id']}"
    prompt_inputs = {**case["prompt_inputs"], "run_id": run_id}
    data, timing = run_thought_model(prompt_inputs)
    record = score_thought(case, data["thought"], timing)
    record["run_id"] = run_id
    return record


def build_report(records: list[dict], batch_ts: str, wall_seconds: float) -> dict:
    """Pure report assembly from already-scored records."""
    passed = sum(1 for r in records if r["passed"])
    return {
        "mode": "triage",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "batch_id": batch_ts,
        "num_cases": len(records),
        "passed_count": passed,
        "total": len(records),
        "status": "GREEN" if records and passed == len(records) else "RED",
        "wall_time_seconds": round(wall_seconds, 3),
        "cases": records,
        "misses": [
            {
                "case_id": r["case_id"],
                "plan_case": r["plan_case"],
                "triage": r["triage"],
                "decision": r["decision"],
                "triage_allowed": r["triage_allowed"],
                "decision_allowed": r["decision_allowed"],
            }
            for r in records
            if not r["passed"]
        ],
    }


def print_report(report: dict) -> None:
    print()
    print("=" * 20 + " STAGE-5 TRIAGE BATTERY " + "=" * 20)
    for r in report["cases"]:
        tmark = "PASS" if r["triage_pass"] else "FAIL"
        dmark = "PASS" if r["decision_pass"] else "FAIL"
        verdict = "PASS" if r["passed"] else "FAIL"
        print(
            f"  {r['case_id']:<17} [{r['plan_case']}]\n"
            f"      triage={r['triage']:<16} {tmark}  "
            f"(allowed: {r['triage_allowed']})\n"
            f"      decision={r['decision']:<16} {dmark}  "
            f"(allowed: {r['decision_allowed']})  -> {verdict}"
        )
    print("-" * 64)
    print(
        f"TRIAGE: {report['status']} "
        f"({report['passed_count']}/{report['total']} passed)"
    )
    if report["misses"]:
        for m in report["misses"]:
            print(
                f"    MISS: {m['case_id']} — got triage={m['triage']} "
                f"decision={m['decision']}; expected triage in {m['triage_allowed']} "
                f"decision in {m['decision_allowed']}"
            )
    print("=" * 64)


def run_battery(report_path: Path | None = None,
                cases_dir: Path = TRIAGE_CASES_DIR) -> int:
    """Load, run all four cases through the real Stage-5 path, score, print the
    banner, write the machine report, and return 0 (GREEN) / 1 (RED)."""
    report_path = Path(report_path) if report_path is not None else TRIAGE_LAST_RUN_PATH
    cases = load_cases(cases_dir)
    batch_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start = time.perf_counter()
    records = [run_case(case, batch_ts) for case in cases]
    wall = time.perf_counter() - start
    report = build_report(records, batch_ts, wall)
    print_report(report)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"report written to {report_path}")
    return 0 if report["status"] == "GREEN" else 1
