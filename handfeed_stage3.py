"""
handfeed_stage3.py — side door for testing stage 3 without paying for
stages 1 and 2.

Rebuilds exactly what the supervisor would hand stage 3 after gate 2 — a
fresh baton whose payload is {domain, chosen_hypothesis, experiment_spec} —
from a past run's ON-DISK evidence, then calls the real stage-3 run()
directly. No supervisor, no gates. Reconstruction prefers the source run's
baton_after_stage_2.json snapshot; if that snapshot is absent it falls back
to the run's saved artifacts (stage2/spec.json plus the chosen-hypothesis
record in baton_after_gate_1.json or baton_before_stage_2.json), and either
way it reports which path was used. Hypothesis ids are per-run, so the
source run id is always recorded alongside the id in source.json.

Usage: venv/bin/python3 handfeed_stage3.py --source-run <run-directory-name>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from baton import Baton
from stages import stage3_fidelity_gate


def reconstruct_payload(source_dir: Path) -> tuple[dict, str]:
    """Rebuild the post-stage-2 payload from disk. Returns (payload, path_used)."""
    snapshot = source_dir / "baton_after_stage_2.json"
    if snapshot.exists():
        payload = json.loads(snapshot.read_text())["payload"]
        missing = [
            k for k in ("domain", "chosen_hypothesis", "experiment_spec") if k not in payload
        ]
        if missing:
            sys.exit(f"{snapshot} payload is missing {missing} — cannot reconstruct.")
        return (
            {
                "domain": payload["domain"],
                "chosen_hypothesis": payload["chosen_hypothesis"],
                "experiment_spec": payload["experiment_spec"],
            },
            "baton_after_stage_2.json",
        )

    spec_path = source_dir / "stage2" / "spec.json"
    if not spec_path.exists():
        sys.exit(
            f"{source_dir} has neither baton_after_stage_2.json nor stage2/spec.json — "
            "cannot reconstruct a post-stage-2 payload."
        )
    spec = json.loads(spec_path.read_text())

    chosen_source = None
    for name in ("baton_after_gate_1.json", "baton_before_stage_2.json"):
        candidate = source_dir / name
        if candidate.exists():
            chosen_source = candidate
            break
    if chosen_source is None:
        sys.exit(
            f"{source_dir} has no chosen-hypothesis record (baton_after_gate_1.json "
            "or baton_before_stage_2.json) — cannot reconstruct."
        )
    chosen_payload = json.loads(chosen_source.read_text())["payload"]
    return (
        {
            "domain": chosen_payload["domain"],
            "chosen_hypothesis": chosen_payload["chosen_hypothesis"],
            "experiment_spec": spec,
        },
        f"stage2/spec.json + {chosen_source.name}",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-run", required=True, help="run directory name under runs/ to feed from"
    )
    args = parser.parse_args()

    source_dir = Path("runs") / args.source_run
    if not source_dir.is_dir():
        sys.exit(f"source run directory not found: {source_dir}")

    payload, path_used = reconstruct_payload(source_dir)
    hypothesis_id = payload["chosen_hypothesis"]["id"]

    now = datetime.now(timezone.utc)
    run_id = f"handfeed3-{now.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True)
    with open(run_dir / "log.txt", "w") as f:
        f.write(
            f"HANDFEED3 run_id={run_id} source_run={args.source_run} "
            f"hyp={hypothesis_id} reconstructed_from={path_used!r}\n"
        )
    (run_dir / "source.json").write_text(
        json.dumps({"source_run": args.source_run, "hypothesis_id": hypothesis_id}, indent=2)
    )
    print(f"reconstructed payload from {path_used!r} (source {args.source_run}, {hypothesis_id})")

    baton = Baton(
        run_id=run_id,
        created_at=now.isoformat(),
        mode="auto",
        payload=payload,
        history=[],
    )
    baton.validate()
    (run_dir / "baton_before_stage_3.json").write_text(baton.to_json())

    baton = stage3_fidelity_gate.run(baton)

    baton.validate()
    (run_dir / "baton_after_stage_3.json").write_text(baton.to_json())

    print(f"evidence: {run_dir}/")
    print(f"  source:    {run_dir / 'source.json'}")
    print(f"  verdict:   {run_dir / 'stage3' / 'verdict.json'}")
    print(f"  snapshots: baton_before_stage_3.json, baton_after_stage_3.json")
    print(f"  log:       {run_dir / 'log.txt'}")


if __name__ == "__main__":
    main()
