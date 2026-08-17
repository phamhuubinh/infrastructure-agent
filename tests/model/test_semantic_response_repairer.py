from __future__ import annotations

import json
from dataclasses import dataclass, field

from src.model.semantic_response_repairer import (
    SemanticRepairStatus,
    SemanticResponseRepairer,
)
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.provenance import Provenance


@dataclass
class MockRepairModel:
    response: str | Exception
    prompts: list[str] = field(default_factory=list)

    def assess_raw(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _fact() -> Fact:
    return Fact(
        subject="web",
        metric="service.latency_ms",
        value=120,
        unit="ms",
        observed_at="2026-08-14T00:00:00Z",
        collected_at="2026-08-14T00:00:00Z",
        source="monitor",
        target="api-1",
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=Provenance(
            source="monitor",
            capability="monitor.latency",
            target="api-1",
            source_reference="run-1",
        ),
    )


def test_repair_prompt_contains_only_failure_request_and_required_facts() -> None:
    model = MockRepairModel("The API latency is 120 ms.")
    fact = _fact()

    result = SemanticResponseRepairer(model).repair(
        "What is the API latency?",
        violations=("semantic_not_aligned",),
        relevance_reason="request_not_answered",
        facts=(fact,),
    )

    assert result.repaired
    assert result.to_trace_dict() == {"attempted": True, "status": "repaired"}
    payload = json.loads(model.prompts[0].split("Repair input:\n", 1)[1])
    assert payload == {
        "request": "What is the API latency?",
        "failure": {
            "postconditions": ["semantic_not_aligned"],
            "relevance": "request_not_answered",
        },
        "facts": [
            {
                "id": fact.id,
                "metric": "service.latency_ms",
                "value": 120,
                "unit": "ms",
                "target": "api-1",
                "source": "monitor",
            }
        ],
    }
    assert "draft" not in payload
    assert "draft" not in model.prompts[0]


def test_provider_failure_or_empty_repair_is_explicit_and_safe() -> None:
    unavailable = SemanticResponseRepairer(MockRepairModel(RuntimeError("down"))).repair(
        "Say hello", violations=("semantic_not_aligned",), relevance_reason=None, facts=()
    )
    empty = SemanticResponseRepairer(MockRepairModel(" \n")).repair(
        "Say hello", violations=("semantic_not_aligned",), relevance_reason=None, facts=()
    )

    assert unavailable.status is SemanticRepairStatus.PROVIDER_UNAVAILABLE
    assert not unavailable.repaired
    assert empty.status is SemanticRepairStatus.EMPTY_RESPONSE
    assert not empty.repaired
