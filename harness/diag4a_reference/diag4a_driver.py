"""Step 17 chunk 4a READ-ONLY diagnostic driver.

Lives in the session scratchpad, NOT the repo. Mirrors supervisor.main()'s
baton construction (run_id + created_at + mode + payload={"domain": ...}),
then calls the existing stages.stage1_ideation.run(baton) unchanged — the
same Stage-1-only entry path the chunk-3 reflect6smoke run used. Writes
baton_after_stage_1.json into the run dir on success. No project file is
modified; only runs/<id>/ evidence is produced.
"""

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path("/Users/jesseyu/research-system")
os.chdir(PROJECT)
sys.path.insert(0, str(PROJECT))

from baton import Baton  # noqa: E402
from stages import stage1_ideation  # noqa: E402

SAME_DOMAIN = "mean-flow structure and vortex strength in laminar lid-driven cavity flows"
ALT_DOMAIN = (
    "secondary corner eddies and their dependence on Reynolds number in "
    "two-dimensional laminar lid-driven cavity flow"
)

RUNS = [
    ("same1", SAME_DOMAIN),
    ("same2", SAME_DOMAIN),
    ("same3", SAME_DOMAIN),
    ("alt1", ALT_DOMAIN),
]

PROGRESS = Path(__file__).parent / "diag4a_progress.txt"


def main() -> None:
    # Optional argv tags select a subset (relaunch-after-kill support).
    wanted = set(sys.argv[1:])
    runs = [(t, d) for t, d in RUNS if not wanted or t in wanted]
    for tag, domain in runs:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"diag4a-{ts}-{tag}"
        run_dir = PROJECT / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        baton = Baton(
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            mode="auto",
            payload={"domain": domain},
        )
        baton.validate()
        with open(PROGRESS, "a") as f:
            f.write(f"START\t{run_id}\t{domain}\n")
        t0 = time.time()
        try:
            out = stage1_ideation.run(baton)
            (run_dir / "baton_after_stage_1.json").write_text(out.to_json())
            status = "OK"
        except Exception as exc:  # honest per-run failure record; batch continues
            status = f"FAILED: {type(exc).__name__}: {exc}"
            traceback.print_exc()
        wall = time.time() - t0
        with open(PROGRESS, "a") as f:
            f.write(f"DONE\t{run_id}\t{status}\twall_s={wall:.0f}\n")
        print(f"[driver] {run_id}: {status} ({wall:.0f}s)", flush=True)
        # Space runs out to be gentle on arXiv's rate limiter (the first
        # batch attempt died on 503/429/timeouts from back-to-back runs
        # during an arXiv bad window).
        time.sleep(180)


if __name__ == "__main__":
    main()
