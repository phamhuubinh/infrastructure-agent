"""Shared Phase 3A rank fusion for production hybrid search and its benchmark."""

from collections.abc import Collection, Sequence

HYBRID_CANDIDATE_DEPTH = 50
_RRF_K = 60
_EXACT_FILENAME_BONUS = 0.05


def fuse_hybrid_ranks(
    baseline_ids: Sequence[str], dense_ids: Sequence[str], exact_filename_ids: Collection[str]
) -> dict[str, float]:
    """Fuse bounded segment ranks; preserve the measured exact-filename signal."""
    scores: dict[str, float] = {}
    for ranked in (dense_ids[:HYBRID_CANDIDATE_DEPTH], baseline_ids[:HYBRID_CANDIDATE_DEPTH]):
        for rank, segment_id in enumerate(ranked, 1):
            scores[segment_id] = scores.get(segment_id, 0.0) + 1 / (_RRF_K + rank)
    for segment_id in scores:
        if segment_id in exact_filename_ids:
            scores[segment_id] += _EXACT_FILENAME_BONUS
    return scores
