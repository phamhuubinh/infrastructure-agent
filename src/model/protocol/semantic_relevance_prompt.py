"""Bounded prompt input for the final semantic relevance verifier."""

from __future__ import annotations

import json
from dataclasses import dataclass

from src.pipeline.semantic_plan import SemanticPlan
from src.shared.execution.command_result import redact_sensitive

MAX_RELEVANCE_REQUEST_CHARS = 4_096
MAX_RELEVANCE_DRAFT_BYTES = 2_048
MAX_RELEVANCE_PLAN_BYTES = 1_024
MAX_RELEVANCE_FIELD_CHARS = 256

SEMANTIC_RELEVANCE_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision", "reason"],
    "properties": {
        "decision": {
            "type": "string",
            "enum": ["aligned", "not_aligned"],
        },
        "reason": {
            "type": "string",
            "enum": [
                "aligned",
                "cross_task",
                "request_not_answered",
                "plan_mismatch",
            ],
        },
    },
}

_SYSTEM_PROMPT = (
    "You are Orion's compact final-answer relevance verifier. Decide only whether "
    "the bounded draft answers the original request consistently with the semantic "
    "plan summary. You have no tools, no external-evidence authority, and must not "
    "add facts. Return exactly one JSON object with keys decision and reason. "
    "decision must be aligned or not_aligned. For aligned use reason=aligned. For "
    "not_aligned use one of cross_task, request_not_answered, or plan_mismatch. "
    "Return no prose, analysis, explanation, or hidden reasoning."
)


@dataclass(frozen=True, slots=True)
class SemanticRelevancePrompt:
    """Complete authority-free verifier prompt."""

    system_prompt: str
    user_prompt: str

    def render(self) -> str:
        return f"{self.system_prompt}\n\nVerifier input:\n{self.user_prompt}"


def build_semantic_relevance_prompt(
    original_request: str,
    plan: SemanticPlan,
    draft: str,
) -> SemanticRelevancePrompt:
    """Build a prompt containing only request, plan summary, and bounded draft."""

    if not isinstance(original_request, str) or not original_request.strip():
        raise ValueError("original_request must be non-empty text.")
    if len(original_request) > MAX_RELEVANCE_REQUEST_CHARS:
        raise ValueError(
            f"original_request exceeds {MAX_RELEVANCE_REQUEST_CHARS} characters."
        )
    if not isinstance(plan, SemanticPlan):
        raise TypeError("plan must be a SemanticPlan.")
    if not isinstance(draft, str) or not draft.strip():
        raise ValueError("draft must be non-empty text.")

    payload = {
        "request": original_request,
        "plan": semantic_plan_relevance_summary(plan),
        "draft": _bounded_draft(draft),
    }
    return SemanticRelevancePrompt(
        system_prompt=_SYSTEM_PROMPT,
        user_prompt=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
    )


def semantic_plan_relevance_summary(plan: SemanticPlan) -> dict[str, object]:
    """Return a compact allowlisted summary without tools or evidence."""

    if not isinstance(plan, SemanticPlan):
        raise TypeError("plan must be a SemanticPlan.")
    summary: dict[str, object] = {
        "route": plan.route.value,
        "domain": plan.domain.name.casefold(),
        "intent": plan.execution_intent.name.casefold(),
        "freshness": plan.freshness.value,
    }
    sources = [source.name.casefold() for source in plan.source_constraints]
    if sources:
        summary["sources"] = sources
    optional = (
        ("concept", plan.concept),
        ("metric", plan.metric),
        ("service", plan.service),
        ("target", plan.target.value),
        ("path", plan.path),
        ("url", plan.explicit_url),
    )
    for key, value in optional:
        safe = _safe_field(value)
        if safe is not None:
            candidate = {**summary, key: safe}
            if _json_size(candidate) <= MAX_RELEVANCE_PLAN_BYTES:
                summary = candidate
    return summary


def _safe_field(value: str | None) -> str | None:
    if value is None:
        return None
    compact = " ".join(redact_sensitive(value).split())
    return compact[:MAX_RELEVANCE_FIELD_CHARS] or None


def _bounded_draft(draft: str) -> str:
    safe = redact_sensitive(draft)
    encoded = safe.encode("utf-8")
    if len(encoded) <= MAX_RELEVANCE_DRAFT_BYTES:
        return safe
    return encoded[:MAX_RELEVANCE_DRAFT_BYTES].decode("utf-8", errors="ignore")


def _json_size(value: object) -> int:
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    )


__all__ = [
    "MAX_RELEVANCE_DRAFT_BYTES",
    "MAX_RELEVANCE_PLAN_BYTES",
    "MAX_RELEVANCE_REQUEST_CHARS",
    "SEMANTIC_RELEVANCE_JSON_SCHEMA",
    "SemanticRelevancePrompt",
    "build_semantic_relevance_prompt",
    "semantic_plan_relevance_summary",
]
