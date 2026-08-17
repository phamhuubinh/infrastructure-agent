"""Current/external verification regression matrix (#46).

Deterministic fake Internet results and unavailable fixtures only. Live
current-information claims must come from verified evidence, never from
model memory.
"""

from __future__ import annotations

import pytest

from src.agent.deterministic_agent import DeterministicAgent
from src.model.semantic_planner_adapter import SemanticPlannerAdapter
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
    ("Giá vàng hôm nay là bao nhiêu?", "giá vàng hôm nay là 10 triệu đồng"),
    ("What is the weather right now?", "weather right now: sunny and clear"),
    ("Tin tức mới nhất tuần này là gì?", "tin tức mới nhất tuần này: họp báo"),
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
    if trace["evidence_status"] == "SUFFICIENT":
        assert claim in result["response"]
        return
    # Unverified current-info must never present the model draft as an
    # answer; the deterministic unavailable template is the only fallback.
    assert trace["evidence_status"] == "UNAVAILABLE"
    assert claim not in result["response"]
    assert "response" not in [call.kind for call in model.calls]


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
