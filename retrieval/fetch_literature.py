"""
fetch_literature.py — one-time script that populates retrieval/literature_corpus/
with real arXiv abstracts, replacing the Step 7 placeholder.

Queries the public arXiv API (http://export.arxiv.org/api/query) for four
topics relevant to the pipeline's demo research domain (laminar cavity flows,
vortex dynamics, mixing, and convective heat transfer). Uses only the
standard library — urllib for the HTTP request, xml.etree.ElementTree for
parsing the Atom feed response. No API key, no new pip dependencies.

Polite to the API: one request per topic (max_results=50), a 3-second sleep
between requests, and a descriptive User-Agent header.

Run:  venv/bin/python3 retrieval/fetch_literature.py
"""

from __future__ import annotations

import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    # certifi is already present in venv/ (pulled in transitively by the
    # Claude SDK's HTTP stack); this is not a new dependency of this script.
    import certifi

    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

API_URL = "https://export.arxiv.org/api/query"
CORPUS_DIR = Path(__file__).parent / "literature_corpus"
MAX_RESULTS = 50
SLEEP_SECONDS = 3
USER_AGENT = "research-system/step8-fetch_literature.py (one-time corpus build)"

ATOM_NS = "{http://www.w3.org/2005/Atom}"

# Each topic is (label, arXiv search_query). A single long quoted phrase
# only matches abstracts containing that exact wording, which starved
# topics 2-4 (their phrasing was invented for this brief, not arXiv-abstract
# language) down to near-zero hits. AND-of-shorter-quoted-phrases keeps each
# query on the same topic while actually matching how papers are worded.
TOPICS = [
    ("lid-driven cavity flow", 'all:"lid-driven cavity"'),
    ("laminar cavity flows and vortex dynamics", 'all:"cavity flow" AND all:"vortex"'),
    ("mixing in laminar flows", 'all:"mixing" AND all:"laminar flow"'),
    ("laminar convective heat transfer in enclosures", 'all:"natural convection" AND all:"cavity"'),
]


def _fetch_topic(search_query: str, retries: int = 5) -> bytes:
    params = {
        "search_query": search_query,
        "start": 0,
        "max_results": MAX_RESULTS,
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < retries - 1:
                wait = int(e.headers.get("Retry-After", 20))
                print(f"  HTTP {e.code}, waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise
        except (TimeoutError, urllib.error.URLError) as e:
            if attempt < retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  request failed ({e}), waiting {wait}s before retry...")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("unreachable")


def _parse_entries(xml_bytes: bytes) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    papers = []
    for entry in root.findall(f"{ATOM_NS}entry"):
        raw_id = entry.findtext(f"{ATOM_NS}id", default="").strip()
        # raw_id looks like "http://arxiv.org/abs/2103.01234v1" (or old-style
        # "http://arxiv.org/abs/hep-th/9901001v1"); strip the URL prefix and
        # the trailing version suffix to get the stable, de-duplicable id.
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

        papers.append({
            "id": arxiv_id,
            "year": year,
            "title": title,
            "abstract": summary,
        })
    return papers


def _write_paper(paper: dict) -> Path:
    safe_id = paper["id"].replace("/", "_")
    path = CORPUS_DIR / f"{safe_id}.txt"
    content = (
        f"{paper['title']}\n"
        f"arXiv:{paper['id']} ({paper['year']})\n\n"
        f"{paper['abstract']}\n"
    )
    path.write_text(content)
    return path


def main() -> None:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    seen_ids: set[str] = set()
    written = 0

    for i, (label, search_query) in enumerate(TOPICS):
        print(f"querying arXiv for: {label!r} ({search_query})")
        xml_bytes = _fetch_topic(search_query)
        papers = _parse_entries(xml_bytes)
        print(f"  -> {len(papers)} entries returned")

        for paper in papers:
            if paper["id"] in seen_ids:
                continue
            seen_ids.add(paper["id"])
            _write_paper(paper)
            written += 1

        if i < len(TOPICS) - 1:
            time.sleep(SLEEP_SECONDS)

    print(f"done: {written} unique abstracts written to {CORPUS_DIR}")
    if written < 80:
        print(
            f"WARNING: only {written} abstracts landed, well under the ~80 floor — "
            "widen the search deliberately rather than padding with off-topic queries."
        )


if __name__ == "__main__":
    main()
