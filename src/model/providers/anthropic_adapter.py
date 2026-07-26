from __future__ import annotations

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.assessment_result import AssessmentResult
from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest
from src.shared.logger import info as _info
from src.shared.logger import warning as _warning


class AnthropicAssessmentAdapter(AssessmentModelAdapter):
    """Assessment adapter using Anthropic Claude.

    Second production implementation of AssessmentModelAdapter,
    proving the ABC works for non-OpenAI providers.

    Uses the Anthropic Messages API via the official SDK.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-haiku-20240307",
        timeout: int = 180,
        temperature: float = 0.0,
        max_tokens: int = 4096,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._last_usage: dict[str, int] | None = None

    @property
    def last_usage(self) -> dict[str, int] | None:
        return self._last_usage

    def _get_client(self):
        """Lazy-import the Anthropic client.

        Raises ImportError with a helpful message if anthropic is not installed.
        """
        try:
            import anthropic  # type: ignore[import-untyped]  # noqa: F401

            return anthropic.Anthropic(api_key=self._api_key, timeout=self._timeout)
        except ImportError:
            raise ImportError(
                "anthropic package is required for AnthropicAssessmentAdapter. "
                "Install it with: pip install anthropic"
            ) from None

    def assess(self, assessment_request: AssessmentRequest) -> str:
        """Produce an assessment from collected evidence.

        Args:
            assessment_request: Completed evidence and context.

        Returns:
            A string containing the assessment from Claude.
        """
        result = self._assess_with_result(assessment_request)
        return result.content

    def assess_raw(self, prompt: str) -> str:
        """Send a raw prompt to Claude without evidence wrapper."""
        import time as _time

        t0 = _time.perf_counter()
        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )
            latency = round((_time.perf_counter() - t0) * 1000, 1)
            content = response.content[0].text if response.content else ""
            self._last_usage = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
            }
            _info(
                "llm",
                status="success",
                mode="raw",
                provider="anthropic",
                model=self._model,
                duration_ms=latency,
                input_tokens=self._last_usage.get("input_tokens", "N/A"),
                output_tokens=self._last_usage.get("output_tokens", "N/A"),
                message="Anthropic raw response received",
            )
            return content
        except Exception as exc:
            latency = round((_time.perf_counter() - t0) * 1000, 1)
            _warning(
                "llm",
                status="error",
                mode="raw",
                provider="anthropic",
                model=self._model,
                duration_ms=latency,
                error=str(exc)[:80],
                message="Anthropic raw call failed",
            )
            raise

    def health_check(self, timeout: float = 5.0) -> bool:
        """Check if the Anthropic API is reachable.

        Sends a minimal message to verify connectivity.
        """
        try:
            client = self._get_client()
            client.messages.create(
                model=self._model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ok"}],
                timeout=timeout,
            )
            return True
        except Exception:
            return False

    def _assess_with_result(
        self,
        assessment_request: AssessmentRequest,
    ) -> AssessmentResult:
        """Internal implementation using Anthropic Messages API."""
        import time as _time

        t0 = _time.perf_counter()

        try:
            prompt = build_assessment_prompt(assessment_request)
        except Exception as exc:
            return AssessmentResult(
                content="",
                success=False,
                model=self._model,
                error=f"Prompt construction failed: {exc}",
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        try:
            client = self._get_client()
            response = client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            _info(
                "llm",
                status="error",
                provider="anthropic",
                model=self._model,
                error=str(exc)[:80],
                duration_ms=round((_time.perf_counter() - t0) * 1000, 1),
                message="Anthropic call failed",
            )
            return AssessmentResult(
                content="",
                success=False,
                model=self._model,
                error=f"Anthropic call failed: {exc}",
                latency_ms=round((_time.perf_counter() - t0) * 1000, 1),
            )

        latency = round((_time.perf_counter() - t0) * 1000, 1)
        content = response.content[0].text if response.content else ""

        pt = getattr(response.usage, "input_tokens", None) if response.usage else None
        ct = getattr(response.usage, "output_tokens", None) if response.usage else None
        self._last_usage = {
            "input_tokens": pt or 0,
            "output_tokens": ct or 0,
        }
        _info(
            "llm",
            status="success",
            provider="anthropic",
            model=self._model,
            duration_ms=latency,
            input_tokens=pt or "N/A",
            output_tokens=ct or "N/A",
            message="Anthropic response received",
        )
        return AssessmentResult(
            content=content,
            success=True,
            model=self._model,
            latency_ms=latency,
            prompt_tokens=pt,
            completion_tokens=ct,
        )
