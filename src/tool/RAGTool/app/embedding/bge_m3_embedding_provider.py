"""BGE-M3 embedding provider — use when multilingual retrieval quality
matters more than Qwen3-Embedding's benchmark scores (BGE-M3 supports
100+ languages natively and also exposes sparse + ColBERT-style vectors,
though this provider only exposes the dense vector to keep the interface
uniform with the other providers).

Requires `pip install FlagEmbedding`. Model downloads from Hugging Face on
first use.
"""

from __future__ import annotations


class BgeM3EmbeddingProvider:
    name = "bge-m3"

    def __init__(
        self,
        model_name: str = "BAAI/bge-m3",
        device: str = "cuda",
        use_fp16: bool = True,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._use_fp16 = use_fp16
        self._model = None
        self.dimension = 1024

    def _get_model(self):
        if self._model is None:
            try:
                from FlagEmbedding import BGEM3FlagModel
            except ImportError as exc:
                raise RuntimeError(
                    "FlagEmbedding is not installed (`pip install FlagEmbedding`)"
                ) from exc
            self._model = BGEM3FlagModel(
                self._model_name, use_fp16=self._use_fp16, device=self._device
            )
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        output = model.encode(
            texts, return_dense=True, return_sparse=False, return_colbert_vecs=False
        )
        return output["dense_vecs"].tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]
