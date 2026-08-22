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
from unittest.mock import MagicMock

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


class _FakeLlmClient:
    def complete(self, prompt, temperature=0.2, max_tokens=512):
        return "Synthesized analysis"


class PipelineEndToEndTest(unittest.TestCase):
    def setUp(self):
        self.embedder = HashEmbeddingProvider(dimension=128)
        self.vector_store = InMemoryVectorStore()
        self.bm25 = BM25Index()
        self.chunker = HierarchicalSemanticChunker(
            embedder=self.embedder, max_tokens=100
        )

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
        self.doc = doc

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
            llm_client=_FakeLlmClient(),
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

    def test_answer_requires_llm_client(self):
        self.ingest_pipeline.ingest("fake.pdf", doc_id="doc1")
        pipeline = QueryPipeline(
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            reranker=NoOpReranker(),
            collection="test",
        )
        with self.assertRaisesRegex(RuntimeError, "No analysis model configured"):
            pipeline.answer("grafana data sources")

    def test_answer_always_synthesizes_with_model(self):
        self.ingest_pipeline.ingest("fake.pdf", doc_id="doc1")
        result = self.query_pipeline.answer("grafana data sources")
        self.assertEqual(result.answer, "Synthesized analysis")
        self.assertGreater(len(result.retrieved), 0)

    def test_project_collections_do_not_cross_retrieve(self):
        alpha_doc = ParsedDocument(
            source_path="alpha.txt",
            parser_name="fake",
            blocks=[
                ParsedBlock(text="alphaonly deployment plan", block_type="paragraph")
            ],
        )
        beta_doc = ParsedDocument(
            source_path="beta.txt",
            parser_name="fake",
            blocks=[
                ParsedBlock(text="betaonly incident report", block_type="paragraph")
            ],
        )

        def project_pipeline(project: str, document: ParsedDocument):
            sparse = BM25Index()
            ingest = IngestPipeline(
                parser_router=_FakeParserRouter(document),
                chunker=self.chunker,
                embedder=self.embedder,
                vector_store=self.vector_store,
                bm25_index=sparse,
                collection=f"project-{project}",
            )
            query = QueryPipeline(
                embedder=self.embedder,
                vector_store=self.vector_store,
                bm25_index=sparse,
                reranker=NoOpReranker(),
                collection=f"project-{project}",
            )
            return ingest, query

        alpha_ingest, alpha_query = project_pipeline("alpha", alpha_doc)
        beta_ingest, beta_query = project_pipeline("beta", beta_doc)
        alpha_ingest.ingest("alpha.txt", doc_id="doc-alpha")
        beta_ingest.ingest("beta.txt", doc_id="doc-beta")

        alpha_hits = alpha_query.retrieve("alphaonly")
        beta_hits = beta_query.retrieve("alphaonly")

        self.assertTrue(alpha_hits)
        self.assertEqual(beta_hits, [])
        self.assertTrue(all(hit.payload["doc_id"] == "doc-alpha" for hit in alpha_hits))

    def test_sparse_failure_rolls_back_dense_chunks(self):
        failing_sparse = MagicMock(spec=BM25Index)
        failing_sparse.add.side_effect = RuntimeError("sparse index failed")
        pipeline = IngestPipeline(
            parser_router=_FakeParserRouter(self.doc),
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=failing_sparse,
            collection="rollback",
        )

        with self.assertRaisesRegex(RuntimeError, "sparse index failed"):
            pipeline.ingest("fake.pdf", doc_id="rollback-doc")

        query_vector = self.embedder.embed_query("zabbix")
        self.assertEqual(self.vector_store.search("rollback", query_vector), [])

    def test_path_traversal_prevention(self):
        """Test that path traversal attempts raise ValueError"""
        # Create a separate pipeline instance with data_dir to test path traversal
        # This avoids affecting the main test setup
        test_pipeline = IngestPipeline(
            parser_router=_FakeParserRouter(
                ParsedDocument(source_path="fake.pdf", parser_name="fake", blocks=[])
            ),
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            collection="test",
            data_dir="/tmp/test_data",  # Set data_dir to enable validation
        )

        # Test with a path that tries to traverse up the directory structure
        with self.assertRaises(ValueError) as context:
            test_pipeline.ingest("../etc/passwd", doc_id="doc1")

        # Verify that the error message contains the expected text
        self.assertIn("Invalid path", str(context.exception))

    def test_ingest_with_malicious_path_raises_validation_error(self):
        """Test that malicious path inputs raise validation error"""
        # Create a separate pipeline instance with data_dir to test path traversal
        test_pipeline = IngestPipeline(
            parser_router=_FakeParserRouter(
                ParsedDocument(source_path="fake.pdf", parser_name="fake", blocks=[])
            ),
            chunker=self.chunker,
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            collection="test",
            data_dir="/tmp/test_data",  # Set data_dir to enable validation
        )

        # Test with various malicious paths that try to traverse up the directory structure
        malicious_paths = [
            "../../etc/passwd",
            "../../../etc/passwd",
            "../secret_file.txt",
            "/etc/passwd",
            "../../../../../../../../etc/passwd",
        ]

        for malicious_path in malicious_paths:
            with self.subTest(path=malicious_path):
                with self.assertRaises(ValueError) as context:
                    test_pipeline.ingest(malicious_path, doc_id="doc1")

                # Verify that the error message contains the expected text
                self.assertIn("Invalid path", str(context.exception))

    def test_ingest_pipeline_raises_value_error_on_mismatched_lengths(self):
        """Test that ingest_pipeline raises ValueError when chunks and vectors have different lengths"""
        # Create fake data with chunks of length 3 and vectors of length 5
        # We'll mock the embedder to return vectors of different length than chunks
        # Create a mock embedder that returns more vectors than chunks
        mock_embedder = MagicMock()
        mock_embedder.embed.return_value = [1, 2, 3, 4, 5]  # 5 vectors for 3 chunks

        # Create a mock chunker that returns 3 chunks
        mock_chunker = MagicMock()
        mock_chunker.chunk.return_value = [
            MagicMock(chunk_id="chunk1", text="text1"),
            MagicMock(chunk_id="chunk2", text="text2"),
            MagicMock(chunk_id="chunk3", text="text3"),
        ]

        # Create a fake document
        fake_doc = ParsedDocument(
            source_path="fake.pdf",
            parser_name="fake",
            blocks=[
                ParsedBlock(text="Text 1", block_type="paragraph"),
                ParsedBlock(text="Text 2", block_type="paragraph"),
                ParsedBlock(text="Text 3", block_type="paragraph"),
            ],
        )

        # Create pipeline with mocks
        test_pipeline = IngestPipeline(
            parser_router=_FakeParserRouter(fake_doc),
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=self.vector_store,
            bm25_index=self.bm25,
            collection="test",
        )

        # Verify that ValueError is raised with appropriate message
        with self.assertRaises(ValueError) as context:
            test_pipeline.ingest("fake.pdf", doc_id="doc1")

        # Check that the error message contains 'lengths differ'
        self.assertIn("longer than", str(context.exception))


if __name__ == "__main__":
    unittest.main()
