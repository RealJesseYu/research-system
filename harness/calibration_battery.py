"""harness/calibration_battery.py — Step 26: the substrate calibration battery.

Scores the REAL fidelity gate against the pre-registered FEA and code
calibration cases (docs/fea_calibration_cases_v1.md,
docs/code_calibration_cases_v1.md), and — the design point of this battery —
SEPARATES the gate's RAW pre-hook verdict from the ROUTED post-hook outcome, so
one launch yields TWO products:

  1. THE GATE'S CALIBRATION — raw_verdict scored against the case label, reported
     as a CONFUSION matrix (never a single accuracy number), gate cases only.
  2. THE SAFETY HOOK WITNESS — for every gate case the real Step-28 maturity hook
     (supervisor.apply_substrate_maturity_hook, imported, never copied) is fired
     on the raw verdict and its effect recorded: hook_fired, routed_outcome, and
     the standing invariant ZERO SILENT TRUSTS (no trust/refine verdict is ever
     silently routed on a non-mature substrate).

RATIFIED DESIGN (the fidelity_case_runner precedent, Step 16.6 chunk 3): gate
cases go through the DIRECT call_stage_model path — the FROZEN stage-3
SYSTEM_PROMPT / SCHEMA / _validate_verdict imported from
stages.stage3_fidelity_gate — with EACH CASE'S OWN substrate/envelope/experiment
prompt_inputs. It does NOT go through stage3_fidelity_gate.run(), because run()
hardcodes CAVITY_2D_CONTRACT (an FEA or code spec judged against the cavity CFD
contract is meaningless) and run() appends to the production fidelity ledger.

CRITICAL INVARIANTS
  * LEDGER-SILENT: this module never calls any ledger writer. It is a test, not
    a real experiment.
  * NO RUN DIRS: calls are BARE (no "run_id" in stage_input), so model_call's
    run-dir machinery prints but writes nothing under runs/.
  * HOOK BYTE-IDENTITY: the hook is imported from supervisor.py and NOT modified;
    routing behavior is unchanged by one byte. The battery captures raw_verdict
    BEFORE calling the hook and routed_outcome AFTER, purely by ordering — no
    logging was added to any frozen file.
  * RULE-1 (spike carry-over): the answer key never reaches the model. stage_input
    is built from prompt fields alone, asserted free of any answer-key key.

WRAPPER-BEHAVIOR CASES (setup_error) are scored SEPARATELY and NEVER averaged in
with gate cases: they are run through the wrapper's own validator (run_fea
._validate_input / run_code.validate_spec — imported and called, the wrappers are
never modified), asserting valid=False with the pre-registered reason. These
reject before any solver/container, so they need no docker.

This is a separate --mode calibration (with --substrate); it is NOT part of FAST's
hard gate. It SPENDS MODEL CALLS (one Opus fidelity call per gate case) and must
be launched from a plain Terminal per the run-venue rule — never a builder-session
background task.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cost_meter  # noqa: E402
from baton import Baton  # noqa: E402
from model_call import call_stage_model  # noqa: E402
from stages.stage3_fidelity_gate import (  # noqa: E402
    OPUS_MODEL,
    SCHEMA,
    SYSTEM_PROMPT,
    VALID_LABELS,
    _validate_verdict,
)
from supervisor import apply_substrate_maturity_hook  # noqa: E402  (the REAL hook)
from tools import substrate_registry as registry  # noqa: E402

STAGE_NAME = "calibration_fidelity_case"

# substrate_id -> (case file, wrapper validator callable, wrapper exception class)
_CASE_FILES = {
    "calculix_cantilever_fea": "calibration_cases_fea.json",
    "code_sklearn_eval": "calibration_cases_code.json",
}

# Answer-key keys that must never appear in what the model is sent (RULE-1).
# This blocklist equals (gate-case keys) - {"id", "experiment"} today — the two
# fields that map into the model-visible stage_input ("id"->case_id, "experiment"
# verbatim). Everything else on a gate case is answer key. A drift test
# (tests/test_calibration_battery.py) fails if any gate case gains a hidden field
# this blocklist does not know, so it cannot silently fall out of coverage.
_ANSWER_KEY_KEYS = ("expected_class", "acceptable_labels", "note", "right_instrument")

# Gate-case fields that DO legitimately reach the model (the allowlist the
# blocklist is the complement of). Used only by the drift test's derivation.
_MODEL_VISIBLE_GATE_FIELDS = ("id", "experiment")


def _assert_no_answer_key_leak(stage_input: dict, case_id: str) -> None:
    """RULE-1 tripwire: abort if any answer-key key name appears in the serialized
    model input. EXTRACTED from run_gate_case so it can be exercised directly with
    a LEAKING input — a guard wired only into the known-safe construction path can
    never fire, and a check that cannot fail is not a proof. Kept as `assert`
    (mechanism unchanged): no launch path uses `python -O`, so stripping is not
    reachable; if one is ever added this must become an explicit `raise`."""
    serialized = json.dumps(stage_input)
    leaked = [k for k in _ANSWER_KEY_KEYS if f'"{k}"' in serialized]
    assert not leaked, f"ANSWER KEY LEAK in case {case_id}: {leaked} — aborting"


class _CollectingLogger:
    """Duck-typed logger for the imported hook: the hook only calls .log().
    Collects lines instead of writing a run-dir log (NO RUN DIRS invariant)."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, line: str) -> None:
        self.lines.append(line)


def _wrapper_validator(substrate_id: str):
    """Return (callable(spec)->None|raises, exception_class) for the substrate's
    OWN wrapper validator. Imported and CALLED; the wrappers are never modified."""
    if substrate_id == "calculix_cantilever_fea":
        from tools.run_fea import FeaInputError, _validate_input

        return _validate_input, FeaInputError
    if substrate_id == "code_sklearn_eval":
        from tools.run_code import CodeSpecError, validate_spec

        return validate_spec, CodeSpecError
    raise KeyError(f"no wrapper validator wired for substrate {substrate_id!r}")


def load_cases(substrate_id: str, harness_dir: Path | None = None) -> dict:
    """Load a substrate's calibration case file. Fails loudly on a malformed
    file BEFORE any model call."""
    harness_dir = harness_dir or Path(__file__).resolve().parent
    if substrate_id not in _CASE_FILES:
        raise KeyError(
            f"unknown substrate {substrate_id!r}; known: {sorted(_CASE_FILES)}"
        )
    data = json.loads((harness_dir / _CASE_FILES[substrate_id]).read_text())
    if data.get("substrate_id") != substrate_id:
        raise ValueError(
            f"case file substrate_id {data.get('substrate_id')!r} != {substrate_id!r}"
        )
    for gc in data["gate_cases"]:
        bad = [lbl for lbl in gc["acceptable_labels"] if lbl not in VALID_LABELS]
        if bad:
            raise ValueError(f"gate case {gc['id']} acceptable_labels has non-vocabulary {bad}")
        if not gc["acceptable_labels"]:
            raise ValueError(f"gate case {gc['id']} has empty acceptable_labels")
    return data


def witness_hook(raw_verdict: dict, mode: str) -> dict:
    """Fire the REAL maturity hook on a copy of the raw verdict and record its
    effect. The raw verdict is deep-copied so the caller's record is never
    mutated by the in-place downgrade. Returns
    {hook_fired, routed_outcome, signoff_substrates}."""
    baton = Baton(
        run_id=f"calib-witness-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}",
        created_at=datetime.now(timezone.utc).isoformat(),
        mode=mode,
        payload={"fidelity_verdict": copy.deepcopy(raw_verdict)},
    )
    logger = _CollectingLogger()
    apply_substrate_maturity_hook(logger, baton, mode)
    signoff = getattr(baton, "_maturity_signoff", None)
    hook_fired = bool(isinstance(signoff, dict) and signoff.get("required"))
    return {
        "hook_fired": hook_fired,
        "routed_outcome": baton.payload["fidelity_verdict"]["label"],
        "signoff_substrates": (signoff or {}).get("substrates", []) if hook_fired else [],
        "hook_log": logger.lines,
    }


def run_gate_case(data: dict, gate_case: dict, mode: str) -> dict:
    """One gate case: build input -> ONE frozen-prompt Opus call -> capture the
    RAW verdict -> fire the real hook -> score raw vs the case's acceptable set."""
    stage_input = {
        "case_id": gate_case["id"],
        "substrate": data["substrate_text"],
        "envelope": data["envelope_text"],
        "experiment": gate_case["experiment"],
    }
    # RULE-1 tripwire: no answer-key key may be in what the model sees.
    _assert_no_answer_key_leak(stage_input, gate_case["id"])

    start = time.perf_counter()
    result, timing = call_stage_model(
        STAGE_NAME,
        SYSTEM_PROMPT,
        stage_input,
        SCHEMA,
        model=OPUS_MODEL,
        extra_validator=_validate_verdict,
    )
    wall = time.perf_counter() - start

    raw = result["verdict"]
    raw_label = raw["label"]
    hook = witness_hook(raw, mode)
    return {
        "case_id": gate_case["id"],
        "track": "gate",
        "expected_class": gate_case["expected_class"],
        "acceptable_labels": list(gate_case["acceptable_labels"]),
        "raw_verdict": raw_label,
        "routed_outcome": hook["routed_outcome"],
        "hook_fired": hook["hook_fired"],
        "signoff_substrates": hook["signoff_substrates"],
        "passed": raw_label in gate_case["acceptable_labels"],
        "rationale": raw["rationale"],
        "right_instrument": raw["right_instrument"],
        "wall_time_seconds": round(wall, 3),
        "reask_attempts": timing["attempts"],
    }


def run_wrapper_case(substrate_id: str, wrapper_case: dict) -> dict:
    """One wrapper-behavior (setup_error) case: call the substrate's OWN validator
    and assert it rejects with the pre-registered reason. No model, no container."""
    validate, exc_class = _wrapper_validator(substrate_id)
    start = time.perf_counter()
    valid = True
    reason = ""
    try:
        validate(wrapper_case["spec"])
    except exc_class as e:  # the wrapper's typed rejection
        valid = False
        reason = str(e)
    except Exception as e:  # any other exception is still a rejection, flagged
        valid = False
        reason = f"[UNEXPECTED {type(e).__name__}] {e}"
    wall = time.perf_counter() - start

    substr = wrapper_case["reason_substring"]
    reason_matched = (substr in reason)
    # PASS iff the wrapper rejected (valid=False as expected) AND the reason
    # carries the pre-registered substring.
    passed = (valid == wrapper_case["expect_valid"]) and reason_matched
    return {
        "case_id": wrapper_case["id"],
        "track": "wrapper",
        "expected_class": wrapper_case["expected_class"],
        "wrapper_valid": valid,
        "expect_valid": wrapper_case["expect_valid"],
        "wrapper_reason": reason,
        "reason_substring": substr,
        "reason_matched": reason_matched,
        "passed": passed,
        "wall_time_seconds": round(wall, 3),
    }


def build_confusion(gate_records: list[dict]) -> dict:
    """Confusion matrix over gate cases: expected_class -> {trust, refine, defer}
    counts of the RAW verdict. Reported instead of a single accuracy number."""
    matrix: dict[str, dict[str, int]] = {}
    for r in gate_records:
        row = matrix.setdefault(r["expected_class"], {lbl: 0 for lbl in VALID_LABELS})
        row[r["raw_verdict"]] += 1
    return matrix


def hook_summary(gate_records: list[dict], mode: str) -> dict:
    """The safety-hook witness product. The standing invariant is ZERO SILENT
    TRUSTS: no gate case is left with a routed 'trust' on a non-mature substrate.
    The hook fires exactly on raw trust/refine verdicts (a raw defer routes
    nowhere, so the hook correctly no-ops); this is asserted, not assumed."""
    n_gate = len(gate_records)
    trust_refine = [r for r in gate_records if r["raw_verdict"] in ("trust", "refine")]
    n_hook_fired = sum(1 for r in gate_records if r["hook_fired"])
    # Invariant checks (recorded, not thrown — the report is the evidence):
    hook_matches_raw = all(
        r["hook_fired"] == (r["raw_verdict"] in ("trust", "refine")) for r in gate_records
    )
    silent_trusts = [
        r["case_id"] for r in gate_records if r["routed_outcome"] == "trust"
    ]
    # In auto mode every trust/refine is downgraded, so routed_outcome is never
    # trust; in human mode the verdict is untouched but the signoff is still
    # recorded, so a routed 'trust' is NOT silent (it carries needs_human_signoff).
    silent_trusts_unflagged = [
        r["case_id"]
        for r in gate_records
        if r["routed_outcome"] == "trust" and not r["hook_fired"]
    ]
    return {
        "mode": mode,
        "n_gate_cases": n_gate,
        "n_raw_trust_or_refine": len(trust_refine),
        "n_hook_fired": n_hook_fired,
        "hook_fired_matches_raw_trust_refine": hook_matches_raw,
        "routed_trust_case_ids": silent_trusts,
        "silent_trust_case_ids": silent_trusts_unflagged,
        "zero_silent_trusts": not silent_trusts_unflagged,
        "note": (
            "The hook fires on raw trust/refine only (defer routes nowhere). "
            "It is keyed to the registry routable set (currently "
            f"{list(registry.routable_ids())}, all non-mature), NOT to the "
            "substrate under calibration, which is UNROUTABLE — see debrief."
        ),
    }


def run_battery(substrate_id: str, mode: str = "auto",
                report_path: Path | None = None) -> int:
    data = load_cases(substrate_id)
    batch_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = Path(report_path) if report_path is not None else (
        Path(__file__).resolve().parent / f"calibration_{substrate_id}_{batch_ts}.json"
    )

    cost_meter.reset()
    from memory import ledgers

    fidelity_before = ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH)
    override_before = ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH)

    start = time.perf_counter()
    gate_records = [run_gate_case(data, gc, mode) for gc in data["gate_cases"]]
    wrapper_records = [
        run_wrapper_case(substrate_id, wc) for wc in data["wrapper_cases"]
    ]
    wall = time.perf_counter() - start
    meter = cost_meter.read()

    report = {
        "mode_arg": mode,
        "substrate_id": substrate_id,
        "maturity_at_run": registry.maturity_of(substrate_id),
        "routable_at_run": registry.get(substrate_id).routable,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "batch_id": batch_ts,
        "gate": {
            "n_cases": len(gate_records),
            "n_passed": sum(1 for r in gate_records if r["passed"]),
            "confusion": build_confusion(gate_records),
            "hook_witness": hook_summary(gate_records, mode),
            "cases": gate_records,
        },
        "wrapper_behavior": {
            "n_cases": len(wrapper_records),
            "n_passed": sum(1 for r in wrapper_records if r["passed"]),
            "cases": wrapper_records,
            "note": "scored separately from gate cases; never averaged together",
        },
        "cost": {
            "model_calls": meter["model_calls"],
            "attempts": meter["attempts"],
            "tokens": meter["tokens"],
            "wall_time_seconds": round(wall, 3),
        },
        "ledger_activity": {
            "fidelity_entries": ledgers.count_entries(ledgers.FIDELITY_LEDGER_PATH)
            - fidelity_before,
            "override_entries": ledgers.count_entries(ledgers.OVERRIDE_LEDGER_PATH)
            - override_before,
        },
    }

    print_report(report)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    print(f"\nreport written to {report_path}")
    # Exit code: RED if any wrapper-behavior case failed (deterministic, should
    # never fail) OR the zero-silent-trusts invariant broke. The GATE calibration
    # is NOT a pass/fail gate — it is measured, so gate misses never set the code.
    ok = (
        report["wrapper_behavior"]["n_passed"] == report["wrapper_behavior"]["n_cases"]
        and report["gate"]["hook_witness"]["zero_silent_trusts"]
        and report["gate"]["hook_witness"]["hook_fired_matches_raw_trust_refine"]
        and report["ledger_activity"]["fidelity_entries"] == 0
        and report["ledger_activity"]["override_entries"] == 0
    )
    return 0 if ok else 1


def print_report(report: dict) -> None:
    g = report["gate"]
    w = report["wrapper_behavior"]
    hw = g["hook_witness"]
    print()
    print("=" * 18 + f" CALIBRATION BATTERY: {report['substrate_id']} " + "=" * 18)
    print(
        f"maturity={report['maturity_at_run']} routable={report['routable_at_run']} "
        f"mode={report['mode_arg']}"
    )
    print()
    print("-- PRODUCT 1: GATE CALIBRATION (raw pre-hook verdict vs label) --")
    for r in g["cases"]:
        mark = "OK " if r["passed"] else "XX "
        print(
            f"  {mark}{r['case_id']:>4} [{r['expected_class']:<16}] "
            f"raw={r['raw_verdict']:<6} routed={r['routed_outcome']:<6} "
            f"hook={'fired' if r['hook_fired'] else 'no-op':<5} "
            f"accept={r['acceptable_labels']}  {r['wall_time_seconds']}s"
        )
    print(f"  gate cases scored-in-band: {g['n_passed']}/{g['n_cases']} "
          "(band membership, NOT a pass/fail gate)")
    print()
    print("  CONFUSION (expected_class -> raw verdict counts):")
    header = "    " + " " * 18 + "".join(f"{lbl:>8}" for lbl in VALID_LABELS)
    print(header)
    for cls, row in g["confusion"].items():
        print("    " + f"{cls:<18}" + "".join(f"{row[lbl]:>8}" for lbl in VALID_LABELS))
    print()
    print("-- PRODUCT 2: SAFETY HOOK WITNESS --")
    print(f"  raw trust/refine verdicts: {hw['n_raw_trust_or_refine']}/{hw['n_gate_cases']}")
    print(f"  hook fired:                {hw['n_hook_fired']}  "
          f"(matches raw trust/refine: {hw['hook_fired_matches_raw_trust_refine']})")
    print(f"  routed 'trust' cases:      {hw['routed_trust_case_ids']}")
    print(f"  ZERO SILENT TRUSTS:        {hw['zero_silent_trusts']}  "
          f"(silent: {hw['silent_trust_case_ids']})")
    print(f"  hook keying note: {hw['note']}")
    print()
    print("-- WRAPPER-BEHAVIOR (setup_error; scored SEPARATELY, no model/container) --")
    for r in w["cases"]:
        mark = "OK " if r["passed"] else "XX "
        print(
            f"  {mark}{r['case_id']:>4} valid={r['wrapper_valid']} "
            f"matched={r['reason_matched']}  reason={r['wrapper_reason'][:60]!r}"
        )
    print(f"  wrapper-behavior: {w['n_passed']}/{w['n_cases']} rejected as pre-registered")
    print()
    la = report["ledger_activity"]
    print(f"  LEDGER ACTIVITY (must be 0/0): fidelity={la['fidelity_entries']} "
          f"override={la['override_entries']}")
    print(f"  COST: model_calls total={report['cost']['model_calls'].get('total')} "
          f"wall={report['cost']['wall_time_seconds']}s")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Step-26 substrate calibration battery.")
    parser.add_argument("--substrate", required=True, choices=sorted(_CASE_FILES))
    parser.add_argument("--mode", default="auto", choices=["auto", "human"],
                        help="hook mode: auto downgrades trust/refine in place; "
                             "human leaves the verdict untouched (both record signoff)")
    parser.add_argument("--report-path", default=None,
                        help="per-launch report file (default: "
                             "calibration_<substrate>_<UTC>.json)")
    args = parser.parse_args(argv)
    return run_battery(args.substrate, args.mode, args.report_path)


if __name__ == "__main__":
    raise SystemExit(main())
