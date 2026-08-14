from __future__ import annotations

from src.pipeline.request_semantics import SourceConstraint
from src.pipeline.semantic_plan import SemanticPlan
from src.pipeline.semantic_plan_validation import (
    SemanticPlanValidationReason,
    SemanticPlanValidationStatus,
)
from src.pipeline.source_constraints import validate_semantic_sources
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.zabbix_tool import ZabbixTool


def _tool() -> KnowledgeTool:
    registry = TargetRegistry()
    registry.add("localhost")
    registry.add("remote", SSHExecutionBackend("example.invalid"))
    registry.register_tool("grafana", GrafanaTool("http://grafana", "token"))
    registry.register_tool("zabbix", ZabbixTool("http://zabbix", "token"))
    return KnowledgeTool(registry)


def test_source_only_constraints_produce_exact_allow_sets() -> None:
    tool = _tool()
    grafana = validate_semantic_sources(
        tool,
        SemanticPlan(source_constraints=(SourceConstraint.GRAFANA,)),
        target="localhost",
    )
    ssh = validate_semantic_sources(
        tool,
        SemanticPlan(source_constraints=(SourceConstraint.SSH,)),
        target="remote",
    )

    assert grafana.allowed_sources == frozenset({"grafana"})
    assert ssh.allowed_sources == frozenset({"remote"})
    assert "localhost" not in grafana.allowed_sources
    assert "zabbix" not in ssh.allowed_sources


def test_excluded_sources_cannot_be_selected() -> None:
    result = validate_semantic_sources(
        _tool(),
        SemanticPlan(
            source_constraints=(SourceConstraint.ANY,),
            excluded_sources=(SourceConstraint.GRAFANA, SourceConstraint.ZABBIX),
        ),
        target="localhost",
    )

    assert result.allowed_sources == frozenset({"localhost", "remote"})
    assert result.excluded_sources == frozenset({"grafana", "zabbix"})
    provenance = result.validate_provenance(frozenset({"grafana"}))
    assert provenance.reason is SemanticPlanValidationReason.SOURCE_FORBIDDEN


def test_missing_or_conflicting_source_is_structured_and_never_falls_back() -> None:
    unavailable = validate_semantic_sources(
        _tool(),
        SemanticPlan(source_constraints=(SourceConstraint.INTERNET,)),
        target="localhost",
    )
    conflict = validate_semantic_sources(
        _tool(),
        SemanticPlan(
            source_constraints=(SourceConstraint.GRAFANA,),
            excluded_sources=(SourceConstraint.GRAFANA,),
        ),
        target="localhost",
    )

    assert unavailable.validation.status is SemanticPlanValidationStatus.UNAVAILABLE
    assert (
        unavailable.validation.reason is SemanticPlanValidationReason.SOURCE_UNAVAILABLE
    )
    assert unavailable.allowed_sources is None
    assert conflict.validation.status is SemanticPlanValidationStatus.REJECT
    assert conflict.validation.reason is SemanticPlanValidationReason.SOURCE_CONFLICT


def test_url_only_requires_an_explicit_url_instead_of_substituting_search() -> None:
    result = validate_semantic_sources(
        _tool(),
        SemanticPlan(source_constraints=(SourceConstraint.URL_ONLY,)),
        target=None,
    )

    assert result.validation.status is SemanticPlanValidationStatus.CLARIFY
    assert result.validation.reason is SemanticPlanValidationReason.PARAMETER_MISSING
    assert result.allowed_sources is None
