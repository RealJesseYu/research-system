"""
scholar_search.py — live scholarly retrieval for the Step-17 ideation rebuild:
arXiv (grounding) and Semantic Scholar (novelty-checking, cross-publisher
coverage plus citation counts).

Both functions follow the summarize-at-the-wrapper rule: they return small
bounded records (snippet capped at SNIPPET_CAP chars) and never the raw
HTTP/XML/JSON response. HTTP style copied from fetch_literature.py (the
repo's proven arXiv code): stdlib urllib + certifi, a descriptive
User-Agent, polite throttling, bounded retry with backoff. No API key is
required by either function; an optional S2_API_KEY environment variable,
when present, is sent to Semantic Scholar for a dedicated rate limit.

On any failure these functions raise a plain-language error — they never
fabricate results.
"""

from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

try:
    # certifi is already present in venv/ (pulled in transitively by the
    # Claude SDK's HTTP stack); this is not a new dependency of this module.
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

ARXIV_API_URL = "https://export.arxiv.org/api/query"
S2_API_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,year,citationCount"

SNIPPET_CAP = 1400
USER_AGENT = "research-system/step17-scholar_search.py (ideation literature retrieval)"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# arXiv terms of use: no more than one request every three seconds, single
# connection. Module-level throttle so back-to-back calls in one process
# stay polite.
ARXIV_MIN_INTERVAL_SECONDS = 3.0
_last_arxiv_request_monotonic = 0.0

MAX_RETRIES = 5


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
                wait = int(e.headers.get("Retry-After", 20))
                print(f"  {what}: HTTP {e.code}, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"{what} request failed with HTTP {e.code} and was not retried further. "
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


def search_arxiv(query: str, top_k: int = 3) -> list[dict]:
    """Search arXiv by relevance and return at most top_k bounded records.

    Each record is {"source": "arxiv:<id>", "title", "year",
    "snippet": <abstract capped at SNIPPET_CAP chars>}.
    """
    if not query or not query.strip():
        raise ValueError("search_arxiv: query must be a non-empty string")
    if top_k < 1:
        raise ValueError(f"search_arxiv: top_k must be >= 1, got {top_k}")

    global _last_arxiv_request_monotonic
    since_last = time.monotonic() - _last_arxiv_request_monotonic
    if since_last < ARXIV_MIN_INTERVAL_SECONDS:
        time.sleep(ARXIV_MIN_INTERVAL_SECONDS - since_last)

    params = {
        "search_query": f"all:{query.strip()}",
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
        # A well-formed reply always carries "data" (possibly empty); its
        # absence means an error envelope we should surface, not paper data.
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


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3 or sys.argv[1] not in ("arxiv", "s2"):
        print("usage: scholar_search.py <arxiv|s2> <query...>")
        sys.exit(1)
    fn = search_arxiv if sys.argv[1] == "arxiv" else search_semantic_scholar
    for r in fn(" ".join(sys.argv[2:])):
        print(json.dumps(r, indent=2))
