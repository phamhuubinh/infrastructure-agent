"""OpenAI-compatible embedding provider.

Works against ANY server exposing the OpenAI `/v1/embeddings` schema:
- vLLM serving an embedding model (matches the architecture's "Serving: vLLM")
- Qwen3-Embedding or BGE-M3 served behind an OpenAI-compatible wrapper
  (e.g. Infinity, TEI, or vLLM's own embedding endpoint)
- OpenAI itself, or any other compatible provider

This is the recommended default per your choice of "start with lighter/
API-based models" — it's real, network-testable code (point `base_url` at
any running OpenAI-compatible server, including a local vLLM instance),
without needing to load a model in-process.
"""
from __future__ import annotations

import requests


class OpenAICompatibleEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        dimension: int = 1024,
        timeout: float = 30.0,
    ) -> None:
        self.name = f"openai-compatible:{model}"
        self.dimension = dimension
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = requests.post(
            f"{self._base_url}/embeddings",
            headers=self._headers(),
            json={"model": self._model, "input": texts},
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        # OpenAI schema guarantees `data` is returned in the same order as input.
        return [item["embedding"] for item in payload["data"]]

    def embed_query(self, text: str) -> list[float]:
        return self.embed([text])[0]

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
