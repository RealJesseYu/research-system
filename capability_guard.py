"""
capability_guard.py — what a tooled stage may NOT touch, enforced in code.

Granting stages tools (model_call.Capabilities) re-opened three holes that the
old allowed_tools=[] closed by accident rather than by design. Prose cannot
close them again: "anything we can't afford to have broken goes in code, not in
a prompt." This module is that code — a can_use_tool callback the SDK consults
before every tool call, plus the stage->profile pairing that decides which
stages may hold tools at all.

THE THREE HOLES.

1. TRANSCRIPT READ-BACK. runs/<id>/transcripts/ holds every assembled model
   input. The architecture's hardest isolation rule is that no stage sees
   another stage's context — "a read-back would be a covert channel between
   fresh contexts." Read/Glob/Grep at a predictable path is exactly that
   channel. Denied.

2. ANSWER-KEY LEAK. Calibration and battery files carry expected_class /
   acceptable_labels for the very judgments the gate stages make. A gate that
   can grep its own answer key is not a gate, and a calibration measured
   through one is worthless. Denied — and reinforced by the pairing below,
   which keeps those stages tool-free in the first place.

3. EVIDENCE AND MEMORY MUTATION. memory/*.jsonl are append-only by discipline
   and are read by the deterministic supervisor; runs/ is append-only evidence.
   BUILDER grants Write/Edit/Bash. A stage that can rewrite the journal can
   rewrite what the next run believes, and the supervisor's "NO AI calls in
   this file" stays literally true while its inputs become model-authored.
   Denied.

WHAT IS DELIBERATELY ALLOWED. Reading source, reading docs, searching the web,
writing scratch files, running code in a sandbox. The point of the inversion is
that discovery roams; the guard exists so that roaming cannot reach into the
evidence, the memory, or another context.

This is a floor, not a proof. Bash argument inspection is textual and a
determined adversary could evade it; the model here is a capable agent that
might stumble somewhere it shouldn't, not one trying to escape. The verification
pass, not this file, is what makes a fabricated RESULT detectable.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent

# Protected path segments. Written WITHOUT a leading separator and matched at a
# boundary, because a first pass used "/memory/" and cheerfully allowed
# Write(memory/journal.jsonl) — the relative form, which is exactly how every
# call site in this project writes a path. A guard that only catches the
# absolute form is not a guard.
_BOUNDARY = r"(?:^|[\s\"'`=:,(\[]|\.{1,2}/|/)"


def _seg(fragment: str) -> re.Pattern:
    return re.compile(_BOUNDARY + re.escape(fragment))


_READ_DENY = tuple(_seg(f) for f in (
    "transcripts/",            # hole 1: cross-context covert channel
    "calibration_",            # hole 2: gate answer keys
    "acceptable_labels",
    "expected_class",
    "harness/last_run",
    "harness/killrate_last_run",
    "harness/validation_batch",
    # Credentials. Read-denied as well as write-denied: a stage has no reason
    # to see the MP or S2 keys, and anything it reads can reach a transcript.
    ".env",
    "credentials",
    "id_rsa",
))

_WRITE_DENY = tuple(_seg(f) for f in (
    "memory/",                 # hole 3: journal + ledgers the supervisor reads
    "runs/",                   # append-only evidence
    "cases_",                  # substrate case evidence
    "transcripts/",            # hole 1, write side: see _AGENT_WORKSPACE below
    ".env",                    # credentials
    ".git/",
))

# THE AGENT'S OWN WORKSPACE IS NOT EVIDENCE IT MAY NOT TOUCH.
#
# A tooled agent's cwd is runs/<id>/workspace (model_call._workspace_option_kwargs),
# so every absolute path it writes there — and every Bash command naming one —
# contains "runs/" and was denied outright. An agent that resolves `pwd` before
# writing, which is the natural thing to do, was told its own scratch directory
# was append-only run evidence and had to route around its own task. That is the
# cage the PRIME DIRECTIVE forbids, built by a path pattern rather than a policy.
#
# The exemption is narrow and positional: occurrences of runs/<id>/workspace are
# masked out of the text BEFORE the deny patterns run, so a path inside the
# workspace no longer presents a bare "runs/" to match. Any OTHER runs/ reference
# in the same command still trips the deny — including runs/<id>/transcripts,
# which is why transcripts/ also joins the write list above: the read side was
# always guarded, but Write/Edit consult only _WRITE_DENY, so a stage sitting in
# the workspace could rewrite the write-only evidence one directory up.
# The trailing boundary is load-bearing: without it "runs/A/workspaces_backup"
# matched on its prefix and the exemption swallowed a sibling directory that is
# ordinary run evidence.
_AGENT_WORKSPACE = re.compile(r"runs/[^/\s\"'`]+/workspace(?![^/\s\"'`])")

_READ_TOOLS = ("Read", "Glob", "Grep", "NotebookRead")
_WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")

# Shell verbs that mutate. A Bash call naming a protected path is denied
# outright regardless of verb (reads of the journal are a leak too), so this
# list only exists to make the denial message accurate about what was seen.
_MUTATING_SHELL = re.compile(
    r"\b(rm|mv|cp|tee|truncate|sed\s+-i|>|>>|dd|chmod|chown|git\s+(add|commit|push|checkout|reset))\b"
)


def _text_of(tool_input: dict) -> str:
    """Every string in a tool input, flattened. Deliberately broad: a path can
    arrive as file_path, path, pattern, command, notebook_path or nested in a
    list, and a guard that inspects only the field it expected is a guard with
    a hole in it."""
    out = []

    def walk(v):
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(tool_input)
    return " ".join(out)


def _normalized(text: str) -> str:
    """Lowercased with backslashes folded to forward slashes, so a fragment
    check is not defeated by separator or case differences."""
    return text.replace("\\", "/").lower()


def _mask_own_workspace(text: str) -> str:
    """Blank out runs/<id>/workspace occurrences so the agent's own scratch
    directory does not read as protected run evidence.

    Masking the matched span (rather than returning early on a match) is what
    keeps the guard honest on a mixed command: `cp runs/A/workspace/out.csv
    runs/B/results.json` loses only the first path and is still denied for the
    second. The replacement carries no slash, so it cannot form a new match."""
    return _AGENT_WORKSPACE.sub("agent-workspace", text)


def check(tool_name: str, tool_input: dict) -> tuple[bool, str]:
    """(allowed, reason). Pure — no I/O, so it is unit-testable without the SDK
    and cannot itself touch the filesystem it is protecting."""
    text = _mask_own_workspace(_normalized(_text_of(tool_input)))
    if not text:
        return True, ""

    is_read = tool_name in _READ_TOOLS
    is_write = tool_name in _WRITE_TOOLS
    is_shell = tool_name == "Bash"

    if is_read or is_shell:
        for pattern in _READ_DENY:
            m = pattern.search(text)
            if m:
                return False, (
                    f"reading {m.group(0).strip()!r} is denied: transcripts and "
                    "calibration answer keys are write-only evidence, and a "
                    "stage that reads them breaks context isolation or grades "
                    "its own work"
                )

    if is_write or is_shell:
        for pattern in _WRITE_DENY:
            m = pattern.search(text)
            if m:
                # A shell command merely NAMING a protected path is denied, not
                # only an obviously-mutating one: `cat memory/journal.jsonl` is
                # a leak, and enumerating every dangerous verb is a losing game.
                verb = "shell command" if is_shell else tool_name
                return False, (
                    f"{verb} touching {m.group(0).strip()!r} is denied: memory, "
                    "runs/ and case evidence are append-only and are read by "
                    "the deterministic supervisor — a stage may not rewrite "
                    "what the next run believes, nor read another run's record"
                )

    return True, ""


def make_can_use_tool(stage_name: str, log=None):
    """Build the SDK can_use_tool callback for one stage.

    `log` is an optional callable taking one line; denials are recorded so a
    stage that tried is visible in the run evidence rather than silently
    steered. A denial is not a crash — the model is told why and continues,
    which is the behavior that lets it route around a wall it should not climb.
    """
    from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

    async def can_use_tool(tool_name: str, tool_input: dict, context):
        allowed, reason = check(tool_name, tool_input)
        if allowed:
            return PermissionResultAllow()
        line = f"TOOL_DENIED stage={stage_name} tool={tool_name} reason={reason}"
        if log is not None:
            log(line)
        else:
            print(line)
        return PermissionResultDeny(message=reason)

    return can_use_tool


# ---------------------------------------------------------------------------
# DELIVERY: WHY THE HOOK, NOT THE PERMISSION CALLBACK.
#
# can_use_tool above is the SDK's replacement for the interactive permission
# PROMPT. The SDK is explicit (claude_agent_sdk/types.py, ClaudeAgentOptions):
# it "is *not* invoked for tool calls already permitted by ``allowed_tools``…
# To observe or gate *every* tool call regardless of permission rules, use a
# ``PreToolUse`` hook via ``hooks`` instead."
#
# Every tool a profile grants is on allowed_tools. So for the experimenter's
# Bash/Write/Edit — the exact tools the three holes above are about — the
# callback was never consulted. The policy in check() was correct and the
# delivery was inert. This function is the same policy delivered where the SDK
# actually calls it.
#
# can_use_tool stays attached as well: it is the only thing that speaks for a
# tool NOT on the allowlist (an "ask" outcome), and belt-and-braces costs
# nothing when both consult the same pure check().
# ---------------------------------------------------------------------------


def make_pre_tool_use_hook(stage_name: str, log=None):
    """Build the SDK PreToolUse hook callback for one stage.

    Signature and return shape follow claude_agent_sdk.types.HookCallback:
    `(input, tool_use_id, context) -> HookJSONOutput`. An ALLOW returns the
    empty object — silence, so the CLI's own permission rules still decide;
    returning permissionDecision "allow" would instead OVERRIDE them, which is
    a wider grant than this guard is entitled to make. A DENY returns the
    PreToolUse-specific decision object, whose reason the model reads and
    routes around, exactly as the callback's deny message did.

    Never raises. A guard that crashes the run it protects has failed worse
    than one that misses — same doctrine as the cost meter reading 0 on a
    broken read. An unreadable hook input widens (allows) and says so.
    """

    async def pre_tool_use(hook_input, tool_use_id, context):
        try:
            tool_name = (hook_input or {}).get("tool_name") or ""
            tool_input = (hook_input or {}).get("tool_input") or {}
            allowed, reason = check(tool_name, tool_input)
        except Exception as exc:  # noqa: BLE001
            line = (f"TOOL_GUARD_ERROR stage={stage_name} — hook could not read "
                    f"its input ({type(exc).__name__}: {exc}); allowing")
            (log or print)(line)
            return {}
        if allowed:
            return {}
        line = f"TOOL_DENIED stage={stage_name} tool={tool_name} reason={reason}"
        (log or print)(line)
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return pre_tool_use


# ---------------------------------------------------------------------------
# STAGE -> PROFILE PAIRING.
#
# capabilities= is an ordinary keyword argument, so without this table nothing
# stops a future edit from handing the fidelity gate a tooled profile — and a
# gate that can read is a gate that can find its answer key. The pairing is
# enforced at the door, so the mistake fails loudly at the call rather than
# quietly in a calibration six weeks later.
#
# The rule is one line: a stage that PRODUCES OR JUDGES A MEASUREMENT stays
# sealed. Everything else may roam.
# ---------------------------------------------------------------------------

# Stages that must never hold tools, matched as prefixes of the stage name.
SEALED_ONLY_STAGES = (
    "stage3_fidelity_gate",   # judges instrument fidelity; answer keys on disk
    "stage4",                 # execution: determinism is the whole contract
    "stage5_thought_layer",   # judges results; must not re-derive them
    "stage6_desk_review",     # judges the paper; must not research around it
    "fidelity_case",          # the gate harness
    "calibration",            # measures the gate; tools would measure the internet
)


class CapabilityPairingError(RuntimeError):
    """A stage asked for a profile its role forbids."""


def assert_profile_allowed(stage_name: str, profile_name: str) -> None:
    """Raise if `stage_name` may not hold `profile_name`. Called at the door."""
    if profile_name == "sealed":
        return
    for prefix in SEALED_ONLY_STAGES:
        if stage_name.startswith(prefix):
            raise CapabilityPairingError(
                f"stage {stage_name!r} may not use the {profile_name!r} profile: "
                "stages that produce or judge a measurement stay sealed, because "
                "a stage that can read can read its own answer key and a stage "
                "that can act cannot be reproduced. Move the work upstream to a "
                "discovery stage, or route it through a substrate wrapper."
            )
