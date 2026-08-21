"""Minimal provider-neutral prompt for first-pass semantic planning."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from src.pipeline.hard_request_constraints import HardRequestConstraints
from src.pipeline.input_context_budget import (
    InputContextBudgetClass,
    InputContextBudgetPolicy,
    InputContextSection,
)
from src.pipeline.normalizer import Normalizer
from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan_wire import (
    MAX_SOURCE_CONSTRAINTS,
    planner_output_json_schema,
)

MAX_PLANNER_REQUEST_CHARS = 4096
MAX_PLANNER_CONTEXT_CHARS = 256
MAX_PLANNER_CONTEXT_BYTES = 1024

_PLANNER_SYSTEM_PROMPT = (
    "Return one OrionPlannerOutputV1 JSON object matching the schema. "
    "The user JSON contains request plus deterministic hints parsed from that "
    "same request. The plan is advisory. Preserve concrete hint values; they "
    "are not model guesses and grant no execution authority. The harness "
    "remains authoritative for targets, sources, safety, capabilities and "
    "execution. do not use unknown for a clear request; never weaken a "
    "concrete hint to unknown or unspecified. A hints.target value is an "
    "explicit user target; a target from session context is inherited. "
    "t is only an execution-target identity. Never use a concept, source name, "
    "model, memory, internet, or URL as t.v. Keep explicit URLs only in u and "
    "source constraints only in s/x; do not rewrite an explicit user target. "
    "Use null for absent nullable text fields t.v,m,c,svc,p,u,q.f; never put "
    "answer prose or placeholder words such as unknown/none/null into them. "
    "m is only a requested measurement such as cpu; c is only a conceptual "
    "subject. s is allowed/required sources and x is explicit exclusions; "
    "never place one source in both. "
    "For a greeting or trivial stable general request: "
    "direct_answer/general/explain, target unspecified with null value, "
    "s=[any], x=[], freshness=stable, dc=not_required, calc=null, "
    "q.s=not_required, q.f=null; put answer prose only in a. "
    "Exact arithmetic: direct_answer/general/explain, target unspecified, "
    "s=[any], x=[], freshness=stable, dc=required, populate calc exactly for "
    "the requested operation, and a=null. "
    "Live environment inspection: capability_assisted/environment/"
    "inspect_read_only, explicit or inherited target as indicated, "
    "freshness=current, dc=not_required, calc=null, a=null. "
    "For environment mutation: capability_assisted/action/mutate_environment "
    "and a=null. For external current information preserve its external/source "
    "and freshness requirements. For coordinated requests use multi_intent "
    "with 2-4 complete non-recursive subplans depending only on earlier ones. "
    "For every route other than multi_intent, sp MUST be exactly []. A single "
    "question, including an explanation, calculation, rewrite, code request, "
    "or one live lookup, is never multi_intent and MUST NOT contain a subplan. "
    "Never emit commands, credentials, tool schemas, evidence, hidden "
    "reasoning, or prose outside a."
)

_PLANNER_V2_SYSTEM_PROMPT = (
    "Return one OrionPlannerOutputV1 JSON object matching the schema. "
    "The user JSON contains the original request, bounded session context, "
    "and an enforceable hard_constraints snapshot. The plan is advisory and "
    "the harness remains authoritative for safety, targets, sources, "
    "freshness, capabilities, and execution. Preserve concrete hard "
    "constraints, but decide the request's domain, intent, concepts, "
    "calculation, and route from the original request yourself. "
    "A hard target with registered_target is an exact configured identity; "
    "a target with null registered_target is an explicit unresolved reference. "
    "Never turn an absent target into localhost. Keep explicit URLs only in u "
    "and source constraints only in s/x. Use null for absent nullable text "
    "fields t.v,m,c,svc,p,u,q.f; never put answer prose or placeholder words "
    "such as unknown/none/null into them. m is only a requested measurement; "
    "c is only a conceptual subject. s is allowed/required sources and x is "
    "explicit exclusions; never place one source in both. For a greeting or "
    "trivial stable general request: direct_answer/general/explain, target "
    "unspecified with null value, s=[any], x=[], freshness=stable, "
    "dc=not_required, calc=null, q.s=not_required, q.f=null; put answer prose "
    "only in a. For a calculation, select the calculator contract only when "
    "the request warrants it. For live environment inspection: "
    "capability_assisted/environment/inspect_read_only, explicit or inherited "
    "target as indicated, freshness=current, dc=not_required, calc=null, "
    "a=null. For environment mutation: capability_assisted/action/"
    "mutate_environment and a=null. For external current information preserve "
    "its external/source and freshness requirements. For coordinated requests "
    "use multi_intent with 2-4 complete non-recursive subplans depending only "
    "on earlier ones. For every route other than multi_intent, sp MUST be "
    "exactly []. A single question, including an explanation, calculation, "
    "rewrite, code request, or one live lookup, is never multi_intent and MUST "
    "NOT contain a subplan. Never emit commands, credentials, tool schemas, "
    "evidence, hidden reasoning, or prose outside a."
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


def _request_hints(raw_request: str) -> dict[str, object]:
    """Return bounded deterministic semantics parsed from the same request."""

    frame = Normalizer().normalize(raw_request)

    hints: dict[str, object] = {
        "domain": frame.request_domain.name.casefold(),
        "intent": frame.execution_intent.name.casefold(),
        "scope": frame.information_scope.name.casefold(),
        "sources": [item.name.casefold() for item in frame.source_constraints],
        "exclude": [item.name.casefold() for item in frame.excluded_sources],
    }

    if frame.target_raw is not None:
        hints["target"] = frame.target_raw

    # Do not expose the Normalizer's generic fallback "machine" as though
    # the user explicitly supplied that concept.
    concepts = list(frame.concepts)

    # General/self-contained requests do not need infrastructure concept
    # guesses. Fuzzy Normalizer matches here can poison planner semantics
    # (for example arithmetic text being misclassified as "gpu").
    if frame.request_domain.name == "GENERAL":
        concepts = []

    # A lexical item already extracted as the explicit environment target is
    # not also a planner concept. Keep the actual requested measurement
    # (for example cpu) while dropping target-derived "monitor"/"monitors".
    if frame.target_raw is not None:
        target = frame.target_raw.casefold()
        target_forms = {target, f"{target}s"}
        concepts = [
            concept for concept in concepts if concept.casefold() not in target_forms
        ]

    if concepts and concepts != ["machine"]:
        hints["concepts"] = concepts

    if frame.explicit_url is not None:
        hints["url"] = frame.explicit_url

    if frame.freshness_phrase is not None:
        hints["freshness"] = frame.freshness_phrase

    if frame.ambiguity:
        hints["ambiguity"] = list(frame.ambiguity)

    # Deterministic percentage calculations are resolved by the calculator
    # contract, not by free-form planner reasoning.
    percent_match = re.search(
        r"(?P<pct>\d+(?:[.,]\d+)?)\s*%\s*"
        r"(?:của|cua|of)\s*"
        r"(?P<base>\d[\d.,]*)\s*"
        r"(?P<unit>triệu|trieu|million|nghìn|nghin|thousand|tỷ|ty|billion)?",
        raw_request,
        re.IGNORECASE,
    )

    if percent_match:
        pct = percent_match.group("pct").replace(",", ".")
        base = percent_match.group("base").replace(",", "")

        unit = percent_match.group("unit")
        if unit:
            unit = unit.casefold()
            if unit in {"triệu", "trieu", "million"}:
                base = str(int(float(base) * 1_000_000))
            elif unit in {"nghìn", "nghin", "thousand"}:
                base = str(int(float(base) * 1_000))
            elif unit in {"tỷ", "ty", "billion"}:
                base = str(int(float(base) * 1_000_000_000))

        hints["deterministic_compute"] = "required"
        hints["calculation"] = {
            "operation": "percent_of",
            "percent": pct,
            "base_value": base,
        }

    remaining_match = re.search(
        r"(?:có|co|has)\s*(?P<total>\d+(?:[.,]\d+)?)\s*(?:gb)?[\s\S]{0,80}?"
        r"(?:đang dùng|dang dung|used)\s*(?P<used>\d+(?:[.,]\d+)?)\s*(?:gb)?[\s\S]{0,80}?"
        r"(?:còn lại|con lai|remaining|left)",
        raw_request,
        re.IGNORECASE,
    )
    if remaining_match:
        hints["deterministic_compute"] = "required"
        hints["calculation"] = {
            "operation": "subtract",
            "left": remaining_match.group("total").replace(",", "."),
            "right": remaining_match.group("used").replace(",", "."),
        }

    percent_values = re.findall(r"\d+(?:[.,]\d+)?(?=\s*%)", raw_request)
    if (
        any(marker in raw_request.casefold() for marker in ("trung bình", "trung binh", "average"))
        and 2 <= len(percent_values) <= 8
    ):
        hints["deterministic_compute"] = "required"
        hints["calculation"] = {
            "operation": "average",
            "values": [item.replace(",", ".") for item in percent_values],
            "unit": "%",
        }

    availability_match = re.search(
        r"availability\s*(\d+(?:[.,]\d+)?)%[\s\S]{0,100}?(\d+)\s*(?:ngày|ngay|days?)",
        raw_request,
        re.IGNORECASE,
    )
    if availability_match and any(
        marker in raw_request.casefold() for marker in ("downtime", "gián đoạn", "gian doan")
    ):
        hints["deterministic_compute"] = "required"
        hints["calculation"] = {
            "operation": "availability_downtime",
            "availability": availability_match.group(1).replace(",", "."),
            "days": availability_match.group(2),
            "unit": "minutes",
        }

    return hints


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

    request_hints = _request_hints(raw_request)
    request_payload = json.dumps(
        {"request": raw_request, "hints": request_hints},
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
            {
                "request": raw_request,
                "hints": request_hints,
                "context": context_payload,
            },
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


def build_semantic_planner_v2_prompt(
    raw_request: str,
    *,
    context: PlannerPromptContext | None = None,
    hard_constraints: HardRequestConstraints | None = None,
) -> SemanticPlannerPrompt:
    """Build the primary v2 prompt without ``Normalizer`` semantic hints.

    The hard snapshot is intentionally limited to independently enforceable
    facts.  It does not decide a request's domain, concept, capability, or
    calculator operation before the model receives the original text.
    """
    if not isinstance(raw_request, str) or not raw_request.strip():
        raise ValueError("Planner request must be non-empty text.")
    if len(raw_request) > MAX_PLANNER_REQUEST_CHARS:
        raise ValueError(
            f"Planner request exceeds {MAX_PLANNER_REQUEST_CHARS} characters."
        )
    if context is not None and not isinstance(context, PlannerPromptContext):
        raise TypeError("context must be PlannerPromptContext or None.")
    if hard_constraints is None:
        hard_constraints = HardRequestConstraints()
    if not isinstance(hard_constraints, HardRequestConstraints):
        raise TypeError("hard_constraints must be HardRequestConstraints or None.")

    request_payload = json.dumps(
        {
            "request": raw_request,
            "hard_constraints": hard_constraints.to_dict(),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
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
            InputContextSection("system_prompt", _PLANNER_V2_SYSTEM_PROMPT),
            InputContextSection("request_payload", request_payload),
        ),
        optional=optional_sections,
    )

    user_prompt = request_payload
    if context_payload is not None and "session_context" in enforced.optional_included:
        user_prompt = json.dumps(
            {
                "request": raw_request,
                "hard_constraints": hard_constraints.to_dict(),
                "context": context_payload,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return SemanticPlannerPrompt(
        system_prompt=_PLANNER_V2_SYSTEM_PROMPT,
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
    "build_semantic_planner_v2_prompt",
    "planner_context_to_dict",
]
