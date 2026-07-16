"""LLM client for the generation model — OpenAI-compatible chat/completions
API, which is exactly what vLLM's `--served-model-name` OpenAI server
exposes (`python -m vllm.entrypoints.openai.api_server ...`). This one
client is reused by HyDE (query expansion), RAPTOR (cluster summarization),
and the final answer-generation step in the query pipeline.
"""

from __future__ import annotations

import requests


class LlmClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: float = 60.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    def complete(
        self, prompt: str, temperature: float = 0.2, max_tokens: int = 512
    ) -> str:
        return self.chat([{"role": "user", "content": prompt}], temperature, max_tokens)

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 512,
    ) -> str:
        response = requests.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload["choices"][0]["message"]["content"]

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers
