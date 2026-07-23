"""
web_search.py — live web retrieval for the Step-17 ideation rebuild.

RECORDED RULING (Step 17 strategy chat): retrieval is deterministic EXCEPT
this one tool. There is no way to reach the SDK's WebSearch capability
outside a model turn, so this wrapper makes its OWN bounded Haiku call with
allowed_tools=["WebSearch"], through the same SDK/auth path model_call.py
uses. model_call.py itself is untouched — this wrapper stands on its own.

Discipline preserved from model_call.py:
- Transcript write-before-call: the fully assembled model input is written
  to runs/<run_id>/transcripts/ BEFORE the call fires (which is why run_id
  is a parameter). Same record shape and filename format as model_call's
  _write_transcript, but with this module's OWN per-process sequence
  counter — stage names differ so filenames cannot collide, though
  cross-module sort order is not guaranteed (noted, acceptable until the
  parallelization revisit).
- Summarize-at-the-wrapper: the caller gets at most top_k bounded records
  {"source": "web", "title", "url", "snippet" (capped)}. The model's
  search-and-read transcript and any page text NEVER leave this module.
- Fence tolerance: Haiku fences nearly 100% of replies (running fence
  watch), so the same strip_fence tolerance is applied (a small local copy,
  disclosed — importing model_call from retrieval/ would invert the layer
  order).

Malformed output raises a plain-language error — never fabricated records.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

# Step 16.6: the shared cost meter lives at the project root; cost_meter is a
# leaf module (imports nothing project-local), so this is NOT the layer
# inversion importing model_call would be. The path insert mirrors the
# stages/ convention and only matters when this file runs standalone.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import cost_meter  # noqa: E402
from models import model_for  # model-tier resolver

HAIKU_MODEL = model_for("triage")
MAX_TURNS = 6  # enough turns to search and read before answering
SNIPPET_CAP = 1400

# Everything except WebSearch stays blocked, mirroring model_call.py's list.
_DISALLOWED_TOOLS = [
    "Bash", "Read", "Write", "Edit", "Glob", "Grep",
    "WebFetch", "ToolSearch",
]

SYSTEM_PROMPT_TEMPLATE = (
    "You are a web-search retrieval tool inside an autonomous research pipeline. "
    "Use the WebSearch tool to search the web for the query you are given. Then reply with "
    "ONLY a JSON array of at most {top_k} objects, each exactly of the form "
    '{{"title": "<page title>", "url": "<page url>", "snippet": "<one-to-three sentence '
    'factual summary of what that page says about the query>"}} — no prose, no markdown, '
    "no code fence, nothing but the JSON array. Every entry must come from a search result "
    "you actually received; never invent a page. If the search fails or returns nothing, "
    "reply with exactly []."
)

_TRANSCRIPT_SEQ = 0


def _write_transcript(run_id: str, system_prompt: str, user_turn: str) -> None:
    """Write the fully assembled model input BEFORE the call fires.

    Same record shape and naming scheme as model_call._write_transcript
    (write-only evidence; a crashed call still leaves its transcript), with
    this module's own per-process sequence counter.
    """
    global _TRANSCRIPT_SEQ
    _TRANSCRIPT_SEQ += 1
    transcripts_dir = Path("runs") / str(run_id) / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "stage_name": "web_search",
        "model": HAIKU_MODEL,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "system_prompt": system_prompt,
        "stage_input_serialized": user_turn,
    }
    with open(transcripts_dir / f"{_TRANSCRIPT_SEQ:04d}_web_search.json", "w") as f:
        json.dump(record, f, indent=2)


def _strip_fence(reply: str) -> str:
    """Local copy of model_call.strip_fence's tolerance (fenced-or-not)."""
    text = reply.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    return text


async def _search_once(system_prompt: str, user_turn: str) -> str:
    """One fresh-session Haiku call that may use ONLY the WebSearch tool."""
    # Step 16.6 chunk 2: record the ATTEMPT before the SDK call fires, so a
    # transport failure mid-stream still leaves a trace in the meter.
    cost_meter.record_attempt("web_search")
    options = ClaudeAgentOptions(
        model=HAIKU_MODEL,
        system_prompt=system_prompt,
        allowed_tools=["WebSearch"],
        disallowed_tools=_DISALLOWED_TOOLS,
        setting_sources=[],
        max_turns=MAX_TURNS,
    )
    parts: list[str] = []
    result_usage = None
    async for message in query(prompt=user_turn, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(message, ResultMessage):
            result_usage = message.usage
    # Step 16.6: the ONE observing touch at this door — count the completed
    # call (+ SDK-reported usage) into the shared cost meter. Observation
    # only; the return value is untouched.
    cost_meter.record_call("web_search", result_usage)
    # Interleaved text from pre-search turns would corrupt the JSON parse;
    # the final text block is the answer, so keep only the LAST JSON-looking
    # segment: take the last block that starts like an array once stripped.
    for part in reversed(parts):
        candidate = _strip_fence(part)
        if candidate.startswith("["):
            return candidate
    return _strip_fence("".join(parts))


def web_search(query_text: str, run_id: str, top_k: int = 3) -> list[dict]:
    """Search the live web and return at most top_k bounded records.

    Each record is {"source": "web", "title", "url",
    "snippet": <capped at SNIPPET_CAP chars>}. run_id is required because
    the transcript of the wrapper's own model call is written to
    runs/<run_id>/transcripts/ before the call fires.
    """
    if not query_text or not query_text.strip():
        raise ValueError("web_search: query must be a non-empty string")
    if not run_id or not str(run_id).strip():
        raise ValueError("web_search: run_id is required (transcript discipline)")
    if top_k < 1:
        raise ValueError(f"web_search: top_k must be >= 1, got {top_k}")

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(top_k=top_k)
    stage_input = {"run_id": str(run_id), "query": query_text.strip(), "top_k": top_k}
    user_turn = json.dumps(stage_input)

    # The input is now fully assembled; record it verbatim BEFORE the call.
    _write_transcript(str(run_id), system_prompt, user_turn)

    reply = asyncio.run(_search_once(system_prompt, user_turn))

    try:
        parsed = json.loads(reply)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"web_search: the model's reply was not parseable JSON ({e}; raw reply "
            f"starts: {reply[:200]!r}). No results were returned — nothing was fabricated."
        ) from e

    if not isinstance(parsed, list):
        raise RuntimeError(
            f"web_search: the model replied with {type(parsed).__name__}, not the "
            "required JSON array. No results were returned — nothing was fabricated."
        )

    records = []
    for item in parsed:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("title"), str)
            or not isinstance(item.get("url"), str)
            or not isinstance(item.get("snippet"), str)
            or not item["title"].strip()
            or not item["url"].strip()
        ):
            raise RuntimeError(
                f"web_search: malformed result entry {item!r} — every entry must be "
                '{"title": str, "url": str, "snippet": str}. No results were returned '
                "— nothing was fabricated."
            )
        records.append(
            {
                "source": "web",
                "title": item["title"].strip(),
                "url": item["url"].strip(),
                "snippet": item["snippet"].strip()[:SNIPPET_CAP],
            }
        )
        if len(records) == top_k:
            break
    return records


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: web_search.py <run_id> <query...>")
        sys.exit(1)
    for r in web_search(" ".join(sys.argv[2:]), run_id=sys.argv[1]):
        print(json.dumps(r, indent=2))
