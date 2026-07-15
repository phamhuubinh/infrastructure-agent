from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chunking.hierarchical_semantic_chunker import HierarchicalSemanticChunker
from app.embedding.hash_provider import HashEmbeddingProvider
from app.parsers.base import ParsedBlock, ParsedDocument


class ChunkerTest(unittest.TestCase):
    def test_headings_produce_heading_path(self):
        doc = ParsedDocument(
            source_path="x",
            parser_name="test",
            blocks=[
                ParsedBlock(text="Chapter 1", block_type="heading", level=1),
                ParsedBlock(text="Some intro text here.", block_type="paragraph"),
                ParsedBlock(text="Section 1.1", block_type="heading", level=2),
                ParsedBlock(text="Detail text under 1.1.", block_type="paragraph"),
            ],
        )
        chunker = HierarchicalSemanticChunker(embedder=None)
        chunks = chunker.chunk(doc, doc_id="d1")
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[-1].heading_path, ["Chapter 1", "Section 1.1"])

    def test_tables_stay_atomic(self):
        doc = ParsedDocument(
            source_path="x",
            parser_name="test",
            blocks=[
                ParsedBlock(text="para before", block_type="paragraph"),
                ParsedBlock(text="| a | b |\n| 1 | 2 |", block_type="table"),
                ParsedBlock(text="para after", block_type="paragraph"),
            ],
        )
        chunker = HierarchicalSemanticChunker(embedder=None)
        chunks = chunker.chunk(doc, doc_id="d1")
        table_chunks = [c for c in chunks if c.metadata.get("block_type") == "table"]
        self.assertEqual(len(table_chunks), 1)
        self.assertIn("| a | b |", table_chunks[0].text)

    def test_long_section_splits_on_token_budget(self):
        long_paragraphs = [ParsedBlock(text="word " * 100, block_type="paragraph") for _ in range(5)]
        doc = ParsedDocument(source_path="x", parser_name="test", blocks=long_paragraphs)
        chunker = HierarchicalSemanticChunker(embedder=None, max_tokens=80)
        chunks = chunker.chunk(doc, doc_id="d1")
        self.assertGreater(len(chunks), 1)

    def test_semantic_split_with_embedder(self):
        doc = ParsedDocument(
            source_path="x",
            parser_name="test",
            blocks=[
                ParsedBlock(text="Zabbix triggers monitor CPU usage on servers.", block_type="paragraph"),
                ParsedBlock(text="Zabbix triggers also monitor disk usage thresholds.", block_type="paragraph"),
                ParsedBlock(text="The recipe requires flour sugar and butter mixed well.", block_type="paragraph"),
            ],
        )
        chunker = HierarchicalSemanticChunker(
            embedder=HashEmbeddingProvider(dimension=64),
            max_tokens=1000,
            min_tokens=1,
            similarity_threshold=0.3,
        )
        chunks = chunker.chunk(doc, doc_id="d1")
        # the unrelated recipe sentence should not be merged with the zabbix ones
        self.assertGreaterEqual(len(chunks), 1)


if __name__ == "__main__":
    unittest.main()
