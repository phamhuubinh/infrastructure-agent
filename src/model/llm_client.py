from __future__ import annotations

import json
import time
from collections.abc import Mapping
from urllib import error as urlerror
from urllib import request

from src.model.output_sanitizer import sanitize_model_output
from src.model.reasoning_effort import ReasoningEffort
from src.model.usage_metadata import ModelCallUsage, normalize_openai_usage
from src.shared.logger import debug, info
from src.shared.logger import error as log_error


def _extract_provider(base_url: str, model: str = "") -> str:
    u = base_url.lower()
    if "qwen" in model.lower():
        return "qwen"
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
        supports_reasoning_effort: bool = False,
        supports_structured_output: bool | None = None,
        supports_json_object_output: bool | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if self._base_url.endswith("/v1"):
            self._base_url = self._base_url[:-3].rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._temperature = temperature
        if not isinstance(supports_reasoning_effort, bool):
            raise TypeError("supports_reasoning_effort must be bool.")
        self._supports_reasoning_effort = supports_reasoning_effort
        if supports_structured_output is not None and not isinstance(
            supports_structured_output, bool
        ):
            raise TypeError("supports_structured_output must be bool or None.")
        self._last_usage: ModelCallUsage | None = None
        self._last_generation_diagnostics: dict[str, object] | None = None
        self._provider = _extract_provider(base_url, model)
        self._supports_structured_output = (
            self._provider != "ollama"
            if supports_structured_output is None
            else supports_structured_output
        )
        if supports_json_object_output is not None and not isinstance(
            supports_json_object_output, bool
        ):
            raise TypeError("supports_json_object_output must be bool or None.")
        self._supports_json_object_output = (
            self._provider != "ollama"
            if supports_json_object_output is None
            else supports_json_object_output
        )

    @property
    def last_usage(self) -> ModelCallUsage | None:
        return self._last_usage

    @property
    def last_generation_diagnostics(self) -> Mapping[str, object] | None:
        """Safe, bounded metadata from the most recent chat completion.

        This deliberately excludes prompts, content, reasoning, and raw provider
        payloads. It exists so an invalid structured response can explain whether
        generation ended because of a provider limit without retaining that text.
        """

        if self._last_generation_diagnostics is None:
            return None
        return dict(self._last_generation_diagnostics)

    @property
    def supports_structured_output(self) -> bool:
        """Whether this endpoint accepts OpenAI-compatible JSON Schema output."""

        return self._supports_structured_output

    @property
    def supports_json_object_output(self) -> bool:
        """Whether the endpoint supports the broadly compatible JSON-object mode."""

        return self._supports_json_object_output

    def generate(
        self,
        prompt: str,
        request_id: str | None = None,
        system_prompt: str | None = None,
        purpose: str | None = None,
        reasoning_effort: ReasoningEffort | None = None,
        response_schema: dict[str, object] | None = None,
        json_object: bool = False,
    ) -> str:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": False,
        }
        if not isinstance(json_object, bool):
            raise TypeError("json_object must be bool.")
        if response_schema is not None and json_object:
            raise ValueError("response_schema and json_object are mutually exclusive.")
        if response_schema is not None:
            if not isinstance(response_schema, dict):
                raise TypeError("response_schema must be a dict or None.")
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "orion_structured_output",
                    "strict": True,
                    "schema": response_schema,
                },
            }
        elif json_object:
            payload["response_format"] = {"type": "json_object"}

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
        self._last_generation_diagnostics = None
        provider_http_status: int | None = None
        try:
            with request.urlopen(req, timeout=self._timeout) as response:
                status = getattr(response, "status", None)
                if isinstance(status, int) and not isinstance(status, bool):
                    provider_http_status = status
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
        finish_reason = first.get("finish_reason")
        if not isinstance(finish_reason, str):
            finish_reason = None
        if not isinstance(content, str):
            msg = "LLM API returned no content in message"
            raise RuntimeError(msg)
        content_bytes_before_sanitization = len(content.encode("utf-8"))
        content = sanitize_model_output(content)
        content_bytes_after_sanitization = len(content.encode("utf-8"))

        usage = data.get("usage")
        self._last_generation_diagnostics = {
            "finish_reason": _safe_finish_reason(finish_reason),
            "usage_completion_tokens": _usage_token_count(
                usage,
                "completion_tokens",
            ),
            "usage_prompt_tokens": _usage_token_count(usage, "prompt_tokens"),
            "stop_sequence_configured": "stop" in payload,
            "content_bytes_before_sanitization": content_bytes_before_sanitization,
            "content_bytes_after_sanitization": content_bytes_after_sanitization,
            "provider_http_status": provider_http_status,
        }
        if not content:
            msg = "LLM API returned no user-visible content"
            raise RuntimeError(msg)

        self._last_usage = normalize_openai_usage(
            usage,
            model=self._model,
            provider=self._provider,
            purpose=purpose,
            latency_ms=elapsed_ms,
            configured_effort=configured_effort,
        )

        info(
            "llm",
            request=request_id or "-",
            model=self._model,
            provider=self._provider,
            endpoint=self._base_url,
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


def _usage_token_count(usage: object, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _safe_finish_reason(value: object) -> str | None:
    """Keep only a provider control category, never arbitrary response text."""

    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized or len(normalized) > 64:
        return "other"
    if all(character.isascii() and (character.isalnum() or character in "_.-") for character in normalized):
        return normalized
    return "other"
