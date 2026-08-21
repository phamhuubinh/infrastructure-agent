from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from src.model.llm_assessment_adapter import LLMAssessmentAdapter
from src.model.llm_client import LLMClient
from src.model.protocol.semantic_relevance_prompt import (
    MAX_RELEVANCE_DRAFT_BYTES,
    SEMANTIC_RELEVANCE_JSON_SCHEMA,
)
from src.model.semantic_relevance_verifier import (
    RELEVANCE_MAX_OUTPUT_TOKENS,
    SemanticRelevanceDecision,
    SemanticRelevanceReason,
    SemanticRelevanceVerifier,
)
from src.pipeline.request_semantics import (
    ExecutionIntent,
    RequestDomain,
    SourceConstraint,
)
from src.pipeline.semantic_plan import (
    ClarificationState,
    DeterministicComputeIntent,
    FreshnessRequirement,
    SemanticPlan,
    SemanticPlanRoute,
)


@dataclass
class MockRelevanceModel:
    response: str
    prompts: list[str] = field(default_factory=list)

    def assess_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def _plan(concept: str) -> SemanticPlan:
    return SemanticPlan(
        route=SemanticPlanRoute.DIRECT_ANSWER,
        domain=RequestDomain.GENERAL,
        execution_intent=ExecutionIntent.EXPLAIN,
        source_constraints=(SourceConstraint.ANY,),
        freshness=FreshnessRequirement.STABLE,
        concept=concept,
        deterministic_compute=DeterministicComputeIntent.NOT_REQUIRED,
        clarification=ClarificationState.NOT_REQUIRED,
    )


@pytest.mark.parametrize(
    ("user_request", "concept", "draft", "reason"),
    (
        (
            "Cảm ơn bạn nhé",
            "gratitude acknowledgement",
            "Hãy lắp camera, cảm biến cửa và còi báo động cho ngôi nhà.",
            "cross_task",
        ),
        (
            "Review the HTTP retry logic.",
            "HTTP retry review",
            "The production server currently has 32 CPU cores and 128 GB RAM.",
            "request_not_answered",
        ),
    ),
)
def test_cross_task_drafts_are_rejected_from_tiny_mocked_results(
    user_request: str,
    concept: str,
    draft: str,
    reason: str,
) -> None:
    model = MockRelevanceModel(
        json.dumps({"decision": "not_aligned", "reason": reason})
    )

    result = SemanticRelevanceVerifier(model).verify(
        user_request,
        _plan(concept),
        draft,
    )

    assert result.decision is SemanticRelevanceDecision.NOT_ALIGNED
    assert result.reason.value == reason
    payload = json.loads(model.prompts[0].split("Verifier input:\n", 1)[1])
    assert payload == {
        "request": user_request,
        "plan": {
            "route": "direct_answer",
            "domain": "general",
            "intent": "explain",
            "freshness": "stable",
            "concept": concept,
            "sources": ["any"],
        },
        "draft": draft,
    }


@pytest.mark.parametrize(
    ("user_request", "concept", "draft"),
    (
        ("Cảm ơn bạn nhé", "gratitude acknowledgement", "Không có gì!"),
        (
            "Review the HTTP retry logic.",
            "HTTP retry review",
            "The retry loop correctly stops after three transient failures.",
        ),
    ),
)
def test_correct_concise_answers_pass(
    user_request: str,
    concept: str,
    draft: str,
) -> None:
    model = MockRelevanceModel('{"decision":"aligned","reason":"aligned"}')

    result = SemanticRelevanceVerifier(model).verify(
        user_request,
        _plan(concept),
        draft,
    )

    assert result.aligned
    assert result.reason is SemanticRelevanceReason.ALIGNED


def test_llm_verifier_uses_tiny_native_schema_for_a_relevant_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate(
        self: LLMClient,
        prompt: str,
        **kwargs: object,
    ) -> str:
        del self, prompt
        captured.update(kwargs)
        return '{"decision":"aligned","reason":"aligned"}'

    monkeypatch.setattr(LLMClient, "generate", fake_generate)
    model = LLMAssessmentAdapter(LLMClient(max_tokens=4096))

    result = SemanticRelevanceVerifier(model).verify(
        "Cảm ơn bạn nhé",
        _plan("gratitude acknowledgement"),
        "Không có gì!",
    )

    assert result.aligned
    assert captured["purpose"] == "relevance"
    assert captured["max_tokens"] == RELEVANCE_MAX_OUTPUT_TOKENS
    assert captured["response_schema"] == SEMANTIC_RELEVANCE_JSON_SCHEMA


def test_invalid_or_explanatory_verifier_output_fails_closed_without_storage() -> None:
    model = MockRelevanceModel(
        '{"decision":"aligned","reason":"aligned","analysis":"hidden"}'
    )

    result = SemanticRelevanceVerifier(model).verify(
        "Say hello",
        _plan("greeting"),
        "Hello!",
    )

    assert not result.aligned
    assert result.reason is SemanticRelevanceReason.INVALID_OUTPUT
    assert result.to_trace_dict() == {
        "decision": "not_aligned",
        "reason": "invalid_output",
    }


def test_verifier_receives_a_byte_bounded_draft() -> None:
    model = MockRelevanceModel('{"decision":"aligned","reason":"aligned"}')

    SemanticRelevanceVerifier(model).verify(
        "Summarize this",
        _plan("summary"),
        "ừ" * 10_000,
    )

    payload = json.loads(model.prompts[0].split("Verifier input:\n", 1)[1])
    assert len(payload["draft"].encode("utf-8")) <= MAX_RELEVANCE_DRAFT_BYTES
    assert set(payload) == {"request", "plan", "draft"}
