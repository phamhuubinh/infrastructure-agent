"""Current/external verification regression matrix (#46).

Deterministic fake Internet results and unavailable fixtures only. Live
current-information claims must come from verified evidence, never from
model memory.
"""

from __future__ import annotations

import pytest

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
from src.model.usage_metadata import ModelCallUsage
from src.pipeline.request_semantics import RequestDomain, SourceConstraint
from src.pipeline.semantic_plan import FreshnessRequirement
from tests.fixtures.fake_environment import (
    InternetTool,
    fake_environment,
    raw_search_payload,
)
from tests.fixtures.fake_models import (
    RecordingEngine,
    ScriptedAssessmentModel,
    ScriptedPlannerProvider,
    capability_plan,
    plan_response,
)

PRODUCTS = (
    "Python",
    "Node.js",
    "Kubernetes",
    "OpenSSH",
    "Ubuntu",
    "PostgreSQL",
    "Redis",
    "Grafana",
    "Zabbix",
    "Nginx",
)

CURRENT_INFO_REQUESTS = (
    (
        "Who is the current office holder of this role?",
        "The current office holder is president Alice Example.",
    ),
    (
        "What is the current price of gold?",
        "Gold price today is $82.50 per gram.",
    ),
    ("What is the latest Python version?", "Python latest version is 3.14.2."),
    ("What is the latest Node.js version?", "Node.js latest version is 22.13.0."),
)


def _fetch_payload(url: str, content: str) -> dict[str, object]:
    return {
        "url": url,
        "status": 200,
        "content_type": "text/html",
        "content_length": len(content),
        "truncated": False,
        "data": content,
    }


def _verified_agent(
    *,
    product: str,
    claim: str,
    question: str | None = None,
) -> tuple[DeterministicAgent, InternetTool, ScriptedAssessmentModel]:
    url = f"https://{product.casefold().replace(' ', '-')}.example/release"
    internet = InternetTool(
        search_payloads=[raw_search_payload(url)],
        fetch_payloads={url: _fetch_payload(url, claim)},
    )
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft=claim)
    plan = capability_plan(
        concept=f"{product} current version",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )
    return agent, internet, model


@pytest.mark.parametrize("product", PRODUCTS)
def test_latest_version_claims_require_verified_fetch(product: str) -> None:
    claim = f"{product} latest version is 9.9.9"
    agent, internet, model = _verified_agent(
        product=product,
        claim=claim,
    )

    result = agent.run_with_steps(f"What is the latest {product} version?")

    trace = result["execution_trace"]
    assert trace["evidence_status"] == "SUFFICIENT"
    assert trace["answer_strategy"] == "LLM_ASSESSMENT"
    assert claim in result["response"]
    assert len(internet.search_calls) == 1
    assert len(internet.fetch_calls) == 1
    assert [call.kind for call in model.calls].count("response") == 1


@pytest.mark.parametrize(("question", "claim"), CURRENT_INFO_REQUESTS)
def test_current_info_requests_use_verified_evidence_only(
    question: str,
    claim: str,
) -> None:
    """The fixture is intentionally configured to succeed (valid fake search
    result + valid fake fetch payload + sufficient relevant content), so the
    success behavior must be asserted explicitly — a regression that breaks
    the external path and silently degrades every case to UNAVAILABLE must
    not keep this test green."""
    url = "https://news.example/current"
    internet = InternetTool(
        search_payloads=[raw_search_payload(url)],
        fetch_payloads={url: _fetch_payload(url, claim)},
    )
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft=claim)
    plan = capability_plan(
        concept="current information",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps(question)

    trace = result["execution_trace"]
    assert trace["evidence_status"] == "SUFFICIENT"
    assert trace["answer_strategy"] == "LLM_ASSESSMENT"
    assert len(internet.search_calls) == 1
    assert len(internet.fetch_calls) == 1
    assert [call.kind for call in model.calls].count("response") == 1
    assert claim in result["response"]


RESPONSE_USAGE = ModelCallUsage(
    input_tokens=120,
    reasoning_tokens=80,
    visible_output_tokens=40,
    total_output_tokens=120,
    model="fake-model",
    provider="fake",
    latency_ms=10.0,
)


def test_verified_external_response_records_exactly_one_response_usage() -> None:
    url = "https://news.example/current"
    claim = "The current office holder is president Alice Example."
    internet = InternetTool(
        search_payloads=[raw_search_payload(url)],
        fetch_payloads={url: _fetch_payload(url, claim)},
    )
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(
        draft=claim,
        usages={"response": RESPONSE_USAGE},
    )
    plan = capability_plan(
        concept="current information",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("Who is the current office holder of this role?")

    assert [call.kind for call in model.calls].count("response") == 1
    usage = result["execution_trace"]["runtime_metrics"]["model_usage"]
    assert usage["by_purpose"]["response"] == {
        "calls": 1,
        "latency_ms": 10.0,
        "input_tokens": 120,
        "reasoning_tokens": 80,
        "visible_output_tokens": 40,
        "total_output_tokens": 120,
        "estimated_input_tokens": None,
    }
    response_purposes = [
        entry["purpose"]
        for entry in usage["per_call"]
        if entry["purpose"] == "response"
    ]
    assert response_purposes == ["response"]


def test_unverified_external_response_never_fabricates_response_usage() -> None:
    internet = InternetTool(search_error=RuntimeError("provider down"))
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(
        draft="Stale memory claim.",
        usages={"response": RESPONSE_USAGE},
    )
    plan = capability_plan(
        concept="current information",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("Who is the current office holder of this role?")

    assert [call.kind for call in model.calls] == []
    usage = result["execution_trace"]["runtime_metrics"]["model_usage"]
    assert "response" not in usage["by_purpose"]


def test_explicit_public_url_fetches_directly_without_search() -> None:
    url = "https://docs.example.com/page"
    claim = "The documented current version is 42.0.0"
    internet = InternetTool(fetch_payloads={url: _fetch_payload(url, claim)})
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft=claim)
    plan = capability_plan(
        concept="documented version",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.URL_ONLY,),
        freshness=FreshnessRequirement.CURRENT,
        explicit_url=url,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps(
        f"Read {url} and tell me the current version"
    )

    assert internet.search_calls == []
    assert len(internet.fetch_calls) == 1
    assert claim in result["response"]
    assert result["execution_trace"]["evidence_status"] == "SUFFICIENT"


def test_unavailable_search_never_falls_back_to_model_memory() -> None:
    internet = InternetTool(search_error=RuntimeError("provider down"))
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Python 9.9.9 is the latest version.")
    plan = capability_plan(
        concept="Python current version",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("What is the latest Python version?")

    trace = result["execution_trace"]
    assert trace["evidence_status"] == "UNAVAILABLE"
    assert "cannot be verified" in result["response"]
    assert "9.9.9" not in result["response"]
    # The model is never asked to answer current-info from memory.
    assert "response" not in [call.kind for call in model.calls]


def test_fetched_but_insufficient_content_never_falls_back_to_model_memory() -> None:
    """A fetch that succeeds but returns non-claim-shaped content must not
    promote the model draft — the deterministic unavailable fallback is the
    only answer and the response model is never called."""
    url = "https://news.example/current"
    internet = InternetTool(
        search_payloads=[raw_search_payload(url)],
        fetch_payloads={url: _fetch_payload(url, "Some unrelated page text.")},
    )
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Python 9.9.9 is the latest version.")
    plan = capability_plan(
        concept="current information",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("What is the latest Python version?")

    trace = result["execution_trace"]
    assert trace["evidence_status"] == "UNAVAILABLE"
    assert "9.9.9" not in result["response"]
    assert [call.kind for call in model.calls] == []


def test_search_result_pointing_to_private_address_is_blocked() -> None:
    internet = InternetTool(
        search_payloads=[raw_search_payload("http://192.168.1.1/secret")]
    )
    env = fake_environment(localhost=True, internet_tool=internet)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="Stale memory claim.")
    plan = capability_plan(
        concept="current information",
        domain=RequestDomain.EXTERNAL_INFORMATION,
        sources=(SourceConstraint.INTERNET,),
        freshness=FreshnessRequirement.CURRENT,
    )
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("What is today's internal metric?")

    assert internet.fetch_calls == []
    assert result["execution_trace"]["evidence_status"] == "UNAVAILABLE"
    assert "Stale memory claim." not in result["response"]
