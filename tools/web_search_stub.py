"""
web_search_stub.py — STEP 28.7-STUB: the web-search substrate stub.

web_search is a RETRIEVAL-PROVISIONAL substrate (see tools/substrate_registry.py):
it is a retrieval source that is structurally never trusted alone, never
routable, and never the target of a fidelity trust decision. This module is the
stub for it.

Two structural guarantees, both enforced by CODE, not by a prompt:

1. SUMMARIZED AT THE WRAPPER. web_search_stub returns only a bounded, summarized
   shape — title, url, and a length-capped snippet per result. A full-page body
   never crosses this boundary. (Same discipline as run_cfd's bounded summary:
   raw tool output is summarized BEFORE any agent sees it.)

2. STRUCTURALLY INCAPABLE OF VALIDATED-CLASS OUTPUT. Its journal writer,
   journal_web_finding, writes kind='web_finding' entries whose provenance is
   HARD-CODED to 'provisional'. Attempting to write any other provenance
   raises — a web finding can never be laundered into a validated-class value.

This is a STUB: it does not itself reach the network. It returns deterministic
placeholder records shaped exactly like a real summarized search result, so the
shape and the provenance contract can be exercised without a live dependency. A
live wrapper would replace web_search_stub's body; the provenance contract in
journal_web_finding is what guarantees, structurally, that no live wrapper can
ever emit validated-class output.
"""

from __future__ import annotations

from typing import Any

from memory.journal import journal_append

# The ONE provenance this substrate may ever emit. web_search is
# retrieval-provisional by construction; there is no code path to any other
# provenance (see journal_web_finding).
PROVENANCE = "provisional"

# Snippets are summarized at the wrapper: bounded, never a full-page body.
SNIPPET_CAP = 300


def _bounded_snippet(text: Any, cap: int = SNIPPET_CAP) -> str:
    """Collapse whitespace and hard-cap length. A summarized snippet, never a
    full page body."""
    collapsed = " ".join(str(text).split())
    return collapsed[:cap]


def web_search_stub(query: str, k: int = 3) -> dict:
    """Return up to k summarized web-search results for `query`, plus the
    provenance tag.

    Shape: {"results": [{"title", "url", "snippet"}, ...],
            "provenance": "provisional"}

    The snippet is bounded (SNIPPET_CAP chars); no full-page body is ever
    returned. provenance is always "provisional" — this substrate cannot emit
    anything else. This stub body is deterministic placeholder data; a live
    wrapper replaces it, but the summarized shape and the provenance tag are
    fixed by contract.
    """
    n = max(0, int(k))
    results = []
    for i in range(n):
        results.append(
            {
                "title": _bounded_snippet(f"[stub] result {i + 1} for query: {query}"),
                "url": f"https://example.invalid/web-search-stub/{i + 1}",
                "snippet": _bounded_snippet(
                    f"Summarized stub snippet {i + 1} responding to query "
                    f"'{query}'. Bounded at the wrapper — no full page body is "
                    "carried across this boundary."
                ),
            }
        )
    return {"results": results, "provenance": PROVENANCE}


def journal_web_finding(
    run_id: str,
    query: str,
    results: list[dict],
    provenance: str = PROVENANCE,
) -> dict:
    """Append one kind='web_finding' journal entry via the existing append path.

    HARD RULE (Step 28.7): provenance is structurally pinned to 'provisional'.
    `provenance` is accepted as an argument ONLY so that any attempt to write a
    different one is refused loudly — anything other than PROVENANCE raises. A
    web finding can never be recorded as a validated-class value.
    """
    if provenance != PROVENANCE:
        raise ValueError(
            "web_search_stub is a retrieval-provisional substrate: it can only "
            f"ever journal provenance={PROVENANCE!r}, never {provenance!r} — a "
            "web finding cannot be emitted as validated-class."
        )
    bounded = [
        {
            "title": _bounded_snippet(r.get("title", "")),
            "url": r.get("url", ""),
            "snippet": _bounded_snippet(r.get("snippet", "")),
        }
        for r in results
    ]
    entry = {
        "run_id": run_id,
        "kind": "web_finding",
        "text": f"web_search_stub[{PROVENANCE}] query={query!r} ({len(bounded)} results)",
        "extras": {
            "provenance": PROVENANCE,  # pinned, never from the argument's alt path
            "query": query,
            "results": bounded,
        },
    }
    return journal_append(entry)
