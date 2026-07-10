"""
tournament.py — pure Elo-tournament machinery for stage-1 Ranking (Step 17-C).

Every function in this module is pure: ZERO model calls, ZERO file I/O, no
randomness — so all of it is unit-testable with canned inputs. The stage flow
that USES these functions (the Opus judge calls, the tiered debate
construction, A/B presentation randomization, evidence writes, logging) lives
in stages/stage1_ideation.py. This module only computes: standard Elo
updates, a TF-IDF proximity matrix over survivor texts (reusing
retrieval/tfidf_core.py's vectorizer machinery — its expand_identifiers
preprocessing and its exact TfidfVectorizer configuration), near-duplicate
flags (J8: flag, never remove), the most-similar-first match order (J3: every
pair plays, no sampling), the both-orderings debate score rule (J5), the
final Elo ranking with the J9 tiebreak, and the tournament_state.json dict
shape (J7).
"""

from __future__ import annotations

from retrieval.tfidf_core import expand_identifiers

ELO_INIT = 1200.0
K_FACTOR = 32
DEDUP_THRESHOLD = 0.85


def elo_update(
    r_a: float, r_b: float, score_a: float, k: int = K_FACTOR
) -> tuple[float, float]:
    """Standard Elo update for one match. score_a is A's result: 1.0 win,
    0.5 draw, 0.0 loss. Returns (new_r_a, new_r_b); zero-sum, so the pair's
    total rating is conserved."""
    expected_a = 1.0 / (1.0 + 10.0 ** ((r_b - r_a) / 400.0))
    expected_b = 1.0 - expected_a
    score_b = 1.0 - score_a
    return (r_a + k * (score_a - expected_a), r_b + k * (score_b - expected_b))


def proximity_matrix(survivors: list[dict]) -> list[list[float]]:
    """Pairwise cosine similarities over each survivor's statement+rationale
    text, through the same vectorizer machinery tfidf_core builds this
    project's retrieval indices with (expand_identifiers preprocessing; same
    TfidfVectorizer parameters). Deterministic for a fixed survivor list.
    Returns a k x k symmetric list-of-lists of floats."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    texts = [
        expand_identifiers(s["statement"] + " " + s["rationale"]) for s in survivors
    ]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, stop_words="english")
    sims = cosine_similarity(vectorizer.fit_transform(texts))
    k = len(survivors)
    return [[float(sims[i][j]) for j in range(k)] for i in range(k)]


def dedup_flags(
    matrix: list[list[float]], threshold: float = DEDUP_THRESHOLD
) -> list[tuple[int, int, float]]:
    """Near-duplicate pairs: every (i, j, sim) with i < j and sim >= threshold.
    Flags only — nothing is ever removed on their account (J8)."""
    flags = []
    for i in range(len(matrix)):
        for j in range(i + 1, len(matrix)):
            if matrix[i][j] >= threshold:
                flags.append((i, j, matrix[i][j]))
    return flags


def order_matches(
    pairs: list[tuple[int, int]], matrix: list[list[float]]
) -> list[tuple[int, int]]:
    """All given pairs sorted most-similar-first (J3: every pair plays — the
    caller passes all C(k,2) pairs; nothing is sampled away here), with a
    deterministic tiebreak on the (i, j) indices themselves."""
    return sorted(pairs, key=lambda p: (-matrix[p[0]][p[1]], p[0], p[1]))


def debate_score(id_a: str, id_b: str, winner_first: str, winner_second: str) -> float:
    """J5 rule for a debate match run twice with A/B swapped: the two judge
    verdicts agree -> that winner takes the match at score 1.0; they disagree
    -> draw at 0.5. Returns the score for id_a (id_b's score is 1 - this)."""
    if winner_first == winner_second:
        return 1.0 if winner_first == id_a else 0.0
    return 0.5


def final_ranking(
    ratings: dict[str, float],
    survivors_full: list[dict],
    flags: list[tuple[int, int, float]] = (),
) -> list[dict]:
    """Survivors sorted by Elo descending; EQUAL Elo breaks by
    survivors_full's existing order, which is already (reflection quality
    desc, generation order asc) from filter_survivors (J9). For each
    near-dupe pair in `flags` (index pairs into survivors_full), the member
    ranked below its sibling gets "deduped_by": <the higher-ranked sibling's
    id> — a flag only; nothing is removed from the ranking (J8). A member
    flagged against several higher-ranked siblings points at the
    highest-ranked one. Returns ranked copies; the inputs are not mutated."""
    order = sorted(
        range(len(survivors_full)),
        key=lambda i: (-ratings[survivors_full[i]["id"]], i),
    )
    ranked = [dict(survivors_full[i]) for i in order]
    pos = {s["id"]: p for p, s in enumerate(ranked)}
    for i, j, _sim in flags:
        id_i, id_j = survivors_full[i]["id"], survivors_full[j]["id"]
        lower, higher = (id_i, id_j) if pos[id_i] > pos[id_j] else (id_j, id_i)
        current = ranked[pos[lower]].get("deduped_by")
        if current is None or pos[higher] < pos[current]:
            ranked[pos[lower]]["deduped_by"] = higher
    return ranked


def build_match_record(
    pair_ids: list[str],
    tier: str,
    orderings: list[list[str]],
    verdicts: list[str],
    reasons: list[str],
    elo_before: dict[str, float],
    elo_after: dict[str, float],
) -> dict:
    """One match_log entry in tournament_state.json's J7 shape. The plural
    fields are always lists: one element for a single-turn match, two for a
    debate match (both orderings)."""
    return {
        "pair": pair_ids,
        "tier": tier,
        "orderings": orderings,
        "verdicts": verdicts,
        "reasons": reasons,
        "elo_before": elo_before,
        "elo_after": elo_after,
    }


def matrix_pair_map(ids: list[str], matrix: list[list[float]]) -> dict[str, float]:
    """The proximity matrix flattened to a '<id_i>_vs_<id_j>': sim map
    (i < j only — the matrix is symmetric and the diagonal is trivial)."""
    return {
        f"{ids[i]}_vs_{ids[j]}": matrix[i][j]
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
    }


def build_state(
    rng_seed: str,
    ratings: dict[str, float],
    match_log: list[dict],
    ids: list[str],
    matrix: list[list[float]],
    flags: list[tuple[int, int, float]],
    ranked: list[dict],
) -> dict:
    """The complete tournament_state.json dict (J7). `ids` is the survivor
    ids in survivors_full order (indexing `matrix` and `flags`); `ranked` is
    final_ranking's output."""
    return {
        "elo_init": ELO_INIT,
        "k_factor": K_FACTOR,
        "rng_seed": rng_seed,
        "ratings": ratings,
        "match_log": match_log,
        "proximity": {
            "matrix": matrix_pair_map(ids, matrix),
            "dedup_flags": [
                {"pair": [ids[i], ids[j]], "similarity": sim} for i, j, sim in flags
            ],
        },
        "final_ranking": [
            {
                "id": s["id"],
                "elo": ratings[s["id"]],
                **({"deduped_by": s["deduped_by"]} if "deduped_by" in s else {}),
            }
            for s in ranked
        ],
    }
