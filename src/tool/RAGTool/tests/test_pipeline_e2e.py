"""End-to-end test of the RAG pipeline using ONLY offline-testable
providers (hash embedding, in-memory vector store, BM25, no-op reranker,
no LLM). Proves the wiring between every stage is correct without needing
any network, GPU, or external service. Run with:

    python3 -m unittest tests.test_pipeline_e2e -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chunking.hierarchical_semantic_chunker import HierarchicalSemanticChunker
from app.embedding.hash_provider import HashEmbeddingProvider
from app.parsers.base import ParsedBlock, ParsedDocument
from app.parsers.router import ParserRouter
from app.pipeline.ingest_pipeline import IngestPipeline
from app.pipeline.query_pipeline import QueryPipeline
from app.rerank.noop_reranker import NoOpReranker
from app.sparse.bm25_index import BM25Index
from app.vectordb.memory_store import InMemoryVectorStore


class _FakeParserRouter(ParserRouter):
    """Bypasses real file parsing (no test PDF needed) — feeds a
    pre-built ParsedDocument straight into the pipeline so this test
    only exercises chunking -> embedding -> indexing -> retrieval."""

    def __init__(self, doc: ParsedDocument) -> None:
        self._doc = doc

    def parse(self, path):  # noqa: D401 - test double
        return self._doc


class PipelineEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.embedder = HashEmbeddingProvider(dimension=128)
        self.vector_store = InMemoryVectorStore()
        self.bm25 = BM25Index()
        self.chunker = HierarchicalSemanticChunker(embedder=self.embedder, max_tokens=100)

        doc = ParsedDocument(
            source_path="fake.pdf",
            parser_name="fake",
            blocks=[
                ParsedBlock(text="Zabbix Monitoring", block_type="heading", level=1),
                ParsedBlock(
                    text="Zabbix triggers fire when CPU usage exceeds 90 percent on any monitored host.",
                    block_type="paragraph",
                ),
                ParsedBlock(
                    text="Active problems are shown on the Zabbix dashboard with severity levels.",
                    block_type="paragraph",
                ),
                ParsedBlock(text="Grafana Dashboards", block_type="heading", level=1),
                ParsedBlock(
                    text="Grafana visualizes metrics pulled from Prometheus and other data sources.",
                    block_type="paragraph",
                ),
            ],
        )

        self.ingest_pipeline = IngestPipeline(
            parser_router=_FakeParserRouter(doc),
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            collection="test",
        )
        self.query_pipeline = QueryPipeline(
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            reranker=NoOpReranker(),
            collection="test",
        )

    def test_ingest_produces_chunks(self):
        result = self.ingest_pipeline.ingest("fake.pdf", doc_id="doc1")
        self.assertGreater(result.chunk_count, 0)
        self.assertEqual(result.parser_used, "fake")

    def test_query_retrieves_relevant_chunk(self):
        self.ingest_pipeline.ingest("fake.pdf", doc_id="doc1")
        retrieved = self.query_pipeline.retrieve("zabbix cpu trigger")
        self.assertGreater(len(retrieved), 0)
        # the top hit should be about Zabbix, not Grafana, for a Zabbix-specific query
        self.assertIn("zabbix", retrieved[0].text.lower())

    def test_answer_without_llm_client_is_retrieval_only(self):
        self.ingest_pipeline.ingest("fake.pdf", doc_id="doc1")
        result = self.query_pipeline.answer("grafana data sources")
        self.assertIn("no LLM client configured", result.answer)
        self.assertGreater(len(result.retrieved), 0)


if __name__ == "__main__":
    unittest.main()
