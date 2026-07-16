"""Reciprocal Rank Fusion (RRF) — combines dense (vector) and sparse (BM25)
result lists into one ranking, using rank position only (not raw scores,
which aren't comparable across the two systems). Standard formula:
score(d) = sum over each ranking r containing d of 1 / (k + rank_r(d))
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FusedResult:
    id: str
    score: float
    sources: dict[str, int]  # ranking name -> rank position (1-indexed) it appeared at


def reciprocal_rank_fusion(
    rankings: dict[str, list[str]],
    k: int = 60,
    top_k: int | None = None,
) -> list[FusedResult]:
    """
    Args:
        rankings: e.g. {"dense": ["docA", "docB", ...], "sparse": ["docB", "docC", ...]}
                  each list already ordered best-first.
        k: RRF constant (60 is the standard default from the original paper).
        top_k: truncate the fused result; None returns everything.
    """
    scores: dict[str, float] = {}
    sources: dict[str, dict[str, int]] = {}

    for ranking_name, ids in rankings.items():
        for rank, doc_id in enumerate(ids, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
            sources.setdefault(doc_id, {})[ranking_name] = rank

    fused = [
        FusedResult(id=doc_id, score=score, sources=sources[doc_id])
        for doc_id, score in scores.items()
    ]
    fused.sort(key=lambda r: r.score, reverse=True)
    return fused[:top_k] if top_k else fused
