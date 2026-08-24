from __future__ import annotations

import inspect

from src.agent.authority import (
    ExactReferenceRegistry,
    ReferenceEntry,
)
from src.agent.capabilities import (
    CapabilityDefinition,
    CapabilityRegistry,
)
from src.agent.discovery import (
    CapabilityDetailStatus,
    CapabilityDiscovery,
    DiscoveryStatus,
)
from src.agent.permissions import EffectClass


def _schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "window": {
                "type": "integer",
                "minimum": 1,
            }
        },
        "required": ["window"],
    }


def _capability(
    capability_id: str,
    *,
    group: str,
    tool_id: str,
    target_kind: str | None = None,
    source_kind: str | None = None,
    allowed_target_refs: frozenset[str] | None = None,
    allowed_source_refs: frozenset[str] | None = None,
    available: bool = True,
    effect: EffectClass = EffectClass.READ,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        capability_id=capability_id,
        purpose=f"Purpose for {capability_id}",
        tool_id=tool_id,
        effect=effect,
        arguments_schema=_schema(),
        runtime_binding=f"{tool_id}.execute",
        discovery_group=group,
        target_kind=target_kind,
        source_kind=source_kind,
        allowed_target_refs=allowed_target_refs,
        allowed_source_refs=allowed_source_refs,
        available=available,
        result_kind="observation",
    )


def _discovery() -> CapabilityDiscovery:
    capabilities = CapabilityRegistry(
        (
            _capability(
                "host.cpu",
                group="host",
                tool_id="linux",
                target_kind="machine",
                allowed_target_refs=frozenset(
                    {"monitor"}
                ),
            ),
            _capability(
                "grafana.metrics",
                group="grafana",
                tool_id="grafana",
                source_kind="grafana",
                allowed_source_refs=frozenset(
                    {"grafana-prod"}
                ),
            ),
            _capability(
                "grafana.write",
                group="grafana",
                tool_id="grafana",
                source_kind="grafana",
                allowed_source_refs=frozenset(
                    {"grafana-prod"}
                ),
                available=False,
                effect=EffectClass.WRITE,
            ),
        )
    )

    targets = ExactReferenceRegistry(
        (
            ReferenceEntry("monitor", "machine"),
            ReferenceEntry("server01", "machine"),
        )
    )

    sources = ExactReferenceRegistry(
        (
            ReferenceEntry("grafana-prod", "grafana"),
            ReferenceEntry("grafana-other", "grafana"),
        )
    )

    return CapabilityDiscovery(
        capabilities,
        targets,
        sources,
    )


def test_groups_are_exact_registry_metadata() -> None:
    discovery = _discovery()

    assert discovery.groups() == (
        "grafana",
        "host",
    )


def test_group_guidance_uses_available_capability_metadata_without_ids() -> None:
    guidance = _discovery().group_guidance()

    assert guidance == (
        {
            "group": "grafana",
            "purposes": ["Purpose for grafana.metrics"],
            "result_kinds": ["observation"],
        },
        {
            "group": "host",
            "purposes": ["Purpose for host.cpu"],
            "result_kinds": ["observation"],
        },
    )
    assert all("capability_id" not in item for item in guidance)


def test_discover_is_exact_without_alias_or_fuzzy_match() -> None:
    discovery = _discovery()

    result = discovery.discover("Host")

    assert result.status is DiscoveryStatus.UNKNOWN_GROUP


def test_discover_returns_only_available_bounded_summaries() -> None:
    result = _discovery().discover("grafana")

    assert result.status is DiscoveryStatus.DISCOVERED
    assert result.group == "grafana"

    assert [
        item["capability_id"]
        for item in result.summaries
    ] == ["grafana.metrics"]

    summary = result.summaries[0]

    assert summary["effect"] == "read"
    assert "arguments_schema" not in summary
    assert "source_refs" not in summary


def test_selected_detail_comes_from_same_capability_registry() -> None:
    detail = _discovery().selected_detail(
        "grafana.metrics"
    )

    assert detail.status is CapabilityDetailStatus.DISCLOSED
    assert detail.detail is not None

    assert detail.detail["capability_id"] == "grafana.metrics"
    assert detail.detail["source_refs"] == ["grafana-prod"]
    assert detail.detail["target_refs"] == []
    assert detail.detail["arguments_schema"] == _schema()

    assert detail.selected_capability_schema == {
        "capability_id": "grafana.metrics",
        "arguments_schema": _schema(),
        "target_ref": {"applicable": False},
        "source_ref": {"applicable": True, "allowed_refs": ["grafana-prod"]},
    }


def test_selected_detail_intersects_registered_ref_scope() -> None:
    detail = _discovery().selected_detail("host.cpu")

    assert detail.detail is not None
    assert detail.detail["target_refs"] == ["monitor"]


def test_selected_unavailable_capability_is_not_disclosed() -> None:
    detail = _discovery().selected_detail(
        "grafana.write"
    )

    assert (
        detail.status
        is CapabilityDetailStatus.UNAVAILABLE_CAPABILITY
    )
    assert detail.detail is None


def test_unknown_capability_is_exact() -> None:
    detail = _discovery().selected_detail(
        "Grafana.metrics"
    )

    assert (
        detail.status
        is CapabilityDetailStatus.UNKNOWN_CAPABILITY
    )


def test_discovery_has_no_language_constraint_or_permission_input() -> None:
    discover_parameters = inspect.signature(
        CapabilityDiscovery.discover
    ).parameters
    detail_parameters = inspect.signature(
        CapabilityDiscovery.selected_detail
    ).parameters

    for parameters in (
        discover_parameters,
        detail_parameters,
    ):
        assert "hard_constraints" not in parameters
        assert "raw_request" not in parameters
        assert "semantic_plan" not in parameters
        assert "permission_mode" not in parameters
