"""
tfidf_core.py — shared TF-IDF + cosine-similarity machinery, copied in from
the earlier risky-bit spike's search_docs tool (read-only reference; nothing
in this project imports from or writes back to that project).

Classic TF-IDF: every document and every query becomes a vector of
word-importance scores, and search returns the documents whose vectors point
most nearly the same direction as the query's. No API key, fully offline,
deterministic — the simplest thing that answered the spike's actual need, so
it's what this project reuses rather than reaching for embeddings or a vector
database.

Both retrieval indices in this project (solver_docs and literature) are built
and searched through this one module; only document loading differs per index.
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Any

DEFAULT_K = 3


def expand_identifiers(text: str) -> str:
    """
    Bridge natural-language queries and camelCase identifiers.

    'movingWallVelocity' -> 'movingWallVelocity moving Wall Velocity'
    so a query like "moving wall velocity" matches it. Then lowercase
    everything — this is the only preprocessing the vectorizer does.
    """
    out = []
    for word in re.findall(r"[A-Za-z0-9]+", text):
        out.append(word)
        split = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", word)
        if split != word:
            out.append(split)
    return " ".join(out).lower()


def build_index(docs: list[dict[str, Any]], index_path: Path) -> int:
    """Build a TF-IDF index over `docs` (each needs a "text" key) and pickle it to index_path.

    Each doc dict is stored as-is alongside the vectorizer/matrix, so callers
    can put whatever display fields they want (source, title, snippet, ...).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    matrix = vectorizer.fit_transform(expand_identifiers(d["text"]) for d in docs)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "wb") as f:
        pickle.dump({"vectorizer": vectorizer, "matrix": matrix, "docs": docs}, f)
    return len(docs)


def search(index_path: Path, query: str, top_k: int = DEFAULT_K) -> list[dict[str, Any]]:
    """Return the top_k most relevant docs for `query` (most relevant first)."""
    from sklearn.metrics.pairwise import cosine_similarity

    with open(index_path, "rb") as f:
        idx = pickle.load(f)

    qvec = idx["vectorizer"].transform([expand_identifiers(query)])
    scores = cosine_similarity(qvec, idx["matrix"])[0]
    order = scores.argsort()[::-1][:top_k]

    results = []
    for i in order:
        if scores[i] <= 0:
            continue
        d = dict(idx["docs"][i])
        d["score"] = round(float(scores[i]), 3)
        results.append(d)
    return results
