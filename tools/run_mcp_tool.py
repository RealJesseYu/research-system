"""run_mcp_tool — call an MCP connector from deterministic Python. NO AI in
execution.

WHAT THIS IS FOR. Connectors gave the free agent REACH and not RECORD. The
agent could ask a materials database, a chemistry API or a literature service
anything it liked — but the answer could never become a kept number, because
`stages/verification.py` regenerates a claim by RE-RUNNING its artifact, and
nothing could re-run an agent's connector call. The obvious workaround (fetch
the value, paste it into the verification script) is exactly what the
hardcoded-constant tripwire rejects: a number written into source reproduces
perfectly while measuring nothing. So a connector result could only ever be an
unverified caveat.

This module is the bridge. It speaks the same Model Context Protocol the SDK
speaks, to the same server named in the same `mcp_servers.json` — but as plain
Python with no model in the loop. That makes a connector call a re-runnable
artifact, which is the ONLY property this project requires of a kept number:

    {"kind": "substrate", "substrate_id": "mcp_connector",
     "typed_input": {"server": ..., "tool": ..., "arguments": {...},
                     "select": ...},
     "quantity": "..."}

Verification re-invokes THIS function with that typed input and compares. The
artifact records the CALL, never the answer, so a re-run genuinely re-asks the
service rather than re-reading a stored number.

WHAT REPRODUCTION PROVES HERE, AND WHAT IT DOES NOT. Re-running a solver proves
a number is a property of the experiment. Re-calling a database proves a number
is a property of the QUERY AND THE SERVICE — its provenance — and NOT that it
is correct: a stale or erroneous record looks identical to a good one from the
outside, and the service could return something different tomorrow. That is the
LOOKUP-class never-trusted-alone doctrine this project already applies to
bio_db_lookup and web_search (card D3), and every success diagnostic here
carries it, so a downstream reader is told what the verification verdict means.

PURITY (R-MCP-2). An MCP server is an arbitrary process and some MCP servers
are language models. A connector may back a claim ONLY when its config declares
`"_verifiable": true` — the operator's assertion that it is a deterministic
data source. Undeclared servers are refused HERE, at the one door verification
uses, so the purity rule cannot be broken by a config edit alone. See
tools/mcp_config.py and docs/memo_connector_bridge.md.

Typed input (exactly these four fields):
    run_mcp_tool({"server": "pubchem",
                  "tool": "compound_property",
                  "arguments": {"identifier": "caffeine",
                                "property": "MolecularWeight"},
                  "select": "value"})
Return: {"valid": bool, "qoi": float|None, "diagnostics": str, "runtime_s": float}
— the scalar wrapper summary shape (run_ngspice's), read by the registry's
scalar run-entry constructor.

THE OUTCOMES (no fabrication in any of them):
  * RESOLVED           -> valid=True, qoi=<the number at `select`>, with the
                          never-trusted-alone note in diagnostics;
  * NOT DECLARED       -> valid=False, a refusal naming the missing
                          `_verifiable` declaration (exploration is unaffected);
  * NO SUCH SERVER     -> valid=False, setup_error naming the configured set;
  * UNREACHABLE/TIMEOUT-> valid=False, setup_error (the connector could not run);
  * TOOL ERROR         -> valid=False, carrying the server's own error text;
  * NO VALUE AT `select`-> valid=False, naming the path and the shape it saw;
  * NON-NUMERIC VALUE  -> valid=False; a string answer is a real result but not
                          a scalar measurement, and is never coerced.
"""

from __future__ import annotations

import asyncio
import json
import time

from tools import mcp_config

_REQUIRED_FIELDS = ("server", "tool", "arguments", "select")

# Hard ceiling on one connector call, INCLUDING launching a stdio server and
# the protocol handshake. Verification must not be able to hang on a wedged
# connector: a timeout is an honest could-not-run, an infinite wait is a broken
# pass.
TIMEOUT_S = 60.0

_NTA_NOTE = (
    "NEVER-TRUSTED-ALONE: re-running this call attests PROVENANCE (the service "
    "still answers the same way), not correctness — the source's own currency "
    "and accuracy are unverifiable from here, and a stale or wrong record looks "
    "identical to a good one. Corroborate before resting a conclusion on it."
)


class McpToolInputError(ValueError):
    """The typed input is not a runnable connector call."""


class McpTransportError(RuntimeError):
    """The connector could not be reached or did not answer in time — a
    could-not-run condition, DISTINCT from a server that answered with an
    error or with no value at the requested path."""


def _validate_input(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise McpToolInputError(f"spec must be a dict, got {type(spec).__name__}")
    missing = [k for k in _REQUIRED_FIELDS if k not in spec]
    if missing:
        raise McpToolInputError(f"missing required field(s): {', '.join(missing)}")
    extra = [k for k in spec if k not in _REQUIRED_FIELDS]
    if extra:
        raise McpToolInputError(f"unsupported field(s): {', '.join(sorted(extra))}")
    for field in ("server", "tool", "select"):
        if not isinstance(spec[field], str) or not spec[field].strip():
            raise McpToolInputError(f"{field!r} must be a non-empty string")
    if not isinstance(spec["arguments"], dict):
        raise McpToolInputError(
            f"'arguments' must be an object, got {type(spec['arguments']).__name__}")
    return {
        "server": spec["server"].strip(),
        "tool": spec["tool"].strip(),
        "arguments": spec["arguments"],
        "select": spec["select"].strip(),
    }


def select_value(payload, path: str):
    """Walk a dotted `path` into a decoded tool result and return what is there,
    or raise KeyError naming where the walk stopped.

    Deterministic and dumb ON PURPOSE: dictionary keys and list indices, nothing
    else. No expressions, no wildcards, no model. A path is a locator, and a
    locator that could compute would be a second, unverified experiment hiding
    inside the verifier.
    """
    node = payload
    walked: list[str] = []
    for part in path.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.lstrip("-").isdigit():
            index = int(part)
            try:
                node = node[index]
            except IndexError:
                raise KeyError(
                    f"index {part!r} is out of range at "
                    f"{'.'.join(walked) or '<result>'} (length {len(node)})")
        else:
            where = ".".join(walked) or "<result>"
            available = (", ".join(sorted(node)[:12]) if isinstance(node, dict)
                         else f"a {type(node).__name__}")
            raise KeyError(
                f"no {part!r} at {where} — the result carries {available}")
        walked.append(part)
    return node


def _decode_result(result) -> tuple:
    """(payload, error_text) from an MCP CallToolResult. The payload is the
    server's structured output when it sent one, else its text content parsed as
    JSON, else the raw text. Structured output is preferred because it is the
    part of the protocol that carries typed data; the text fallback keeps
    servers that only emit text usable."""
    if getattr(result, "isError", False):
        return None, _text_of(result) or "the connector reported an error"
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured, None
    text = _text_of(result)
    if not text:
        return None, "the connector returned no content"
    try:
        return json.loads(text), None
    except ValueError:
        return text, None


def _text_of(result) -> str:
    """Every text block of a tool result, joined. Bounded: a connector's raw
    output must never travel whole into a summary (the baton rule — raw tool
    output is summarized at the wrapper, never handed on)."""
    parts = []
    for block in getattr(result, "content", None) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)[:2000]


async def _call_async(cfg: dict, tool: str, arguments: dict):
    """One MCP tool call over the transport the config names. Deterministic
    plumbing only — the SDK is not involved and no model is reachable from
    here."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import get_default_environment, stdio_client

    kind = (cfg.get("type") or "stdio").lower()
    if kind == "stdio":
        command = cfg.get("command")
        if not command:
            raise McpToolInputError(
                "the server config is type 'stdio' but names no 'command'")
        # The configured env is MERGED onto the default, not substituted for it:
        # a server that lost PATH cannot launch, and a config that names one
        # variable should not have to restate the environment.
        env = dict(get_default_environment())
        env.update({k: str(v) for k, v in (cfg.get("env") or {}).items()})
        params = StdioServerParameters(
            command=command, args=list(cfg.get("args") or []), env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments)

    if kind in ("http", "sse", "streamable-http", "streamable_http"):
        url = cfg.get("url")
        if not url:
            raise McpToolInputError(
                f"the server config is type {kind!r} but names no 'url'")
        headers = {k: str(v) for k, v in (cfg.get("headers") or {}).items()}
        if kind == "sse":
            from mcp.client.sse import sse_client as connect
        else:
            from mcp.client.streamable_http import streamablehttp_client as connect
        async with connect(url, headers=headers) as streams:
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool, arguments)

    raise McpToolInputError(
        f"unsupported MCP transport type {kind!r} (stdio, http, sse)")


def _call_connector(cfg: dict, tool: str, arguments: dict, timeout_s: float):
    """Run one call to completion, or raise McpTransportError. Every failure of
    the transport — a server that will not launch, a dead URL, a hang — arrives
    here as a could-not-run, never as a value."""
    async def _bounded():
        return await asyncio.wait_for(
            _call_async(cfg, tool, arguments), timeout=timeout_s)

    try:
        return asyncio.run(_bounded())
    except McpToolInputError:
        raise
    except asyncio.TimeoutError as e:
        raise McpTransportError(
            f"the connector did not answer within {timeout_s:g}s") from e
    except Exception as e:  # noqa: BLE001 — any transport failure is could-not-run
        raise McpTransportError(f"{type(e).__name__}: {e}") from e


def run_mcp_tool(spec: dict, *, config_path=None, timeout_s: float = TIMEOUT_S,
                 call=None) -> dict:
    """Call one MCP connector tool and return the scalar wrapper summary.

    `config_path` and `call` are injection seams: production reads
    mcp_servers.json and speaks real MCP; the offline suite injects a fake
    `call(cfg, tool, arguments)` so every outcome above is provable without a
    live server. The seams change WHERE the call goes, never what is reported.
    """
    wall_start = time.time()

    def done(valid, qoi, msg):
        return {"valid": valid, "qoi": qoi, "diagnostics": msg[:800],
                "runtime_s": round(time.time() - wall_start, 3)}

    try:
        clean = _validate_input(spec)
    except McpToolInputError as e:
        return done(False, None, f"input rejected: {e}")

    server = clean["server"]
    cfg = mcp_config.server_config(server, config_path)
    if cfg is None:
        configured = sorted(mcp_config.load_servers(config_path))
        return done(False, None, (
            f"setup_error: no MCP server named {server!r} is configured — "
            f"mcp_servers.json defines {configured or 'no servers'}; this call "
            "could not run (no result was fabricated)"))

    if not mcp_config.is_verifiable(server, config_path):
        return done(False, None, (
            f"refused: connector {server!r} is not declared "
            f'"{mcp_config.VERIFIABLE_KEY}": true in mcp_servers.json, so its '
            "output may not back a kept number. Verification runs with NO model "
            "in it, and an undeclared MCP server may itself be a model — the "
            "declaration is the operator's assertion that this one is a "
            "deterministic data source. The agent may still call this connector "
            "freely for exploration; report what it returns as an unverified "
            "caveat."))

    try:
        result = (call(cfg, clean["tool"], clean["arguments"]) if call is not None
                  else _call_connector(cfg, clean["tool"], clean["arguments"],
                                       timeout_s))
    except McpToolInputError as e:
        return done(False, None, f"input rejected: {e}")
    except McpTransportError as e:
        return done(False, None, (
            f"setup_error: connector {server!r} could not be reached ({e}) — "
            "this call could not run (no result was fabricated)"))

    payload, error = _decode_result(result)
    if error is not None:
        return done(False, None, (
            f"the connector {server!r} tool {clean['tool']!r} returned an "
            f"error: {error}"))

    try:
        value = select_value(payload, clean["select"])
    except KeyError as e:
        return done(False, None, (
            f"no value at select path {clean['select']!r}: {e}. The call "
            "succeeded; nothing was read from it (no number was fabricated)"))

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return done(False, None, (
            f"the value at {clean['select']!r} is {value!r}, not a number — a "
            "connector result becomes a MEASUREMENT only when it is scalar; it "
            "is not coerced. Use it as context, or select a numeric field"))

    return done(True, float(value), (
        f"{clean['select']}={value} from connector {server!r} tool "
        f"{clean['tool']!r}. {_NTA_NOTE}"))


if __name__ == "__main__":  # a hand probe: python -m tools.run_mcp_tool '<json>'
    import sys

    request = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "server": "pubchem", "tool": "compound_property",
        "arguments": {"identifier": "caffeine", "property": "MolecularWeight"},
        "select": "value"}
    print(json.dumps(run_mcp_tool(request), indent=2))
