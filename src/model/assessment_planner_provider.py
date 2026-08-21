"""Runtime bridge from configured assessment adapters to semantic planning.

The bridge deliberately exposes only the planner provider protocol. It reuses
an already-constructed assessment adapter/client; it never owns credentials,
conversation state, tools, or a second provider configuration.
"""

from __future__ import annotations

import json
from collections.abc import Mapping

from src.model.assessment_model_adapter import AssessmentModelAdapter
from src.model.llm_client import LLMClient
from src.model.semantic_planner_adapter import (
    PlannerProviderRequest,
    PlannerProviderResponse,
)
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.safety_policy import sensitive_refusal
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)
from src.pipeline.semantic_plan_wire import (
    PLANNER_OUTPUT_WIRE_VERSION,
    semantic_plan_to_wire,
)

# Compact provider fallback contract. The canonical JSON Schema remains on the
# PlannerProviderRequest and the parser remains authoritative; this hint exists
# only for assessment adapters that do not expose a native structured-output
# API. It contains no registry, tool catalog, evidence, or credentials.
_WIRE_HINT = (
    "JSON only. Envelope keys exactly v,p,a; v=1; a=string|null. "
    "Plan p keys exactly v,r,d,i,t,s,x,f,m,c,svc,p,u,dc,calc,q,sp; p.v=1; "
    "t={k,v}; q={s,f}; sp is an array of {r,p,d} and is empty unless r=multi_intent. "
    "Routes: direct_answer,capability_assisted,multi_intent,refuse,clarify,"
    "unspecified,unknown. Domains: general,environment,external_information,"
    "content_generation,action,unspecified,unknown. Intent/source/freshness/target values "
    "must use the schema vocabulary; use null for absent text. "
    "calc must be null unless exact deterministic computation is required."
)

PLANNER_MAX_OUTPUT_TOKENS = 512


def _planner_generation_schema(
    schema: dict[str, object],
    user_prompt: str | None = None,
) -> dict[str, object]:
    """Return a decoder-compatible schema narrowed by hard request hints.

    The canonical parser and harness remain authoritative.  This transport
    schema only prevents the model from contradicting deterministic semantics
    already extracted from the same user request.
    """

    def normalize(value: object) -> object:
        if isinstance(value, dict):
            return {
                key: normalize(item)
                for key, item in value.items()
                if key != "uniqueItems"
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    result = {
        key: normalize(value) for key, value in schema.items() if key != "uniqueItems"
    }

    if user_prompt is None:
        return result

    try:
        payload = json.loads(user_prompt)
    except json.JSONDecodeError:
        return result

    if not isinstance(payload, dict):
        return result

    hints = payload.get("hints")
    if not isinstance(hints, dict):
        return result

    root = result.get("properties")
    if not isinstance(root, dict):
        return result

    plan = root.get("p")
    if not isinstance(plan, dict):
        return result

    props = plan.get("properties")
    if not isinstance(props, dict):
        return result

    context = payload.get("context")
    inherited_target = (
        context.get("target")
        if isinstance(context, dict) and isinstance(context.get("target"), str)
        else None
    )
    explicit_target = hints.get("target")
    target_value = (
        explicit_target
        if isinstance(explicit_target, str) and explicit_target
        else inherited_target
    )
    target_kind = "explicit" if target_value == explicit_target else "inherited"
    props["t"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["k", "v"],
        "properties": {
            "k": {
                "type": "string",
                "enum": [target_kind if target_value else "unspecified"],
            },
            "v": (
                {"type": "string", "enum": [target_value]}
                if target_value
                else {"type": "null"}
            ),
        },
    }

    # Source, route and freshness are raw-request authority, not planning
    # suggestions.  Narrowing them at generation time prevents a structurally
    # valid payload from silently downgrading current/external/URL requests
    # before the harness gets a chance to reject it.
    sources = hints.get("sources")
    excluded_sources = hints.get("exclude")
    if isinstance(sources, list) and all(isinstance(item, str) for item in sources):
        props["s"] = {"type": "array", "enum": [sources]}
    if isinstance(excluded_sources, list) and all(
        isinstance(item, str) for item in excluded_sources
    ):
        props["x"] = {"type": "array", "enum": [excluded_sources]}

    domain = hints.get("domain")
    intent = hints.get("intent")
    scope = hints.get("scope")
    if isinstance(domain, str):
        props["d"] = {"type": "string", "enum": [domain]}
    if isinstance(intent, str):
        props["i"] = {"type": "string", "enum": [intent]}

    if scope in {"current_external", "explicit_url"}:
        props["r"] = {"type": "string", "enum": ["capability_assisted"]}
        props["f"] = {"type": "string", "enum": ["current"]}
        props["dc"] = {"type": "string", "enum": ["not_required"]}
        props["calc"] = {"type": "null"}
        props["sp"] = {"type": "array", "enum": [[]]}
        root["a"] = {"type": "null"}
        explicit_url = hints.get("url")
        if isinstance(explicit_url, str) and explicit_url:
            props["u"] = {"type": "string", "enum": [explicit_url]}
        return result

    # A single stable general request is not a coordinated request.  Qwen's
    # native decoder can otherwise invent a structurally complete subplan
    # beneath a direct answer, which the canonical wire parser must reject.
    # This does not affect deliberate multi-intent requests, environment
    # inspection, current external information, or explicit URLs.
    if domain == "general" and scope == "stable_knowledge":
        props["r"] = {"type": "string", "enum": ["direct_answer"]}
        props["f"] = {"type": "string", "enum": ["stable"]}
        props["sp"] = {"type": "array", "enum": [[]]}
        calculation = hints.get("calculation")
        if (
            hints.get("deterministic_compute") == "required"
            and isinstance(calculation, dict)
            and calculation.get("operation") == "subtract"
            and isinstance(calculation.get("left"), str)
            and isinstance(calculation.get("right"), str)
        ):
            props["dc"] = {"type": "string", "enum": ["required"]}
            props["calc"] = {
                "type": "object",
                "enum": [{"op": "subtract", "values": [], "l": calculation["left"], "r": calculation["right"], "base": None, "pct": None, "tasks": None, "workers": None, "duration": None, "duration_unit": None, "rate": None, "rate_unit": None, "target_rate_unit": None, "unit": "GB"}],
            }
            root["a"] = {"type": "null"}
        return result

    if (
        hints.get("domain") != "environment"
        or hints.get("intent") != "inspect_read_only"
        or hints.get("scope") != "live_environment"
    ):
        return result

    props["r"] = {
        "type": "string",
        "enum": ["capability_assisted"],
    }
    props["d"] = {
        "type": "string",
        "enum": ["environment"],
    }
    props["i"] = {
        "type": "string",
        "enum": ["inspect_read_only"],
    }
    props["f"] = {
        "type": "string",
        "enum": ["current"],
    }
    props["dc"] = {
        "type": "string",
        "enum": ["not_required"],
    }
    props["calc"] = {"type": "null"}
    props["sp"] = {"type": "array", "enum": [[]]}

    concepts = hints.get("concepts")
    if (
        isinstance(concepts, list)
        and len(concepts) == 1
        and isinstance(concepts[0], str)
    ):
        props["m"] = {
            "type": "string",
            "enum": [concepts[0]],
        }
        props["c"] = {"type": "null"}

    props["q"] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["f", "s"],
        "properties": {
            "s": {
                "type": "string",
                "enum": ["not_required"],
            },
            "f": {"type": "null"},
        },
    }

    root["a"] = {"type": "null"}

    return result


_PROTECTED_SETUP_REFUSAL = (
    "I cannot disclose hidden instructions, secrets, credentials, or credential files."
)


class AssessmentPlannerProvider:
    """Use one existing assessment adapter as a bounded planner provider."""

    def __init__(self, model: AssessmentModelAdapter) -> None:
        if not isinstance(model, AssessmentModelAdapter):
            raise TypeError("model must be an AssessmentModelAdapter.")
        self._model = model

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        if not isinstance(request, PlannerProviderRequest):
            raise TypeError("request must be PlannerProviderRequest.")

        client = getattr(self._model, "_client", None)
        if isinstance(client, LLMClient):
            max_tokens = min(PLANNER_MAX_OUTPUT_TOKENS, client.max_tokens)
            if client.supports_structured_output:
                raw = client.generate(
                    request.user_prompt,
                    request_id=request.request_id,
                    purpose=request.purpose.value,
                    reasoning_effort=request.reasoning_effort,
                    system_prompt=request.system_prompt,
                    response_schema=_planner_generation_schema(
                        request.response_schema,
                        request.user_prompt,
                    ),
                    max_tokens=max_tokens,
                )
            else:
                # Some OpenAI-compatible endpoints (including Qwen gateways)
                # accept JSON-object mode but not the full JSON-Schema dialect.
                # Keep strict parsing authoritative while requesting the
                # strongest contract this endpoint explicitly supports.
                raw = client.generate(
                    request.user_prompt,
                    request_id=request.request_id,
                    purpose=request.purpose.value,
                    reasoning_effort=request.reasoning_effort,
                    system_prompt=f"{request.system_prompt} {_WIRE_HINT}",
                    json_object=client.supports_json_object_output,
                    max_tokens=max_tokens,
                )
            usage = client.last_usage
            fallback_provider = getattr(client, "_provider", "configured")
            fallback_model = getattr(client, "_model", "configured")
        else:
            raw = self._model.assess_raw(
                f"{request.system_prompt} {_WIRE_HINT}\n{request.user_prompt}"
            )
            usage = getattr(self._model, "last_usage", None)
            fallback_provider = type(self._model).__name__
            fallback_model = getattr(self._model, "_model", "configured")

        normalized_usage = usage if isinstance(usage, ModelCallUsage) else None
        return PlannerProviderResponse(
            payload=raw,
            provider=(
                normalized_usage.provider
                if normalized_usage is not None and normalized_usage.provider
                else str(fallback_provider)
            ),
            model=(
                normalized_usage.model
                if normalized_usage is not None and normalized_usage.model
                else str(fallback_model)
            ),
            raw_usage=_raw_usage(normalized_usage),
            configured_effort=(
                request.reasoning_effort
                if normalized_usage is not None
                and normalized_usage.configured_effort == request.reasoning_effort.value
                else None
            ),
        )


class UnconfiguredPlannerProvider:
    """Deterministic setup-mode planner: no model call and no tool authority."""

    def generate_structured(
        self,
        request: PlannerProviderRequest,
    ) -> PlannerProviderResponse:
        from src.model.unconfigured_adapter import model_unconfigured_message

        if not isinstance(request, PlannerProviderRequest):
            raise TypeError("request must be PlannerProviderRequest.")
        try:
            payload = json.loads(request.user_prompt)
        except json.JSONDecodeError as exc:
            raise ValueError("setup-mode planner request is malformed") from exc
        raw_request = payload.get("request") if isinstance(payload, dict) else None
        if not isinstance(raw_request, str) or not raw_request.strip():
            raise ValueError("setup-mode planner request has no request text")

        answer = (
            _PROTECTED_SETUP_REFUSAL
            if sensitive_refusal(raw_request) is not None
            else model_unconfigured_message(raw_request)
        )
        plan = SemanticPlan(
            route=SemanticPlanRoute.DIRECT_ANSWER,
            domain=RequestDomain.GENERAL,
            execution_intent=ExecutionIntent.EXPLAIN,
            source_constraints=(SourceConstraint.ANY,),
            freshness=FreshnessRequirement.STABLE,
            deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
            clarification=ClarificationState.NOT_REQUIRED,
        )
        return PlannerProviderResponse(
            payload={
                "v": PLANNER_OUTPUT_WIRE_VERSION,
                "p": semantic_plan_to_wire(plan),
                "a": answer,
            },
            provider="unconfigured",
            model="none",
        )


def _raw_usage(usage: ModelCallUsage | None) -> Mapping[str, object] | None:
    if usage is None:
        return None
    raw: dict[str, object] = {}
    if usage.input_tokens is not None:
        raw["prompt_tokens"] = usage.input_tokens
    if usage.total_output_tokens is not None:
        raw["completion_tokens"] = usage.total_output_tokens
    if usage.reasoning_tokens is not None:
        raw["reasoning_tokens"] = usage.reasoning_tokens
    return raw or None


__all__ = [
    "AssessmentPlannerProvider",
    "PLANNER_MAX_OUTPUT_TOKENS",
    "UnconfiguredPlannerProvider",
]
