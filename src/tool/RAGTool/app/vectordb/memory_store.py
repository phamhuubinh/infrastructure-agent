"""In-memory vector store — real, testable without any external service.

Useful for local dev, unit tests, and small collections. Swap for
`QdrantVectorStore` in production (same interface). Optionally persists to
a JSON file so a local dev instance survives restarts.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import numpy as np

from app.vectordb.base import ScoredRecord, VectorRecord


class InMemoryVectorStore:
    name = "memory"

    def __init__(self, persist_path: str | None = None) -> None:
        self._collections: dict[str, dict[str, VectorRecord]] = {}
        self._persist_path = Path(persist_path) if persist_path else None
        self._lock = threading.RLock()
        if self._persist_path and self._persist_path.exists():
            self._load()

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        with self._lock:
            bucket = self._collections.setdefault(collection, {})
            for record in records:
                bucket[record.id] = record
            self._save()

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[ScoredRecord]:
        with self._lock:
            bucket = dict(self._collections.get(collection, {}))
            if not bucket:
                return []

        query = np.asarray(query_vector, dtype=np.float64)
        query_norm = np.linalg.norm(query) or 1e-9

        scored: list[ScoredRecord] = []
        for record in bucket.values():
            vec = np.asarray(record.vector, dtype=np.float64)
            if vec.shape != query.shape:
                continue
            denom = (np.linalg.norm(vec) or 1e-9) * query_norm
            score = float(np.dot(vec, query) / denom)
            scored.append(
                ScoredRecord(id=record.id, score=score, payload=record.payload)
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def delete(self, collection: str, ids: list[str]) -> None:
        with self._lock:
            bucket = self._collections.get(collection, {})
            for record_id in ids:
                bucket.pop(record_id, None)
            self._save()

    def delete_collection(self, collection: str) -> None:
        with self._lock:
            self._collections.pop(collection, None)
            self._save()

    def _save(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            coll: [
                {"id": r.id, "vector": r.vector, "payload": r.payload}
                for r in records.values()
            ]
            for coll, records in self._collections.items()
        }
        tmp_path = self._persist_path.with_suffix(self._persist_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data), encoding="utf-8")
        tmp_path.replace(self._persist_path)

    def _load(self) -> None:
        if self._persist_path is None:
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        for raw_collection, records in data.items():
            if not isinstance(records, list):
                continue
            collection = str(raw_collection)
            bucket: dict[str, VectorRecord] = {}
            for record in records:
                if not isinstance(record, dict):
                    continue
                record_id = record.get("id")
                vector = record.get("vector")
                payload = record.get("payload", {})
                if not isinstance(record_id, str) or not isinstance(vector, list):
                    continue
                bucket[record_id] = VectorRecord(
                    id=record_id,
                    vector=vector,
                    payload=payload if isinstance(payload, dict) else {},
                )
            self._collections[collection] = bucket
