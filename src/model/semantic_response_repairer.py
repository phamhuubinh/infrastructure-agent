"""One-shot repair boundary for failed final semantic responses."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.model.protocol.semantic_repair_prompt import build_semantic_repair_prompt
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.fact import Fact


class SemanticRepairStatus(str, Enum):
    REPAIRED = "repaired"
    EMPTY_RESPONSE = "empty_response"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    # A repair candidate was generated but did not pass the second final
    # verification, so it did not become the accepted answer.
    VERIFICATION_FAILED = "verification_failed"
    # Repair input was unacceptable (e.g. an oversized original request);
    # the repair model was never called.
    INPUT_REJECTED = "input_rejected"


@dataclass(frozen=True, slots=True)
class SemanticRepairResult:
    status: SemanticRepairStatus
    text: str | None = None

    @property
    def repaired(self) -> bool:
        return self.status is SemanticRepairStatus.REPAIRED and bool(self.text)

    def to_trace_dict(self) -> dict[str, object]:
        return {"attempted": True, "status": self.status.value}


@runtime_checkable
class RawRepairModel(Protocol):
    """Narrow model boundary without tool or evidence authority."""

    def assess_raw(self, prompt: str) -> str: ...


@runtime_checkable
class SemanticResponseRepairerProtocol(Protocol):
    def repair(
        self,
        original_request: str,
        *,
        violations: tuple[str, ...],
        relevance_reason: str | None,
        facts: tuple[Fact, ...],
    ) -> SemanticRepairResult: ...


class SemanticResponseRepairer:
    """Perform exactly one compact regeneration call, with no retry path."""

    def __init__(self, model: RawRepairModel) -> None:
        if not isinstance(model, RawRepairModel):
            raise TypeError("model must implement assess_raw().")
        self._model = model

    @property
    def last_usage(self) -> ModelCallUsage | None:
        """Normalized usage of the most recent repair call, when reported."""

        usage = getattr(self._model, "last_usage", None)
        return usage if isinstance(usage, ModelCallUsage) else None

    def repair(
        self,
        original_request: str,
        *,
        violations: tuple[str, ...],
        relevance_reason: str | None,
        facts: tuple[Fact, ...],
    ) -> SemanticRepairResult:
        # GA2-C09: an unacceptable repair input (e.g. an oversized original
        # request) must fail safely *inside* the repair boundary without
        # ever calling the repair model — it must not bubble into the
        # semantic coordinator as a generic response failure. The original
        # request is never silently truncated.
        try:
            prompt = build_semantic_repair_prompt(
                original_request,
                violations=violations,
                relevance_reason=relevance_reason,
                facts=facts,
            )
        except ValueError:
            return SemanticRepairResult(SemanticRepairStatus.INPUT_REJECTED)
        try:
            text = self._model.assess_raw(prompt.render())
        except Exception:
            return SemanticRepairResult(SemanticRepairStatus.PROVIDER_UNAVAILABLE)
        if not isinstance(text, str) or not text.strip():
            return SemanticRepairResult(SemanticRepairStatus.EMPTY_RESPONSE)
        return SemanticRepairResult(SemanticRepairStatus.REPAIRED, text)


__all__ = [
    "RawRepairModel",
    "SemanticRepairResult",
    "SemanticRepairStatus",
    "SemanticResponseRepairer",
    "SemanticResponseRepairerProtocol",
]
