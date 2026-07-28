"""
scholar_search.py — live scholarly retrieval for the Step-17 ideation rebuild:
arXiv, Semantic Scholar (cross-publisher coverage plus citation counts), and
— since 17-fix-B — OpenAlex, the preferred novelty-grounding source
(citation-aware, and its `search` endpoint stays on-topic where arXiv's
full-sentence all:-queries returned off-topic noise).

All functions follow the summarize-at-the-wrapper rule: they return small
bounded records (snippet capped at SNIPPET_CAP chars) and never the raw
HTTP/XML/JSON response. HTTP style copied from fetch_literature.py (the
repo's proven arXiv code): stdlib urllib + certifi, a descriptive
User-Agent, polite throttling, bounded retry with backoff. arXiv and
Semantic Scholar need no API key (an optional S2_API_KEY environment
variable, when present, is sent to Semantic Scholar for a dedicated rate
limit); OpenAlex requires a free key — anonymous access is metered too low
for a battery — read as OPENALEX_API_KEY from the project root's .env via
python-dotenv, the materials_lookup.py precedent.

On any failure these functions raise a plain-language error — they never
fabricate results.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from dotenv import load_dotenv

try:
    # certifi is already present in venv/ (pulled in transitively by the
    # Claude SDK's HTTP stack); this is not a new dependency of this module.
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

#: Ceiling on an honoured Retry-After. The header is SERVER-CONTROLLED, and it was
#: taken at face value: `int(e.headers.get("Retry-After", 20))`. Two failures came
#: with that. A server sending the HTTP-DATE form ("Wed, 21 Oct 2026 07:28:00 GMT")
#: raised an uncaught ValueError, so a plain 429 surfaced as a crash instead of a
#: retry. And a large numeric value was slept in full — multiplied by the retry
#: count, a misconfigured or hostile server could park a study in time.sleep for
#: hours, with the run looking exactly like normal quiet work.
MAX_RETRY_AFTER_S = 120


def _retry_after_seconds(headers, default: int = 20) -> int:
    """Seconds to wait from a Retry-After header: numeric only, clamped, never
    raising. A date-form value falls back to `default` — waiting the default is
    always better than crashing on a retryable status."""
    raw = None
    try:
        raw = headers.get("Retry-After")
    except Exception:  # noqa: BLE001 — a header map that misbehaves is not fatal
        raw = None
    try:
        wait = int(str(raw).strip())
    except (TypeError, ValueError):
        wait = default
    return max(0, min(wait, MAX_RETRY_AFTER_S))


ARXIV_API_URL = "https://export.arxiv.org/api/query"
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,year,citationCount"
OPENALEX_API_URL = "https://api.openalex.org/works"
# select= bounds the per-work payload (~19KB unfiltered) to just these
# root-level fields; abstract_inverted_index is how OpenAlex ships abstracts.
OPENALEX_SELECT = "id,title,publication_year,cited_by_count,abstract_inverted_index"
# OpenAlex "polite pool" convention: identify yourself with a mailto param.
OPENALEX_MAILTO = "jesse.gift.yu@gmail.com"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_PATH = _PROJECT_ROOT / ".env"

SNIPPET_CAP = 1400
USER_AGENT = "research-system/step17-scholar_search.py (ideation literature retrieval)"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# arXiv terms of use: no more than one request every three seconds, single
# connection. Module-level throttle so back-to-back calls in one process
# stay polite.
ARXIV_MIN_INTERVAL_SECONDS = 3.0
_last_arxiv_request_monotonic = 0.0

MAX_RETRIES = 5


def _redact_key(url: str) -> str:
    """Redact the api_key query parameter's value so a request URL can appear
    in an error message without leaking the key."""
    return re.sub(r"(api_key=)[^&]*", r"\1REDACTED", url)


def _http_get(url: str, headers: dict[str, str], what: str, retries: int = MAX_RETRIES) -> bytes:
    """GET `url` with bounded retry; `what` names the service in errors.

    Retry shape copied from fetch_literature._fetch_topic: 429/503 honor
    Retry-After (default 20 s), transport errors back off 10 s * attempt;
    exhaustion raises a plain-language RuntimeError.
    """
    req = urllib.request.Request(url, headers=headers)
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code in (429, 503) and attempt < retries - 1:
                wait = _retry_after_seconds(e.headers)
                print(f"  {what}: HTTP {e.code}, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"{what} request failed with HTTP {e.code} and was not retried further "
                f"(request URL, key redacted: {_redact_key(url)}). "
                "No results were returned — nothing was fabricated."
            ) from e
        except (TimeoutError, urllib.error.URLError) as e:
            last_error = e
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  {what}: request failed ({e}), waiting {wait}s before retry...")
                time.sleep(wait)
                continue
    raise RuntimeError(
        f"{what} was unreachable after {retries} attempts (last error: {last_error}). "
        "No results were returned — nothing was fabricated."
    )


# arXiv's all: field ORs the terms of an unquoted multi-word query, so a
# full-sentence hypothesis statement scores enormous, heavily-indexed papers
# (CMS, ATLAS, IceCube) above anything on the actual subject. Known since Step
# 17 chunk 3, where the models correctly declined to cite the noise; run
# 20260720T080610Z then shipped an E. coli paper whose entire reference list
# was three particle-physics collaborations, because nothing downstream
# rechecked relevance. ANDing the salient terms is the fix at the source.
_ARXIV_STOPWORDS = frozenset("""
a an the and or but if then than that this these those of in on at to for from
by with without within into over under as is are was were be been being it its
we our you your they their he she his her i me my do does did doing have has
had having will would shall should can could may might must not no nor so such
about above below between through during before after here there when where why
how all any both each few more most other some only own same too very just also
""".split())

# The relaxation ladder, measured live against arXiv 2026-07-20 on the FBA
# hypothesis sentence from run 20260720T080610Z:
#   8 terms -> 0 hits (over-constrained)
#   5 terms -> on-topic (metabolic-network steady-state growth; E. coli
#              metabolism scaling) — the first rung that actually works
#   4 terms -> drifts off topic (solar maximum, glass transition)
#   3 terms -> noise again
# So 6 is the opening bid and the ladder relaxes only when a rung returns
# NOTHING, never to widen an already-answered query. Recall is preserved
# without paying the precision cost up front.
_ARXIV_MAX_TERMS = 6
_ARXIV_TERM_LADDER = (6, 5, 4)


def build_arxiv_query(query: str, max_terms: int | None = None) -> str:
    """Turn free text into an arXiv search_query that stays on topic.

    Content words are ANDed inside all:, so every hit must match all of them;
    stopwords are dropped and order is preserved. A query with no content
    words left (or already carrying arXiv field syntax) falls back to the
    original all: form rather than issuing something empty.

    Pure — no I/O, so the term selection is unit-testable without a network.
    """
    text = (query or "").strip()
    if not text:
        return ""
    if ":" in text and any(
        text.startswith(p) for p in ("all:", "ti:", "abs:", "au:", "cat:")
    ):
        return text  # already field-qualified; caller knows what it wants
    limit = _ARXIV_MAX_TERMS if max_terms is None else max_terms
    words = re.findall(r"[A-Za-z][A-Za-z0-9_-]+", text)
    terms, seen = [], set()
    for w in words:
        lw = w.lower()
        if lw in _ARXIV_STOPWORDS or lw in seen or len(lw) < 3:
            continue
        seen.add(lw)
        terms.append(w)
        if len(terms) >= limit:
            break
    if not terms:
        return f"all:{text}"
    return " AND ".join(f"all:{t}" for t in terms)


def search_arxiv(query: str, top_k: int = 3) -> list[dict]:
    """Search arXiv by relevance and return at most top_k bounded records.

    Each record is {"source": "arxiv:<id>", "title", "year",
    "snippet": <abstract capped at SNIPPET_CAP chars>}.

    The query is narrowed by build_arxiv_query before it is sent (see the note
    there on why a raw full-sentence all: query returns off-topic noise), and
    relaxed down _ARXIV_TERM_LADDER only while a rung returns NOTHING. An
    empty list is an honest result — arXiv genuinely has nothing matching —
    and is never padded with lower-relevance hits.
    """
    if not query or not query.strip():
        raise ValueError("search_arxiv: query must be a non-empty string")
    if top_k < 1:
        raise ValueError(f"search_arxiv: top_k must be >= 1, got {top_k}")

    for rung in _ARXIV_TERM_LADDER:
        records = _search_arxiv_once(build_arxiv_query(query, rung), top_k)
        if records:
            return records
    return []


def _search_arxiv_once(search_query: str, top_k: int) -> list[dict]:
    """One throttled arXiv request for an already-built search_query."""
    global _last_arxiv_request_monotonic
    since_last = time.monotonic() - _last_arxiv_request_monotonic
    if since_last < ARXIV_MIN_INTERVAL_SECONDS:
        time.sleep(ARXIV_MIN_INTERVAL_SECONDS - since_last)

    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": top_k,
        "sortBy": "relevance",
        "sortOrder": "descending",
    }
    url = f"{ARXIV_API_URL}?{urllib.parse.urlencode(params)}"
    _last_arxiv_request_monotonic = time.monotonic()
    xml_bytes = _http_get(url, headers={"User-Agent": USER_AGENT}, what="arXiv")

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise RuntimeError(
            f"arXiv replied but its response was not parseable Atom XML ({e}). "
            "No results were returned — nothing was fabricated."
        ) from e

    records = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = entry.findtext(f"{ATOM_NS}id", default="").strip()
        # raw_id looks like "http://arxiv.org/abs/2103.01234v1" (or old-style
        # "http://arxiv.org/abs/hep-th/9901001v1"); strip the URL prefix and
        # the trailing version suffix to get the stable id — same logic as
        # fetch_literature.py.
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1]
        if "v" in arxiv_id.rsplit("/", 1)[-1]:
            stem, _, version = arxiv_id.rpartition("v")
            if version.isdigit():
                arxiv_id = stem

        title = " ".join(entry.findtext(f"{ATOM_NS}title", default="").split())
        summary = " ".join(entry.findtext(f"{ATOM_NS}summary", default="").split())
        published = entry.findtext(f"{ATOM_NS}published", default="")
        year = published[:4] if len(published) >= 4 else "unknown"

        if not arxiv_id or not title or not summary:
            continue

        records.append(
            {
                "source": f"arxiv:{arxiv_id}",
                "title": title,
                "year": year,
                "snippet": summary[:SNIPPET_CAP],
            }
        )
        if len(records) == top_k:
            break
    return records


def search_semantic_scholar(query: str, top_k: int = 3) -> list[dict]:
    """Search Semantic Scholar by relevance and return at most top_k bounded records.

    Each record is {"source": "s2:<paperId>", "title", "year",
    "citation_count", "snippet": <abstract capped at SNIPPET_CAP chars>}.
    Papers with no abstract in the index get an empty snippet — honest,
    never invented. Keyless by default (shared public rate pool, so 429s are
    possible and retried with backoff); an S2_API_KEY env var is used when
    present.
    """
    if not query or not query.strip():
        raise ValueError("search_semantic_scholar: query must be a non-empty string")
    if top_k < 1:
        raise ValueError(f"search_semantic_scholar: top_k must be >= 1, got {top_k}")

    params = {"query": query.strip(), "fields": S2_FIELDS, "limit": top_k}
    url = f"{S2_API_URL}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": USER_AGENT}
    api_key = os.environ.get("S2_API_KEY", "").strip()
    if api_key:
        headers["x-api-key"] = api_key

    body = _http_get(url, headers=headers, what="Semantic Scholar")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Semantic Scholar replied but its response was not parseable JSON ({e}). "
            "No results were returned — nothing was fabricated."
        ) from e

    papers = parsed.get("data")
    if papers is None:
        # Zero-hit replies legitimately omit "data" and carry "total"
        # (witnessed live in Step 17 chunk 3: reply keys ['offset', 'total']).
        # That is a well-formed empty result, not an error. Only a reply
        # missing BOTH "data" and "total" is a malformed/error envelope.
        if isinstance(parsed, dict) and "total" in parsed:
            return []
        raise RuntimeError(
            "Semantic Scholar replied without a 'data' field "
            f"(reply keys: {sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__}). "
            "No results were returned — nothing was fabricated."
        )

    records = []
    for paper in papers:
        paper_id = paper.get("paperId")
        title = paper.get("title")
        if not paper_id or not title:
            continue
        abstract = paper.get("abstract") or ""
        records.append(
            {
                "source": f"s2:{paper_id}",
                "title": " ".join(title.split()),
                "year": paper.get("year"),
                "citation_count": paper.get("citationCount"),
                "snippet": " ".join(abstract.split())[:SNIPPET_CAP],
            }
        )
        if len(records) == top_k:
            break
    return records


def _load_openalex_api_key() -> str:
    """Same mechanism as materials_lookup._load_api_key: project-root .env
    via python-dotenv, plain-language error naming the exact variable."""
    load_dotenv(_ENV_PATH)
    key = os.environ.get("OPENALEX_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            f"No OpenAlex API key found. Open {_ENV_PATH} and paste your key "
            "directly after OPENALEX_API_KEY= (no quotes, no spaces). Keys are "
            "free: create one at openalex.org — anonymous access is metered to "
            "a handful of searches per day, too few for a battery. "
            "No results were returned — nothing was fabricated."
        )
    return key


def _reconstruct_abstract(inverted_index: dict) -> str:
    """Rebuild plain abstract text from OpenAlex's abstract_inverted_index
    ({word: [positions...]}). Deterministic: words sorted by position."""
    placed = [
        (pos, word)
        for word, positions in inverted_index.items()
        if isinstance(positions, list)
        for pos in positions
    ]
    placed.sort()
    return " ".join(word for _, word in placed)


# OpenAlex's search= endpoint parses a small set of characters as query
# operators and returns HTTP 400 on a bare occurrence of any of them. Probed
# live against api.openalex.org (each char embedded in a normal query):
# EXACTLY these four reject — "!" (NOT), "*" (wildcard), "?" (wildcard), "|"
# (OR). Every other ASCII punctuation mark (including — : ( ) . , and long
# queries) passes. "|" was the Step-18 alt-domain root cause (2026-07-13);
# "?" was the FBA-domain root cause (2026-07-19, a natural question-phrased
# domain). Kept as an evidence-based SET so the next operator char is one
# entry, not another incident.
_OPENALEX_SEARCH_REJECT = ("!", "*", "?", "|")


def _sanitize_openalex_search(query: str) -> str:
    """Make `query` safe for OpenAlex search= by replacing each operator
    character OpenAlex rejects (see _OPENALEX_SEARCH_REJECT) with a single
    space, then collapsing the doubled spaces that creates. This touches ONLY
    the literature search string — never the model-visible domain/hypothesis
    text, which flows to the prompts unchanged. A query free of every reject
    character passes through byte-identical."""
    text = query.strip()
    if not any(ch in text for ch in _OPENALEX_SEARCH_REJECT):
        return text
    for ch in _OPENALEX_SEARCH_REJECT:
        text = text.replace(ch, " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def search_openalex(query: str, top_k: int = 3) -> list[dict]:
    """Search OpenAlex works by relevance and return at most top_k bounded records.

    Each record is {"source": "openalex:<Wid>", "title", "year",
    "citation_count", "snippet": <abstract capped at SNIPPET_CAP chars>}.
    OpenAlex ships abstracts as an inverted index, absent on some works —
    present it is reconstructed; absent the snippet is empty, honest, never
    invented (same behavior as S2 on a missing abstract). A zero-hit reply
    returns [] — not an error; transport/HTTP failure raises so a
    best-effort caller can record it. Requires OPENALEX_API_KEY (see
    _load_openalex_api_key). Makes NO model call and reports nothing to
    cost_meter — pure keyed HTTP, like search_arxiv/search_semantic_scholar.
    """
    if not query or not query.strip():
        raise ValueError("search_openalex: query must be a non-empty string")
    if top_k < 1:
        raise ValueError(f"search_openalex: top_k must be >= 1, got {top_k}")

    api_key = _load_openalex_api_key()
    params = {
        "search": _sanitize_openalex_search(query),
        "per-page": top_k,
        "select": OPENALEX_SELECT,
        "mailto": OPENALEX_MAILTO,
        "api_key": api_key,
    }
    url = f"{OPENALEX_API_URL}?{urllib.parse.urlencode(params)}"
    body = _http_get(url, headers={"User-Agent": USER_AGENT}, what="OpenAlex")

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"OpenAlex replied but its response was not parseable JSON ({e}). "
            "No results were returned — nothing was fabricated."
        ) from e

    works = parsed.get("results") if isinstance(parsed, dict) else None
    if works is None:
        # A well-formed works reply always carries "results" (an empty list
        # on zero hits — unlike S2, OpenAlex does not drop the key); its
        # absence means an error envelope we should surface, not work data.
        raise RuntimeError(
            "OpenAlex replied without a 'results' field "
            f"(reply keys: {sorted(parsed) if isinstance(parsed, dict) else type(parsed).__name__}). "
            "No results were returned — nothing was fabricated."
        )

    records = []
    for work in works:
        raw_id = (work.get("id") or "").strip()
        # raw_id looks like "https://openalex.org/W2741809807"; the stable
        # work id is the trailing W-number.
        work_id = raw_id.rsplit("/", 1)[-1]
        title = work.get("title")
        if not work_id or not title:
            continue
        inverted = work.get("abstract_inverted_index")
        abstract = _reconstruct_abstract(inverted) if isinstance(inverted, dict) else ""
        records.append(
            {
                "source": f"openalex:{work_id}",
                "title": " ".join(title.split()),
                "year": work.get("publication_year"),
                "citation_count": work.get("cited_by_count"),
                "snippet": " ".join(abstract.split())[:SNIPPET_CAP],
            }
        )
        if len(records) == top_k:
            break
    return records


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3 or sys.argv[1] not in ("arxiv", "s2"):
        print("usage: scholar_search.py <arxiv|s2> <query...>")
        sys.exit(1)
    fn = search_arxiv if sys.argv[1] == "arxiv" else search_semantic_scholar
    for r in fn(" ".join(sys.argv[2:])):
        print(json.dumps(r, indent=2))
