"""
model_call.py — the ONE shared door between any stage and the model.

call_stage_model(stage_name, system_prompt, stage_input, schema) is the only
function stages use to talk to Claude. Its input is built from exactly its
own arguments (system_prompt + json.dumps(stage_input)) — nothing else is
concatenated in, so there is no code path here by which a transcript, another
stage's output, or any file content could reach the model. Isolation is
enforced the same way the spike's fidelity-gate harness did it: no tools,
no settings, one turn per attempt, fresh session every call.

Structured output is enforced in Python, not trusted from the model: the
reply must parse as JSON and satisfy `schema`, or we re-ask (bounded) with
the validation error appended, and fail loudly after 3 total attempts.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

HAIKU_MODEL = "claude-haiku-4-5-20251001"

MAX_ATTEMPTS = 3

_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebSearch", "WebFetch", "ToolSearch",
]


class SchemaValidationError(Exception):
    """Raised internally when a reply fails schema validation; carries the message re-sent to the model."""


def validate_schema(data: Any, schema: dict) -> None:
    """Check `data` against a small hand-rolled schema dict.

    schema = {
        "required": ["field_a", "field_b"],
        "enums": {"field_b": ["exit"]},   # optional: field_b must be one of these values
    }
    Raises SchemaValidationError with a human-readable reason on failure.
    """
    if not isinstance(data, dict):
        raise SchemaValidationError("reply must be a JSON object")

    for field in schema.get("required", []):
        if field not in data:
            raise SchemaValidationError(f"missing required field: {field}")

    for field, allowed in schema.get("enums", {}).items():
        if field in data and data[field] not in allowed:
            raise SchemaValidationError(
                f"field {field!r} must be one of {allowed}, got {data[field]!r}"
            )


async def _ask_once(system_prompt: str, user_turn: str, model: str) -> str:
    """Send exactly one isolated, tool-free turn to `model` and return its raw text reply."""
    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=[],
        disallowed_tools=_DISALLOWED_TOOLS,
        setting_sources=[],
        max_turns=1,
    )
    parts: list[str] = []
    async for message in query(prompt=user_turn, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
    return "".join(parts).strip()


def strip_fence(reply: str) -> tuple[str, bool]:
    """Detect and remove a surrounding ``` code fence. Pure function, no I/O.

    Returns (stripped_text, was_fenced). Stripping is exactly the tolerance
    the old in-parse version applied: trim whitespace, strip backticks off
    both ends, drop a leading "json" language tag, trim again. Detection is
    separated from JSON parsing so a fence can be recorded whether or not
    the reply then parses.
    """
    text = reply.strip()
    was_fenced = text.startswith("```")
    if was_fenced:
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text, was_fenced


def _log_fence_note(stage_name: str, stage_input: dict) -> None:
    """Durably record a fenced reply the moment it is seen, before any parse.

    Same durable path and same limitation as _log_reask: the run log is
    runs/<run_id>/log.txt with run_id taken from stage_input; without a
    run_id the NOTE is printed but cannot be durably logged. The line format
    matches what log_stage_call used to write, so the fence watch keeps
    counting the same string — but now every fenced reply is counted, not
    only the ones that went on to parse."""
    line = f"NOTE stage={stage_name} fence_stripped — reply arrived wrapped in a ``` code fence"
    print(line)
    run_id = stage_input.get("run_id") if isinstance(stage_input, dict) else None
    if run_id:
        with open(Path("runs") / str(run_id) / "log.txt", "a") as f:
            f.write(line + "\n")


_TRANSCRIPT_SEQ = 0


def _write_transcript(
    stage_name: str,
    system_prompt: str,
    stage_input: dict,
    stage_input_serialized: str,
    model: str,
) -> None:
    """Write the fully assembled model input to runs/<run_id>/transcripts/.

    Called immediately after the model input is assembled and BEFORE the
    model is called, so a crashed call still leaves its transcript. One file
    per call, named <zero-padded per-process sequence>_<stage_name>.json —
    unique and sortable in call order. Contents are exactly
    {stage_name, model, timestamp_utc, system_prompt, stage_input_serialized},
    where stage_input_serialized is the byte-for-byte string sent to the
    model. The transcript captures the attempt-1 assembled input; re-ask
    additions on attempts 2+ are already durably captured verbatim by RE-ASK
    lines in log.txt, so attempt-2+ inputs are reconstructible from this file
    plus those lines.

    Transcripts are WRITE-ONLY evidence: no code path in the project may read
    a transcript back into any model input or any stage logic. Run-dir
    derivation is the same single source of truth as _log_reask /
    _log_fence_note: run_id from stage_input; a bare call without run_id
    writes no transcript.
    """
    run_id = stage_input.get("run_id") if isinstance(stage_input, dict) else None
    if not run_id:
        return
    global _TRANSCRIPT_SEQ
    _TRANSCRIPT_SEQ += 1
    transcripts_dir = Path("runs") / str(run_id) / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "stage_name": stage_name,
        "model": model,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system_prompt": system_prompt,
        "stage_input_serialized": stage_input_serialized,
    }
    with open(transcripts_dir / f"{_TRANSCRIPT_SEQ:04d}_{stage_name}.json", "w") as f:
        json.dump(record, f, indent=2)


def _log_reask(stage_name: str, stage_input: dict, attempt: int, error: str) -> None:
    """Durably record a re-ask the moment it is triggered.

    Appends one line to the same run log log_stage_call writes to
    (runs/<run_id>/log.txt), with the verbatim error JSON-encoded so
    multi-line errors stay on one log line. The run_id comes from
    stage_input — every stage's input carries it, and it is the only
    run-identifying thing this function is allowed to see. If stage_input
    carries no run_id (e.g. a bare unit-test call), the line is printed
    but cannot be durably logged.
    """
    line = f"RE-ASK stage={stage_name} attempt={attempt} error={json.dumps(error)}"
    print(line)
    run_id = stage_input.get("run_id") if isinstance(stage_input, dict) else None
    if run_id:
        with open(Path("runs") / str(run_id) / "log.txt", "a") as f:
            f.write(line + "\n")


def call_stage_model(
    stage_name: str,
    system_prompt: str,
    stage_input: dict,
    schema: dict,
    model: str = HAIKU_MODEL,
    extra_validator: Optional[Callable[[dict], list[str]]] = None,
) -> tuple[dict, dict]:
    """Call `model` for one stage, enforcing isolation and schema, with bounded re-asks.

    `model` defaults to Haiku so stages 2-6 behave byte-identically without
    passing it. `extra_validator`, if given, is a callable parsed_json ->
    list of plain-language error strings (empty = valid); it runs only after
    schema validation passes, and a non-empty list is treated exactly like a
    schema failure — the errors are re-asked within the same bounded loop.
    Returns (validated_dict, timing_info) where timing_info is
    {"model": ..., "duration_seconds": ..., "attempts": N, "fence_stripped": bool}.
    Raises RuntimeError after MAX_ATTEMPTS total failed attempts.
    """
    start = time.monotonic()
    user_turn = json.dumps(stage_input)
    # The input is now fully assembled; record it verbatim before the call.
    _write_transcript(stage_name, system_prompt, stage_input, user_turn, model)
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            user_turn = json.dumps(
                {"original_input": stage_input, "validation_error": last_error}
            )

        reply = asyncio.run(_ask_once(system_prompt, user_turn, model))

        text, fence_stripped = strip_fence(reply)
        if fence_stripped:
            # Recorded here, BEFORE any parse attempt, so a fenced reply that
            # then fails to parse is still counted (the Step-10 undercount).
            _log_fence_note(stage_name, stage_input)

        try:
            data = json.loads(text)
            validate_schema(data, schema)
            if extra_validator is not None:
                extra_errors = extra_validator(data)
                if extra_errors:
                    raise SchemaValidationError(" ".join(extra_errors))
        except (json.JSONDecodeError, SchemaValidationError) as e:
            last_error = f"{e} (raw reply: {reply!r})"
            if attempt < MAX_ATTEMPTS:
                # A re-ask is now certain: persist the correction verbatim so a
                # success-after-re-ask still leaves a recoverable record.
                _log_reask(stage_name, stage_input, attempt, last_error)
            continue

        duration = time.monotonic() - start
        timing_info = {
            "model": model,
            "duration_seconds": round(duration, 3),
            "attempts": attempt,
            "fence_stripped": fence_stripped,
        }
        return data, timing_info

    duration = time.monotonic() - start
    raise RuntimeError(
        f"stage {stage_name!r}: model reply failed schema validation after "
        f"{MAX_ATTEMPTS} attempts ({duration:.3f}s). Last error: {last_error}"
    )


def log_stage_call(run_id: str, stage_name: str, timing: dict) -> None:
    """Append one line to runs/<run_id>/log.txt recording this stage's model call.

    Computes the same log path the supervisor's Logger already created for
    this run_id (runs/<run_id>/log.txt) and appends to it directly — stages
    only receive a baton, never the Logger object, so this is the one place
    that path gets reconstructed.
    """
    line = (
        f"STAGE_MODEL_CALL stage={stage_name} model={timing['model']} "
        f"duration={timing['duration_seconds']}s attempts={timing['attempts']}"
    )
    log_path = Path("runs") / run_id / "log.txt"
    print(line)
    with open(log_path, "a") as f:
        f.write(line + "\n")
    # The fence NOTE is no longer written here: since Step 11 chunk 1 it is
    # recorded by _log_fence_note at the moment of detection, per fenced
    # reply, whether or not that reply parsed.
