"""
meta_induce.py — Phase-1 Lane-3 meta-induction v1.

ONE Opus pass that reads the cross-run artifacts the system has already
written to disk (learned summaries tagged with their provenance, the
fidelity/override ledgers, the gate-bets headline, the anomaly scanner's
findings, and an offline recompute of the pi-gate sweep) and induces
cross-run RULES: patterns that hold across >= 2 distinct runs.

Boundaries (hard rules for this lane):
  - The induced rules go to a SIDECAR (memory/induced_rules.jsonl, append-only)
    and a human-readable doc (docs/induced_rules_v1.md) ONLY. Nothing any
    pipeline model sees changes: no retrieval wiring, no injected blocks, no
    prompt text. This module is never imported by a stage or the supervisor.
  - The induction call is routed through model_call's transport + validation
    seam, so it inherits the same isolation the gateway enforces (one turn,
    no tools, fresh session, SDK-usage metered into cost_meter via _ask_once).
    It is deliberately capped at 2 attempts (one schema-checked call + at most
    one re-ask) rather than call_stage_model's 3-attempt loop, to honour the
    session's "at most 2 live model calls" budget. There is no run dir, so no
    transcript is written (disclosed) — the sidecar + doc are the record.
  - The digest is composed by deterministic Python from files already on disk.
    No raw solver logs ever enter it; every source is already a summary.

R-MI-1: META_INDUCE_MODEL is a new pin (Opus). No existing pin changes.
"""

from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable, Optional

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

import model_call  # noqa: E402  (repo-root gateway)
import lesson_provenance  # noqa: E402  (tools/ leaf — join helpers)
import pi_gate  # noqa: E402  (tools/ leaf — offline sweep)

# --- pins & paths -----------------------------------------------------------

META_INDUCE_MODEL = "claude-opus-4-8"  # R-MI-1

JOURNAL_PATH = _ROOT / "memory" / "journal.jsonl"
PROVENANCE_PATH = _ROOT / "memory" / "lesson_provenance.jsonl"
FIDELITY_PATH = _ROOT / "memory" / "fidelity_ledger.jsonl"
OVERRIDE_PATH = _ROOT / "memory" / "override_ledger.jsonl"
GATE_BETS_PATH = _ROOT / "harness" / "gate_bets_report.json"
ANOMALY_REPORT_PATH = _ROOT / "tools" / "anomaly_scan_report.md"
SPECS_GLOB = str(_ROOT / "runs" / "**" / "spec.json")

INDUCED_RULES_PATH = _ROOT / "memory" / "induced_rules.jsonl"
DOC_PATH = _ROOT / "docs" / "induced_rules_v1.md"

# ~10k-token cap on the composed digest. Tokens are estimated at the standard
# ~4 chars/token rule of thumb (no tokenizer dependency added).
CHARS_PER_TOKEN = 4
DIGEST_TOKEN_CAP = 10_000
_SUMMARY_TEXT_CAP = 500      # per learned-summary text
_RATIONALE_CAP = 260         # per fidelity rationale

PROVENANCE_BASES = ("measured", "said", "mixed")


# --- digest composition (deterministic, code-authored) ----------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _clip(text: str, cap: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= cap else text[: cap - 1] + "…"


def _learned_summary_lines(
    journal_path: Path, provenance_path: Path
) -> list[str]:
    """Learned summaries JOINED to their lesson_provenance tags.

    Join key is lesson_provenance.stable_key (run_id|hypothesis_id|timestamp).
    Every summary is emitted; an unjoined one is tagged basis=untagged so the
    absence is visible rather than silently dropped.
    """
    prov = {r["key"]: r for r in _read_jsonl(provenance_path)}
    summaries = lesson_provenance.load_learned_summaries(journal_path)
    lines: list[str] = []
    for s in summaries:
        key = lesson_provenance.stable_key(s)
        tag = prov.get(key)
        basis = tag["provenance"] if tag else "untagged"
        rid = s.get("run_id", "?")
        hyp = s.get("hypothesis_id", "?")
        lines.append(f"[{rid} | {hyp} | {basis}] {_clip(s.get('text', ''), _SUMMARY_TEXT_CAP)}")
    return lines


def _fidelity_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for r in _read_jsonl(path):
        lines.append(
            f"{r.get('run_id', '?')} | {r.get('verdict', '?')} | "
            f"{r.get('substrate', '?')} | outcome={r.get('outcome')} | "
            f"{_clip(r.get('rationale', ''), _RATIONALE_CAP)}"
        )
    return lines


def _override_lines(path: Path) -> list[str]:
    lines: list[str] = []
    for r in _read_jsonl(path):
        lines.append(
            f"{r.get('run_id', '?')} | gate {r.get('gate', '?')} | "
            f"system={r.get('system_decision', '?')} | human={r.get('human_decision', '?')} | "
            f"override={r.get('did_override')}"
        )
    return lines


def _gate_bets_headline(path: Path) -> list[str]:
    if not path.exists():
        return ["(no gate_bets_report.json on disk)"]
    d = json.loads(path.read_text())
    return [
        f"n_total={d.get('n_total')} n_resolved={d.get('n_resolved')} "
        f"n_excluded={d.get('n_excluded')} n_unpredictable={d.get('n_unpredictable')} "
        f"cumulative_brier={d.get('cumulative_brier')}",
        "(all entries currently unresolved: no run has recorded a verified "
        "y/n outcome yet, so no Brier score is computable.)",
    ]


def _anomaly_lines(path: Path) -> list[str]:
    """The anomaly scanner's own findings, verbatim, minus the numeric-families
    tail (which is a raw family census, not a finding)."""
    if not path.exists():
        return ["(no anomaly_scan_report.md on disk)"]
    text = path.read_text()
    text = text.split("## Numeric families collected", 1)[0]
    return [ln for ln in text.strip().splitlines() if ln.strip()]


def _pi_sweep_lines(specs_glob: str) -> list[str]:
    """Offline recompute of the pi-gate sweep over every stage-2 spec on disk.

    v1 pi-gate is advisory and never kills; here we only tally its verdicts and
    the most common (value-stripped) reasons across specs. No spec is modified.
    """
    specs = sorted(glob.glob(specs_glob, recursive=True))
    verdicts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    errors = 0
    for s in specs:
        try:
            report = pi_gate.pi_report(json.loads(Path(s).read_text()))
        except Exception as exc:  # a malformed spec must not abort the sweep
            errors += 1
            continue
        v = report.get("verdict", "?")
        verdicts[v] = verdicts.get(v, 0) + 1
        seen_here: set[str] = set()
        for reason in report.get("reasons", []):
            # normalise away specific numbers so reasons cluster across specs
            norm = re.sub(r"[-+]?\d[\d.eE+]*", "N", str(reason))
            norm = re.sub(r"\s+", " ", norm).strip()
            if norm not in seen_here:  # count each pattern once per spec
                seen_here.add(norm)
                reason_counts[norm] = reason_counts.get(norm, 0) + 1
    lines = [
        f"specs swept: {len(specs)}  (parse errors: {errors})",
        "verdicts: " + ", ".join(f"{k}={v}" for k, v in sorted(verdicts.items())),
        "most common flag reasons (spec-count, numbers elided):",
    ]
    for reason, cnt in sorted(reason_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]:
        lines.append(f"  ({cnt}) {reason}")
    return lines


def compose_digest(
    *,
    journal_path: Path = JOURNAL_PATH,
    provenance_path: Path = PROVENANCE_PATH,
    fidelity_path: Path = FIDELITY_PATH,
    override_path: Path = OVERRIDE_PATH,
    gate_bets_path: Path = GATE_BETS_PATH,
    anomaly_report_path: Path = ANOMALY_REPORT_PATH,
    specs_glob: str = SPECS_GLOB,
) -> str:
    """Compose the cross-run digest handed to the induction model.

    All sources are already-summarised on-disk artifacts; no raw logs enter.
    The result is hard-capped at ~DIGEST_TOKEN_CAP tokens (a marker is
    appended if truncation fires).
    """
    sections: list[tuple[str, list[str]]] = [
        ("LEARNED SUMMARIES (joined to lesson-provenance tags)",
         _learned_summary_lines(journal_path, provenance_path)),
        ("FIDELITY-LEDGER VERDICTS", _fidelity_lines(fidelity_path)),
        ("OVERRIDE-LEDGER DECISIONS", _override_lines(override_path)),
        ("GATE-BETS HEADLINE (Brier calibration)", _gate_bets_headline(gate_bets_path)),
        ("ANOMALY-SCANNER FINDINGS", _anomaly_lines(anomaly_report_path)),
        ("PI-GATE SWEEP SUMMARY (offline recompute)", _pi_sweep_lines(specs_glob)),
    ]
    parts: list[str] = []
    for title, lines in sections:
        parts.append(f"=== {title} ===")
        parts.extend(lines if lines else ["(none on disk)"])
        parts.append("")
    digest = "\n".join(parts).rstrip() + "\n"

    cap_chars = DIGEST_TOKEN_CAP * CHARS_PER_TOKEN
    if len(digest) > cap_chars:
        digest = digest[:cap_chars] + "\n[... digest truncated at token cap ...]\n"
    return digest


def digest_size(digest: str) -> dict:
    return {
        "chars": len(digest),
        "est_tokens": (len(digest) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN,
        "token_cap": DIGEST_TOKEN_CAP,
    }


# --- the induction call ------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a meta-induction pass over an autonomous research system's own "
    "cross-run records. You are given a DIGEST assembled from artifacts already "
    "on disk: learned summaries (each tagged measured|said|untagged), fidelity "
    "and override ledgers, a gate-bets calibration headline, an anomaly-scanner "
    "report, and a pi-gate sweep summary.\n\n"
    "Induce RULES: patterns that hold across AT LEAST TWO distinct runs or "
    "artifacts in the digest. A rule must be a general, actionable statement "
    "about how this system behaves or should behave — not a restatement of a "
    "single run. Do NOT invent facts not present in the digest, and do NOT cite "
    "artifacts that are not in it.\n\n"
    "For each rule set provenance_basis to:\n"
    "  measured — every supporting artifact rests on measured on-disk numbers;\n"
    "  said     — supporting artifacts are model-asserted lessons only;\n"
    "  mixed    — a blend of measured and said support.\n\n"
    "Return ONLY a JSON object of the exact form:\n"
    '{\"rules\": [ {\"rule\": \"<statement>\", '
    '\"supporting_artifacts\": [\"<run_id or artifact name>\", ...], '
    '\"provenance_basis\": \"measured|said|mixed\", '
    '\"suggested_scope\": \"<where this rule would apply>\"} ]}\n'
    "supporting_artifacts must name concrete items visible in the digest and "
    "must span >= 2 distinct runs/artifacts. If nothing generalises, return "
    '{\"rules\": []}. No prose outside the JSON object.'
)

INDUCTION_SCHEMA = {"required": ["rules"]}


def validate_induction(data: Any) -> list[str]:
    """Shape check for the induction reply. Returns plain-language errors
    (empty == valid). Zero-artifact rules are NOT rejected here — they are
    dropped by drop_zero_support after acceptance."""
    errors: list[str] = []
    rules = data.get("rules")
    if not isinstance(rules, list):
        return ["'rules' must be a list"]
    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            errors.append(f"rule {i} must be an object")
            continue
        rule_text = r.get("rule")
        if not isinstance(rule_text, str) or not rule_text.strip():
            errors.append(f"rule {i}: 'rule' must be a non-empty string")
        arts = r.get("supporting_artifacts")
        if not isinstance(arts, list) or not all(isinstance(x, str) for x in arts):
            errors.append(f"rule {i}: 'supporting_artifacts' must be a list of strings")
        if r.get("provenance_basis") not in PROVENANCE_BASES:
            errors.append(
                f"rule {i}: 'provenance_basis' must be one of {list(PROVENANCE_BASES)}"
            )
        scope = r.get("suggested_scope")
        if not isinstance(scope, str) or not scope.strip():
            errors.append(f"rule {i}: 'suggested_scope' must be a non-empty string")
    return errors


def _default_transport(system_prompt: str, user_turn: str, model: str) -> str:
    # The standard gateway transport seam (isolation + SDK-usage metering live
    # here). No run_id, so nothing is written to runs/.
    return model_call._transport_with_retry("meta_induce", {}, system_prompt, user_turn, model)


def induce_rules(
    digest: str,
    *,
    model: str = META_INDUCE_MODEL,
    max_attempts: int = 2,
    transport: Optional[Callable[[str, str, str], str]] = None,
) -> dict:
    """One induction pass, capped at max_attempts live calls (default 2: one
    schema-checked call + at most one re-ask). On repeated failure it degrades
    to an honest empty result rather than raising.

    Returns {ok, rules, attempts, error}. rules is the RAW accepted list
    (zero-support dropping is a separate, caller-invoked step)."""
    transport = transport or _default_transport
    last_error = ""
    attempts_used = 0
    for attempt in range(1, max_attempts + 1):
        attempts_used = attempt
        payload: dict = {"digest": digest}
        if attempt > 1:
            payload["validation_error"] = last_error
        reply = transport(SYSTEM_PROMPT, json.dumps(payload), model)

        text, _ = model_call.strip_fence(reply)
        try:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                block = model_call.extract_single_fenced_block(reply)
                if block is None:
                    raise
                data = json.loads(block)
            model_call.validate_schema(data, INDUCTION_SCHEMA)
            errs = validate_induction(data)
            if errs:
                raise model_call.SchemaValidationError("; ".join(errs))
        except (json.JSONDecodeError, model_call.SchemaValidationError) as exc:
            last_error = f"{exc} (raw reply: {reply!r})"
            continue

        return {"ok": True, "rules": data["rules"], "attempts": attempts_used, "error": None}

    return {"ok": False, "rules": [], "attempts": attempts_used, "error": last_error}


def drop_zero_support(rules: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition rules into (kept, dropped) by whether supporting_artifacts is
    non-empty. Code drops any rule citing zero artifacts (HARD RULE)."""
    kept, dropped = [], []
    for r in rules:
        (kept if r.get("supporting_artifacts") else dropped).append(r)
    return kept, dropped


# --- writers -----------------------------------------------------------------

def append_rules(rules: list[dict], out_path: Path = INDUCED_RULES_PATH) -> None:
    """Append accepted rules to the append-only sidecar, one JSON object/line.
    Never truncates or rewrites existing content."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "a") as f:
        for r in rules:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def render_doc(
    rules: list[dict],
    *,
    size: dict,
    live: dict,
    dropped: list[dict],
    out_path: Path = DOC_PATH,
) -> None:
    """Render the human-readable doc: rule + support + basis, plus an honest
    header recording the digest size, the live-call outcome, and any drops."""
    lines = [
        "# Induced rules v1 — meta-induction over cross-run artifacts",
        "",
        "One Opus pass (`META_INDUCE_MODEL = claude-opus-4-8`, R-MI-1) over a "
        "deterministically-composed digest of on-disk artifacts. These rules are "
        "**advisory sidecar output only** — nothing any pipeline model sees was "
        "changed by this pass (no retrieval wiring, no injected blocks, no prompt "
        "text). Provenance basis is the model's, over provenance-tagged inputs.",
        "",
        f"- digest size: {size['chars']} chars ≈ {size['est_tokens']} tokens "
        f"(cap {size['token_cap']})",
        f"- induction call: outcome={'ok' if live['ok'] else 'degraded-empty'}, "
        f"attempts={live['attempts']}",
        f"- rules accepted: {len(rules)}   dropped (zero supporting artifacts): "
        f"{len(dropped)}",
        "",
    ]
    if not live["ok"]:
        lines += [
            "> The induction call did not return a schema-valid result within the "
            "2-attempt budget; the honest empty result stands.",
            f"> Last error: `{live.get('error')}`",
            "",
        ]
    if not rules:
        lines += ["_No rules were accepted._", ""]
    for i, r in enumerate(rules, 1):
        arts = ", ".join(r.get("supporting_artifacts", []))
        lines += [
            f"## Rule {i}",
            "",
            f"**{r.get('rule', '').strip()}**",
            "",
            f"- provenance basis: `{r.get('provenance_basis')}`",
            f"- suggested scope: {r.get('suggested_scope', '').strip()}",
            f"- supporting artifacts: {arts}",
            "",
        ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines).rstrip() + "\n")


# --- orchestration (the one live pass) --------------------------------------

def main() -> int:
    digest = compose_digest()
    size = digest_size(digest)
    print("=== META-INDUCTION v1 ===")
    print(f"digest: {size['chars']} chars ~= {size['est_tokens']} tokens "
          f"(cap {size['token_cap']})")

    live = induce_rules(digest)
    print(f"induction call: ok={live['ok']} attempts={live['attempts']}")
    if not live["ok"]:
        print(f"  degraded to empty; last error: {live['error']}")

    kept, dropped = drop_zero_support(live["rules"])
    if dropped:
        print(f"dropped {len(dropped)} rule(s) citing zero artifacts")

    append_rules(kept)
    render_doc(kept, size=size, live=live, dropped=dropped)
    print(f"accepted {len(kept)} rule(s) -> {INDUCED_RULES_PATH.name}, {DOC_PATH.name}")
    for i, r in enumerate(kept, 1):
        print(f"  R{i} [{r['provenance_basis']}] {r['rule']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
