"""Deterministic semantic candidate retrieval.

This module deliberately returns ranked candidates only.  Acceptance remains
the responsibility of a deterministic validator using both a score threshold
and a top-candidate margin.
"""

from __future__ import annotations

import difflib
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass


def normalize_lexical_text(text: str) -> str:
    """Normalize case, Vietnamese diacritics and punctuation deterministically."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_marks = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_marks = without_marks.replace("đ", "d")
    tokens = (
        token.strip("._-")
        for token in re.findall(r"[a-z0-9._-]+", without_marks)
    )
    return " ".join(token for token in tokens if token)


def _ngrams(text: str, size: int = 3) -> set[str]:
    compact = f"  {text.replace(' ', '_')}  "
    if len(compact) <= size:
        return {compact}
    return {compact[index : index + size] for index in range(len(compact) - size + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    label: str
    score: float
    matched_text: str
    source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "score": round(self.score, 4),
            "matched_text": self.matched_text,
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class CandidateValidation:
    accepted: bool
    candidate: SemanticCandidate | None
    margin: float | None
    reason: str


class SemanticCandidateRetriever:
    """Rank aliases with exact, token/BM25-like and character n-gram signals."""

    def __init__(self, aliases: Mapping[str, Iterable[str]]) -> None:
        self._aliases: dict[str, tuple[str, ...]] = {
            label: tuple(
                sorted(
                    {
                        normalized
                        for alias in values
                        if (normalized := normalize_lexical_text(str(alias)))
                    },
                    key=lambda value: (-len(value), value),
                )
            )
            for label, values in aliases.items()
        }
        documents = [
            set(alias.split()) for values in self._aliases.values() for alias in values
        ]
        self._document_count = max(1, len(documents))
        self._document_frequency: Counter[str] = Counter()
        for document in documents:
            self._document_frequency.update(document)

    def retrieve(self, text: str, *, limit: int = 5) -> tuple[SemanticCandidate, ...]:
        """Return ranked candidates; never choose a final route."""
        query = normalize_lexical_text(text)
        if not query:
            return ()
        query_tokens = set(query.split())
        query_grams = _ngrams(query)
        best: dict[str, SemanticCandidate] = {}

        for label, aliases in self._aliases.items():
            for alias in aliases:
                alias_tokens = set(alias.split())
                phrase_match = f" {alias} " in f" {query} "
                if alias == query or alias in query_tokens or phrase_match:
                    score = 1.0 if alias == query or alias in query_tokens else 0.97
                    source = "exact"
                else:
                    overlap = query_tokens & alias_tokens
                    weighted_overlap = sum(
                        math.log(
                            1
                            + self._document_count
                            / (1 + self._document_frequency.get(token, 0))
                        )
                        for token in overlap
                    )
                    possible = sum(
                        math.log(
                            1
                            + self._document_count
                            / (1 + self._document_frequency.get(token, 0))
                        )
                        for token in alias_tokens
                    )
                    token_score = weighted_overlap / possible if possible else 0.0
                    char_score = _jaccard(query_grams, _ngrams(alias))
                    edit_score = max(
                        difflib.SequenceMatcher(None, token, alias).ratio()
                        for token in query_tokens
                    )
                    score = max(token_score * 0.92, char_score, edit_score * 0.9)
                    source = "lexical_fuzzy"

                candidate = SemanticCandidate(
                    label=label,
                    score=round(min(1.0, score), 6),
                    matched_text=alias,
                    source=source,
                )
                current = best.get(label)
                if current is None or candidate.score > current.score:
                    best[label] = candidate

        ranked = sorted(best.values(), key=lambda item: (-item.score, item.label))
        return tuple(ranked[: max(1, limit)])

    @staticmethod
    def validate(
        candidates: Sequence[SemanticCandidate],
        *,
        threshold: float,
        margin_threshold: float,
        compatible: Callable[[str], bool] | None = None,
    ) -> CandidateValidation:
        """Accept only a strong, separated and operation-compatible candidate."""
        eligible = [
            candidate
            for candidate in candidates
            if compatible is None or compatible(candidate.label)
        ]
        if not eligible:
            return CandidateValidation(False, None, None, "no_compatible_candidate")

        top = eligible[0]
        second = eligible[1] if len(eligible) > 1 else None
        margin = top.score - second.score if second is not None else top.score
        if top.score < threshold:
            return CandidateValidation(False, top, margin, "below_threshold")
        if second is not None and margin < margin_threshold:
            return CandidateValidation(False, top, margin, "ambiguous_margin")
        return CandidateValidation(True, top, margin, "accepted")
