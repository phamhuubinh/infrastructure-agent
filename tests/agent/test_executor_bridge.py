from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from types import ModuleType

from src.agent.execution import (
    AuthorizedActionExecutor,
    AuthorizedExecutionRequest,
    ExecutionStatus,
)
from src.agent.executor_bridge import (
    CanonicalActionExecutor,
    evidence_execution_result,
)
from src.agent.permissions import EffectClass
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.external_verification import (
    ExternalVerificationOutcome,
)
from src.pipeline.fact import (
    Fact,
    FactFreshness,
    FactValidity,
)
from src.pipeline.provenance import Provenance
from src.shared.capability import Capability, ParameterSpec
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import (
    CapabilityResult,
    CapabilityStatus,
)
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.tool import Tool


def _handler(window: int = 60) -> CapabilityResult:
    return CapabilityResult.from_data({"window": window, "value": 42})


def _grafana_tool(monkeypatch) -> Tool:
    module_name = "tests.fake_executor_bridge_grafana"
    module = ModuleType(module_name)

    capabilities = {
        "metrics": Capability(
            name="metrics",
            handler=_handler,
            description="Read metrics",
            parameters=("window",),
            parameter_specs=(
                ParameterSpec(
                    name="window",
                    required=True,
                    value_type="int",
                    minimum=1,
                    maximum=300,
                ),
            ),
            mutation_risk="none",
        ),
    }

    module._CAPABILITIES = capabilities  # type: ignore[attr-defined]

    class GrafanaTool(Tool):
        def execute(
            self,
            arguments: dict[str, object],
        ) -> ToolResult:
            return self._dispatch(
                capabilities,
                arguments,
                "GrafanaTool",
            )

    GrafanaTool.__module__ = module_name
    module.GrafanaTool = GrafanaTool
    monkeypatch.setitem(sys.modules, module_name, module)

    return GrafanaTool()


def _knowledge(monkeypatch) -> KnowledgeTool:
    registry = TargetRegistry()
    registry.register_domain_tool(
        "grafana-prod",
        _grafana_tool(monkeypatch),
    )
    return KnowledgeTool(registry)


def _calculator_arguments() -> dict[str, object]:
    return {
        "operation": "multiply",
        "left": 287,
        "right": 419,
    }


class FakeExternalVerification:
    def __init__(self) -> None:
        self.search_calls: list[dict[str, object]] = []
        self.fetch_calls: list[dict[str, object]] = []

    def collect_search_action(
        self,
        **kwargs: object,
    ) -> ExternalVerificationOutcome:
        self.search_calls.append(dict(kwargs))
        return ExternalVerificationOutcome(
            evidence=EvidencePackage(
                capability_name="external_verification",
                evidence_name="internet_search",
                data={"status": "ok"},
                source_tool="internet",
                source="internet",
                resource="web_search",
                status=CapabilityStatus.VALID,
            ),
            search_calls=1,
        )

    def collect_fetch_action(
        self,
        **kwargs: object,
    ) -> ExternalVerificationOutcome:
        self.fetch_calls.append(dict(kwargs))
        return ExternalVerificationOutcome(
            evidence=EvidencePackage(
                capability_name="external_verification",
                evidence_name="internet_fetch",
                data={"status": "ok"},
                source_tool="internet",
                source="internet",
                resource="web_fetch",
                status=CapabilityStatus.VALID,
            ),
            fetch_calls=1,
            total_bytes=100,
        )


def test_executor_satisfies_authorized_protocol(monkeypatch) -> None:
    executor = CanonicalActionExecutor(_knowledge(monkeypatch))

    assert isinstance(
        executor,
        AuthorizedActionExecutor,
    )


def test_knowledge_binding_dispatches_exact_source_and_resource(
    monkeypatch,
) -> None:
    knowledge = _knowledge(monkeypatch)
    original = knowledge.execute
    calls: list[dict[str, object]] = []

    def recording_execute(
        arguments: dict[str, object],
    ) -> ToolResult:
        calls.append(dict(arguments))
        return original(arguments)

    monkeypatch.setattr(
        knowledge,
        "execute",
        recording_execute,
    )

    result = CanonicalActionExecutor(knowledge).execute(
        AuthorizedExecutionRequest(
            capability_id="grafana.metrics",
            runtime_binding="knowledge.dispatch",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="grafana-prod",
            arguments={"window": 60},
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.dispatched is True
    assert calls == [
        {
            "source": "grafana-prod",
            "resource": "metrics",
            "window": 60,
        }
    ]


def test_knowledge_binding_does_not_fallback_source(
    monkeypatch,
) -> None:
    knowledge = _knowledge(monkeypatch)
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        knowledge,
        "execute",
        lambda arguments: calls.append(dict(arguments)) or ToolResult(success=True),
    )

    result = CanonicalActionExecutor(knowledge).execute(
        AuthorizedExecutionRequest(
            capability_id="grafana.metrics",
            runtime_binding="knowledge.dispatch",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="grafana-other",
            arguments={"window": 60},
        )
    )

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.dispatched is False
    assert calls == []


def test_executor_blocks_effect_metadata_drift(
    monkeypatch,
) -> None:
    knowledge = _knowledge(monkeypatch)
    metadata = knowledge.get_capability_metadata()

    for entry in metadata["grafana-prod"]:
        if entry.get("name") == "metrics":
            entry["mutation_risk"] = "high"

    monkeypatch.setattr(
        knowledge,
        "get_capability_metadata",
        lambda: metadata,
    )

    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        knowledge,
        "execute",
        lambda arguments: calls.append(dict(arguments)) or ToolResult(success=True),
    )

    result = CanonicalActionExecutor(knowledge).execute(
        AuthorizedExecutionRequest(
            capability_id="grafana.metrics",
            runtime_binding="knowledge.dispatch",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="grafana-prod",
            arguments={"window": 60},
        )
    )

    assert result.status is ExecutionStatus.BLOCKED
    assert result.reason == "effect_metadata_mismatch"
    assert result.dispatched is False
    assert calls == []


def test_calculator_executes_structured_transport(
    monkeypatch,
) -> None:
    result = CanonicalActionExecutor(_knowledge(monkeypatch)).execute(
        AuthorizedExecutionRequest(
            capability_id="compute.deterministic",
            runtime_binding="calculator.execute",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref=None,
            arguments=_calculator_arguments(),
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.dispatched is True
    assert result.facts[0]["value"] == "120253"


def test_evidence_projection_removes_secret_shaped_values() -> None:
    now = datetime.now(timezone.utc)

    fact = Fact(
        subject="service",
        metric="service.example.state",
        value={
            "token": "super-secret",
            "message": "Authorization: Bearer abc123",
        },
        unit="state",
        observed_at=now,
        collected_at=now,
        source="test",
        target="example",
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=Provenance(
            source="test",
            capability="read",
            target="example",
            observed_at=now,
        ),
    )

    result = evidence_execution_result(
        EvidencePackage(
            capability_name="test.read",
            evidence_name="test.read",
            data={"ignored": "raw"},
            source_tool="test",
            source="test",
            resource="read",
            status=CapabilityStatus.VALID,
            facts=(fact,),
        ),
        dispatched=True,
    )

    serialized = json.dumps(
        result.facts,
        default=str,
    )

    assert "super-secret" not in serialized
    assert "abc123" not in serialized
    assert '"token"' not in serialized


def test_unknown_runtime_binding_never_dispatches(
    monkeypatch,
) -> None:
    result = CanonicalActionExecutor(_knowledge(monkeypatch)).execute(
        AuthorizedExecutionRequest(
            capability_id="host.unknown",
            runtime_binding="unknown.execute",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref=None,
            arguments={},
        )
    )

    assert result.status is ExecutionStatus.UNAVAILABLE
    assert result.dispatched is False
    assert result.reason == "runtime_binding_unavailable"


def _internet_knowledge() -> KnowledgeTool:
    registry = TargetRegistry()

    class InternetTool(Tool):
        def execute(
            self,
            arguments: dict[str, object],
        ) -> ToolResult:
            return ToolResult(success=True)

    registry.register_domain_tool(
        "internet-main",
        InternetTool(),
    )

    return KnowledgeTool(registry)


def test_internet_current_uses_exact_source_and_fresh_semantics() -> None:
    internet = FakeExternalVerification()
    knowledge = _internet_knowledge()

    result = CanonicalActionExecutor(
        knowledge,
        external_verification=internet,
    ).execute(
        AuthorizedExecutionRequest(
            capability_id="internet.current",
            runtime_binding="internet.current",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="internet-main",
            arguments={
                "queries": ("latest release",),
            },
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.dispatched is True

    assert internet.search_calls == [
        {
            "source_id": "internet-main",
            "queries": ("latest release",),
            "max_results": 5,
            "freshness_required": True,
        }
    ]

    assert internet.fetch_calls == []


def test_internet_fetch_uses_only_authorized_url() -> None:
    internet = FakeExternalVerification()
    knowledge = _internet_knowledge()

    url = "https://example.com/release"

    result = CanonicalActionExecutor(
        knowledge,
        external_verification=internet,
    ).execute(
        AuthorizedExecutionRequest(
            capability_id="internet.fetch_url",
            runtime_binding="internet.fetch_url",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="internet-main",
            arguments={
                "url": url,
            },
        )
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.dispatched is True

    assert internet.fetch_calls == [
        {
            "source_id": "internet-main",
            "url": url,
            "user_request": url,
            "freshness_required": False,
        }
    ]

    assert internet.search_calls == []


def test_post_dispatch_normalization_failure_remains_dispatched(
    monkeypatch,
) -> None:
    executor = CanonicalActionExecutor(_knowledge(monkeypatch))

    def explode(**kwargs):
        raise RuntimeError("normalizer failed")

    monkeypatch.setattr(
        executor._evidence_merge,
        "package_from_result",
        explode,
    )

    result = executor.execute(
        AuthorizedExecutionRequest(
            capability_id="grafana.metrics",
            runtime_binding="knowledge.dispatch",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="grafana-prod",
            arguments={"window": 60},
        )
    )

    assert result.status is ExecutionStatus.ERROR
    assert result.dispatched is True
    assert result.reason == "evidence_normalization_failure"


def test_internet_exception_after_binding_is_counted_as_dispatch() -> None:
    class ExplodingInternet:
        def collect_search_action(self, **kwargs):
            raise RuntimeError("network failed")

    result = CanonicalActionExecutor(
        _internet_knowledge(),
        external_verification=ExplodingInternet(),
    ).execute(
        AuthorizedExecutionRequest(
            capability_id="internet.current",
            runtime_binding="internet.current",
            effect=EffectClass.READ,
            target_ref=None,
            source_ref="internet-main",
            arguments={"queries": ("latest release",)},
        )
    )

    assert result.status is ExecutionStatus.ERROR
    assert result.dispatched is True
    assert result.reason == "internet_dispatch_failure"
