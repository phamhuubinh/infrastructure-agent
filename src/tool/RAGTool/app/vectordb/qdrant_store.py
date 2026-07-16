"""Qdrant vector store — production backend.

Requires `pip install qdrant-client` and a running Qdrant instance (see
`docker-compose.yml` at the repo root, which starts one). Written against
the real `qdrant-client` API; collections are created on first upsert if
they don't exist yet, sized from the first vector's dimension.
"""

from __future__ import annotations

from app.vectordb.base import ScoredRecord, VectorRecord


class QdrantVectorStore:
    name = "qdrant"

    def __init__(
        self, url: str = "http://localhost:6333", api_key: str | None = None
    ) -> None:
        try:
            from qdrant_client import QdrantClient
        except ImportError as exc:
            raise RuntimeError(
                "qdrant-client is not installed (`pip install qdrant-client`)"
            ) from exc
        self._client = QdrantClient(url=url, api_key=api_key)
        self._known_collections: set[str] = set()

    def _ensure_collection(self, collection: str, dimension: int) -> None:
        if collection in self._known_collections:
            return
        from qdrant_client.models import Distance, VectorParams

        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
        self._known_collections.add(collection)

    def upsert(self, collection: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        from qdrant_client.models import PointStruct

        self._ensure_collection(collection, dimension=len(records[0].vector))
        points = [
            PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records
        ]
        self._client.upsert(collection_name=collection, points=points)

    def search(
        self, collection: str, query_vector: list[float], top_k: int = 10
    ) -> list[ScoredRecord]:
        if not self._client.collection_exists(collection):
            return []
        results = self._client.query_points(
            collection_name=collection, query=query_vector, limit=top_k
        ).points
        return [
            ScoredRecord(id=str(p.id), score=p.score, payload=p.payload or {})
            for p in results
        ]

    def delete(self, collection: str, ids: list[str]) -> None:
        from qdrant_client.models import PointIdsList

        if not self._client.collection_exists(collection):
            return
        self._client.delete(
            collection_name=collection, points_selector=PointIdsList(points=ids)
        )
