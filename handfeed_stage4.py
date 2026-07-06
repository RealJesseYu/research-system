"""
handfeed_stage4.py — side door for testing stage 4 without paying for
stages 1-3.

Rebuilds exactly what the supervisor would hand stage 4 after stage 3 — a
fresh baton whose payload is {domain, chosen_hypothesis, experiment_spec,
fidelity_verdict} — then calls the real stage-4 run() directly. No
supervisor, no gates, no model calls anywhere (stage 4 itself is
deterministic).

Two payload sources, mutually exclusive:
  --source-run <run-dir>   reconstruct from that run's ON-DISK evidence,
                           preferring baton_after_stage_3.json; else
                           stage2/spec.json + stage3/verdict.json plus the
                           chosen-hypothesis record in baton_after_gate_1.json
                           or baton_before_stage_2.json.
  --payload <file.json>    read a HAND-AUTHORED payload file carrying all
                           four keys (used for hand-fed executable specs
                           whose verdict never came from stage 3). Recorded
                           in source.json as hand_authored so the evidence
                           is honest about the intervention.

--force-label trust|refine|defer REPLACES the verdict label for this
handfeed only (recorded in source.json as forced_label) — needed because no
existing run carries a trust verdict yet.

--then-stage5 (Step 15 chunk 1, default off; behavior without it unchanged):
after stage 4 completes, invoke the LIVE stages/stage5_thought_layer.run()
on the same baton. Because the baton's run_id is this handfeed's run id,
stage 5 reads runs/<handfeed-id>/stage4/results.json and writes its
thought.json and transcript into this handfeed's run dir. The live path's
journaling (JC6) is deliberately NOT suppressed — a non-exit decision
appends a learned_summary to memory/journal.jsonl, and that behavior is
part of what the flag exists to observe.

Usage: venv/bin/python3 handfeed_stage4.py --source-run <run-directory-name>
       venv/bin/python3 handfeed_stage4.py --source-run <run-dir> --force-label trust
       venv/bin/python3 handfeed_stage4.py --payload specs/<payload>.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from baton import Baton
from stages import stage4_simulation, stage5_thought_layer

PAYLOAD_KEYS = ("domain", "chosen_hypothesis", "experiment_spec", "fidelity_verdict")


def reconstruct_payload(source_dir: Path) -> tuple[dict, str]:
    """Rebuild the post-stage-3 payload from disk. Returns (payload, path_used)."""
    snapshot = source_dir / "baton_after_stage_3.json"
    if snapshot.exists():
        payload = json.loads(snapshot.read_text())["payload"]
        missing = [k for k in PAYLOAD_KEYS if k not in payload]
        if missing:
            sys.exit(f"{snapshot} payload is missing {missing} — cannot reconstruct.")
        return {k: payload[k] for k in PAYLOAD_KEYS}, "baton_after_stage_3.json"

    spec_path = source_dir / "stage2" / "spec.json"
    verdict_path = source_dir / "stage3" / "verdict.json"
    if not spec_path.exists() or not verdict_path.exists():
        sys.exit(
            f"{source_dir} has neither baton_after_stage_3.json nor both "
            "stage2/spec.json and stage3/verdict.json — cannot reconstruct a "
            "post-stage-3 payload."
        )
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
            "experiment_spec": json.loads(spec_path.read_text()),
            "fidelity_verdict": json.loads(verdict_path.read_text()),
        },
        f"stage2/spec.json + stage3/verdict.json + {chosen_source.name}",
    )


def load_hand_payload(payload_path: Path) -> tuple[dict, str]:
    payload = json.loads(payload_path.read_text())
    missing = [k for k in PAYLOAD_KEYS if k not in payload]
    if missing:
        sys.exit(f"{payload_path} is missing {missing} — not a stage-4 payload.")
    return {k: payload[k] for k in PAYLOAD_KEYS}, str(payload_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--source-run", help="run directory name under runs/ to feed from"
    )
    source_group.add_argument(
        "--payload", help="path to a hand-authored payload JSON (all four keys)"
    )
    parser.add_argument(
        "--force-label",
        choices=("trust", "refine", "defer"),
        help="REPLACE the verdict label for this handfeed (recorded as forced_label)",
    )
    parser.add_argument(
        "--then-stage5",
        action="store_true",
        help="after stage 4, run the LIVE stage 5 thought layer on the same "
        "baton (journaling NOT suppressed)",
    )
    args = parser.parse_args()

    if args.source_run:
        source_dir = Path("runs") / args.source_run
        if not source_dir.is_dir():
            sys.exit(f"source run directory not found: {source_dir}")
        payload, path_used = reconstruct_payload(source_dir)
        source_record = {"source_run": args.source_run, "reconstructed_from": path_used}
    else:
        payload_path = Path(args.payload)
        if not payload_path.is_file():
            sys.exit(f"payload file not found: {payload_path}")
        payload, path_used = load_hand_payload(payload_path)
        source_record = {"payload_file": path_used, "hand_authored": True}

    original_label = payload["fidelity_verdict"]["label"]
    if args.force_label:
        payload["fidelity_verdict"] = dict(
            payload["fidelity_verdict"], label=args.force_label
        )
        source_record["forced_label"] = args.force_label
        source_record["original_label"] = original_label

    now = datetime.now(timezone.utc)
    run_id = f"handfeed4-{now.strftime('%Y%m%dT%H%M%SZ')}"
    run_dir = Path("runs") / run_id
    run_dir.mkdir(parents=True)
    with open(run_dir / "log.txt", "w") as f:
        f.write(
            f"HANDFEED4 run_id={run_id} payload_from={path_used!r} "
            f"label={payload['fidelity_verdict']['label']}"
            + (f" (forced; original={original_label})" if args.force_label else "")
            + "\n"
        )
    (run_dir / "source.json").write_text(json.dumps(source_record, indent=2))
    print(f"payload from {path_used!r}, verdict label {payload['fidelity_verdict']['label']}"
          + (" (FORCED)" if args.force_label else ""))

    baton = Baton(
        run_id=run_id,
        created_at=now.isoformat(),
        mode="auto",
        payload=payload,
        history=[],
    )
    baton.validate()
    (run_dir / "baton_before_stage_4.json").write_text(baton.to_json())

    baton = stage4_simulation.run(baton)

    baton.validate()
    (run_dir / "baton_after_stage_4.json").write_text(baton.to_json())

    if args.then_stage5:
        with open(run_dir / "log.txt", "a") as f:
            f.write("HANDFEED4 --then-stage5: invoking LIVE stage 5 on the same baton\n")
        baton = stage5_thought_layer.run(baton)
        baton.validate()
        (run_dir / "baton_after_stage_5.json").write_text(baton.to_json())

    print(f"evidence: {run_dir}/")
    print(f"  source:    {run_dir / 'source.json'}")
    print(f"  results:   {run_dir / 'stage4' / 'results.json'}")
    print(f"  snapshots: baton_before_stage_4.json, baton_after_stage_4.json")
    if args.then_stage5:
        print(f"  stage 5:   {run_dir / 'stage5' / 'thought.json'}, baton_after_stage_5.json")
    print(f"  log:       {run_dir / 'log.txt'}")


if __name__ == "__main__":
    main()
