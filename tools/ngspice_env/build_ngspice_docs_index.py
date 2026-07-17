"""
build_ngspice_docs_index.py — builds the "ngspice_docs" index from the NGSPICE
USER'S MANUAL (PDF). A SEPARATE index from solver_docs and fea_docs, mirroring
their layout: corpus under retrieval/ngspice_docs_corpus/, pickle at
retrieval/ngspice_docs_index.pkl, built through the same tfidf_core.build_index.

SCRIPT LOCATION: this build script lives in tools/ngspice_env/ rather than
retrieval/ (where build_fea_docs_index.py and build_solver_docs_index.py live),
because the ruled session scope names only the corpus dir and the .pkl as new
retrieval/ paths. Deliberate deviation from the sibling convention, ruled.

Source: https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf
  sha256 ac745b5e7a38abcdb1b000356045d3525020c097a803e99a3faa9d8349f72a7e
  737 pages. The title page self-declares:
      "Ngspice User's Manual / Version 42 (ngspice release version) /
       Holger Vogt, Giles Atkinson, Paolo Nenzi / December 27th, 2023"

VERSION MATCH: ZERO SKEW. The container's binary reports `ngspice-42`
(dpkg 42+ds-3build1, creation date 2024-03-31) and this manual self-declares
Version 42. Contrast the FEA card's §1, which carries a real docs-v2.23 vs
solver-v2.17 skew. Nothing here needs that caveat.

As with solver_docs and fea_docs, the CORPUS carries extracted TEXT rather than
the source PDF, so re-indexing needs no PDF-reading dependency (pypdf is used
ONCE, at extraction, and is already present in the venv — zero installs). The
index is pure offline TF-IDF: ZERO embedding/API calls.

Run:  venv/bin/python3 tools/ngspice_env/build_ngspice_docs_index.py
      venv/bin/python3 tools/ngspice_env/build_ngspice_docs_index.py --extract <manual.pdf>
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_RETRIEVAL = _REPO / "retrieval"
sys.path.insert(0, str(_RETRIEVAL))

from tfidf_core import build_index  # noqa: E402

CORPUS_DIR = _RETRIEVAL / "ngspice_docs_corpus" / "manual_text"
INDEX_PATH = _RETRIEVAL / "ngspice_docs_index.pkl"

MANUAL_URL = "https://ngspice.sourceforge.io/docs/ngspice-42-manual.pdf"
MANUAL_SHA256 = "ac745b5e7a38abcdb1b000356045d3525020c097a803e99a3faa9d8349f72a7e"

SNIPPET_MAX_CHARS = 1400
CHUNK_WORDS = 150          # words per indexed chunk   (mirrors fea_docs)
CHUNK_STEP = 120           # overlap-friendly stride   (mirrors fea_docs)
MIN_CHUNK_WORDS = 40       # drop TOC / index-only fragments

# LaTeX PDF ligatures and quotes that survive text extraction.
_LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi",
    "ﬄ": "ffl", "’": "'", "‘": "'", "“": '"',
    "”": '"', "–": "-", "—": "-", " ": " ",
}

# A running header like "3.3. ELEMENTARY DEVICES 81" or "CHAPTER 12. ANALYSES".
_HEADER_RE = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?([A-Z][A-Za-z0-9 ,'\-/&()]{3,60}?)\s*\d*\s*$")


def normalize(text: str) -> str:
    for bad, good in _LIGATURES.items():
        text = text.replace(bad, good)
    return re.sub(r"[ \t]+", " ", text)


def page_title(text: str) -> str:
    """Best-effort section title from a page's running header; falls back to a
    generic label. Never raises — a bad title only costs display quality."""
    for line in text.splitlines()[:3]:
        line = line.strip()
        if not line or line.isdigit():
            continue
        m = _HEADER_RE.match(line)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()
            if title and not title.isdigit():
                return title[:120]
    return "ngspice manual"


def extract_pdf(pdf_path: Path) -> int:
    """Extract per-page text from the manual PDF into CORPUS_DIR. Returns the
    page count. Needs pypdf; run once, then the corpus is self-contained."""
    import pypdf

    reader = pypdf.PdfReader(str(pdf_path))
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, page in enumerate(reader.pages, start=1):
        text = normalize(page.extract_text() or "")
        if not text.strip():
            continue
        (CORPUS_DIR / f"page_{i:04d}.txt").write_text(text)
        written += 1
    return written


def _chunks_for_page(path: Path) -> list[dict]:
    text = path.read_text(errors="replace")
    title = page_title(text)
    words = text.split()
    if len(words) < MIN_CHUNK_WORDS:
        return []
    docs = []
    for start in range(0, len(words), CHUNK_STEP):
        chunk = " ".join(words[start:start + CHUNK_WORDS]).strip()
        if len(chunk.split()) < MIN_CHUNK_WORDS and start > 0:
            break
        docs.append({
            "kind": "ngspice_manual",
            "source": f"ngspice manual v42: {path.name}",
            "title": f"ngspice — {title}",
            "text": chunk,
            "snippet": chunk[:SNIPPET_MAX_CHARS],
        })
        if start + CHUNK_WORDS >= len(words):
            break
    return docs


def load_docs() -> tuple[list[dict], int]:
    """Return (chunk docs, number of source pages that contributed >=1 chunk)."""
    docs, pages = [], 0
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        page_docs = _chunks_for_page(path)
        if page_docs:
            pages += 1
            docs.extend(page_docs)
    return docs, pages


def main() -> None:
    if "--extract" in sys.argv:
        pdf = Path(sys.argv[sys.argv.index("--extract") + 1])
        n = extract_pdf(pdf)
        print(f"extracted {n} text pages from {pdf.name} -> {CORPUS_DIR}")

    if not CORPUS_DIR.exists():
        raise SystemExit(
            f"corpus missing at {CORPUS_DIR}\n"
            f"fetch the manual and extract it first:\n"
            f"  curl -sL {MANUAL_URL} -o /tmp/ngspice-42-manual.pdf\n"
            f"  # verify: sha256 == {MANUAL_SHA256}\n"
            f"  venv/bin/python3 {Path(__file__).name} --extract /tmp/ngspice-42-manual.pdf")

    docs, pages = load_docs()
    n = build_index(docs, INDEX_PATH)
    print(f"ngspice_docs index built: {pages} source pages -> {n} chunks -> {INDEX_PATH}")
    print("embedding/API calls: 0 (offline TF-IDF)")


if __name__ == "__main__":
    main()
