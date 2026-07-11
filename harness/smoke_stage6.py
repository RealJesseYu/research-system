"""
harness/smoke_stage6.py — fires live Haiku calls — manual invocation only.

The Step-22 supervised smoke: builds a synthetic run dir under runs/ from
the tests/fixtures/paper/ fixture set (the DEFER verdict — the class with
the richest sidecar rules — plus the canned stage-5 thought), invokes the
REAL stages/stage6_paper.run with the reference seam forced OFFLINE
(tests/fixtures/refs_canned.json; this worktree carries no .env by
design), prints a per-call tally from the shared cost meter, lints the
output with harness/paper_lint.py, and prints PASS/FAIL.

Never wired into any default path: no harness mode, no supervisor route,
no test imports it. Expected spend: ~17 Haiku calls (1 sidecar + 8
sections x draft+reflect), zero Sonnet, zero Opus.

Run from the project root:
    venv/bin/python3 harness/smoke_stage6.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
os.chdir(_PROJECT_ROOT)  # stage code addresses runs/ relative to the root

import cost_meter  # noqa: E402
from baton import Baton  # noqa: E402
from harness.paper_lint import lint_paper  # noqa: E402
from stages import stage6_paper  # noqa: E402

FIXTURES = _PROJECT_ROOT / "tests" / "fixtures" / "paper"
VERDICT_FIXTURE = "verdict_defer.json"  # richest class-conditional sidecar rules


def build_synthetic_run(run_id: str) -> Baton:
    run_dir = _PROJECT_ROOT / "runs" / run_id
    (run_dir / "stage3").mkdir(parents=True)
    (run_dir / "log.txt").write_text("")
    shutil.copy(FIXTURES / VERDICT_FIXTURE, run_dir / "stage3" / "verdict.json")
    stage5 = json.loads((FIXTURES / "stage5_thought.json").read_text())
    return Baton(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode="auto",
        payload={
            "thought": stage5["thought"],
            "iterate_decision": stage5["iterate_decision"],
        },
        history=[],
    )


def main() -> int:
    run_id = f"smoke6-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    print(f"SMOKE stage6: synthetic run {run_id} (verdict fixture: {VERDICT_FIXTURE})")
    baton = build_synthetic_run(run_id)

    stage6_paper.REFS_MODE = "offline"  # the ruled offline seam; no .env here
    cost_meter.reset()
    start = time.perf_counter()
    baton = stage6_paper.run(baton)
    wall = time.perf_counter() - start

    meter = cost_meter.read()
    print()
    print("=" * 20 + " SMOKE CALL TALLY " + "=" * 20)
    stages = meter["stages"]
    for stage, stats in stages.items():
        if stage == "total":
            continue
        print(f"  {stage}: calls={stats['calls']} rejects={stats['rejects']}")
    total = stages.get("total", {"calls": 0, "rejects": 0})
    print(
        f"  TOTAL: calls={total['calls']} rejects={total['rejects']} | "
        f"door model_calls={meter['model_calls']} | "
        f"wall_time_seconds={round(wall, 1)}"
    )
    print("=" * 58)

    failures = lint_paper(run_id)
    for failure in failures:
        print(
            f"PAPERLINT FAIL [{failure['code']}] "
            f"target={failure['target']}: {failure['message']}"
        )
    print(f"history note: {baton.history[-1]['note'] if baton.history else '(none)'}")
    print(f"evidence: runs/{run_id}/stage6/paper.md + paper_validation.json")
    verdict = "PASS" if not failures else "FAIL"
    print(f"SMOKE stage6: {verdict}")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
