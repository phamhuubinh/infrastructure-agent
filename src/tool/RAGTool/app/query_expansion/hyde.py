"""HyDE (Hypothetical Document Embeddings, arxiv.org/abs/2212.10496).

Instead of embedding the raw user query (short, sparse in vocabulary),
ask an LLM to write a hypothetical answer/passage, then embed *that* — it
tends to be lexically/semantically closer to real relevant documents than
the bare query is. Uses whatever LLM client is configured
(app/serving/llm_client.py, OpenAI-compatible — works with vLLM).
"""

from __future__ import annotations

from app.embedding.base import EmbeddingProvider
from app.serving.llm_client import LlmClient

_HYDE_PROMPT_TEMPLATE = (
    "Write a short, factual passage (3-5 sentences) that would answer the "
    "following question. Do not mention that this is hypothetical — write "
    "as if it were a real excerpt from technical documentation.\n\n"
    "Question: {query}\n\nPassage:"
)


class HydeQueryExpander:
    def __init__(
        self,
        llm_client: LlmClient,
        embedder: EmbeddingProvider,
        num_hypotheses: int = 1,
    ) -> None:
        self._llm = llm_client
        self._embedder = embedder
        self._num_hypotheses = num_hypotheses

    def expand_to_embedding(self, query: str) -> list[float]:
        """Generate hypothesis document(s) and return the (averaged)
        embedding to use for dense retrieval instead of the raw query
        embedding."""
        hypotheses = self._generate_hypotheses(query)
        vectors = self._embedder.embed(hypotheses)

        if len(vectors) == 1:
            return vectors[0]

        import numpy as np

        averaged = np.mean(np.array(vectors), axis=0)
        norm = np.linalg.norm(averaged) or 1e-9
        return (averaged / norm).tolist()

    def _generate_hypotheses(self, query: str) -> list[str]:
        prompt = _HYDE_PROMPT_TEMPLATE.format(query=query)
        hypotheses = []
        for _ in range(self._num_hypotheses):
            text = self._llm.complete(prompt, temperature=0.7, max_tokens=200)
            hypotheses.append(text.strip() or query)
        return hypotheses or [query]
