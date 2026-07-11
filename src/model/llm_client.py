from __future__ import annotations

import json
from urllib import error as urlerror
from urllib import request


class LLMClient:
    """Minimal HTTP client for OpenAI-compatible chat completions API.

    Responsibilities:
    - HTTP communication only
    - No prompt logic
    - No parsing logic
    - No assessment logic

    Configuration is provided at construction time.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "gpt-4",
        api_key: str | None = None,
        timeout: int = 60,
        temperature: float = 0.0,
        max_tokens: int = 2048,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._last_usage: dict[str, int] | None = None

    @property
    def last_usage(self) -> dict[str, int] | None:
        """Token usage from the most recent API response, or None if absent."""
        return self._last_usage

    def generate(self, prompt: str) -> str:
        """Send a chat completion request and return the response content.

        Args:
            prompt: The full prompt string to send.

        Returns:
            The model's response content string.

        Raises:
            RuntimeError: On HTTP errors, timeouts, or invalid responses.
        """
        payload = {
            "model": self._model,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }

        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }

        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"

        body = json.dumps(payload).encode("utf-8")

        req = request.Request(
            url=f"{self._base_url}/v1/chat/completions",
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                data: dict[str, object] = json.loads(
                    response.read().decode("utf-8")
                )
        except urlerror.HTTPError as exc:
            raise RuntimeError(
                f"LLM API returned HTTP {exc.code} at "
                f"{self._base_url}/v1/chat/completions "
                f"(model={self._model}): {exc.reason}"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"LLM API request failed at "
                f"{self._base_url}/v1/chat/completions: {exc}"
            ) from exc

        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            raise RuntimeError(
                f"LLM API returned no choices at "
                f"{self._base_url}/v1/chat/completions"
            )

        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError(
                f"LLM API returned unexpected response format"
            )

        message = first.get("message")
        if not isinstance(message, dict):
            raise RuntimeError(
                f"LLM API returned no message in choice"
            )

        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError(
                f"LLM API returned no content in message"
            )

        # Capture token usage if the server reports it.
        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            self._last_usage = {
                k: int(v) for k, v in raw_usage.items()
                if isinstance(v, (int, float))
            }
        else:
            self._last_usage = None

        return content
