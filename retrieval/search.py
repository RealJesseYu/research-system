"""
search.py — the one entry point for querying either retrieval index.

Substrate-agnostic boundary: everything in retrieval/ is CFD-specific
(solver_docs) or research-specific (literature) content that lives BELOW the
future tool-wrapper line. Nothing in stages/ or supervisor.py may import or
mention this module yet — wiring retrieval into a stage is Step 8+.
"""

from __future__ import annotations

from pathlib import Path

# WORKS BOTH WAYS ON PURPOSE. The bare `from tfidf_core import ...` form only
# resolves when retrieval/ is itself on sys.path — which is how the stage call
# sites reach this module (they insert the directory, then `from search import
# search_index`). But it made `import retrieval.search` raise
# ModuleNotFoundError, so this module was unimportable by its own package name:
# any tool, test or REPL that reached for it the ordinary way simply could not.
# retrieval/ has no __init__.py, so both spellings are legitimate; support both
# rather than force every caller onto the sys.path dance.
try:
    from tfidf_core import search
except ModuleNotFoundError:  # imported as retrieval.search
    from retrieval.tfidf_core import search

_INDEX_PATHS = {
    "solver_docs": Path(__file__).parent / "solver_docs_index.pkl",
    "literature": Path(__file__).parent / "literature_index.pkl",
}


def search_index(index_name: str, query: str, top_k: int = 3) -> list[dict]:
    """Search a named index. index_name must be "solver_docs" or "literature"."""
    if index_name not in _INDEX_PATHS:
        raise ValueError(f"unknown index {index_name!r}, expected one of {list(_INDEX_PATHS)}")

    index_path = _INDEX_PATHS[index_name]
    if not index_path.exists():
        raise FileNotFoundError(
            f"{index_name} index not built yet — run "
            f"venv/bin/python3 retrieval/build_{index_name}_index.py"
        )
    return search(index_path, query, top_k=top_k)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: search.py <solver_docs|literature> <query...>")
        sys.exit(1)
    name, query = sys.argv[1], " ".join(sys.argv[2:])
    for r in search_index(name, query):
        print(f"[{r['score']}] {r['source']}")
        print(f"      {r['title']}")
        for line in r["snippet"].splitlines():
            print(f"      | {line}")
        print()
