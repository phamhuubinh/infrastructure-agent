from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.fusion.rrf import reciprocal_rank_fusion


class RrfTest(unittest.TestCase):
    def test_doc_appearing_in_both_rankings_outranks_single_ranking_doc(self):
        fused = reciprocal_rank_fusion({
            "dense": ["a", "b", "c"],
            "sparse": ["b", "a", "d"],
        })
        ids = [f.id for f in fused]
        # 'a' and 'b' both appear in both rankings near the top; either could
        # be first depending on exact ranks, but both must outrank 'c' and 'd'
        # which each appear in only one ranking.
        self.assertLess(ids.index("a"), ids.index("c"))
        self.assertLess(ids.index("b"), ids.index("d"))

    def test_top_k_truncates(self):
        fused = reciprocal_rank_fusion({"dense": ["a", "b", "c", "d"]}, top_k=2)
        self.assertEqual(len(fused), 2)

    def test_sources_tracks_rank_per_ranking(self):
        fused = reciprocal_rank_fusion({"dense": ["a", "b"], "sparse": ["b", "a"]})
        by_id = {f.id: f.sources for f in fused}
        self.assertEqual(by_id["a"], {"dense": 1, "sparse": 2})
        self.assertEqual(by_id["b"], {"dense": 2, "sparse": 1})


if __name__ == "__main__":
    unittest.main()
