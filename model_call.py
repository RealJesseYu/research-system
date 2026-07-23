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
import contextlib
import contextvars
import inspect
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Optional

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    query,
)

import capability_guard
import cost_meter
from models import model_for  # model-tier resolver

HAIKU_MODEL = model_for("triage")

MAX_ATTEMPTS = 3

# The repo root — used to keep substrate wrappers (tools.run_*) importable from
# a tooled agent whose cwd is a per-run workspace elsewhere on disk.
_PROJECT_ROOT = Path(__file__).resolve().parent

# Per-run WORKSPACE for a TOOLED agent (the free experimenter). The caller sets
# it via agent_workspace(); a tooled call then runs with the SDK cwd there, so
# the agent's Bash/Read/Write land in runs/<id>/workspace/ instead of the repo
# root. Ambient (a ContextVar) rather than threaded through the transport-retry
# seam, which does signature introspection a new positional arg would disturb.
# None (the default) => the SDK's own cwd (the repo root), so every SEALED stage
# and every non-workspace call is byte-identical to before.
_AGENT_CWD: "contextvars.ContextVar[Optional[str]]" = contextvars.ContextVar(
    "agent_cwd", default=None
)


@contextlib.contextmanager
def agent_workspace(path):
    """Run the tooled calls inside this block with the agent's working directory
    set to `path` (its private per-run workspace). `path=None` is a no-op — the
    agent keeps the default cwd (repo root). Sealed calls make no tool calls, so
    this never affects them."""
    token = _AGENT_CWD.set(str(path) if path else None)
    try:
        yield
    finally:
        _AGENT_CWD.reset(token)


def _workspace_option_kwargs(uses_tools: bool) -> dict:
    """The cwd + env kwargs for ClaudeAgentOptions when a tooled agent has an
    active workspace; {} otherwise (SDK default cwd, byte-identical old path).

    PYTHONPATH is set to the repo root (prepended to any inherited value) so a
    substrate wrapper import — `from tools.run_rdkit import run_rdkit` — still
    resolves from the workspace. The SDK MERGES this env onto the inherited
    process env, so PATH and everything else survive."""
    cwd = _AGENT_CWD.get()
    if not (uses_tools and cwd):
        return {}
    existing = os.environ.get("PYTHONPATH", "")
    pythonpath = str(_PROJECT_ROOT) + (os.pathsep + existing if existing else "")
    return {"cwd": cwd, "env": {"PYTHONPATH": pythonpath}}


# Optional MCP CONNECTORS for a TOOLED agent (the free experimenter). A project
# file, mcp_servers.json, lists MCP servers the free agent may reach — a CAD
# tool, a domain API, anything speaking the Model Context Protocol — as a
# {"<name>": {<McpServerConfig>}} map (the exact dict the SDK's mcp_servers
# takes: stdio {type,command,args,env} or http/sse {type,url,headers}). Absent
# or empty => no connectors, byte-identical. Gitignored: it may carry URLs and
# keys. Each configured server's tools are permitted as mcp__<name>; the
# capability guard still vets every call, so a connector cannot reach memory/,
# runs/, or credentials. This is the path to genuinely-new, domain-agnostic
# capability — the owner drops in a connector config, no code change.
_MCP_CONFIG_PATH = _PROJECT_ROOT / "mcp_servers.json"


def load_mcp_servers(path=None) -> dict:
    """The {name: config} MCP-server map from mcp_servers.json, or {} when the
    file is absent, empty, or malformed. NEVER raises — a broken connector
    config must not take down every run; it degrades to no connectors."""
    path = Path(path) if path else _MCP_CONFIG_PATH
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    # Tolerate either a bare {name: config} map or {"servers": {...}}.
    if isinstance(data, dict) and isinstance(data.get("servers"), dict):
        data = data["servers"]
    return data if isinstance(data, dict) else {}


def _mcp_option_kwargs(uses_tools: bool) -> tuple:
    """(options_kwargs, extra_allowed_tools) wiring the configured MCP connectors
    into a tooled call; ({}, []) when the call is sealed or none are configured.
    strict_mcp_config keeps the agent to OUR configured servers only — never
    whatever a stray user/project settings file happens to define."""
    if not uses_tools:
        return {}, []
    servers = load_mcp_servers()
    if not servers:
        return {}, []
    allowed = [f"mcp__{name}" for name in servers]
    return {"mcp_servers": servers, "strict_mcp_config": True}, allowed

_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebSearch", "WebFetch", "ToolSearch",
]

# ---------------------------------------------------------------------------
# CAPABILITY PROFILES (owner-ruled 2026-07-20 — the autonomy inversion).
#
# Until now every stage went through this door with allowed_tools=[] and
# max_turns=1: one blind shot, no way to look anything up, no way to see a
# result and react. That was not an oversight — it is what "the supervisor is
# deterministic Python", "typed batons, never transcripts" and "tool output
# summarized at the wrapper" require. But it was applied to EVERY stage, when
# it was only ever needed on the path that produces measurements.
#
# Two different activities were being governed by one rule:
#
#   EXECUTION  — where a number comes from. Must be reproducible and auditable,
#                because a fabricated measurement is fraud, not a bug. Stays
#                sealed, exactly as before.
#   DISCOVERY  — reading, searching, exploring, deciding what is worth asking.
#                Produces context, never claims. Sealing it bought nothing and
#                cost the project its premise.
#
# The guarantee that mattered does not move with the tools: it is re-sited at
# the END, in the verification pass, where every number that reaches a paper
# must come with an artifact that regenerates it. Permission up front is
# replaced by verification at the back.
#
# SEALED is the default, so every existing call site is byte-identical until
# it explicitly opts in.
# ---------------------------------------------------------------------------


class Capabilities:
    """What one stage may do at this door. Frozen by convention — profiles are
    module constants and must never be mutated in place, or a stage could
    silently widen another stage's powers."""

    __slots__ = ("name", "allowed_tools", "max_turns")

    def __init__(self, name: str, allowed_tools: tuple, max_turns: int):
        self.name = name
        self.allowed_tools = tuple(allowed_tools)
        self.max_turns = max_turns

    @property
    def uses_tools(self) -> bool:
        return bool(self.allowed_tools)

    def __repr__(self) -> str:  # appears in transcripts and logs
        return f"Capabilities({self.name!r}, tools={list(self.allowed_tools)}, max_turns={self.max_turns})"


# SEALED — the historical behavior: one turn, no tools. Kept for one narrow
# purpose only (see the pairing table in capability_guard.py): a stage that
# JUDGES A MEASUREMENT must not be able to look up the answer it is grading.
# It is no longer the default for anything else.
SEALED = Capabilities("sealed", (), 1)

# FULL — a Claude Code agent, undiminished. This is what a stage gets now.
#
# There is no tiering here, deliberately. An earlier version of this file split
# capability into "discovery" (read and search) and "builder" (also write and
# run), which was just a smaller cage with more moving parts: an agent that
# must ask permission to write a file is not autonomous, it is supervised. The
# unit of this system is a Claude Code agent, and a Claude Code agent loops,
# reads, searches, writes code and runs it. Anything less is the thing that
# made every stage in this project a blind one-shot function.
#
# The turn budget is high rather than unlimited for the same reason the campaign
# budget is: a loop that never terminates produces nothing. It is a backstop,
# not a leash.
FULL = Capabilities(
    "full",
    ("WebSearch", "WebFetch", "Read", "Glob", "Grep", "Write", "Edit", "Bash",
     "NotebookEdit", "TodoWrite"),
    200,
)

# Retained as aliases so nothing that already named them breaks; both now mean
# FULL. The distinction they encoded was not a real one.
DISCOVERY = FULL
BUILDER = FULL

PROFILES = {p.name: p for p in (SEALED, FULL)}


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


async def _ask_once(
    system_prompt: str, user_turn: str, model: str,
    capabilities: "Capabilities" = None, action_trail: list = None,
    stage_name: str = "unknown",
) -> str:
    """Send one isolated turn (or, under a tool-bearing profile, one bounded
    agentic loop) to `model` and return its final text reply.

    When `action_trail` is provided it is filled with every tool use and tool
    result observed. That is not optional bookkeeping: a sealed call is fully
    described by its assembled input, so the transcript alone reproduces it,
    but a tool-bearing call does things the input does not determine. Without
    the trail, "transcripts are write-only evidence" would quietly become
    false the moment a stage was given a tool — the audit trail would name the
    question and lose the entire investigation.
    """
    caps = capabilities or SEALED
    # Step 16.6 chunk 2: record the ATTEMPT before the SDK call fires, so a
    # transport failure mid-stream still leaves a trace in the meter.
    cost_meter.record_attempt("model_call")
    # Optional MCP connectors: extra allowed tools (mcp__<name>) plus the
    # mcp_servers/strict_mcp_config kwargs, empty unless mcp_servers.json exists.
    mcp_kwargs, mcp_allowed = _mcp_option_kwargs(caps.uses_tools)
    options = ClaudeAgentOptions(
        model=model,
        system_prompt=system_prompt,
        allowed_tools=list(caps.allowed_tools) + mcp_allowed,
        # Everything not explicitly granted stays blocked, so a widened profile
        # can never silently inherit a tool nobody listed.
        disallowed_tools=[t for t in _DISALLOWED_TOOLS if t not in caps.allowed_tools],
        setting_sources=[],
        max_turns=caps.max_turns,
        # The guard consults every tool call before it runs. Sealed calls make
        # no tool calls, so attaching it there would be dead weight.
        **({"can_use_tool": capability_guard.make_can_use_tool(stage_name)}
           if caps.uses_tools else {}),
        # Per-run workspace: an isolated cwd (+ PYTHONPATH to the repo root) when
        # the caller wrapped this in agent_workspace(); {} otherwise, so the
        # default-cwd path is unchanged.
        **_workspace_option_kwargs(caps.uses_tools),
        # Configured MCP connectors (a CAD tool, a domain API, …); {} unless
        # mcp_servers.json is present, so the no-connector path is unchanged.
        **mcp_kwargs,
    )
    # The SDK requires STREAMING input (an AsyncIterable) whenever a
    # can_use_tool callback is attached — a bare string prompt is rejected with
    # "can_use_tool callback requires streaming mode". Sealed calls have no
    # callback and keep the plain string path unchanged. For tool-bearing calls
    # we wrap the single user turn in a one-message stream that mirrors the exact
    # envelope the SDK builds for a string prompt; stream_input ends input when
    # the generator is exhausted, so the bounded agentic loop still runs once.
    prompt_arg = user_turn
    if caps.uses_tools:
        async def _single_turn_stream():
            yield {
                "type": "user",
                "message": {"role": "user", "content": user_turn},
                "parent_tool_use_id": None,
                "session_id": "",
            }
        prompt_arg = _single_turn_stream()

    parts: list[str] = []
    result_usage = None
    async for message in query(prompt=prompt_arg, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
                elif action_trail is not None and isinstance(block, ToolUseBlock):
                    action_trail.append({
                        "kind": "tool_use",
                        "tool": block.name,
                        "input": _bounded(block.input),
                    })
        elif isinstance(message, UserMessage) and action_trail is not None:
            # Tool RESULTS arrive as user-role messages. They are bounded here
            # because a raw result (a full web page, a directory listing) is
            # exactly the unbounded tool output the architecture forbids from
            # reaching any downstream reader.
            content = message.content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, ToolResultBlock):
                        action_trail.append({
                            "kind": "tool_result",
                            "content": _bounded(block.content),
                        })
        elif isinstance(message, ResultMessage):
            result_usage = message.usage
    # Step 16.6: the ONE observing touch at this door — count the completed
    # call (+ SDK-reported usage) into the shared cost meter. Observation
    # only; the return value is untouched.
    cost_meter.record_call("model_call", result_usage)
    # Under a tool profile the model's LAST text block is its answer; earlier
    # blocks are narration between tool calls and would corrupt the JSON parse
    # if concatenated. A sealed call has exactly one block, so joining and
    # taking the last are identical there — the default path is unchanged.
    if caps.uses_tools and parts:
        return parts[-1].strip()
    return "".join(parts).strip()


MAX_TRAIL_CHARS = 2000


def _bounded(value) -> str:
    """Render any tool input/result as a bounded string for the action trail."""
    try:
        text = value if isinstance(value, str) else json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= MAX_TRAIL_CHARS:
        return text
    return text[:MAX_TRAIL_CHARS] + f" [...truncated, {len(text)} chars total]"


# Backoff before transport retry 1 and retry 2 (Step 16: initial attempt +
# at most 2 retries; the Step-15 crashed demo proved an SDK exception used
# to propagate uncaught).
TRANSPORT_RETRY_BACKOFFS = (2.0, 5.0)


def _invoke_transport(
    system_prompt: str, user_turn: str, model: str,
    capabilities: "Capabilities" = None, action_trail: list = None,
    stage_name: str = "unknown",
) -> str:
    """The ONE SDK invocation seam — exactly the old asyncio.run(_ask_once(...))
    call site, factored out (Step 16, disclosed) so tests can substitute a
    fake transport by patching this function.

    capabilities/action_trail are keyword-optional and default to the sealed
    behavior, so every existing fake transport with the three-argument
    signature keeps working untouched."""
    return asyncio.run(
        _ask_once(system_prompt, user_turn, model, capabilities, action_trail,
                  stage_name)
    )


def _seam_accepts_capabilities() -> bool:
    """True when the current _invoke_transport can take the capability
    arguments. Recomputed per call because the seam is monkeypatched at
    runtime; a cached answer would be wrong for the next test."""
    try:
        params = inspect.signature(_invoke_transport).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in params.values()):
        return True
    return "capabilities" in params


def _log_transport_retry(stage_name: str, stage_input: dict, retry_number: int, exc: Exception) -> None:
    """Durably record one transport retry the moment it is decided.

    Same run-dir derivation and same bare-call limitation as RE-ASK lines:
    run_id from stage_input; without one, the line is printed but cannot be
    durably logged."""
    first_line = str(exc).splitlines()[0] if str(exc) else ""
    line = (
        f"TRANSPORT-RETRY stage={stage_name} retry={retry_number} "
        f"exception={type(exc).__name__}: {first_line}"
    )
    print(line)
    run_id = stage_input.get("run_id") if isinstance(stage_input, dict) else None
    if run_id:
        with open(Path("runs") / str(run_id) / "log.txt", "a") as f:
            f.write(line + "\n")


def _transport_with_retry(
    stage_name: str, stage_input: dict, system_prompt: str, user_turn: str, model: str,
    capabilities: "Capabilities" = None, action_trail: list = None,
) -> str:
    """Bounded transport retry around _invoke_transport (Step 16).

    Catches Exception from the transport/SDK layer ONLY — our own
    SchemaValidationError and json.JSONDecodeError are raised later, in
    parsing/validation, and never enter this path. Initial attempt plus at
    most len(TRANSPORT_RETRY_BACKOFFS) retries with short backoff; each
    retry writes a durable TRANSPORT-RETRY line; exhaustion re-raises the
    original exception unwrapped. The validation re-ask counter is
    UNTOUCHED: transport retries correct DELIVERY, the validation loop
    corrects CONTENT — the two bounds never interact."""
    # A TOOLED call is NOT idempotent: it may already have written files or run
    # commands before the transport died, and blindly replaying the whole
    # agentic loop would re-commit every one of those side effects with nothing
    # rolling them back or even noticing. A sealed call has no side effects, so
    # it keeps the full retry budget it has always had.
    tooled = capabilities is not None and capabilities is not SEALED and capabilities.uses_tools
    budget = 0 if tooled else len(TRANSPORT_RETRY_BACKOFFS)

    for transport_try in range(1 + budget):
        try:
            # The seam is patched by fakes throughout the test suite, and
            # those fakes were written against the historical 3-argument
            # signature. Pass only what the current callable actually accepts,
            # so adding capabilities did not silently invalidate every
            # contract test by making it raise TypeError instead of asserting.
            if _seam_accepts_capabilities():
                return _invoke_transport(
                    system_prompt, user_turn, model, capabilities, action_trail,
                    stage_name,
                )
            return _invoke_transport(system_prompt, user_turn, model)
        except Exception as exc:
            if transport_try == budget:
                raise
            _log_transport_retry(stage_name, stage_input, transport_try + 1, exc)
            time.sleep(TRANSPORT_RETRY_BACKOFFS[transport_try])
    raise RuntimeError("unreachable")  # loop always returns or raises


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


def extract_single_fenced_block(reply: str) -> str | None:
    """Single-fence prose tolerance (17-CLOSE). Pure function, no I/O.

    When a reply contains EXACTLY one ``` fenced block, return the block's
    content (a leading language tag like ```json dropped), with leading and
    trailing prose around the fence tolerated. No fence or multiple fences
    return None, so the caller keeps its existing failure path untouched.
    Provenance: the Step-22 smoke crash (runs/smoke6-20260711T083510Z in the
    build-22 worktree) — reflect replies wrapped their JSON in prose plus one
    fence and burned the whole re-ask budget; strip_fence only handles a
    reply that IS a fence, not one that CONTAINS a fence.
    """
    if reply.count("```") != 2:
        return None
    inner = reply.split("```", 2)[1]
    first_line, newline, rest = inner.partition("\n")
    if newline and re.fullmatch(r"[A-Za-z0-9_+-]*", first_line.strip()):
        inner = rest
    return inner.strip()


def extract_json_object(reply: str) -> str | None:
    """Prose-wrapped-object tolerance. Pure function, no I/O.

    A FULL/tooled agent that does real work NARRATES, then emits its JSON with
    no fence — 'Both methods agree.\\n\\n{...}'. strip_fence and
    extract_single_fenced_block only handle fences, so such a reply burns the
    whole re-ask budget (first seen live: the free_experimenter Collatz run,
    2026-07-23). Return the substring of the LAST top-level {...} in the reply
    that parses as JSON, or None. Uses json.JSONDecoder.raw_decode so braces
    inside strings are handled correctly; 'last wins' picks the final result
    object when prose earlier in the reply also contains a JSON-looking span.
    """
    decoder = json.JSONDecoder()
    found = None
    idx = 0
    while True:
        start = reply.find("{", idx)
        if start == -1:
            break
        try:
            _obj, end = decoder.raw_decode(reply, start)
            found = reply[start:end]
            idx = end
        except json.JSONDecodeError:
            idx = start + 1
    return found


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
    capabilities: "Capabilities" = SEALED,
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
        # The profile is part of the evidence: the same input under SEALED and
        # under BUILDER are different experiments, and a reader who cannot tell
        # them apart cannot judge the result.
        "capabilities": capabilities.name,
        "allowed_tools": list(capabilities.allowed_tools),
        "max_turns": capabilities.max_turns,
    }
    with open(transcripts_dir / f"{_TRANSCRIPT_SEQ:04d}_{stage_name}.json", "w") as f:
        json.dump(record, f, indent=2)


def _append_action_trail(
    stage_name: str, stage_input: dict, attempt: int, trail: list
) -> None:
    """Append one attempt's tool-use trail beside its transcript.

    A separate <seq>_<stage>.actions.json rather than a rewrite of the
    transcript, because the transcript is written BEFORE the call and that
    write-first property is what makes it survive a crash. Rewriting it
    afterwards would trade a guarantee for tidiness.

    Still write-only evidence: nothing in the project may read these back into
    a model input or stage logic.
    """
    run_id = stage_input.get("run_id") if isinstance(stage_input, dict) else None
    if not run_id:
        return
    transcripts_dir = Path("runs") / str(run_id) / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    path = transcripts_dir / f"{_TRANSCRIPT_SEQ:04d}_{stage_name}.actions.json"
    existing = []
    if path.is_file():
        try:
            existing = json.loads(path.read_text())
        except (ValueError, OSError):
            existing = []
    existing.append({"attempt": attempt, "actions": trail})
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    tools_used = [a["tool"] for a in trail if a.get("kind") == "tool_use"]
    line = (
        f"ACTIONS stage={stage_name} attempt={attempt} "
        f"tool_calls={len(tools_used)} tools={sorted(set(tools_used))}"
    )
    print(line)
    with open(Path("runs") / str(run_id) / "log.txt", "a") as f:
        f.write(line + "\n")


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
    capabilities: "Capabilities" = SEALED,
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
    # Enforced BEFORE anything else: a stage whose role forbids tools must not
    # even assemble a tooled call. Raises CapabilityPairingError.
    capability_guard.assert_profile_allowed(stage_name, capabilities.name)

    start = time.monotonic()
    user_turn = json.dumps(stage_input)
    # The input is now fully assembled; record it verbatim before the call.
    _write_transcript(stage_name, system_prompt, stage_input, user_turn, model,
                      capabilities)
    last_error = ""
    # Filled by the transport under a tool profile; appended to the transcript
    # after the call so the evidence covers what the stage DID, not only what
    # it was asked. Stays empty (and unwritten) for a sealed call.
    action_trail: list = []

    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempt > 1:
            user_turn = json.dumps(
                {"original_input": stage_input, "validation_error": last_error}
            )

        reply = _transport_with_retry(
            stage_name, stage_input, system_prompt, user_turn, model,
            capabilities, action_trail,
        )
        if action_trail:
            _append_action_trail(stage_name, stage_input, attempt, action_trail)
            action_trail = []
        # Step 18.7: attribute this COMPLETED call to its stage (the door-level
        # record_call cannot see stage_name). Observation only.
        cost_meter.record_stage_call(stage_name)

        text, fence_stripped = strip_fence(reply)
        if fence_stripped:
            # Recorded here, BEFORE any parse attempt, so a fenced reply that
            # then fails to parse is still counted (the Step-10 undercount).
            _log_fence_note(stage_name, stage_input)

        try:
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 17-CLOSE single-fence tolerance: the current parse path
                # above is unchanged; only on ITS failure, a reply carrying
                # exactly one fenced block is retried as that block's
                # content (prose around the fence tolerated). None means no
                # rescue — re-raise the original error, existing behavior.
                block = extract_single_fenced_block(reply)
                if block is None:
                    # No fence — a full/tooled agent narrated then emitted raw
                    # JSON. Extract the embedded object (prime-directive reality:
                    # a free agent that does real work explains itself). None =>
                    # no rescue, re-raise (existing behavior).
                    block = extract_json_object(reply)
                if block is None:
                    raise
                data = json.loads(block)
            validate_schema(data, schema)
            if extra_validator is not None:
                extra_errors = extra_validator(data)
                if extra_errors:
                    raise SchemaValidationError(" ".join(extra_errors))
        except (json.JSONDecodeError, SchemaValidationError) as e:
            last_error = f"{e} (raw reply: {reply!r})"
            if attempt < MAX_ATTEMPTS:
                # A re-ask is now certain: persist the correction verbatim so a
                # success-after-re-ask still leaves a recoverable record, and
                # count the REJECT into the stage-keyed meter (Step 18.7 —
                # observation only; the loop's behavior is unchanged).
                cost_meter.record_reject(stage_name)
                _log_reask(stage_name, stage_input, attempt, last_error)
            continue

        duration = time.monotonic() - start
        timing_info = {
            "model": model,
            "duration_seconds": round(duration, 3),
            "attempts": attempt,
            "fence_stripped": fence_stripped,
            "capabilities": capabilities.name,
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
