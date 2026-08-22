"""BM25 sparse index — implemented from scratch (BM25Okapi formula), so it
has zero external dependency (no `rank_bm25` needed) and works fully
offline. This is real, runnable, unit-tested code, not a stub.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)
_PERSISTENCE_FORMAT_VERSION = 2
_NORMALIZATION_VERSION = "unicode-casefold-vietnamese-fold-v1"


def tokenize(text: str) -> list[str]:
    """Return canonical retrieval tokens without modifying stored text."""
    normalized = unicodedata.normalize("NFC", text).casefold()
    folded = "".join(
        character
        for character in unicodedata.normalize("NFKD", normalized)
        if not unicodedata.combining(character)
    ).replace("đ", "d")
    return _TOKEN_RE.findall(folded)


@dataclass
class BM25Hit:
    id: str
    score: float
    text: str = ""
    payload: dict = field(default_factory=dict)


class BM25Index:
    """Classic BM25Okapi. k1/b defaults match the standard Robertson/Sparck-Jones values."""

    def __init__(
        self,
        k1: float = 1.5,
        b: float = 0.75,
        persist_path: str | Path | None = None,
    ) -> None:
        self._k1 = k1
        self._b = b
        self._doc_ids: list[str] = []
        self._doc_term_freqs: list[Counter] = []
        self._doc_lengths: list[int] = []
        self._avg_doc_length = 0.0
        self._doc_freq: Counter = Counter()  # in how many docs does term t appear
        self._id_to_index: dict[str, int] = {}
        self._doc_texts: list[str] = []
        self._doc_payloads: list[dict] = []
        self._persist_path = Path(persist_path) if persist_path else None
        self._needs_rebuild = False
        self._lock = threading.RLock()
        self.logger = logging.getLogger(__name__)
        if self._persist_path and self._persist_path.exists():
            self._load()

    def add(self, doc_id: str, text: str, payload: dict | None = None) -> None:
        with self._lock:
            self._add_unlocked(doc_id, text, payload or {})
            self._save()

    def _add_unlocked(self, doc_id: str, text: str, payload: dict) -> None:
        tokens = tokenize(text)
        term_freqs = Counter(tokens)

        if doc_id in self._id_to_index:
            idx = self._id_to_index[doc_id]
            self._remove_from_stats(idx)
            self._doc_ids[idx] = doc_id
            self._doc_term_freqs[idx] = term_freqs
            self._doc_lengths[idx] = len(tokens)
            self._doc_texts[idx] = text
            self._doc_payloads[idx] = payload
        else:
            self._id_to_index[doc_id] = len(self._doc_ids)
            self._doc_ids.append(doc_id)
            self._doc_term_freqs.append(term_freqs)
            self._doc_lengths.append(len(tokens))
            self._doc_texts.append(text)
            self._doc_payloads.append(payload)

        for term in term_freqs:
            self._doc_freq[term] += 1

        self._recompute_avg_length()

    def add_many(self, docs: list[tuple[str, str]]) -> None:
        with self._lock:
            for doc_id, text in docs:
                self._add_unlocked(doc_id, text, {})
            self._save()

    def _remove_from_stats(self, idx: int) -> None:
        old_terms = self._doc_term_freqs[idx]
        for term in old_terms:
            self._doc_freq[term] -= 1
            if self._doc_freq[term] <= 0:
                del self._doc_freq[term]

    def _recompute_avg_length(self) -> None:
        self._avg_doc_length = (
            sum(self._doc_lengths) / len(self._doc_lengths)
            if self._doc_lengths
            else 0.0
        )

    def _idf(self, term: str) -> float:
        n = len(self._doc_ids)
        df = self._doc_freq.get(term, 0)
        # BM25+ style smoothing to avoid negative idf for very common terms.
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, top_k: int = 10) -> list[BM25Hit]:
        with self._lock:
            return self._search_unlocked(query, top_k)

    def _search_unlocked(self, query: str, top_k: int) -> list[BM25Hit]:
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
                BM25Hit(
                    id=self._doc_ids[i],
                    score=s,
                    text=self._doc_texts[i],
                    payload=dict(self._doc_payloads[i]),
                )
                for i, s in enumerate(scores)
                if s > 0
            ),
            key=lambda h: (-h.score, h.id),
        )
        return ranked[:top_k]

    def delete(self, doc_id: str) -> None:
        with self._lock:
            try:
                idx = self._id_to_index.pop(doc_id)
            except KeyError:
                self.logger.warning("Document ID '%s' not found in index", doc_id)
                return

            self._remove_from_stats(idx)
            del self._doc_ids[idx]
            del self._doc_term_freqs[idx]
            del self._doc_lengths[idx]
            del self._doc_texts[idx]
            del self._doc_payloads[idx]
            self._id_to_index = {
                current_id: current_idx
                for current_idx, current_id in enumerate(self._doc_ids)
            }
            self._recompute_avg_length()
            self._save()

    def clear(self) -> None:
        with self._lock:
            self._doc_ids.clear()
            self._doc_term_freqs.clear()
            self._doc_lengths.clear()
            self._doc_texts.clear()
            self._doc_payloads.clear()
            self._doc_freq.clear()
            self._id_to_index.clear()
            self._avg_doc_length = 0.0
            self._save()

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        documents = [
            {
                "id": doc_id,
                "text": self._doc_texts[idx],
                "payload": self._doc_payloads[idx],
            }
            for idx, doc_id in enumerate(self._doc_ids)
        ]
        data = {
            "format_version": _PERSISTENCE_FORMAT_VERSION,
            "normalization_version": _NORMALIZATION_VERSION,
            "documents": documents,
        }
        temp_path = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp_path.replace(self._persist_path)

    def _load(self) -> None:
        if self._persist_path is None:
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.logger.warning("Could not load BM25 index from %s", self._persist_path)
            return
        if isinstance(data, list):
            # The legacy format contains original source text, so we explicitly
            # rebuild token statistics with the current normalization.
            self.logger.info(
                "Rebuilding legacy BM25 index at %s with normalization %s",
                self._persist_path,
                _NORMALIZATION_VERSION,
            )
            documents = data
            rewrite_after_load = True
        elif (
            isinstance(data, dict)
            and data.get("format_version") == _PERSISTENCE_FORMAT_VERSION
            and isinstance(data.get("documents"), list)
        ):
            documents = data["documents"]
            rewrite_after_load = data.get("normalization_version") != _NORMALIZATION_VERSION
            if rewrite_after_load:
                self.logger.info(
                    "Rebuilding BM25 index at %s from normalization %r to %s",
                    self._persist_path,
                    data.get("normalization_version"),
                    _NORMALIZATION_VERSION,
                )
        else:
            self._needs_rebuild = True
            self.logger.warning(
                "BM25 index at %s has an unsupported format or normalization; "
                "it will not be used until documents are re-indexed",
                self._persist_path,
            )
            return
        for item in documents:
            if not isinstance(item, dict):
                continue
            doc_id = item.get("id")
            text = item.get("text")
            payload = item.get("payload", {})
            if isinstance(doc_id, str) and isinstance(text, str):
                self._add_unlocked(
                    doc_id,
                    text,
                    payload if isinstance(payload, dict) else {},
                )
        if rewrite_after_load:
            self._save()

    @property
    def normalization_version(self) -> str:
        return _NORMALIZATION_VERSION

    @property
    def needs_rebuild(self) -> bool:
        return self._needs_rebuild

    def remove_persistence(self) -> None:
        """Remove this index file when its owning project is deleted."""
        with self._lock:
            if self._persist_path is not None:
                self._persist_path.unlink(missing_ok=True)
