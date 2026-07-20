"""RAPTOR — Recursive Abstractive Processing for Tree-Organized Retrieval
(arxiv.org/abs/2401.18059), OpenRAG-style implementation.

Builds a tree over the corpus: leaf nodes are your normal chunks; each
level above clusters semantically similar chunks (GMM soft clustering,
same as the original paper) and replaces each cluster with an LLM-written
summary node. Retrieval can then match at any tree level — a summary node
answers "what does this whole document cover" questions that no single
chunk can.

The clustering step is real and runs today with only scikit-learn +
numpy (both already available) — no network needed. The summarization
step calls a pluggable `summarize_func(texts: list[str]) -> str`; pass in
any LLM client (see app/serving/llm_client.py) — until one is configured,
a simple extractive fallback (first N sentences of each member, joined) is
used so the tree still builds and is testable end-to-end offline.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from sklearn.mixture import GaussianMixture

from app.embedding.base import EmbeddingProvider


@dataclass
class RaptorNode:
    id: str
    text: str
    level: int
    embedding: list[float]
    children_ids: list[str] = field(default_factory=list)


def _extractive_fallback_summary(texts: list[str]) -> str:
    """Used only if no LLM summarizer is configured — keeps the tree
    buildable/testable offline, but produces a much weaker summary than a
    real LLM call would. Replace with a real summarize_func in production."""
    snippets = [t.strip().split(". ")[0] for t in texts if t.strip()]
    return " / ".join(snippets)[:1000]


class RaptorIndex:
    def __init__(
        self,
        embedder: EmbeddingProvider,
        summarize_func: Callable[[list[str]], str] | None = None,
        max_cluster_size: int = 10,
        max_levels: int = 3,
    ) -> None:
        self._embedder = embedder
        self._summarize = summarize_func or _extractive_fallback_summary
        self._max_cluster_size = max_cluster_size
        self._max_levels = max_levels
        self.nodes: dict[str, RaptorNode] = {}

    def build(self, leaf_texts: list[str]) -> list[RaptorNode]:
        """Build the full tree from leaf chunk texts. Returns all nodes
        (leaves + every summary level) — index all of them in your vector
        store so retrieval can match at any granularity."""
        embeddings = self._embedder.embed(leaf_texts)
        current_level_nodes = [
            RaptorNode(id=str(uuid.uuid4()), text=text, level=0, embedding=emb)
            for text, emb in zip(leaf_texts, embeddings, strict=False)
        ]
        for node in current_level_nodes:
            self.nodes[node.id] = node

        level = 0
        while len(current_level_nodes) > 1 and level < self._max_levels:
            level += 1
            current_level_nodes = self._cluster_and_summarize(
                current_level_nodes, level
            )
            if len(current_level_nodes) <= 1:
                for node in current_level_nodes:
                    self.nodes[node.id] = node
                break

        return list(self.nodes.values())

    def _cluster_and_summarize(
        self, nodes: list[RaptorNode], level: int
    ) -> list[RaptorNode]:
        n_clusters = max(1, len(nodes) // self._max_cluster_size)
        if n_clusters <= 1 or len(nodes) <= self._max_cluster_size:
            summary_node = self._summarize_cluster(nodes, level)
            self.nodes[summary_node.id] = summary_node
            return [summary_node]

        vectors = np.array([n.embedding for n in nodes])
        gmm = GaussianMixture(n_components=n_clusters, random_state=42, n_init=1)
        labels = gmm.fit_predict(vectors)

        clusters: dict[int, list[RaptorNode]] = {}
        for label, node in zip(labels, nodes, strict=False):
            clusters.setdefault(int(label), []).append(node)

        summary_nodes = []
        for cluster_nodes in clusters.values():
            summary_node = self._summarize_cluster(cluster_nodes, level)
            self.nodes[summary_node.id] = summary_node
            summary_nodes.append(summary_node)
        return summary_nodes

    def _summarize_cluster(
        self, cluster_nodes: list[RaptorNode], level: int
    ) -> RaptorNode:
        texts = [n.text for n in cluster_nodes]
        summary_text = self._summarize(texts)
        summary_embedding = self._embedder.embed([summary_text])[0]
        return RaptorNode(
            id=str(uuid.uuid4()),
            text=summary_text,
            level=level,
            embedding=summary_embedding,
            children_ids=[n.id for n in cluster_nodes],
        )
