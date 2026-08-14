"""Deterministic mutation-intent guard for planner-proposed semantic plans."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.pipeline.request_semantics import ExecutionIntent, RequestSemanticsClassifier
from src.pipeline.semantic_plan import SemanticPlan
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationResult,
    SemanticPlanValidationValue,
)


@dataclass(frozen=True, slots=True)
class SemanticMutationValidationResult:
    validation: SemanticPlanValidationResult
    deterministic_intent: ExecutionIntent
    mutation_signal: str | None = None


class SemanticMutationValidator:
    """Prevent a model from downgrading an explicit action to read-only work."""

    _EXAMPLE_ONLY = re.compile(
        r"^\s*(?:how\s+to|what\s+does|explain|giải\s+thích|giai\s+thich|"
        r"cách|cach|example|ví\s+dụ|vi\s+du)\b|"
        r"\b(?:do\s+not\s+run|don't\s+run|không\s+chạy|khong\s+chay|"
        r"write\s+(?:a\s+)?script|"
        r"generate\s+(?:a\s+)?script|show\s+me\s+(?:a\s+)?command|"
        r"viết\s+(?:một\s+)?script|viet\s+(?:mot\s+)?script|"
        r"(?:give|show|provide)\s+me\s+(?:an?\s+)?example)\b",
        re.IGNORECASE,
    )
    _QUOTED_ONLY = re.compile(
        r"^\s*(?:`[^`]+`|'[^']+'|\"[^\"]+\")\s*[?.!]?\s*$",
        re.DOTALL,
    )
    _EXPLICIT_MUTATION = re.compile(
        r"(?:^|\bplease\s+|\bhãy\s+|\bhay\s+|\bexecute\s+|\brun\s+|"
        r"\bchạy\s+|\bchay\s+)"
        r"(?:restart|disable|enable|delete|remove|install|uninstall|chmod|"
        r"chown|kill|reboot|shutdown|"
        r"khởi\s+động\s+lại|khoi\s+dong\s+lai|vô\s+hiệu\s+hóa|"
        r"vo\s+hieu\s+hoa|xóa|xoá|xoa|cài\s+đặt|cai\s+dat)\b"
        r"|\b(?:rm\s+-rf|systemctl\s+(?:restart|stop|start|disable|enable)|"
        r"apt(?:-get)?\s+(?:install|remove)|sudo\s+(?:-i|su)|"
        r"(?:write|overwrite|truncate)\s+(?:to\s+)?(?:/\S+|(?:the\s+)?"
        r"(?:file|config|filesystem|disk)\b)|"
        r"root\s+shell|shell\s+as\s+root)\b",
        re.IGNORECASE,
    )

    def validate(
        self,
        plan: SemanticPlan,
        raw_request: str,
    ) -> SemanticMutationValidationResult:
        if not isinstance(plan, SemanticPlan):
            raise TypeError("plan must be a SemanticPlan.")
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("raw_request must be non-empty text.")

        deterministic = RequestSemanticsClassifier().classify(raw_request)
        example_only = bool(
            self._EXAMPLE_ONLY.search(raw_request)
            or self._QUOTED_ONLY.fullmatch(raw_request)
        )
        signal: str | None = None
        if plan.execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT:
            signal = "planner_mutation"
        elif (
            deterministic.execution_intent is ExecutionIntent.MUTATE_ENVIRONMENT
            and not example_only
        ):
            signal = "deterministic_mutation"
        elif not example_only:
            match = self._EXPLICIT_MUTATION.search(raw_request)
            if match is not None:
                signal = "reviewed_action_pattern"

        if signal is not None:
            return SemanticMutationValidationResult(
                SemanticPlanValidationResult.reject(
                    SemanticPlanValidationReason.MUTATION_UNSAFE,
                    plan=plan,
                    values=(
                        SemanticPlanValidationValue.safe(
                            "mutation.intent",
                            original=plan.execution_intent.name,
                            normalized="rejected",
                        ),
                        SemanticPlanValidationValue.safe(
                            "mutation.signal",
                            original=signal,
                            normalized="read_only_boundary",
                        ),
                    ),
                ),
                deterministic_intent=deterministic.execution_intent,
                mutation_signal=signal,
            )
        return SemanticMutationValidationResult(
            SemanticPlanValidationResult.valid(plan),
            deterministic_intent=deterministic.execution_intent,
        )


__all__ = [
    "SemanticMutationValidationResult",
    "SemanticMutationValidator",
]
