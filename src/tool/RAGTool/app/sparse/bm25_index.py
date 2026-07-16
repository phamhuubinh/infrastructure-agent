"""BM25 sparse index — implemented from scratch (BM25Okapi formula), so it
has zero external dependency (no `rank_bm25` needed) and works fully
offline. This is real, runnable, unit-tested code, not a stub.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_TOKEN_RE = re.compile(r"[\wÀ-ỹ]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass
class BM25Hit:
    id: str
    score: float


class BM25Index:
    """Classic BM25Okapi. k1/b defaults match the standard Robertson/Sparck-Jones values."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self._k1 = k1
        self._b = b
        self._doc_ids: list[str] = []
        self._doc_term_freqs: list[Counter] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length = 0.0
        self._doc_freq: Counter = Counter()  # in how many docs does term t appear
        self._id_to_index: dict[str, int] = {}

    def add(self, doc_id: str, text: str) -> None:
        tokens = tokenize(text)
        term_freqs = Counter(tokens)

        if doc_id in self._id_to_index:
            self._remove_from_stats(self._id_to_index[doc_id])
            idx = self._id_to_index[doc_id]
            self._doc_ids[idx] = doc_id
            self._doc_term_freqs[idx] = term_freqs
            self._doc_lengths[idx] = len(tokens)
        else:
            self._id_to_index[doc_id] = len(self._doc_ids)
            self._doc_ids.append(doc_id)
            self._doc_term_freqs.append(term_freqs)
            self._doc_lengths.append(len(tokens))

        for term in term_freqs:
            self._doc_freq[term] += 1

        self._recompute_avg_length()

    def add_many(self, docs: list[tuple[str, str]]) -> None:
        for doc_id, text in docs:
            self.add(doc_id, text)

    def _remove_from_stats(self, idx: int) -> None:
        old_terms = self._doc_term_freqs[idx]
        for term in old_terms:
            self._doc_freq[term] -= 1
            if self._doc_freq[term] <= 0:
                del self._doc_freq[term]

    def _recompute_avg_length(self) -> None:
        if self._doc_lengths:
            self._avg_doc_length = sum(self._doc_lengths) / len(self._doc_lengths)

    def _idf(self, term: str) -> float:
        n = len(self._doc_ids)
        df = self._doc_freq.get(term, 0)
        # BM25+ style smoothing to avoid negative idf for very common terms.
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[BM25Hit]:
        if not self._doc_ids:
            return []

        query_terms = tokenize(query)
        if not query_terms:
            return []

        scores = [0.0] * len(self._doc_ids)
        for term in set(query_terms):
            idf = self._idf(term)
            if idf <= 0:
                continue
            for idx, term_freqs in enumerate(self._doc_term_freqs):
                freq = term_freqs.get(term, 0)
                if freq == 0:
                    continue
                doc_len = self._doc_lengths[idx]
                denom = freq + self._k1 * (
                    1 - self._b + self._b * doc_len / (self._avg_doc_length or 1)
                )
                scores[idx] += idf * (freq * (self._k1 + 1)) / denom

        ranked = sorted(
            (
                BM25Hit(id=self._doc_ids[i], score=s)
                for i, s in enumerate(scores)
                if s > 0
            ),
            key=lambda h: h.score,
            reverse=True,
        )
        return ranked[:top_k]

    def delete(self, doc_id: str) -> None:
        if doc_id not in self._id_to_index:
            return
        idx = self._id_to_index.pop(doc_id)
        self._remove_from_stats(idx)
        self._doc_ids[idx] = ""
        self._doc_term_freqs[idx] = Counter()
        self._doc_lengths[idx] = 0
        self._recompute_avg_length()
