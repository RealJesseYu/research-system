"""test_pre_tool_use_hook.py — the tool guard is delivered where it fires
(2026-07-28).

The policy in capability_guard.check() was always right; its DELIVERY was
inert. Both the path guard and layer 1 of the move token allowance rode on
`can_use_tool`, which the SDK documents as "*not* invoked for tool calls
already permitted by ``allowed_tools``" — and model_call puts every tool the
profile grants on allowed_tools. So for the free experimenter's Bash, Write and
Edit, the guard was never consulted: transcripts, memory/, runs/, answer keys
and the home directory were protected only on paper.

These tests prove, offline:

  - the PreToolUse hook returns the SDK's documented deny object for a
    protected path and the empty object (silence, not an override) otherwise;
  - a tooled call's ClaudeAgentOptions actually carry that hook under the
    "PreToolUse" event, with a matcher that matches every tool;
  - the hook the OPTIONS carry — not a freshly built one — denies a write to
    memory/ and to a transcripts/ directory;
  - a sealed call carries no hook (it makes no tool calls);
  - with a move token allowance armed, the same hook is the one that delivers
    the wind-up denial, so allowance layer 1 is live again.

NO LIVE MODEL CALL is made, and none should be added: proving the hook fires
end-to-end would require a real agentic run. What is asserted instead is the
constructed options object plus direct invocation of the callback it carries.

Run directly: venv/bin/python3 tests/test_pre_tool_use_hook.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capability_guard  # noqa: E402
import model_call  # noqa: E402
from model_call import (  # noqa: E402
    FULL,
    SEALED,
    MOVE_ALLOWANCE_ENV,
    _MoveBudgetTracker,
    _wrap_hook_with_allowance,
)


def _pre_tool_use_input(tool_name: str, tool_input: dict) -> dict:
    """The shape the CLI sends for a PreToolUse hook_callback control request
    (claude_agent_sdk.types.PreToolUseHookInput)."""
    return {
        "hook_event_name": "PreToolUse",
        "session_id": "s",
        "transcript_path": "/dev/null",
        "cwd": "/tmp",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": "tu_1",
    }


def _decision(output: dict) -> str | None:
    specific = (output or {}).get("hookSpecificOutput") or {}
    return specific.get("permissionDecision")


class TestHookShape(unittest.TestCase):
    def setUp(self):
        self.lines = []
        self.hook = capability_guard.make_pre_tool_use_hook(
            "unit_stage", log=self.lines.append)

    def _call(self, tool_name, tool_input):
        return asyncio.run(self.hook(
            _pre_tool_use_input(tool_name, tool_input), "tu_1", {"signal": None}))

    def test_an_allowed_call_returns_silence_not_an_override(self):
        # {} leaves the CLI's own permission rules in charge. Returning
        # permissionDecision "allow" would OVERRIDE them — a wider grant than
        # this guard is entitled to make.
        self.assertEqual(self._call("Read", {"file_path": "model_call.py"}), {})
        self.assertEqual(self.lines, [])

    def test_a_protected_path_returns_the_sdk_deny_object(self):
        out = self._call("Write", {"file_path": "memory/journal.jsonl",
                                   "content": "x"})
        specific = out["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "PreToolUse")
        self.assertEqual(specific["permissionDecision"], "deny")
        self.assertIn("memory/", specific["permissionDecisionReason"])
        self.assertEqual(len(self.lines), 1)
        self.assertIn("TOOL_DENIED", self.lines[0])

    def test_transcript_read_back_is_denied_through_the_hook(self):
        out = self._call("Read", {"file_path": "runs/abc/transcripts/0001_a.json"})
        self.assertEqual(_decision(out), "deny")

    def test_a_bash_command_naming_a_protected_path_is_denied(self):
        out = self._call("Bash", {"command": "cat memory/journal.jsonl"})
        self.assertEqual(_decision(out), "deny")

    def test_the_agents_own_workspace_is_still_not_evidence(self):
        # The PRIME DIRECTIVE exemption must survive the delivery change.
        out = self._call("Write", {"file_path": "runs/r1/workspace/out.py",
                                   "content": "print(1)"})
        self.assertEqual(out, {})

    def test_a_malformed_hook_input_widens_and_says_so(self):
        # A guard that crashes the run it protects has failed worse than one
        # that misses. None is not a dict; the hook must not raise.
        out = asyncio.run(self.hook(None, None, {"signal": None}))
        self.assertEqual(out, {})


class TestHookReachesTheOptions(unittest.TestCase):
    """The gate is only real if the SDK is actually handed it."""

    def setUp(self):
        self._saved = os.environ.pop(MOVE_ALLOWANCE_ENV, None)

    def tearDown(self):
        os.environ.pop(MOVE_ALLOWANCE_ENV, None)
        if self._saved is not None:
            os.environ[MOVE_ALLOWANCE_ENV] = self._saved

    def _options_for(self, caps, turn_usage=None):
        from claude_agent_sdk.types import (AssistantMessage, ResultMessage,
                                            TextBlock)
        captured = {}

        async def fake_query(prompt, options):
            captured["options"] = options
            yield AssistantMessage(content=[TextBlock(text="done")], model="m",
                                   usage=turn_usage)
            yield ResultMessage(subtype="success", duration_ms=1,
                                duration_api_ms=1, is_error=False, num_turns=1,
                                session_id="s", usage={"input_tokens": 1})

        original = model_call.query
        model_call.query = fake_query
        try:
            asyncio.run(model_call._ask_once("sys", "user", "m", caps))
        finally:
            model_call.query = original
        return captured["options"]

    def _hook_from(self, options):
        matchers = options.hooks["PreToolUse"]
        self.assertEqual(len(matchers), 1)
        # matcher=None matches every tool name (claude_agent_sdk.types
        # .HookMatcher); a tool-name filter here would leave a hole per tool.
        self.assertIsNone(matchers[0].matcher)
        self.assertEqual(len(matchers[0].hooks), 1)
        return matchers[0].hooks[0]

    def test_a_tooled_call_carries_a_pretooluse_hook(self):
        options = self._options_for(FULL)
        self.assertIsNotNone(options.hooks)
        self.assertIn("PreToolUse", options.hooks)
        self._hook_from(options)
        # Belt and braces: the permission callback is still attached for any
        # tool that is NOT on the allowlist.
        self.assertIsNotNone(options.can_use_tool)

    def test_the_hook_the_options_carry_actually_refuses_a_denied_path(self):
        hook = self._hook_from(self._options_for(FULL))
        out = asyncio.run(hook(
            _pre_tool_use_input("Write", {"file_path": "memory/journal.jsonl",
                                          "content": "x"}),
            "tu_1", {"signal": None}))
        self.assertEqual(_decision(out), "deny")

    def test_the_hook_the_options_carry_allows_ordinary_work(self):
        hook = self._hook_from(self._options_for(FULL))
        out = asyncio.run(hook(
            _pre_tool_use_input("Bash", {"command": "python3 sim.py"}),
            "tu_1", {"signal": None}))
        self.assertEqual(out, {})

    def test_a_sealed_call_carries_no_hook(self):
        options = self._options_for(SEALED)
        self.assertIsNone(options.hooks)
        self.assertIsNone(options.can_use_tool)

    def test_with_an_allowance_the_hook_is_the_wind_up_gate(self):
        # A 1-token allowance, and the fake stream reports one turn spending
        # 5,000 face-value tokens. The tracker the OPTIONS' hook closes over is
        # the one the message loop updated, so after the run that same hook —
        # the object the SDK holds — must deny. This is layer 1 of the token
        # ceiling, which was dead while it rode on can_use_tool.
        os.environ[MOVE_ALLOWANCE_ENV] = "1"
        options = self._options_for(FULL, turn_usage={"input_tokens": 5000})
        hook = self._hook_from(options)
        out = asyncio.run(hook(
            _pre_tool_use_input("Bash", {"command": "echo hi"}),
            "tu_1", {"signal": None}))
        self.assertEqual(_decision(out), "deny")
        self.assertIn("TOKEN ALLOWANCE EXHAUSTED",
                      out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_without_an_allowance_the_hook_is_the_bare_capability_guard(self):
        options = self._options_for(FULL, turn_usage={"input_tokens": 5_000_000})
        hook = self._hook_from(options)
        out = asyncio.run(hook(
            _pre_tool_use_input("Bash", {"command": "echo hi"}),
            "tu_1", {"signal": None}))
        self.assertEqual(out, {})


class TestAllowanceWrapperOnTheHook(unittest.TestCase):
    """Layer 1 of the token ceiling, delivered through the hook."""

    def _inner_allowing(self, calls):
        async def inner(hook_input, tool_use_id, context):
            calls.append((hook_input or {}).get("tool_name"))
            return {}
        return inner

    def test_delegates_to_the_capability_guard_while_there_is_room(self):
        calls = []
        tracker = _MoveBudgetTracker(remaining_tokens=10**9, granted_turns=200)
        wrapped = _wrap_hook_with_allowance(
            self._inner_allowing(calls), tracker, "stage")
        out = asyncio.run(wrapped(_pre_tool_use_input("Bash", {}), "tu", {}))
        self.assertEqual(out, {})
        self.assertEqual(calls, ["Bash"])

    def test_denies_with_the_wind_up_message_once_tripped(self):
        calls = []
        tracker = _MoveBudgetTracker(remaining_tokens=100, granted_turns=200)
        tracker.note_assistant_message({"input_tokens": 100})
        wrapped = _wrap_hook_with_allowance(
            self._inner_allowing(calls), tracker, "stage")
        out = asyncio.run(wrapped(_pre_tool_use_input("Bash", {}), "tu", {}))
        self.assertEqual(_decision(out), "deny")
        self.assertEqual(calls, [])  # the guard was never even consulted
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("TOKEN ALLOWANCE EXHAUSTED", reason)
        self.assertIn("final answer", reason)

    def test_a_throwing_tracker_never_ends_the_run(self):
        class Exploding:
            announced = False

            def wind_up_reason(self):
                raise RuntimeError("meter broke")

        calls = []
        wrapped = _wrap_hook_with_allowance(
            self._inner_allowing(calls), Exploding(), "stage")
        out = asyncio.run(wrapped(_pre_tool_use_input("Bash", {}), "tu", {}))
        self.assertEqual(out, {})
        self.assertEqual(calls, ["Bash"])


if __name__ == "__main__":
    unittest.main()
