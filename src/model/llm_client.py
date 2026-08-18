from __future__ import annotations

import json
import time
from urllib import error as urlerror
from urllib import request

from src.model.output_sanitizer import sanitize_model_output
from src.model.reasoning_effort import ReasoningEffort
from src.model.usage_metadata import ModelCallUsage, normalize_openai_usage
from src.shared.logger import debug, info
from src.shared.logger import error as log_error


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
        supports_reasoning_effort: bool = False,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/v1"):
            self._base_url = self._base_url[:-3].rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens
        if not isinstance(supports_reasoning_effort, bool):
            raise TypeError("supports_reasoning_effort must be bool.")
        self._supports_reasoning_effort = supports_reasoning_effort
        self._last_usage: ModelCallUsage | None = None
        self._provider = _extract_provider(base_url, model)

    @property
    def last_usage(self) -> ModelCallUsage | None:
        return self._last_usage

    def generate(
        self,
        prompt: str,
        request_id: str | None = None,
        system_prompt: str | None = None,
        purpose: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        configured_effort: str | None = None
        if reasoning_effort is not None:
            if not isinstance(reasoning_effort, ReasoningEffort):
                raise TypeError("reasoning_effort must be ReasoningEffort or None.")
            if self._supports_reasoning_effort:
                configured_effort = reasoning_effort.value
                payload["reasoning_effort"] = configured_effort

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
        debug(
            "llm",
            request=request_id or "-",
            model=self._model,
            provider=self._provider,
            endpoint=self._base_url,
            message="LLM request started",
        )

        elapsed_ms: int = 0
        self._last_usage = None
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                data: dict[str, object] = json.loads(response.read().decode("utf-8"))
        except KeyboardInterrupt as ki_exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error(
                "llm",
                request=request_id or "-",
                model=self._model,
                provider=self._provider,
                endpoint=self._base_url,
                error="Cancelled",
                elapsed_ms=elapsed_ms,
            )
            msg = "Cancelled"
            raise RuntimeError(msg) from ki_exc
        except urlerror.HTTPError as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error(
                "llm",
                request=request_id or "-",
                model=self._model,
                provider=self._provider,
                endpoint=self._base_url,
                error=exc.reason,
                status=exc.code,
                elapsed_ms=elapsed_ms,
            )
            msg = (
                f"LLM API returned HTTP {exc.code} at "
                f"{self._base_url}/v1/chat/completions "
                f"(model={self._model}): {exc.reason}"
            )
            raise RuntimeError(msg) from exc
        except (OSError, json.JSONDecodeError) as exc:
            elapsed_ms = int((time.monotonic() - t0) * 1000)
            log_error(
                "llm",
                request=request_id or "-",
                model=self._model,
                provider=self._provider,
                endpoint=self._base_url,
                error=str(exc),
                elapsed_ms=elapsed_ms,
            )
            msg = (
                f"LLM API request failed at {self._base_url}/v1/chat/completions: {exc}"
            )
            raise RuntimeError(msg) from exc

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) == 0:
            log_error(
                "llm",
                request=request_id or "-",
                model=self._model,
                provider=self._provider,
                endpoint=self._base_url,
                error="no_choices",
                elapsed_ms=elapsed_ms,
            )
            msg = f"LLM API returned no choices at {self._base_url}/v1/chat/completions"
            raise RuntimeError(msg)

        first = choices[0]
        if not isinstance(first, dict):
            msg = "LLM API returned unexpected response format"
            raise RuntimeError(msg)

        message = first.get("message")
        if not isinstance(message, dict):
            msg = "LLM API returned no message in choice"
            raise RuntimeError(msg)

        content = message.get("content")
        if not isinstance(content, str):
            msg = "LLM API returned no content in message"
            raise RuntimeError(msg)
        content = sanitize_model_output(content)
        if not content:
            msg = "LLM API returned no user-visible content"
            raise RuntimeError(msg)

        usage = data.get("usage")
        self._last_usage = normalize_openai_usage(
            usage,
            model=self._model,
            provider=self._provider,
            purpose=purpose,
            latency_ms=elapsed_ms,
            configured_effort=configured_effort,
        )

        finish_reason: str | None = None
        if isinstance(first, dict):
            fr = first.get("finish_reason")
            if isinstance(fr, str):
                finish_reason = fr

        info(
            "llm",
            request=request_id or "-",
            model=self._model,
            provider=self._provider,
            endpoint=self._base_url,
            max_tokens=self._max_tokens,
            temperature=self._temperature,
            timeout=self._timeout,
            input_tokens=self._last_usage.input_tokens,
            reasoning_tokens=self._last_usage.reasoning_tokens,
            configured_effort=self._last_usage.configured_effort,
            output_tokens=self._last_usage.visible_output_tokens,
            total_tokens=self._last_usage.total_output_tokens,
            duration_ms=elapsed_ms,
            finish_reason=finish_reason,
            message="LLM response received",
        )

        return content

    def health_check(self, timeout: int = 5) -> bool:
        data = json.dumps(
            {"model": self._model, "messages": [{"role": "user", "content": "ok"}]}
        ).encode()
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        req = request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=data,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=timeout) as resp:
            resp.read()
        return True
