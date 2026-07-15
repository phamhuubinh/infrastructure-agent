from __future__ import annotations

import json
import signal
import time
from urllib import error as urlerror
from urllib import request

from src.shared.logger import info, error as log_error, debug


def _extract_provider(base_url: str, model: str = "") -> str:
    u = base_url.lower()
    if "ollama" in u:
        return "ollama"
    if "vllm" in model.lower() or "vllm" in u:
        return "vllm"
    if "openai" in u:
        return "openai"
    if "azure" in u:
        return "azure"
    return "openai"


class LLMClient:
    """Minimal HTTP client for OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "gpt-4",
        api_key: str | None = None,
        timeout: int = 180,
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
        self._provider = _extract_provider(base_url, model)

    @property
    def last_usage(self) -> dict[str, int] | None:
        return self._last_usage

    def generate(self, prompt: str, request_id: str | None = None) -> str:
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

        t0 = time.monotonic()
        debug("llm", request=request_id or "-", model=self._model, provider=self._provider,
              endpoint=self._base_url, message="LLM request started")

        elapsed_ms: int = 0
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                data: dict[str, object] = json.loads(
                    response.read().decode("utf-8")
                )
        except KeyboardInterrupt:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error("llm", request=request_id or "-", model=self._model,
                      provider=self._provider, endpoint=self._base_url, error="Cancelled",
                      elapsed_ms=elapsed_ms)
            raise RuntimeError("Cancelled")
        except urlerror.HTTPError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error("llm", request=request_id or "-", model=self._model,
                      provider=self._provider, endpoint=self._base_url, error=exc.reason,
                      status=exc.code, elapsed_ms=elapsed_ms)
            raise RuntimeError(
                f"LLM API returned HTTP {exc.code} at "
                f"{self._base_url}/v1/chat/completions "
                f"(model={self._model}): {exc.reason}"
            ) from exc
        except (OSError, json.JSONDecodeError) as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error("llm", request=request_id or "-", model=self._model,
                      provider=self._provider, endpoint=self._base_url, error=str(exc),
                      elapsed_ms=elapsed_ms)
            raise RuntimeError(
                f"LLM API request failed at "
                f"{self._base_url}/v1/chat/completions: {exc}"
            ) from exc

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            log_error("llm", request=request_id or "-", model=self._model,
                      provider=self._provider, endpoint=self._base_url, error="no_choices",
                      elapsed_ms=elapsed_ms)
            raise RuntimeError(
                f"LLM API returned no choices at "
                f"{self._base_url}/v1/chat/completions"
            )

        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("LLM API returned unexpected response format")

        message = first.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("LLM API returned no message in choice")

        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("LLM API returned no content in message")

        raw_usage = data.get("usage")
        if isinstance(raw_usage, dict):
            self._last_usage = {
                k: int(v) for k, v in raw_usage.items()
                if isinstance(v, (int, float))
            }
        else:
            self._last_usage = None

        finish_reason: str | None = None
        if isinstance(first, dict):
            fr = first.get("finish_reason")
            if isinstance(fr, str):
                finish_reason = fr

        info("llm", request=request_id or "-",
             model=self._model,
             provider=self._provider,
             endpoint=self._base_url,
             max_tokens=self._max_tokens,
             temperature=self._temperature,
             timeout=self._timeout,
             input_tokens=self._last_usage.get("prompt_tokens") if self._last_usage else None,
             output_tokens=self._last_usage.get("completion_tokens") if self._last_usage else None,
             total_tokens=self._last_usage.get("total_tokens") if self._last_usage else None,
             duration_ms=elapsed_ms,
             finish_reason=finish_reason,
             message="LLM response received")

        return content

    def health_check(self, timeout: int = 5) -> bool:
        data = json.dumps({"model": self._model, "messages": [{"role": "user", "content": "ok"}]}).encode()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=data, headers=headers, method="POST",
        )
        with request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
