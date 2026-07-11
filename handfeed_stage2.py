"""
handfeed_stage2.py — side door for testing stage 2 without paying for stage 1.

Rebuilds exactly what the supervisor would hand stage 2 after gate 1 — a
fresh baton whose payload is {domain, chosen_hypothesis} — from a past run's
stage-1 evidence on disk, then calls the real stage-2 run() directly. No
supervisor, no gates. Hypothesis ids are per-run, so both arguments are
always required.

Usage: python3 handfeed_stage2.py --source-run <run_id> --hyp <id>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from baton import Baton
from stages import stage2_experiment_design


def resolve_hypothesis(source_dir: Path, hyp_id: str) -> dict:
    """Find hyp_id in the source run's stage1/survivors.json; on a miss,
    fall back to stage1/evolution_variants.json — ACCEPTED records only
    (Step 17-D: accepted variants are selectable at gate 1, so the side
    door must reach them too; rejected variants never rank and stay
    unreachable). Exits with the ids available in both files when neither
    has it. Returns the {id, statement, rationale} view stage 2 consumes."""
    survivors = json.loads((source_dir / "stage1" / "survivors.json").read_text())
    matches = [h for h in survivors if h["id"] == hyp_id]
    if not matches:
        variants_path = source_dir / "stage1" / "evolution_variants.json"
        accepted = []
        if variants_path.exists():
            accepted = [
                v
                for v in json.loads(variants_path.read_text())
                if v.get("accepted") is True
            ]
        matches = [v for v in accepted if v["id"] == hyp_id]
        if not matches:
            sys.exit(
                f"hypothesis {hyp_id!r} not found in "
                f"{source_dir / 'stage1' / 'survivors.json'} "
                f"(ids there: {[h['id'] for h in survivors]}) nor among accepted "
                f"evolution variants in {variants_path} "
                f"(accepted ids there: {[v['id'] for v in accepted]})"
            )
    return {k: matches[0][k] for k in ("id", "statement", "rationale")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", required=True, help="run_id under runs/ to feed from")
    parser.add_argument("--hyp", required=True, help="hypothesis id in that run's survivors.json")
    args = parser.parse_args()

    source_dir = Path("runs") / args.source_run
    chosen = resolve_hypothesis(source_dir, args.hyp)

    gate1_snapshot = source_dir / "baton_after_gate_1.json"
    domain_source = (
        gate1_snapshot if gate1_snapshot.exists() else source_dir / "baton_after_stage_1.json"
    )
    domain = json.loads(domain_source.read_text())["payload"]["domain"]

    now = datetime.now(timezone.utc)
    run_id = f"handfeed-{now.strftime('%Y%m%dT%H%M%SZ')}-{args.hyp}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True)
    with open(run_dir / "log.txt", "w") as f:
        f.write(
            f"HANDFEED run_id={run_id} source_run={args.source_run} hyp={args.hyp} "
            f"domain_from={domain_source.name}\n"
        )

    baton = Baton(
        run_id=run_id,
        created_at=now.isoformat(),
        mode="auto",
        payload={"domain": domain, "chosen_hypothesis": chosen},
        history=[],
    )
    baton.validate()
    (run_dir / "baton_before_stage_2.json").write_text(baton.to_json())

    baton = stage2_experiment_design.run(baton)

    baton.validate()
    (run_dir / "baton_after_stage_2.json").write_text(baton.to_json())

    print(f"evidence: {run_dir}/")
    print(f"  spec:      {run_dir / 'stage2' / 'spec.json'}")
    print(f"  snapshots: baton_before_stage_2.json, baton_after_stage_2.json")
    print(f"  log:       {run_dir / 'log.txt'}")


if __name__ == "__main__":
    main()
