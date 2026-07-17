"""Qwen3-Embedding provider (local inference).

Requires `pip install sentence-transformers>=3.0` and a GPU with enough VRAM
for the chosen size (0.6B/4B/8B variants exist — pick based on your host).
Model downloads from Hugging Face on first use (needs network once).

Qwen3-Embedding uses instruction-prefixed queries for retrieval — this
provider applies the recommended instruction template for queries and
leaves documents unprefixed, per the model's usage guide.
"""

from __future__ import annotations


class Qwen3EmbeddingProvider:
    name = "qwen3-embedding"

    _QUERY_INSTRUCTION = (
        "Instruct: Given a web search query, retrieve relevant passages that "
        "answer the query\nQuery: "
    )

    def __init__(
        self, model_name: str = "Qwen/Qwen3-Embedding-0.6B", device: str = "cuda"
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None
        self.dimension = 1024  # overwritten with the real value once the model loads

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                msg = (
                    "sentence-transformers is not installed "
                    "(`pip install sentence-transformers`)"
                )
                raise RuntimeError(msg) from exc
            self._model = SentenceTransformer(self._model_name, device=self._device)
            self.dimension = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        model = self._get_model()
        embeddings = model.encode(
            [self._QUERY_INSTRUCTION + text],
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings[0].tolist()
