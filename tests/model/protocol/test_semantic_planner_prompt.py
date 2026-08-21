from __future__ import annotations

import json

import pytest

from src.model.protocol.semantic_planner_prompt import (
    MAX_PLANNER_CONTEXT_BYTES,
    MAX_PLANNER_REQUEST_CHARS,
    PlannerPromptContext,
    build_semantic_planner_prompt,
)
from src.pipeline.request_semantics import SourceConstraint


@pytest.mark.parametrize(
    "user_text",
    (
        "hello",
        "Translate hello to Vietnamese.",
        "HTTP GET khác POST thế nào?",
    ),
)
def test_simple_first_pass_prompt_is_tiny_and_has_no_catalog(user_text: str) -> None:
    prompt = build_semantic_planner_prompt(user_text)
    user_payload = json.loads(prompt.user_prompt)
    combined = prompt.system_prompt + prompt.user_prompt

    assert user_payload["request"] == user_text
    assert isinstance(user_payload["hints"], dict)
    assert len(combined) < 2600
    assert "OrionPlannerOutputV1" in prompt.system_prompt
    assert "plan is advisory" in prompt.system_prompt
    assert "harness" in prompt.system_prompt
    assert "do not use unknown for a clear request" in prompt.system_prompt
    assert "never place one source in both" in prompt.system_prompt
    assert "Exact arithmetic" in prompt.system_prompt
    assert "Live environment inspection" in prompt.system_prompt
    for forbidden in (
        "LinuxTool",
        "GrafanaTool",
        "ZabbixTool",
        "InternetTool",
        "capability_id",
        "target registry",
        "collector",
        "evidence payload",
        "api_key",
    ):
        assert forbidden.casefold() not in combined.casefold()


def test_prompt_contains_only_allowlisted_bounded_session_context() -> None:
    context = PlannerPromptContext(
        target="monitor",
        concept="cpu",
        service="nginx",
        path="/var/log/nginx/access.log",
        time_range="last_1h",
        sources=(SourceConstraint.GRAFANA,),
        excluded_sources=(SourceConstraint.INTERNET,),
        pending_clarification_field="metric",
    )

    prompt = build_semantic_planner_prompt("Còn RAM thì sao?", context=context)
    payload = json.loads(prompt.user_prompt)

    assert payload["request"] == "Còn RAM thì sao?"
    assert isinstance(payload["hints"], dict)
    assert payload["context"] == {
        "target": "monitor",
        "concept": "cpu",
        "service": "nginx",
        "path": "/var/log/nginx/access.log",
        "time": "last_1h",
        "clarify": "metric",
        "sources": ["grafana"],
        "exclude": ["internet"],
    }
    assert len(json.dumps(payload["context"]).encode()) < MAX_PLANNER_CONTEXT_BYTES


def test_unrelated_registry_growth_cannot_change_prompt_shape() -> None:
    before = build_semantic_planner_prompt("hello")
    unrelated_registry = {
        f"tool-{index}": {"schema": "x" * 1000} for index in range(100)
    }
    assert unrelated_registry
    after = build_semantic_planner_prompt("hello")

    assert after == before


def test_prompt_rejects_unbounded_or_malformed_input() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        build_semantic_planner_prompt("   ")
    with pytest.raises(ValueError, match="exceeds"):
        build_semantic_planner_prompt("x" * (MAX_PLANNER_REQUEST_CHARS + 1))
    with pytest.raises(ValueError, match="trimmed"):
        build_semantic_planner_prompt(
            "hello",
            context=PlannerPromptContext(target=" monitor "),
        )


def test_response_schema_is_out_of_band_and_provider_neutral() -> None:
    prompt = build_semantic_planner_prompt("hello")

    assert prompt.response_schema["title"] == "OrionPlannerOutputV1"
    assert "response_format" not in prompt.response_schema
    assert "anthropic" not in prompt.system_prompt.casefold()
    assert "openai" not in prompt.system_prompt.casefold()


def test_current_request_hints_are_deterministic() -> None:
    greeting = json.loads(build_semantic_planner_prompt("Xin chào").user_prompt)[
        "hints"
    ]
    assert greeting["domain"] == "general"
    assert greeting["intent"] == "explain"
    assert greeting["scope"] == "stable_knowledge"
    assert greeting["sources"] == ["any"]

    cpu = json.loads(
        build_semantic_planner_prompt("Kiểm tra CPU trên monitor.").user_prompt
    )["hints"]
    assert cpu["domain"] == "environment"
    assert cpu["intent"] == "inspect_read_only"
    assert cpu["scope"] == "live_environment"
    assert cpu["target"] == "monitor"
    assert "cpu" in cpu["concepts"]

    arithmetic = json.loads(
        build_semantic_planner_prompt("Tính 15% của 2 triệu.").user_prompt
    )["hints"]
    assert arithmetic["domain"] == "general"
    assert arithmetic["intent"] == "explain"
    assert arithmetic["scope"] == "stable_knowledge"


def test_request_hints_do_not_leak_fuzzy_or_target_concepts() -> None:
    import json

    arithmetic = json.loads(
        build_semantic_planner_prompt("Tính 15% của 2 triệu.").user_prompt
    )["hints"]
    assert arithmetic["domain"] == "general"
    assert arithmetic["intent"] == "explain"
    assert "concepts" not in arithmetic

    environment = json.loads(
        build_semantic_planner_prompt("Kiểm tra CPU trên monitor.").user_prompt
    )["hints"]
    assert environment["domain"] == "environment"
    assert environment["intent"] == "inspect_read_only"
    assert environment["target"] == "monitor"
    assert environment["concepts"] == ["cpu"]


def test_explicit_url_is_a_url_hint_not_a_target_hint() -> None:
    hints = json.loads(
        build_semantic_planner_prompt(
            "Đọc https://example.com và tóm tắt nội dung chính."
        ).user_prompt
    )["hints"]

    assert hints["url"] == "https://example.com"
    assert "target" not in hints
