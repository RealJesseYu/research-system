"""Point the hypothesis apparatus at a question, directly.

Until now ideation was only reachable through the director's `call_ideation`
action, so there was no way to ask it something without first launching a whole
study and hoping the director chose to delegate. This is that missing door: one
question in, ranked hypotheses out, nothing else in the loop.

It is deliberately thin. It builds the same Baton `stages/stage1_ideation.run`
already expects and calls it — no new apparatus, no second code path to keep in
sync. Everything the apparatus does (four generation strategies, six review
types, the Elo tournament, evolution, the meta-review at `--depth full`) is
unchanged, and the evidence lands in the usual place, `runs/<run_id>/stage1/`.

COST IS THE WHOLE REASON THIS PRINTS A WARNING. Measured on
study-20260726T010756Z, one `--depth full` pass was 176 model calls and
17.5M face-value tokens — roughly $17, and an hour of wall clock. `--depth
quick` is one generation pass and a small fraction of that. Neither is a
background task: per the run-venue rule this belongs in a plain Terminal under
`caffeinate`, because a builder session that dies takes the run with it.

    caffeinate -i venv/bin/python3 -m tools.ask_ideation \
        --depth full --pool-size 40 --question "..."

`--novelty-priority` is the dial the director gained on 2026-07-28: `required`
puts every methodologically novel candidate above every known-method one (a
science goal), `irrelevant` ranks on quality alone (an engineering goal, where
a proven method is a virtue), `balanced` lets quality lead and novelty break
ties. Only a handful of candidates survive the filter, so it decides which
CLASS of idea you see, not merely their order.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from baton import Baton  # noqa: E402
from stages import stage1_ideation  # noqa: E402

# Measured, not estimated: study-20260726T010756Z's single full-depth call.
FULL_DEPTH_CALLS = 176
FULL_DEPTH_TOKENS = 17_455_389


def _run_id(prefix: str = "ideation") -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m tools.ask_ideation",
        description="Ask the hypothesis apparatus a question directly.",
    )
    p.add_argument("--question", required=True,
                   help="the OPEN question to ideate on. Do not narrow it to "
                        "the instrument menu — candidates shaped around "
                        "existing tools are overwhelmingly the questions those "
                        "tools' fields have already answered.")
    p.add_argument("--depth", choices=("quick", "full"), default="full",
                   help="'full' (default) is the whole apparatus; 'quick' is "
                        "one literature-grounded generation pass.")
    p.add_argument("--pool-size", type=int, default=None,
                   help="how many candidates to generate. Every candidate is "
                        "reviewed, so cost scales with this.")
    p.add_argument("--novelty-priority",
                   choices=("required", "balanced", "irrelevant"),
                   default="balanced",
                   help="how much a novel METHOD is worth when ranking.")
    p.add_argument("--rounds", type=int, default=None,
                   help="generation/review rounds at full depth (default 1).")
    p.add_argument("--run-id", default=None,
                   help="override the run id (evidence goes to runs/<id>/stage1/).")
    p.add_argument("--yes", action="store_true",
                   help="skip the cost confirmation.")
    args = p.parse_args(argv)

    run_id = args.run_id or _run_id()

    if args.depth == "full" and not args.yes:
        print(f"--depth full measured {FULL_DEPTH_CALLS} model calls and "
              f"{FULL_DEPTH_TOKENS:,} tokens (~$17, ~1 hour) on the one study "
              f"that used it.\nRun id: {run_id}. Continue? [y/N] ", end="")
        if input().strip().lower() not in ("y", "yes"):
            print("Nothing run.")
            return 1

    if args.pool_size is not None:
        # Same seam call_ideation uses; a sizing hint must never sink the run.
        try:
            from stages.generation_strategies import set_pool_size
            set_pool_size(args.pool_size)
        except Exception as e:  # noqa: BLE001
            print(f"NOTE: pool size not applied ({type(e).__name__}: {e})")

    baton = Baton(
        run_id=run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        mode="auto",
        payload={"domain": args.question},
    )
    baton.validate()

    print(f"IDEATION run_id={run_id} depth={args.depth} "
          f"novelty={args.novelty_priority}")
    out = stage1_ideation.run(baton, rounds=args.rounds, depth=args.depth,
                              novelty_priority=args.novelty_priority)

    hyps = (out.payload or {}).get("hypotheses") or []
    ranked = (out.payload or {}).get("hypotheses_ranked") or []
    ordered = ranked or hyps

    print(f"\n{len(ordered)} candidate(s) delivered:\n")
    for i, h in enumerate(ordered, 1):
        if not isinstance(h, dict):
            continue
        print(f"{i}. [{h.get('id')}] {h.get('statement')}")
        if h.get("rationale"):
            print(f"     {h['rationale']}")
        print()

    evidence = Path("runs") / run_id / "stage1"
    print(f"evidence: {evidence}/")
    out_path = evidence / "delivered.json"
    try:
        out_path.write_text(json.dumps(out.payload, indent=2))
        print(f"delivered: {out_path}")
    except Exception as e:  # noqa: BLE001 — the run stands even if this does not
        print(f"NOTE: could not write {out_path} ({type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
