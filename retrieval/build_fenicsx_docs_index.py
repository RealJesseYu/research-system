"""build_fenicsx_docs_index.py — builds the "fenicsx_docs" index from the
DOLFINx documentation (HTML). A SEPARATE index from solver_docs / fea_docs,
mirroring their layout: corpus under retrieval/fenicsx_docs_corpus/pages/,
pickle at retrieval/fenicsx_docs_index.pkl, built through the same
tfidf_core.build_index.

VERSION MATCH (the thing that makes this corpus trustworthy): the API pages are
the **v0.11.0.post0** Python docs — the same version `dolfinx-prod` prints from
`dolfinx.__version__`. No skew. See the card §1 and
retrieval/fenicsx_docs_corpus/SOURCES.md for the per-page provenance.

FEniCS is two projects with one name: this corpus is FEniCSx/DOLFINx ONLY.
Legacy-FEniCS (`from dolfin import *`, last released 2019) material is
deliberately excluded — indexing it would ground the retrieval layer in code
that cannot run in this container.

As with solver_docs/fea_docs, we carry text (HTML) rather than PDFs so no
PDF-reading dependency is needed, and the index is pure offline TF-IDF: ZERO
embedding/API calls.

Run:  venv/bin/python3 retrieval/build_fenicsx_docs_index.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from tfidf_core import build_index

CORPUS_DIR = Path(__file__).parent / "fenicsx_docs_corpus" / "pages"
INDEX_PATH = Path(__file__).parent / "fenicsx_docs_index.pkl"

SNIPPET_MAX_CHARS = 1400   # same snippet cap as the sibling indices
CHUNK_WORDS = 150          # words per indexed chunk
CHUNK_STEP = 120           # overlap-friendly stride (mirrors fea_docs)
MIN_CHUNK_WORDS = 40       # drop nav-only / TOC-only fragments

# Jupyter-Book pages (the tutorial) embed rendered outputs as base64 data URIs
# and ship the whole notebook as JSON. Those blobs are megabytes of noise that
# would swamp the vocabulary, so they are stripped BEFORE chunking.
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_DATA_URI_RE = re.compile(r"data:[a-z/+.-]+;base64,[A-Za-z0-9+/=\s]+", re.IGNORECASE)
_B64_BLOB_RE = re.compile(r"\b[A-Za-z0-9+/]{200,}={0,2}\b")
_HEAD_RE = re.compile(r"<head>.*?</head>", re.IGNORECASE | re.DOTALL)
_NAV_RE = re.compile(
    r"<(nav|footer|aside)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_HEADING_RE = re.compile(r"<h[1-3][^>]*>(.*?)</h[1-3]>", re.IGNORECASE | re.DOTALL)

# Per-page provenance: filename prefix -> (source label, kind).
_SOURCES = (
    ("dolfinx_", "DOLFINx v0.11.0.post0 Python API docs", "fenicsx_api"),
    ("demo_", "DOLFINx v0.11.0.post0 demo", "fenicsx_demo"),
    ("tut_", "jsdokken dolfinx-tutorial (0.11.0.post0)", "fenicsx_tutorial"),
    ("comet_", "comet-fenicsx (Bleyer)", "fenicsx_tutorial"),
)


def _source_for(name: str) -> tuple[str, str]:
    for prefix, label, kind in _SOURCES:
        if name.startswith(prefix):
            return label, kind
    return "DOLFINx docs", "fenicsx_docs"


def strip_html(raw: str) -> tuple[str, str]:
    """Return (title, text) from a Sphinx / Jupyter-Book HTML page.

    Scripts, styles, base64 blobs, <head>, and nav/footer chrome are removed
    first; the page's <title> (falling back to its first heading) becomes the
    title; remaining tags are stripped and entities decoded.
    """
    body = _SCRIPT_RE.sub(" ", raw)
    body = _DATA_URI_RE.sub(" ", body)

    m = _TITLE_RE.search(body) or _HEADING_RE.search(body)
    title = html.unescape(_TAG_RE.sub("", m.group(1))).strip() if m else "DOLFINx docs"
    title = re.sub(r"\s+", " ", title)[:120]

    body = _HEAD_RE.sub(" ", body)
    body = _NAV_RE.sub(" ", body)
    text = _TAG_RE.sub(" ", body)
    text = html.unescape(text)
    text = _B64_BLOB_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _chunks_for_page(path: Path) -> list[dict]:
    title, text = strip_html(path.read_text(errors="replace"))
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return []
    source_label, kind = _source_for(path.name)
    docs = []
    for start in range(0, len(words), CHUNK_STEP):
        chunk = " ".join(words[start:start + CHUNK_WORDS]).strip()
        if len(chunk.split()) < MIN_CHUNK_WORDS and start > 0:
            break
        docs.append({
            "kind": kind,
            "source": f"{source_label}: {path.name}",
            "title": f"DOLFINx — {title}",
            "text": chunk,
            "snippet": chunk[:SNIPPET_MAX_CHARS],
        })
        if start + CHUNK_WORDS >= len(words):
            break
    return docs


def load_docs() -> tuple[list[dict], int]:
    """Return (chunk docs, number of source pages that contributed >=1 chunk)."""
    docs, pages = [], 0
    for path in sorted(CORPUS_DIR.glob("*.html")):
        page_docs = _chunks_for_page(path)
        if page_docs:
            pages += 1
            docs.extend(page_docs)
    return docs, pages


def main() -> None:
    docs, pages = load_docs()
    n = build_index(docs, INDEX_PATH)
    print(f"fenicsx_docs index built: {pages} source pages -> {n} chunks -> {INDEX_PATH}")
    print("embedding/API calls: 0 (offline TF-IDF)")


if __name__ == "__main__":
    main()
