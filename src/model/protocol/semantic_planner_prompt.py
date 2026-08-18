"""Minimal provider-neutral prompt for first-pass semantic planning."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.pipeline.input_context_budget import (
    InputContextBudgetClass,
    InputContextBudgetPolicy,
    InputContextSection,
)
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan_wire import (
    MAX_SOURCE_CONSTRAINTS,
    planner_output_json_schema,
)

MAX_PLANNER_REQUEST_CHARS = 4096
MAX_PLANNER_CONTEXT_CHARS = 256
MAX_PLANNER_CONTEXT_BYTES = 1024

_PLANNER_SYSTEM_PROMPT = (
    "Return one OrionPlannerOutputV1 JSON object: p=plan, a=optional answer. "
    "The plan is advisory. Use only the request and bounded context. The harness validates and controls "
    "tools, targets, sources, safety, and execution. Set a only for trivial stable "
    "direct_answer requests needing no tools, live data, calculation, or clarification; "
    "otherwise null. For coordinated requests use multi_intent with 2-4 complete, "
    "non-recursive sp entries; each states target/source/freshness and may depend only "
    "on earlier entries. Never emit commands, credentials, tool schemas, evidence, "
    "hidden reasoning, or prose outside a. Use unspecified/unknown rather than guessing."
)


@dataclass(frozen=True, slots=True)
class PlannerPromptContext:
    """Preselected semantic state allowed in the first-pass planner prompt."""

    target: str | None = None
    concept: str | None = None
    service: str | None = None
    path: str | None = None
    time_range: str | None = None
    sources: tuple[SourceConstraint, ...] = ()
    excluded_sources: tuple[SourceConstraint, ...] = ()
    pending_clarification_field: str | None = None


@dataclass(frozen=True, slots=True)
class SemanticPlannerPrompt:
    """Prompt text and out-of-band structured-output schema.

    ``estimated_input_tokens`` is the provider-neutral estimate of the
    enforced input context (system prompt plus user prompt) for telemetry;
    it is derived from characters, never from a provider tokenizer.
    """

    system_prompt: str
    user_prompt: str
    response_schema: dict[str, object]
    estimated_input_tokens: int = 0
    input_budget_class: str = InputContextBudgetClass.SIMPLE.value


def build_semantic_planner_prompt(
    raw_request: str,
    *,
    context: PlannerPromptContext | None = None,
) -> SemanticPlannerPrompt:
    """Build a bounded prompt without tool, target-registry, or evidence data.

    Enforces the SIMPLE input-context budget at this construction boundary,
    before any provider is invoked: the user request and the planner system
    prompt are mandatory, while the bounded session context is optional and
    is dropped whole (never sliced) if it would exceed the budget.
    """

    if not isinstance(raw_request, str) or not raw_request.strip():
        raise ValueError("Planner request must be non-empty text.")
    if len(raw_request) > MAX_PLANNER_REQUEST_CHARS:
        raise ValueError(
            f"Planner request exceeds {MAX_PLANNER_REQUEST_CHARS} characters."
        )
    if context is not None and not isinstance(context, PlannerPromptContext):
        raise TypeError("context must be PlannerPromptContext or None.")

    request_payload = json.dumps(
        {"request": raw_request},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    # The optional section is the *additional* text the session context adds
    # to the request payload, so the enforcement counts it exactly once.
    optional_sections: tuple[InputContextSection, ...] = ()
    context_payload: dict[str, object] | None = None
    if context is not None:
        compact_context = _compact_context(context)
        if compact_context:
            context_payload = compact_context
            context_fragment = ',"context":' + json.dumps(
                compact_context, ensure_ascii=False, separators=(",", ":")
            )
            optional_sections = (
                InputContextSection("session_context", context_fragment),
            )

    budget = InputContextBudgetPolicy.for_class(InputContextBudgetClass.SIMPLE)
    enforced = budget.enforce(
        mandatory=(
            InputContextSection("system_prompt", _PLANNER_SYSTEM_PROMPT),
            InputContextSection("request_payload", request_payload),
        ),
        optional=optional_sections,
    )

    user_prompt = request_payload
    if context_payload is not None and "session_context" in enforced.optional_included:
        user_prompt = json.dumps(
            {"request": raw_request, "context": context_payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return SemanticPlannerPrompt(
        system_prompt=_PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        response_schema=planner_output_json_schema(),
        estimated_input_tokens=enforced.estimated_input_tokens,
        input_budget_class=budget.budget_class.value,
    )


def planner_context_to_dict(context: PlannerPromptContext) -> dict[str, object]:
    """Return the same bounded allowlisted context used by planner prompts."""

    if not isinstance(context, PlannerPromptContext):
        raise TypeError("context must be PlannerPromptContext.")
    return _compact_context(context)


def _compact_context(context: PlannerPromptContext) -> dict[str, object]:
    values: tuple[tuple[str, object], ...] = (
        ("target", _optional_context_text(context.target, "target")),
        ("concept", _optional_context_text(context.concept, "concept")),
        ("service", _optional_context_text(context.service, "service")),
        ("path", _optional_context_text(context.path, "path")),
        ("time", _optional_context_text(context.time_range, "time_range")),
        (
            "clarify",
            _optional_context_text(
                context.pending_clarification_field,
                "pending_clarification_field",
            ),
        ),
        ("sources", _source_names(context.sources, "sources")),
        (
            "exclude",
            _source_names(context.excluded_sources, "excluded_sources"),
        ),
    )
    compact = {key: value for key, value in values if value not in (None, [])}
    encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_PLANNER_CONTEXT_BYTES:
        raise ValueError(f"Planner context exceeds {MAX_PLANNER_CONTEXT_BYTES} bytes.")
    return compact


def _optional_context_text(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field} must be text or None.")
    if not value or value != value.strip():
        raise ValueError(f"{field} must be non-empty trimmed text or None.")
    if len(value) > MAX_PLANNER_CONTEXT_CHARS:
        raise ValueError(f"{field} exceeds {MAX_PLANNER_CONTEXT_CHARS} characters.")
    if any(ord(character) < 32 for character in value):
        raise ValueError(f"{field} must not contain control characters.")
    return value


def _source_names(values: object, field: str) -> list[str]:
    if not isinstance(values, tuple):
        raise TypeError(f"{field} must be a tuple of SourceConstraint values.")
    if len(values) > MAX_SOURCE_CONSTRAINTS:
        raise ValueError(
            f"{field} must contain at most {MAX_SOURCE_CONSTRAINTS} items."
        )
    names: list[str] = []
    for value in values:
        if not isinstance(value, SourceConstraint):
            raise TypeError(f"{field} must contain SourceConstraint values.")
        names.append(value.name.casefold())
    if len(set(names)) != len(names):
        raise ValueError(f"{field} must not contain duplicate values.")
    return names


__all__ = [
    "MAX_PLANNER_CONTEXT_BYTES",
    "MAX_PLANNER_REQUEST_CHARS",
    "PlannerPromptContext",
    "SemanticPlannerPrompt",
    "build_semantic_planner_prompt",
    "planner_context_to_dict",
]
