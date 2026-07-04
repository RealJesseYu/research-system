"""
build_solver_docs_index.py — builds the "solver_docs" index from corpus files
copied in from the earlier risky-bit spike (read-only reference). Document
loading here mirrors that project's search_docs tool; only the generic
TF-IDF plumbing moved out to tfidf_core.py.

Corpus, all copied into retrieval/solver_docs_corpus/:
  - tutorials/  — OpenFOAM tutorials' 0/ field files (worked examples of
    correct boundary-condition setups).
  - userguide_case-setup.txt, userguide_boundary-conditions.txt — plain text
    already extracted from the User Guide PDF (pages 90-122 and 167-183), so
    this project carries the ~800KB of relevant prose instead of the 8MB PDF
    and doesn't need a PDF-reading dependency going forward.

Run:  venv/bin/python3 retrieval/build_solver_docs_index.py
"""

from __future__ import annotations

import re
from pathlib import Path

from tfidf_core import build_index

CORPUS_DIR = Path(__file__).parent / "solver_docs_corpus"
TUTORIALS_DIR = CORPUS_DIR / "tutorials"
INDEX_PATH = Path(__file__).parent / "solver_docs_index.pkl"

SNIPPET_MAX_CHARS = 1400


def clean_foam_field(text: str) -> str:
    """Strip the C++ banner + FoamFile header; keep dimensions/internalField/boundaryField."""
    lines = text.splitlines()
    keep, started = [], False
    for ln in lines:
        if not started and re.match(r"\s*(dimensions|internalField|boundaryField)\b", ln):
            started = True
        if started and not ln.strip().startswith("// *"):
            keep.append(ln.rstrip())
    return "\n".join(keep).strip()


def boundary_snippet(cleaned: str) -> str:
    """Pull out the most useful bit for display: dimensions/internalField + boundaryField{...}."""
    lines = cleaned.splitlines()
    head = [ln for ln in lines if re.match(r"\s*(dimensions|internalField)\b", ln)]
    block, depth, inside = [], 0, False
    for ln in lines:
        if not inside and "boundaryField" in ln:
            inside = True
        if inside:
            block.append(ln)
            depth += ln.count("{") - ln.count("}")
            if depth == 0 and "{" in "".join(block):
                break
    snippet = "\n".join(head + block).strip() or cleaned
    return snippet[:SNIPPET_MAX_CHARS]


def _load_tutorial_docs() -> list[dict]:
    docs = []
    for path in sorted(TUTORIALS_DIR.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_text(errors="replace")
        cleaned = clean_foam_field(raw)
        if "boundaryField" not in cleaned:
            continue
        rel = path.relative_to(TUTORIALS_DIR)
        family = rel.parts[0] if rel.parts else "?"
        docs.append({
            "kind": "tutorial",
            "source": f"tutorial: {rel}",
            "title": f"{family} — field {path.name}",
            "text": cleaned,
            "snippet": boundary_snippet(cleaned),
        })
    return docs


def _load_userguide_docs() -> list[dict]:
    docs = []
    for label in ("case-setup", "boundary-conditions"):
        words = (CORPUS_DIR / f"userguide_{label}.txt").read_text().split()
        step, size = 110, 140
        for start in range(0, len(words), step):
            chunk = " ".join(words[start:start + size]).strip()
            if len(chunk) < 200:
                continue
            digits = sum(c.isdigit() for c in chunk)
            if digits > len(chunk) * 0.15:  # skip index/TOC-like noise
                continue
            docs.append({
                "kind": "userguide",
                "source": f"UserGuide §{label}",
                "title": f"User Guide — {label}",
                "text": chunk,
                "snippet": chunk[:SNIPPET_MAX_CHARS],
            })
    return docs


def main() -> None:
    docs = _load_tutorial_docs() + _load_userguide_docs()
    n = build_index(docs, INDEX_PATH)
    print(f"solver_docs index built: {n} documents -> {INDEX_PATH}")


if __name__ == "__main__":
    main()
