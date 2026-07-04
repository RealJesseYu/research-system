"""
build_literature_index.py — builds the "literature" index over
retrieval/literature_corpus/, using the same TF-IDF machinery as solver_docs
(tfidf_core.py). The corpus starts with a single placeholder file; later
chunks populate it with real papers for the Ideation stage's literature-RAG.

Run:  venv/bin/python3 retrieval/build_literature_index.py
"""

from __future__ import annotations

from pathlib import Path

from tfidf_core import build_index

CORPUS_DIR = Path(__file__).parent / "literature_corpus"
INDEX_PATH = Path(__file__).parent / "literature_index.pkl"


def _load_docs() -> list[dict]:
    docs = []
    for path in sorted(CORPUS_DIR.glob("*.txt")):
        text = path.read_text(errors="replace").strip()
        if not text:
            continue
        docs.append({
            "kind": "literature",
            "source": f"literature: {path.name}",
            "title": path.stem,
            "text": text,
            "snippet": text[:1400],
        })
    return docs


def main() -> None:
    docs = _load_docs()
    n = build_index(docs, INDEX_PATH)
    print(f"literature index built: {n} documents -> {INDEX_PATH}")


if __name__ == "__main__":
    main()
