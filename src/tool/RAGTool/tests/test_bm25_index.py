from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.sparse.bm25_index import BM25Index


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


if __name__ == "__main__":
    unittest.main()
