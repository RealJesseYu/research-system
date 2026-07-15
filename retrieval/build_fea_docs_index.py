"""
build_fea_docs_index.py — builds the "fea_docs" index from the CalculiX
CrunchiX USER'S MANUAL (HTML). A SEPARATE index from solver_docs, mirroring its
layout: corpus under retrieval/fea_docs_corpus/, pickle at
retrieval/fea_docs_index.pkl, built through the same tfidf_core.build_index.

Source: the manual's HTML edition, ccx_2.23.htm.tar.bz2 from www.dhondt.de
(Guido Dhondt), extracted to fea_docs_corpus/manual_html/ as 534 per-section
LaTeX2HTML pages. Manual version 2.23; the runnable solver in ccx-prod is 2.17
— the keyword documentation is stable across that gap. As with solver_docs, we
carry text (HTML) rather than the PDF so no PDF-reading dependency is needed,
and the index is pure offline TF-IDF: ZERO embedding/API calls.

Run:  venv/bin/python3 retrieval/build_fea_docs_index.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from tfidf_core import build_index

CORPUS_DIR = Path(__file__).parent / "fea_docs_corpus" / "manual_html"
INDEX_PATH = Path(__file__).parent / "fea_docs_index.pkl"

SNIPPET_MAX_CHARS = 1400
CHUNK_WORDS = 150          # words per indexed chunk
CHUNK_STEP = 120           # overlap-friendly stride (mirrors solver_docs userguide)
MIN_CHUNK_WORDS = 40       # drop nav-only / TOC-only fragments

_NAV_RE = re.compile(r'<DIV CLASS="navigation">.*?</DIV>', re.IGNORECASE | re.DOTALL)
_HEAD_RE = re.compile(r"<HEAD>.*?</HEAD>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_HEADING_RE = re.compile(r"<H[1-6][^>]*>(.*?)</H[1-6]>", re.IGNORECASE | re.DOTALL)


def strip_html(raw: str) -> tuple[str, str]:
    """Return (title, text) from a LaTeX2HTML manual page.

    Navigation panels and the <HEAD> are removed first; the first heading
    becomes the title; remaining tags are stripped and entities decoded.
    """
    body = _HEAD_RE.sub(" ", raw)
    body = _NAV_RE.sub(" ", body)

    m = _HEADING_RE.search(body)
    title = html.unescape(_TAG_RE.sub("", m.group(1))).strip() if m else "CalculiX manual"
    title = re.sub(r"\s+", " ", title)[:120]

    text = _TAG_RE.sub(" ", body)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _chunks_for_page(path: Path) -> list[dict]:
    title, text = strip_html(path.read_text(errors="replace"))
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return []
    docs = []
    for start in range(0, len(words), CHUNK_STEP):
        chunk = " ".join(words[start:start + CHUNK_WORDS]).strip()
        if len(chunk.split()) < MIN_CHUNK_WORDS and start > 0:
            break
        docs.append({
            "kind": "fea_manual",
            "source": f"CalculiX manual: {path.name}",
            "title": f"CalculiX — {title}",
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
    print(f"fea_docs index built: {pages} source pages -> {n} chunks -> {INDEX_PATH}")
    print("embedding/API calls: 0 (offline TF-IDF)")


if __name__ == "__main__":
    main()
