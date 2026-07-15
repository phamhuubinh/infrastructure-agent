"""In-memory vector store — real, testable without any external service.

Useful for local dev, unit tests, and small collections. Swap for
`QdrantVectorStore` in production (same interface). Optionally persists to
a JSON file so a local dev instance survives restarts.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.vectordb.base import ScoredRecord, VectorRecord


class InMemoryVectorStore:
    name = "memory"

    def __init__(self, persist_path: str | None = None) -> None:
        self._collections: dict[str, dict[str, VectorRecord]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        if self._persist_path and self._persist_path.exists():
            self._load()

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        bucket = self._collections.setdefault(collection, {})
        for record in records:
            bucket[record.id] = record
        self._save()

    def search(self, collection: str, query_vector: list[float], top_k: int = 10) -> list[ScoredRecord]:
        bucket = self._collections.get(collection, {})
        if not bucket:
            return []

        query = np.asarray(query_vector, dtype=np.float64)
        query_norm = np.linalg.norm(query) or 1e-9

        scored: list[ScoredRecord] = []
        for record in bucket.values():
            vec = np.asarray(record.vector, dtype=np.float64)
            denom = (np.linalg.norm(vec) or 1e-9) * query_norm
            score = float(np.dot(vec, query) / denom)
            scored.append(ScoredRecord(id=record.id, score=score, payload=record.payload))

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def delete(self, collection: str, ids: list[str]) -> None:
        bucket = self._collections.get(collection, {})
        for record_id in ids:
            bucket.pop(record_id, None)
        self._save()

    def _save(self) -> None:
        if not self._persist_path:
            return
        data = {
            coll: [
                {"id": r.id, "vector": r.vector, "payload": r.payload}
                for r in records.values()
            ]
            for coll, records in self._collections.items()
        }
        self._persist_path.write_text(json.dumps(data))

    def _load(self) -> None:
        data = json.loads(self._persist_path.read_text())
        for coll, records in data.items():
            self._collections[coll] = {
                r["id"]: VectorRecord(id=r["id"], vector=r["vector"], payload=r["payload"])
                for r in records
            }
