"""
build_scipy_docs_index.py — builds the "scipy_docs" index for the sci-Python
substrate (Regime A, `sympy_symbolic_exact`). A SEPARATE index from solver_docs
/ fea_docs / literature, mirroring the fea_docs layout: corpus under
retrieval/scipy_docs_corpus/, pickle at retrieval/scipy_docs_index.pkl, built
through the same tfidf_core.build_index. REUSED, not rebuilt.

SOURCES (all fetched 2026-07-16, recorded honestly):

  * SymPy 1.14.0 — the official HTML docs archive
    `sympy-docs-html-1.14.0.zip` (51,126,961 bytes) from the sympy/sympy GitHub
    release tagged `1.14.0`. This EXACTLY matches the sympy pinned in
    scipy-img (1.14.0 — see tools/scipy_env/RESOLVED_VERSIONS.md), so the docs
    describe the runtime, not a neighbouring version.
    Selected subtrees (the build prompt's named targets, nothing else):
      - tutorials/intro-tutorial/   the SymPy tutorial
      - modules/integrals|solvers|series/   the API reference the wrapper drives
      - modules/assumptions/ + guides/assumptions.html   THE ASSUMPTIONS GUIDE —
        deliberately kept: the card's S5 KNOWN GAP (SymPy's defaults are
        complex; sqrt(x**2) != x) is documented there.
      - explanation/gotchas.html + explanation/best-practices.html   the
        gotchas / best-practices pages
      - guides/solving/, modules/simplify|functions/, modules/core.html,
        explanation/solve_output.html|glossary.html   the surrounding pages the
        above cross-reference
    The physics/mechanics/biomechanics/control subtrees are NOT indexed — they
    are irrelevant to Regime A and would only add retrieval noise.

  * SciPy 1.18.0 — four pages from docs.scipy.org grounding the CROSS-CHECK arm:
    scipy.integrate.quad (incl. its epsabs/epsrel tolerance semantics and the
    fact that the returned abserr is an ESTIMATE, not a bound), the integrate
    tutorial, the integrate reference index, and quad_vec.
    NOTE: fetched from docs.scipy.org/doc/scipy/ which serves the CURRENT
    release. Disclosed: the version served was not pinned by the URL, so these
    four pages are "current as of 2026-07-16" rather than provably 1.18.0.

REDIRECT-STUB FILTER (load-bearing): the archive ships ~300-byte JavaScript
redirect stubs at legacy paths (e.g. `tutorial/gotchas.html` ->
`tutorials/intro-tutorial/gotchas.html`). Indexing them would inject dozens of
content-free chunks that match nothing. Any page under 2,000 bytes is skipped;
0 were encountered in the selected subtrees, and the check is kept as a
regression guard.

Pure offline TF-IDF: ZERO embedding/API calls.

Run:  venv/bin/python3 retrieval/build_scipy_docs_index.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from tfidf_core import build_index

CORPUS_DIR = Path(__file__).parent / "scipy_docs_corpus"
INDEX_PATH = Path(__file__).parent / "scipy_docs_index.pkl"

SNIPPET_MAX_CHARS = 1400   # the same 1400-char cap every other index honors
CHUNK_WORDS = 150          # words per indexed chunk (mirrors fea_docs)
CHUNK_STEP = 120           # overlap-friendly stride
MIN_CHUNK_WORDS = 40       # drop nav-only / TOC-only fragments
MIN_PAGE_BYTES = 2000      # the redirect-stub filter

_SCRIPT_RE = re.compile(r"<script.*?</script>", re.IGNORECASE | re.DOTALL)
_STYLE_RE = re.compile(r"<style.*?</style>", re.IGNORECASE | re.DOTALL)
_HEAD_RE = re.compile(r"<head>.*?</head>", re.IGNORECASE | re.DOTALL)
_NAV_RE = re.compile(
    r'<(nav|footer)[^>]*>.*?</\1>', re.IGNORECASE | re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")
_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def strip_html(raw: str) -> tuple[str, str]:
    """Return (title, text) from a Sphinx HTML page.

    Scripts, styles, <head>, and nav/footer chrome are removed first (Sphinx
    pages carry a large sidebar that would otherwise dominate every chunk); the
    first <h1> becomes the title; remaining tags are stripped, entities decoded.
    """
    body = _SCRIPT_RE.sub(" ", raw)
    body = _STYLE_RE.sub(" ", body)
    body = _HEAD_RE.sub(" ", body)
    body = _NAV_RE.sub(" ", body)

    m = _TITLE_RE.search(body)
    title = html.unescape(_TAG_RE.sub("", m.group(1))).strip() if m else "SymPy/SciPy docs"
    title = re.sub(r"\s+", " ", title).replace("¶", "")[:120]

    text = _TAG_RE.sub(" ", body)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def _chunks_for_page(path: Path, library: str) -> list[dict]:
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
            "kind": "scipy_docs",
            "library": library,
            "source": f"{library} docs: {path.name}",
            "title": f"{library} — {title}",
            "text": chunk,
            "snippet": chunk[:SNIPPET_MAX_CHARS],
        })
        if start + CHUNK_WORDS >= len(words):
            break
    return docs


def load_docs() -> tuple[list[dict], int, int]:
    """Return (chunk docs, pages contributing >=1 chunk, redirect stubs skipped)."""
    docs, pages, stubs = [], 0, 0
    for library in ("sympy", "scipy"):
        for path in sorted((CORPUS_DIR / library).glob("*.html")):
            if path.stat().st_size < MIN_PAGE_BYTES:
                stubs += 1
                continue
            page_docs = _chunks_for_page(path, library)
            if page_docs:
                pages += 1
                docs.extend(page_docs)
    return docs, pages, stubs


def main() -> None:
    docs, pages, stubs = load_docs()
    n = build_index(docs, INDEX_PATH)
    size_kb = INDEX_PATH.stat().st_size / 1024
    print(f"scipy_docs index built: {pages} source pages -> {n} chunks -> {INDEX_PATH}")
    print(f"  redirect stubs skipped: {stubs}")
    print(f"  index size: {size_kb:.1f} KB")
    print("embedding/API calls: 0 (offline TF-IDF)")


if __name__ == "__main__":
    main()
