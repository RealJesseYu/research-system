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


def _extract_json(reply: str) -> tuple[Any, bool]:
    """Parse reply as JSON, tolerating a leading/trailing code fence.

    Returns (parsed_json, fence_stripped) so the caller can record when the
    tolerance fired, without changing what gets parsed or how.
    """
    text = reply.strip()
    fence_stripped = text.startswith("```")
    if fence_stripped:
        print("NOTE: fence_stripped — reply arrived wrapped in a ``` code fence")
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return json.loads(text), fence_stripped


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
    last_error = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            user_turn = json.dumps(
                {"original_input": stage_input, "validation_error": last_error}
            )

        reply = asyncio.run(_ask_once(system_prompt, user_turn, model))

        try:
            data, fence_stripped = _extract_json(reply)
            validate_schema(data, schema)
            if extra_validator is not None:
                extra_errors = extra_validator(data)
                if extra_errors:
                    raise SchemaValidationError(" ".join(extra_errors))
        except (json.JSONDecodeError, SchemaValidationError) as e:
            last_error = f"{e} (raw reply: {reply!r})"
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
        if timing.get("fence_stripped"):
            f.write(
                f"NOTE stage={stage_name} fence_stripped — reply arrived wrapped in a ``` code fence\n"
            )
