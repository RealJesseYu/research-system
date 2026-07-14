"""
harness/validation_batch.py — single-pass validation-survival batch driver.

Pushes each Step-18 arm's top-ranked (rank-1) hypothesis through the REAL
stages 2 -> 3 -> 4 -> 5 in fully autonomous mode, single pass, with NO
loop-backs enacted: the stage-5 iterate decision IS the measurement
(survived == the decision is "exit"). On an exit decision the chain proceeds
to stage 6 (paper) and then paperlint on that run id.

Selection source (18-prep proposal, superseded input): the T1b/T2b/T3b
killrate reports. For each RESOLVED slot the last attempt's run dir is read
and its rank-1 hypothesis taken from baton_after_stage_1.json's ranked
payload (payload["hypotheses"][0]). When that snapshot is absent — an
exception attempt can leave none — rank-1 is named from the final Elo order
in stage1/tournament_state.json and the {id, statement, rationale} view is
resolved from stage1/survivors.json (else an accepted evolution variant),
mirroring handfeed_stage2's resolve pattern.

Per ruling R-18-D1: a slot whose last attempt carries a non-null exception is
INCLUDED but flagged; the flag and the source rounds_completed travel with the
datum into source.json and the machine report.

This driver CALLS stages, never modifies them. Sequential execution only — the
solver container is shared. Each chain is wrapped so one crash is recorded as
evidence and the batch proceeds to the next selection.

Usage:
  venv/bin/python3 harness/validation_batch.py            # run the batch
  venv/bin/python3 harness/validation_batch.py --plan     # print, execute nothing
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from baton import Baton
from harness.paper_lint import lint_paper
from schemas import (
    validate_payload_post_gate1,
    validate_payload_post_stage2,
    validate_payload_post_stage3,
    validate_payload_post_stage4,
    validate_payload_post_stage5,
)
from stages import (
    stage2_experiment_design,
    stage3_fidelity_gate,
    stage4_simulation,
    stage5_thought_layer,
    stage6_paper,
)
from tools.run_cfd import CONTAINER, DOCKER_CONTEXT

REPORTS = [
    ("T1", Path("harness/killrate_18_T1b.json")),
    ("T2", Path("harness/killrate_18_T2b.json")),
    ("T3", Path("harness/killrate_18_T3b.json")),
]
RUNS_ROOT = Path("runs")
REPORT_OUT = Path("harness/validation_batch_18.json")

DEFAULT_STAGES = {
    "stage2": stage2_experiment_design.run,
    "stage3": stage3_fidelity_gate.run,
    "stage4": stage4_simulation.run,
    "stage5": stage5_thought_layer.run,
    "stage6": stage6_paper.run,
}
DEFAULT_VALIDATORS = {
    "post_stage2": validate_payload_post_stage2,
    "post_stage3": validate_payload_post_stage3,
    "post_stage4": validate_payload_post_stage4,
    "post_stage5": validate_payload_post_stage5,
}


# --- selection (pure; reads on-disk evidence) ------------------------------

def _hyp_view(record: dict) -> dict:
    return {k: record[k] for k in ("id", "statement", "rationale")}


def _resolve_hyp(run_dir: Path, hyp_id: str) -> dict:
    """{id, statement, rationale} for hyp_id from survivors.json, falling back
    to an ACCEPTED evolution variant — the handfeed_stage2 resolve pattern."""
    survivors = json.loads((run_dir / "stage1" / "survivors.json").read_text())
    for h in survivors:
        if h["id"] == hyp_id:
            return _hyp_view(h)
    variants_path = run_dir / "stage1" / "evolution_variants.json"
    if variants_path.exists():
        for v in json.loads(variants_path.read_text()):
            if v.get("accepted") is True and v["id"] == hyp_id:
                return _hyp_view(v)
    raise RuntimeError(
        f"rank-1 id {hyp_id!r} not found in survivors.json nor accepted "
        f"evolution variants of {run_dir}"
    )


def select_rank1(run_dir: Path, report_domain: str) -> tuple[dict, str, str]:
    """Return (chosen_hypothesis, domain, selection_source) for a slot's run.
    Primary path: the ranked baton payload. Fallback (snapshot absent):
    tournament_state.json's final Elo ranking + a survivors/variant lookup."""
    snapshot = run_dir / "baton_after_stage_1.json"
    if snapshot.exists():
        payload = json.loads(snapshot.read_text())["payload"]
        return _hyp_view(payload["hypotheses"][0]), payload["domain"], "baton_after_stage_1.json"
    ranking = json.loads((run_dir / "stage1" / "tournament_state.json").read_text())
    rank1_id = ranking["final_ranking"][0]["id"]
    return _resolve_hyp(run_dir, rank1_id), report_domain, "tournament_state.json+survivors.json"


def gather_selections(reports=REPORTS, runs_root=RUNS_ROOT) -> list[dict]:
    """One selection record per RESOLVED slot across all three reports."""
    selections: list[dict] = []
    for arm, path in reports:
        report = json.loads(Path(path).read_text())
        domains = report["domains"]
        for slot in report["slots"]:
            if not slot.get("resolved"):
                continue
            last = slot["attempts"][-1]
            run_dir = runs_root / last["run_id"]
            chosen, domain, source = select_rank1(run_dir, domains.get(slot["domain_key"]))
            selections.append(
                {
                    "arm": arm,
                    "slot": slot["slot"],
                    "source_run_id": last["run_id"],
                    "rank": 1,
                    "hyp_id": chosen["id"],
                    "chosen_hypothesis": chosen,
                    "domain": domain,
                    "exception": last.get("exception"),
                    "exception_flag": last.get("exception") is not None,
                    "rounds_completed": last.get("rounds_completed"),
                    "selection_source": source,
                }
            )
    return selections


# --- guards ----------------------------------------------------------------

def _running_containers() -> list[str]:
    """Names of currently-running containers on the production Docker context,
    via `docker ps`. Raises CalledProcessError-shaped SystemExit if the daemon
    itself did not answer (colima down)."""
    proc = subprocess.run(
        ["docker", "--context", DOCKER_CONTEXT, "ps", "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        raise SystemExit(
            f"DOCKER GUARD FAILED: the Docker daemon on context "
            f"{DOCKER_CONTEXT!r} did not answer `docker ps` "
            f"(exit {proc.returncode}): {proc.stderr.strip() or '(no stderr)'}. "
            "Is colima up? Start it with `colima start`."
        )
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def docker_guard() -> None:
    """Fail loud unless the shared solver container is actually Up.

    18-hygiene (caught live at the ledger-#3 preflight, milestone step18_close):
    a running Colima daemon does NOT imply of12-prod is Up — daemon-up is not
    container-up. The old guard ran `docker exec CONTAINER true`, which
    conflated the two failure modes. This guard checks BOTH, in order:
      (1) the daemon answers `docker ps` at all (else: colima is down), and
      (2) that listing shows CONTAINER running.
    If CONTAINER is not Up, it attempts `docker start CONTAINER` exactly once,
    re-checks `docker ps`, and only then fails loud with a plain-language
    message telling the human what to do."""
    daemon_hint = "Is colima up? Start it with `colima start`."

    # (1) daemon reachable, and (2) is CONTAINER already Up?
    try:
        running = _running_containers()
    except SystemExit:
        raise  # already a plain-language daemon-down message
    except Exception as exc:  # noqa: BLE001 — timeout/transport: colima down
        raise SystemExit(
            f"DOCKER GUARD FAILED: cannot reach the Docker daemon on context "
            f"{DOCKER_CONTEXT!r} ({exc}). {daemon_hint}"
        )
    if CONTAINER in running:
        return

    # Container is not Up though the daemon is. Attempt to start it ONCE.
    start = subprocess.run(
        ["docker", "--context", DOCKER_CONTEXT, "start", CONTAINER],
        capture_output=True, text=True, timeout=30,
    )
    if start.returncode != 0:
        raise SystemExit(
            f"DOCKER GUARD FAILED: the Colima daemon is up but container "
            f"{CONTAINER!r} is not running, and `docker start {CONTAINER}` "
            f"failed (exit {start.returncode}): "
            f"{start.stderr.strip() or '(no stderr)'}. The solver container is "
            "absent or broken — recreate it from the Step-11 image before "
            f"running the battery (CLAUDE.md: `docker --context {DOCKER_CONTEXT} "
            f"run -d --name {CONTAINER} -v .../cases:/work/cases of12-img:latest "
            "sleep infinity`)."
        )

    # Re-check that the start actually brought it Up.
    if CONTAINER not in _running_containers():
        raise SystemExit(
            f"DOCKER GUARD FAILED: `docker start {CONTAINER}` reported success "
            f"but {CONTAINER!r} is still not listed by `docker ps`. Inspect it "
            f"with `docker --context {DOCKER_CONTEXT} logs {CONTAINER}`."
        )


# --- one chain -------------------------------------------------------------

def run_id_for(selection: dict) -> str:
    # arm is included so same1/alt1 slot names never collide across arms.
    return f"validate18-{selection['arm']}-{selection['slot']}-{selection['hyp_id']}"


def run_one(
    selection: dict,
    stages=DEFAULT_STAGES,
    validators=DEFAULT_VALIDATORS,
    lint_fn=lint_paper,
    runs_root=RUNS_ROOT,
) -> dict:
    """Drive one selection through stages 2->5 (then 6+lint on exit). Never
    raises: a chain crash is caught and recorded as status 'crashed'."""
    run_id = run_id_for(selection)
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "log.txt").write_text(
        f"VALIDATION-18 run_id={run_id} arm={selection['arm']} slot={selection['slot']} "
        f"source_run={selection['source_run_id']} hyp={selection['hyp_id']} "
        f"exception_flag={selection['exception_flag']}\n"
    )
    (run_dir / "source.json").write_text(
        json.dumps(
            {
                "report": f"killrate_18_{selection['arm']}b.json",
                "arm": selection["arm"],
                "slot": selection["slot"],
                "source_run_id": selection["source_run_id"],
                "rank": selection["rank"],
                "hyp_id": selection["hyp_id"],
                "exception_flag": selection["exception_flag"],
                "source_exception": selection["exception"],
                "rounds_completed": selection["rounds_completed"],
                "selection_source": selection["selection_source"],
            },
            indent=2,
        )
    )

    result = {
        "arm": selection["arm"],
        "slot": selection["slot"],
        "hyp_id": selection["hyp_id"],
        "source_run_id": selection["source_run_id"],
        "run_id": run_id,
        "exception_flag": selection["exception_flag"],
        "rounds_completed": selection["rounds_completed"],
        "selection_source": selection["selection_source"],
        "status": "completed",
        "stage3_verdict": None,
        "solver_runs_executed": 0,
        "solver_runs_converged": 0,
        "stage4_status": None,
        "stage5_triage": None,
        "stage5_decision": None,
        "survived": False,
        "paper_written": False,
        "lint": None,
        "lint_failures": [],
        "error": None,
    }

    try:
        now = datetime.now(timezone.utc).isoformat()
        baton = Baton(
            run_id=run_id,
            created_at=now,
            mode="auto",
            payload={"domain": selection["domain"], "chosen_hypothesis": selection["chosen_hypothesis"]},
            history=[],
        )
        baton.validate()
        _check(validate_payload_post_gate1, baton.payload, "post-gate-1")
        (run_dir / "baton_before_stage_2.json").write_text(baton.to_json())

        baton = stages["stage2"](baton)
        _snapshot(run_dir, "baton_after_stage_2.json", baton, validators["post_stage2"], "post-stage-2")

        baton = stages["stage3"](baton)
        _snapshot(run_dir, "baton_after_stage_3.json", baton, validators["post_stage3"], "post-stage-3")
        result["stage3_verdict"] = baton.payload["fidelity_verdict"]["label"]

        baton = stages["stage4"](baton)
        _snapshot(run_dir, "baton_after_stage_4.json", baton, validators["post_stage4"], "post-stage-4")
        exec_results = baton.payload["execution_results"]
        result["stage4_status"] = exec_results.get("status")
        runs = exec_results.get("runs", [])
        result["solver_runs_executed"] = len(runs)
        result["solver_runs_converged"] = sum(1 for r in runs if r.get("converged"))

        baton = stages["stage5"](baton)
        _snapshot(run_dir, "baton_after_stage_5.json", baton, validators["post_stage5"], "post-stage-5")
        result["stage5_triage"] = baton.payload["thought"]["surprise_triage"]
        result["stage5_decision"] = baton.payload["iterate_decision"]
        result["survived"] = baton.payload["iterate_decision"] == "exit"

        # NO loop-backs: the chain stops here for every non-exit decision.
        if result["survived"]:
            baton = stages["stage6"](baton)
            baton.validate()
            (run_dir / "baton_after_stage_6.json").write_text(baton.to_json())
            result["paper_written"] = True
            failures = lint_fn(run_id)
            result["lint"] = "PASS" if not failures else "FAIL"
            result["lint_failures"] = failures
    except Exception as exc:  # noqa: BLE001 — a crash is evidence, not batch death
        result["status"] = "crashed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        (run_dir / "crash.txt").write_text(traceback.format_exc())

    (run_dir / "result.json").write_text(json.dumps(result, indent=2))
    return result


def _check(validator, payload, boundary: str) -> None:
    errors = validator(payload)
    if errors:
        raise RuntimeError(f"SCHEMA VIOLATION at {boundary}: {errors}")


def _snapshot(run_dir: Path, name: str, baton: Baton, validator, boundary: str) -> None:
    baton.validate()
    _check(validator, baton.payload, boundary)
    (run_dir / name).write_text(baton.to_json())


# --- batch orchestration ---------------------------------------------------

def summarize(results: list[dict]) -> dict:
    per_arm: dict[str, dict] = {}
    for r in results:
        arm = per_arm.setdefault(
            r["arm"], {"n": 0, "survived": 0, "crashed": 0, "decision_breakdown": {}}
        )
        arm["n"] += 1
        if r["status"] == "crashed":
            arm["crashed"] += 1
            key = "crashed"
        elif r["survived"]:
            arm["survived"] += 1
            key = r["stage5_decision"]
        else:
            key = r["stage5_decision"] or "no_decision"
        arm["decision_breakdown"][key] = arm["decision_breakdown"].get(key, 0) + 1
    for arm in per_arm.values():
        arm["survival_fraction"] = (arm["survived"] / arm["n"]) if arm["n"] else 0.0
    return per_arm


def _banner(results: list[dict], per_arm: dict) -> None:
    print("\n" + "=" * 70)
    print("VALIDATION-18 — single-pass survival batch (stages 2->5, no loop-backs)")
    print("=" * 70)
    for r in results:
        flag = " [EXC-FLAGGED]" if r["exception_flag"] else ""
        if r["status"] == "crashed":
            print(f"  {r['arm']}/{r['slot']} {r['hyp_id']}{flag}: CRASHED — {r['error']}")
            continue
        surv = "SURVIVED" if r["survived"] else "did-not-survive"
        lint = f" lint={r['lint']}" if r["lint"] else ""
        print(
            f"  {r['arm']}/{r['slot']} {r['hyp_id']}{flag}: verdict={r['stage3_verdict']} "
            f"solver={r['solver_runs_converged']}/{r['solver_runs_executed']} "
            f"triage={r['stage5_triage']} decision={r['stage5_decision']} "
            f"-> {surv}{lint}"
        )
    print("-" * 70)
    for arm, s in per_arm.items():
        print(
            f"  ARM {arm}: survived {s['survived']}/{s['n']} "
            f"(fraction {s['survival_fraction']:.2f}); crashed {s['crashed']}; "
            f"decisions {s['decision_breakdown']}"
        )
    print("=" * 70)


def run_batch(reports=REPORTS, runs_root=RUNS_ROOT, report_out=REPORT_OUT) -> dict:
    docker_guard()
    selections = gather_selections(reports, runs_root)
    print(f"VALIDATION-18: {len(selections)} selection(s) across {len(reports)} arm(s); "
          "sequential execution.")
    results = []
    for sel in selections:
        print(f"  -> driving {sel['arm']}/{sel['slot']} {sel['hyp_id']} "
              f"(source {sel['source_run_id']})")
        results.append(run_one(sel, runs_root=runs_root))
    per_arm = summarize(results)
    report = {
        "mode": "validation_batch",
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "reports_consumed": [str(p) for _, p in reports],
        "runs": results,
        "per_arm": per_arm,
    }
    Path(report_out).write_text(json.dumps(report, indent=2))
    _banner(results, per_arm)
    print(f"\nmachine report: {report_out}")
    return report


def print_plan(reports=REPORTS, runs_root=RUNS_ROOT) -> None:
    selections = gather_selections(reports, runs_root)
    print(f"VALIDATION-18 --plan: {len(selections)} selection(s), NOTHING executed.\n")
    for sel in selections:
        flag = " [EXCEPTION-FLAGGED]" if sel["exception_flag"] else ""
        print(f"  {sel['arm']}/{sel['slot']}  rank-1 {sel['hyp_id']}{flag}")
        print(f"      source_run   : {sel['source_run_id']}")
        print(f"      selected_from: {sel['selection_source']}")
        print(f"      rounds_compl : {sel['rounds_completed']}   source_exc: {sel['exception']}")
        print(f"      domain       : {sel['domain'][:70]}")
        print(f"      statement    : {sel['chosen_hypothesis']['statement'][:70]}")
        print(f"      -> new run   : {run_id_for(sel)}")
        print(f"      -> chain     : stage2->3->4->5 (auto, no loop-backs); "
              "stage6+paperlint only if decision==exit\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan", action="store_true",
        help="print selections + intended chains and execute nothing (zero calls)",
    )
    args = parser.parse_args()
    if args.plan:
        print_plan()
    else:
        run_batch()


if __name__ == "__main__":
    main()
