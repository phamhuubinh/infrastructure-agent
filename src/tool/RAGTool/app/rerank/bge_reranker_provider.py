"""BGE-reranker-v2 provider.

Requires `pip install FlagEmbedding` (uses the lightweight
`FlagReranker`/`LayerWiseFlagLLMReranker` gemma-based v2 model family).
Written against FlagEmbedding's real API.
"""

from __future__ import annotations

from app.rerank.base import RerankedResult


class BgeRerankerV2Provider:
    name = "bge-reranker-v2"

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cuda",
        use_fp16: bool = True,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._use_fp16 = use_fp16
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from FlagEmbedding import FlagReranker
            except ImportError as exc:
                msg = "FlagEmbedding is not installed (`pip install FlagEmbedding`)"
                raise RuntimeError(msg) from exc
            self._model = FlagReranker(
                self._model_name, use_fp16=self._use_fp16, device=self._device
            )
        return self._model

    def rerank(
        self, query: str, candidates: list[tuple[str, str]], top_k: int = 10
    ) -> list[RerankedResult]:
        if not candidates:
            return []
        model = self._get_model()
        pairs = [[query, text] for _id, text in candidates]
        scores = model.compute_score(pairs, normalize=True)
        if isinstance(scores, float):
            scores = [scores]

        results = [
            RerankedResult(id=cid, score=float(score), text=text)
            for (cid, text), score in zip(candidates, scores)
        ]
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]
