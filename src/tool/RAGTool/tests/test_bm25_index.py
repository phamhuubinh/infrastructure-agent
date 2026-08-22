from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sparse.bm25_index import BM25Index, tokenize


class Bm25IndexTest(unittest.TestCase):
    def setUp(self):
        self.index = BM25Index()
        self.index.add_many(
            [
                ("d1", "zabbix monitoring alerts and triggers for server health"),
                ("d2", "grafana dashboards visualize metrics from prometheus"),
                ("d3", "ssh configuration hardening best practices for linux servers"),
                ("d4", "zabbix host groups and templates configuration guide"),
            ]
        )

    def test_relevant_doc_ranks_first(self):
        hits = self.index.search("zabbix configuration", top_k=4)
        self.assertGreater(len(hits), 0)
        self.assertIn(hits[0].id, ("d1", "d4"))

    def test_irrelevant_query_returns_empty_or_low_scores(self):
        hits = self.index.search("quantum physics blackhole", top_k=4)
        self.assertEqual(hits, [])

    def test_update_existing_doc_changes_results(self):
        self.index.add("d2", "zabbix zabbix zabbix completely different content now")
        hits = self.index.search("zabbix", top_k=4)
        self.assertEqual(hits[0].id, "d2")

    def test_delete_removes_doc_from_results(self):
        self.index.delete("d1")
        hits = self.index.search("zabbix configuration", top_k=4)
        self.assertNotIn("d1", [h.id for h in hits])

    def test_delete_memory_cleanup(self):
        # Verify that deleting documents actually removes entries from internal lists
        initial_doc_ids_len = len(self.index._doc_ids)
        initial_doc_term_freqs_len = len(self.index._doc_term_freqs)
        initial_doc_lengths_len = len(self.index._doc_lengths)

        # Delete one document
        self.index.delete("d1")

        # Check that all three lists have been reduced by 1
        self.assertEqual(len(self.index._doc_ids), initial_doc_ids_len - 1)
        self.assertEqual(
            len(self.index._doc_term_freqs), initial_doc_term_freqs_len - 1
        )
        self.assertEqual(len(self.index._doc_lengths), initial_doc_lengths_len - 1)

    def test_vietnamese_accents_and_d_fold_to_the_same_tokens(self):
        self.index.add("vi", "Máy chủ Đell R750")

        hits = self.index.search("may chu dell")

        self.assertEqual(hits[0].id, "vi")
        self.assertEqual(hits[0].text, "Máy chủ Đell R750")
        self.assertEqual(tokenize("máy chủ Dell"), tokenize("may chu Dell"))
        self.assertEqual(tokenize("Đà Nẵng"), ["da", "nang"])

    def test_persistence_records_normalization_version_and_rebuilds_legacy(self):
        with self.subTest("current format"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                path = Path(directory) / "bm25.json"
                index = BM25Index(persist_path=path)
                index.add("one", "Máy chủ Dell", {"doc_id": "one"})
                persisted = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(persisted["format_version"], 2)
                self.assertTrue(persisted["normalization_version"])
                reloaded = BM25Index(persist_path=path)
                self.assertEqual(
                    reloaded.search("may chu dell")[0].text, "Máy chủ Dell"
                )

        with self.subTest("old normalization version"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                path = Path(directory) / "bm25.json"
                path.write_text(
                    json.dumps(
                        {
                            "format_version": 2,
                            "normalization_version": "old-normalization",
                            "documents": [
                                {
                                    "id": "old-normalization",
                                    "text": "Máy chủ Dell",
                                    "payload": {},
                                }
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                reloaded = BM25Index(persist_path=path)
                self.assertEqual(
                    reloaded.search("may chu dell")[0].id,
                    "old-normalization",
                )
                persisted = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted["normalization_version"],
                    reloaded.normalization_version,
                )

        with self.subTest("legacy format"):
            from tempfile import TemporaryDirectory

            with TemporaryDirectory() as directory:
                path = Path(directory) / "bm25.json"
                path.write_text(
                    json.dumps([{"id": "legacy", "text": "Máy chủ Dell", "payload": {}}]),
                    encoding="utf-8",
                )
                reloaded = BM25Index(persist_path=path)
                self.assertEqual(reloaded.search("may chu dell")[0].id, "legacy")
                self.assertIsInstance(json.loads(path.read_text(encoding="utf-8")), dict)

    def test_remove_persistence_removes_project_index_file(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            path = Path(directory) / "bm25.json"
            index = BM25Index(persist_path=path)
            index.add("one", "project evidence")
            index.remove_persistence()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
