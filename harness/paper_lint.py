"""
harness/paper_lint.py — the Step-22 paper lint: pure, deterministic,
ZERO model calls, importable.

lint_paper(run_id) checks one run's stage-6 output on disk:

  - runs/<run_id>/stage6/paper_validation.json (the sidecar) exists and
    parses;
  - its fidelity_class equals the stage-3 verdict label read from disk
    (runs/<run_id>/stage3/verdict.json) — the sidecar may never contradict
    the run's actual fidelity verdict;
  - runs/<run_id>/stage6/paper.md exists and contains the mandatory
    "What Humans Must Validate" markdown heading;
  - the class-conditional validation_items rules hold (see
    validate_validation_items — the ONE shape authority, shared with
    stage 6's drafting validator so the drafter and the lint can never
    disagree):
      trust  -> exactly one item {"kind": "none_required", "reason": ...}
      refine -> >= 1 item, each exactly {"claim": ...} naming the QoI or
                claim needing downstream validation
      defer  -> >= 1 item, each exactly {"substrate", "conditions",
                "measurement"} — a concrete test spec another instrument
                could run.

The return value is a MACHINE-READABLE failure list — one dict
{"code", "target", "message"} per failure, empty list = lint clean. The
"target" names what must be regenerated ("sidecar", "verdict", "paper",
or a section name) and is what stage 6's error-feedback regeneration loop
keys on. This module never raises on malformed input: everything wrong
becomes a failure entry, in validate_spec's plain-language style.

Items are shape-checked against the sidecar's own DECLARED class (when it
is a valid label), so a class mismatch and a shape defect surface as
separate, independently actionable failures.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# Mirrors schemas.VERDICT_LABELS; restated here so the lint stays a
# standalone pure module with no import into the stage/schema layer.
VERDICT_LABELS = ("trust", "refine", "defer")

REQUIRED_HEADING = "What Humans Must Validate"

_HEADING_RE = re.compile(
    r"^#{1,6}\s+" + re.escape(REQUIRED_HEADING) + r"\s*$", re.MULTILINE
)

TRUST_ITEM_KEYS = ("kind", "reason")
REFINE_ITEM_KEYS = ("claim",)
DEFER_ITEM_KEYS = ("substrate", "conditions", "measurement")


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _check_item_keys(
    item: dict, allowed: tuple, label: str, errors: list[str]
) -> None:
    for key in allowed:
        if not _is_non_empty_str(item.get(key)):
            errors.append(
                f"{label} {key} must be a non-empty string; got {item.get(key)!r}."
            )
    for key in item:
        if key not in allowed:
            errors.append(
                f"{label} field '{key}' is not allowed — it carries exactly: "
                f"{', '.join(allowed)}."
            )


def validate_validation_items(fidelity_class: str, items: Any) -> list[str]:
    """The class-conditional validation_items rules, as plain-language error
    strings (empty = valid). Pure; never raises. Shared by stage 6's
    sidecar-drafting extra_validator and by lint_paper below."""
    errors: list[str] = []
    if not isinstance(items, list) or not items:
        return [
            "validation_items must be a non-empty list of validation items; "
            f"got {items!r}."
        ]
    if fidelity_class == "trust":
        if len(items) != 1:
            errors.append(
                "a trust-class sidecar carries exactly ONE validation item "
                f"(kind none_required); got {len(items)}."
            )
        for n, item in enumerate(items, start=1):
            label = f"validation item {n}"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object.")
                continue
            if item.get("kind") != "none_required":
                errors.append(
                    f"{label} kind must be exactly 'none_required' for a "
                    f"trust-class sidecar; got {item.get('kind')!r}."
                )
            _check_item_keys(item, TRUST_ITEM_KEYS, label, errors)
    elif fidelity_class == "refine":
        for n, item in enumerate(items, start=1):
            label = f"validation item {n}"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object.")
                continue
            _check_item_keys(item, REFINE_ITEM_KEYS, label, errors)
    elif fidelity_class == "defer":
        for n, item in enumerate(items, start=1):
            label = f"validation item {n}"
            if not isinstance(item, dict):
                errors.append(f"{label} must be an object.")
                continue
            _check_item_keys(item, DEFER_ITEM_KEYS, label, errors)
    else:
        errors.append(
            f"fidelity_class must be exactly one of {' | '.join(VERDICT_LABELS)}; "
            f"got {fidelity_class!r}."
        )
    return errors


def _failure(code: str, target: str, message: str) -> dict:
    return {"code": code, "target": target, "message": message}


def _read_json(path: Path) -> tuple[Any, str | None]:
    """(parsed, None) on success, (None, plain-language reason) on failure."""
    try:
        return json.loads(path.read_text()), None
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as e:
        return None, str(e).splitlines()[0] if str(e) else type(e).__name__


def lint_paper(run_id: str, runs_root: Path = Path("runs")) -> list[dict]:
    """Lint one run's stage-6 output. Returns the machine-readable failure
    list described in the module docstring; empty list = lint clean."""
    run_dir = runs_root / str(run_id)
    verdict_path = run_dir / "stage3" / "verdict.json"
    sidecar_path = run_dir / "stage6" / "paper_validation.json"
    paper_path = run_dir / "stage6" / "paper.md"
    failures: list[dict] = []

    # --- stage-3 verdict (the ground truth the sidecar must match) ----------
    verdict_label = None
    if not verdict_path.is_file():
        failures.append(
            _failure(
                "verdict_missing",
                "verdict",
                f"no stage-3 verdict at {verdict_path} — the sidecar's "
                "fidelity_class cannot be checked against the run's verdict.",
            )
        )
    else:
        verdict, reason = _read_json(verdict_path)
        if verdict is None:
            failures.append(
                _failure(
                    "verdict_unparseable",
                    "verdict",
                    f"stage-3 verdict at {verdict_path} did not parse: {reason}",
                )
            )
        elif not isinstance(verdict, dict) or verdict.get("label") not in VERDICT_LABELS:
            got = verdict.get("label") if isinstance(verdict, dict) else verdict
            failures.append(
                _failure(
                    "verdict_invalid",
                    "verdict",
                    f"stage-3 verdict label must be one of "
                    f"{' | '.join(VERDICT_LABELS)}; got {got!r}.",
                )
            )
        else:
            verdict_label = verdict["label"]

    # --- sidecar -------------------------------------------------------------
    if not sidecar_path.is_file():
        failures.append(
            _failure(
                "sidecar_missing",
                "sidecar",
                f"no validation sidecar at {sidecar_path}.",
            )
        )
    else:
        sidecar, reason = _read_json(sidecar_path)
        if sidecar is None:
            failures.append(
                _failure(
                    "sidecar_unparseable",
                    "sidecar",
                    f"validation sidecar at {sidecar_path} did not parse: {reason}",
                )
            )
        elif not isinstance(sidecar, dict):
            failures.append(
                _failure(
                    "sidecar_not_object",
                    "sidecar",
                    "the validation sidecar must be a JSON object with exactly "
                    "fidelity_class and validation_items.",
                )
            )
        else:
            fidelity_class = sidecar.get("fidelity_class")
            if fidelity_class not in VERDICT_LABELS:
                failures.append(
                    _failure(
                        "fidelity_class_invalid",
                        "sidecar",
                        f"sidecar fidelity_class must be exactly one of "
                        f"{' | '.join(VERDICT_LABELS)}; got {fidelity_class!r}.",
                    )
                )
            elif verdict_label is not None and fidelity_class != verdict_label:
                failures.append(
                    _failure(
                        "class_mismatch",
                        "sidecar",
                        f"sidecar fidelity_class {fidelity_class!r} does not "
                        f"equal the stage-3 verdict label {verdict_label!r} "
                        "read from disk.",
                    )
                )
            if fidelity_class in VERDICT_LABELS:
                # Shape-check against the DECLARED class so a mismatch and a
                # shape defect stay separate, independently actionable failures.
                for error in validate_validation_items(
                    fidelity_class, sidecar.get("validation_items")
                ):
                    failures.append(_failure("items_invalid", "sidecar", error))
            elif "validation_items" not in sidecar:
                failures.append(
                    _failure(
                        "items_missing",
                        "sidecar",
                        "the validation sidecar carries no validation_items.",
                    )
                )
            for key in sidecar:
                if key not in ("fidelity_class", "validation_items"):
                    failures.append(
                        _failure(
                            "sidecar_extra_key",
                            "sidecar",
                            f"sidecar field '{key}' is not allowed — the sidecar "
                            "carries exactly fidelity_class and validation_items.",
                        )
                    )

    # --- paper ---------------------------------------------------------------
    if not paper_path.is_file():
        failures.append(
            _failure("paper_missing", "paper", f"no paper at {paper_path}.")
        )
    else:
        try:
            paper_text = paper_path.read_text()
        except (OSError, UnicodeDecodeError) as e:
            paper_text = None
            failures.append(
                _failure(
                    "paper_unreadable",
                    "paper",
                    f"paper at {paper_path} could not be read: "
                    f"{str(e).splitlines()[0]}",
                )
            )
        if paper_text is not None and not _HEADING_RE.search(paper_text):
            failures.append(
                _failure(
                    "heading_missing",
                    REQUIRED_HEADING,
                    f"paper.md is missing the mandatory markdown heading "
                    f"'{REQUIRED_HEADING}'.",
                )
            )

    return failures
