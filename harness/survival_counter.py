"""harness/survival_counter.py — the deep-verification survival-rate counter
(Step 16.6 chunk 4).

Given a completed Stage-1 run dir (runs/<id>/ style), computes the kill-rate
diagnostic's two numbers from artifacts on disk, with NO model calls:

- deep_verify_kill_rate = len(discarded_by_deep_verification)
                          / initial_survivor_count,
  read from stage1/reflection_reviews.json
- k = len(stage1/survivors.json) when that file exists, else 0-with-reason

A run may have RAISED before survivors.json existed. Zero-survivor runs
raise at two distinct code points, and each leaves a distinct file-presence
signature (both verified against the diag4a run dirs on disk):

- reflect_on_pool (stages/reflection_reviews.py) writes
  stage1/reflection_reviews.json and THEN raises when every candidate was
  discarded, so nothing downstream (reflections.json, survivors.json) is
  ever written  -> k=0, reason "deep_verify_discarded_all"
- filter_survivors (stages/stage1_ideation.py) raises when every reflected
  hypothesis was judged 'known', AFTER stage1/reflections.json was written
  but BEFORE survivors.json          -> k=0, reason "all_known_at_filter"

Distinct from both: a run that died BEFORE reflection completed (arXiv/
transport failure, or killed from outside) has NO reflection_reviews.json
and is classified ABORTED — that is not a valid k=0 and must never be
averaged into a survival distribution. The kill rate is still computed
whenever reflection_reviews.json exists, even if survivors.json is absent.

This module is deterministic Python, imports nothing project-local, and
never calls a model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

REFLECTION_REVIEWS = "reflection_reviews.json"
REFLECTIONS = "reflections.json"
SURVIVORS = "survivors.json"
EVOLUTION_VARIANTS = "evolution_variants.json"

# k=0 reason tags (real zero-survivor outcomes, not aborts)
DEEP_VERIFY_DISCARDED_ALL = "deep_verify_discarded_all"
ALL_KNOWN_AT_FILTER = "all_known_at_filter"

STATUS_SCORED = "scored"
STATUS_ABORTED = "aborted"


def _load_json(path: Path) -> Optional[object]:
    """Parse a JSON file; None if absent. A present-but-corrupt file raises —
    that is evidence damage, not a countable outcome."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def count_run(run_dir: Path | str) -> dict:
    """Count one run dir. Never raises on MISSING files (absence is an
    outcome signal); raises only on damaged evidence (unparseable JSON).

    Returns a dict with:
      status                  "scored" | "aborted"
      k                       int for scored runs; None for aborted
      k_reason                reason tag when k == 0; None otherwise
      initial_survivor_count  from reflection_reviews.json, when it exists
      deep_verify_discards    from reflection_reviews.json, when it exists
      deep_verify_kill_rate   discards / initial survivors (float), when
                              computable; None otherwise
      abort_reason            for aborted runs: what is missing
      files_present           the stage1/ filenames actually on disk
      variants_emitted        Step 17-D, ADDITIVE: record count in
                              stage1/evolution_variants.json (each record is
                              one variant slot Evolution attempted, emission
                              failures included as accepted-false records);
                              0 when the file is absent (pre-17-D runs)
      variants_accepted       accepted-true records in that file; 0 when
                              absent. Variants NEVER enter k — k stays
                              len(survivors.json), byte-identical to 17-C.
      variants_emitted_total  17-CLOSE, ADDITIVE: run-total emission count.
                              Under the 17-E controller the canonical
                              stage1/evolution_variants.json is the LAST
                              SUCCESSFUL round's file, so variants_emitted /
                              variants_accepted above are last-round numbers;
                              the *_total fields sum across every round dir
                              (stage1/round*/evolution_variants.json) when
                              round dirs exist. For a single-pass run with no
                              round dirs the totals equal the canonical
                              file's counts — both semantics coincide.
      variants_accepted_total accepted-true records summed the same way.
    """
    run_dir = Path(run_dir)
    stage1 = run_dir / "stage1"
    files_present = (
        sorted(p.name for p in stage1.iterdir()) if stage1.is_dir() else []
    )

    result: dict = {
        "run_dir": str(run_dir),
        "status": None,
        "k": None,
        "k_reason": None,
        "initial_survivor_count": None,
        "deep_verify_discards": None,
        "deep_verify_kill_rate": None,
        "abort_reason": None,
        "files_present": files_present,
        "variants_emitted": 0,
        "variants_accepted": 0,
        "variants_emitted_total": 0,
        "variants_accepted_total": 0,
    }

    # Step 17-D, ADDITIVE ONLY: Evolution's variant counts, read from its
    # evidence file when present. Absent file (every pre-17-D run) -> 0/0,
    # never an error. Nothing below this block changed.
    variants = _load_json(stage1 / EVOLUTION_VARIANTS)
    if isinstance(variants, list):
        result["variants_emitted"] = len(variants)
        result["variants_accepted"] = sum(
            1 for v in variants if isinstance(v, dict) and v.get("accepted") is True
        )

    # 17-CLOSE, ADDITIVE ONLY: run-total variant counts. When 17-E round
    # dirs exist, sum every round's evolution_variants.json (a round that
    # halted before Evolution simply has no file and contributes 0);
    # otherwise the totals are the canonical file's counts, already read
    # above. Nothing else changed.
    round_dirs = (
        sorted(d for d in stage1.glob("round*") if d.is_dir())
        if stage1.is_dir()
        else []
    )
    if round_dirs:
        emitted_total = accepted_total = 0
        for round_dir in round_dirs:
            round_variants = _load_json(round_dir / EVOLUTION_VARIANTS)
            if isinstance(round_variants, list):
                emitted_total += len(round_variants)
                accepted_total += sum(
                    1
                    for v in round_variants
                    if isinstance(v, dict) and v.get("accepted") is True
                )
        result["variants_emitted_total"] = emitted_total
        result["variants_accepted_total"] = accepted_total
    else:
        result["variants_emitted_total"] = result["variants_emitted"]
        result["variants_accepted_total"] = result["variants_accepted"]

    # 18-hygiene (n=1 live, killrate-20260714T001356Z-same1): under the 17-E
    # iteration controller the canonical stage1/*.json are the LAST SUCCESSFUL
    # round's files. When round 1 ITSELF has zero survivors the run crashes
    # honestly with no successful round, so its reflection evidence lives ONLY
    # in stage1/round1/ — canonical stage1/reflection_reviews.json is never
    # written. Reading only stage1/ then misclassifies that legitimate
    # zero-survivor scientific outcome as an infra abort and charges a
    # relaunch. Fix: when the canonical file is absent, fall back to the LAST
    # round dir that completed reflection and count the outcome from there.
    reviews_source = stage1
    if not (stage1 / REFLECTION_REVIEWS).exists() and round_dirs:
        for round_dir in reversed(round_dirs):
            if (round_dir / REFLECTION_REVIEWS).exists():
                reviews_source = round_dir
                result["counted_from_round_dir"] = round_dir.name
                break

    reviews = _load_json(reviews_source / REFLECTION_REVIEWS)

    # Kill rate: computable whenever reflection_reviews.json exists, even if
    # the run then raised and survivors.json never appeared.
    if reviews is not None:
        initial = reviews.get("initial_survivor_count")
        discards = reviews.get("discarded_by_deep_verification")
        result["initial_survivor_count"] = initial
        result["deep_verify_discards"] = (
            len(discards) if isinstance(discards, list) else None
        )
        if isinstance(initial, int) and initial > 0 and isinstance(discards, list):
            result["deep_verify_kill_rate"] = len(discards) / initial

    if reviews is None:
        # The run died before reflection completed (retrieval/transport
        # failure or killed from outside), in EVERY round it started. NOT a
        # valid k=0 — this is the genuine infra-death path.
        result["status"] = STATUS_ABORTED
        result["abort_reason"] = (
            f"no {REFLECTION_REVIEWS} in stage1/ or any round dir — the run "
            "died before reflection completed (e.g. retrieval failure or "
            "killed); not a valid k=0"
        )
        return result

    survivors = _load_json(reviews_source / SURVIVORS)
    if survivors is not None:
        result["status"] = STATUS_SCORED
        result["k"] = len(survivors)
        # filter_survivors raises rather than writing an empty file, so a
        # present-but-empty survivors.json is a shape we have never seen;
        # tag it honestly instead of inventing a mechanism for it.
        if result["k"] == 0:
            result["k_reason"] = "empty_survivors_file_unexpected"
        return result

    # reflection_reviews.json exists but survivors.json does not: one of the
    # two zero-survivor raises fired. Distinguish by file presence. This is a
    # legitimate zero-survivor scientific outcome (SCORED k=0), NOT an abort —
    # including the round-1-crash case reached via reviews_source above.
    result["status"] = STATUS_SCORED
    result["k"] = 0
    if (reviews_source / REFLECTIONS).exists():
        # reflections.json written, then filter_survivors raised.
        result["k_reason"] = ALL_KNOWN_AT_FILTER
    else:
        # reflect_on_pool wrote its evidence file and raised immediately.
        result["k_reason"] = DEEP_VERIFY_DISCARDED_ALL
    return result


# ---------------------------------------------------------------------------
# Validation against the diag4a diagnostic's own counting (Part 2 of the
# chunk-4 spec): recompute every diag4a run dir and cross-check against
# harness/diag4a_reference/diag4a_analysis.json. Zero model calls.
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ANALYSIS_PATH = Path(__file__).resolve().parent / "diag4a_reference" / "diag4a_analysis.json"


def _diagnostic_numbers(entry: dict) -> tuple[float, int]:
    """The diagnostic's own kill rate and k, derived from its analysis file:
    kill = len(deepverify_discards)/initial_survivors; k = len(filter_survivors)
    with the analysis's null (failed run) meaning zero survivors."""
    kill = len(entry["deepverify_discards"]) / entry["initial_survivors"]
    fs = entry["filter_survivors"]
    k = len(fs) if isinstance(fs, list) else 0
    return kill, k


def validate_against_diag4a() -> bool:
    """Print the Part-2 validation table; True only if every scored dir
    matches the diagnostic's own numbers AND every non-scored dir is
    classified ABORTED."""
    analysis = json.loads(_ANALYSIS_PATH.read_text())
    scored_by_run_id = {entry["run_id"]: (tag, entry) for tag, entry in analysis.items()}

    all_dirs = sorted((_PROJECT_ROOT / "runs").glob("diag4a-*"))
    all_ok = True

    print("PART-2 VALIDATION — survival counter vs the diag4a diagnostic's own counting")
    print(f"{'run dir':<38} {'mine kill%':>10} {'mine k':>6} {'diag kill%':>10} {'diag k':>6}  verdict")
    aborted_rows = []
    for d in all_dirs:
        mine = count_run(d)
        if d.name in scored_by_run_id:
            tag, entry = scored_by_run_id[d.name]
            diag_kill, diag_k = _diagnostic_numbers(entry)
            match = (
                mine["status"] == STATUS_SCORED
                and mine["deep_verify_kill_rate"] == diag_kill
                and mine["k"] == diag_k
            )
            all_ok = all_ok and match
            print(
                f"{d.name:<38} "
                f"{mine['deep_verify_discards']}/{mine['initial_survivor_count']}={mine['deep_verify_kill_rate'] * 100:>3.0f}% "
                f"{mine['k']:>6} "
                f"{len(entry['deepverify_discards'])}/{entry['initial_survivors']}={diag_kill * 100:>3.0f}% "
                f"{diag_k:>6}  {'MATCH' if match else '*** MISMATCH ***'}"
                + (f"  [{tag}, k_reason={mine['k_reason']}]" if mine["k_reason"] else f"  [{tag}]")
            )
        else:
            ok = mine["status"] == STATUS_ABORTED
            all_ok = all_ok and ok
            aborted_rows.append(
                f"{d.name:<38} {mine['status'].upper():<8}"
                + ("" if ok else " *** EXPECTED ABORTED ***")
                + f"  ({mine['abort_reason']})"
            )
    print()
    print("non-scored dirs (must all classify ABORTED, never k=0):")
    for row in aborted_rows:
        print(f"  {row}")
    print()
    print("VALIDATION:", "ALL MATCH" if all_ok else "*** MISMATCH — counter bug, do not trust ***")
    return all_ok


if __name__ == "__main__":
    import sys

    if "--validate" in sys.argv[1:]:
        sys.exit(0 if validate_against_diag4a() else 1)
    for arg in sys.argv[1:]:
        print(json.dumps(count_run(arg), indent=2))
