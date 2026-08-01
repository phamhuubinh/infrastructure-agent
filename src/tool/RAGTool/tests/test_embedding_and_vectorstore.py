from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.embedding.hash_provider import HashEmbeddingProvider
from app.vectordb.base import VectorRecord
from app.vectordb.memory_store import InMemoryVectorStore


class HashEmbeddingTest(unittest.TestCase):
    def test_deterministic(self):
        embedder = HashEmbeddingProvider(dimension=64)
        v1 = embedder.embed(["hello world"])[0]
        v2 = embedder.embed(["hello world"])[0]
        self.assertEqual(v1, v2)

    def test_different_text_different_vector(self):
        embedder = HashEmbeddingProvider(dimension=64)
        v1 = embedder.embed(["hello world"])[0]
        v2 = embedder.embed(["completely unrelated sentence about cooking"])[0]
        self.assertNotEqual(v1, v2)

    def test_empty_text_is_zero_vector(self):
        embedder = HashEmbeddingProvider(dimension=32)
        v = embedder.embed([""])[0]
        self.assertEqual(sum(abs(x) for x in v), 0.0)


class InMemoryVectorStoreTest(unittest.TestCase):
    def test_search_returns_closest_first(self):
        store = InMemoryVectorStore()
        store.upsert(
            "coll",
            [
                VectorRecord(id="a", vector=[1.0, 0.0], payload={"text": "a"}),
                VectorRecord(id="b", vector=[0.0, 1.0], payload={"text": "b"}),
            ],
        )
        results = store.search("coll", query_vector=[1.0, 0.0], top_k=2)
        self.assertEqual(results[0].id, "a")

    def test_delete_removes_record(self):
        store = InMemoryVectorStore()
        store.upsert("coll", [VectorRecord(id="a", vector=[1.0, 0.0], payload={})])
        store.delete("coll", ["a"])
        self.assertEqual(store.search("coll", [1.0, 0.0]), [])

    def test_empty_collection_returns_empty(self):
        store = InMemoryVectorStore()
        self.assertEqual(store.search("nonexistent", [1.0, 0.0]), [])

    def test_persistence_keeps_collections_isolated(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = str(Path(directory) / "vectors.json")
            store = InMemoryVectorStore(persist_path=path)
            store.upsert("alpha", [VectorRecord("a", [1.0, 0.0], {"text": "a"})])
            store.upsert("beta", [VectorRecord("b", [0.0, 1.0], {"text": "b"})])

            reloaded = InMemoryVectorStore(persist_path=path)
            self.assertEqual(reloaded.search("alpha", [1.0, 0.0])[0].id, "a")
            self.assertEqual(reloaded.search("beta", [0.0, 1.0])[0].id, "b")

    def test_corrupt_persistence_starts_empty(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "vectors.json"
            path.write_text("not json")
            store = InMemoryVectorStore(persist_path=str(path))
            self.assertEqual(store.search("alpha", [1.0]), [])

    def test_search_skips_vectors_with_old_dimension(self):
        store = InMemoryVectorStore()
        store.upsert("coll", [VectorRecord("old", [1.0, 0.0], {})])
        self.assertEqual(store.search("coll", [1.0, 0.0, 0.0]), [])


if __name__ == "__main__":
    unittest.main()
