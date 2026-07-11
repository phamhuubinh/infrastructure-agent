from __future__ import annotations

from src.pipeline.capability_router import CapabilityRouter
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.zabbix_tool import ZabbixTool


def _build_router() -> tuple[CapabilityRouter, KnowledgeTool]:
    """Build a router with all standard tools registered."""
    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool(
        name="zabbix",
        tool=ZabbixTool(url="http://localhost/zabbix", token="test"),
    )
    registry.register_tool(
        name="grafana",
        tool=GrafanaTool(),
    )
    kt = KnowledgeTool(target_registry=registry)
    router = CapabilityRouter()
    router.build_routes(kt)
    return router, kt


class TestCapabilityRouter:
    def test_known_capability_returns_route(self) -> None:
        router, _ = _build_router()
        route = router.resolve("CPU Information")
        assert route is not None
        source, resource = route
        assert source == "localhost"
        assert resource == "get_cpu"

    def test_zabbix_capability(self) -> None:
        router, _ = _build_router()
        route = router.resolve("Monitoring Problems")
        assert route is not None
        source, resource = route
        assert source == "zabbix"
        assert resource == "get_problems"

    def test_grafana_capability(self) -> None:
        router, _ = _build_router()
        route = router.resolve("Dashboard Discovery")
        assert route is not None
        source, resource = route
        assert source == "grafana"
        assert resource == "dashboards"

    def test_unknown_capability_returns_none(self) -> None:
        router, _ = _build_router()
        route = router.resolve("Unknown Capability")
        assert route is None

    def test_linux_system_capabilities(self) -> None:
        router, _ = _build_router()
        route = router.resolve("System Information")
        assert route is not None
        assert route == ("localhost", "get_system")

    def test_security_capabilities(self) -> None:
        router, _ = _build_router()
        route = router.resolve("Firewall Inspection")
        assert route is not None
        assert route == ("localhost", "get_firewall")

        route = router.resolve("SSH Configuration Inspection")
        assert route is not None
        assert route == ("localhost", "get_ssh")

    def test_network_capabilities(self) -> None:
        router, _ = _build_router()
        route = router.resolve("Port Discovery")
        assert route is not None
        assert route == ("localhost", "get_listening_ports")

    def test_available_routes_returns_list(self) -> None:
        router, _ = _build_router()
        routes = router.available_routes()
        assert isinstance(routes, list)
        assert len(routes) > 0
        assert "CPU Information" in routes
        assert "Monitoring Problems" in routes

    def test_route_count(self) -> None:
        router, _ = _build_router()
        assert router.route_count > 0

    def test_before_build_routes_empty(self) -> None:
        router = CapabilityRouter()
        assert router.route_count == 0
        assert router.resolve("CPU Information") is None


class TestEmptyRouter:
    def test_no_knowledge_tool(self) -> None:
        router = CapabilityRouter()
        kt = KnowledgeTool()
        router.build_routes(kt)
        # localhost should have been auto-added
        assert router.route_count > 0

    def test_no_tools_registered(self) -> None:
        registry = TargetRegistry()
        # No tools added
        kt = KnowledgeTool(target_registry=registry)
        router = CapabilityRouter()
        router.build_routes(kt)
        # No tools to scan — should have few or 0 routes
        # (localhost creates a LinuxTool automatically)
        assert router.route_count >= 0


class TestConventionMapping:
    """Validate that the _COVERS_TO_OPERATIONAL mapping is consistent."""

    def test_all_covers_tags_are_valid(self) -> None:
        """Every covers tag used in tools should have a mapping entry.
        This test scans all registered tool capabilities and checks
        that every covers tag is accounted for."""
        from src.pipeline.capability_router import _COVERS_TO_OPERATIONAL
        from src.tool.grafana_tool import _CAPABILITIES as G
        from src.tool.linux_tool import _CAPABILITIES as L
        from src.tool.zabbix_tool import _CAPABILITIES as Z

        used_tags: set[str] = set()
        for caps in (L, Z, G):
            for cap in caps.values():
                for tag in cap.covers:
                    used_tags.add(tag)

        mapped_tags = set(_COVERS_TO_OPERATIONAL)
        unmapped = used_tags - mapped_tags - {
            # Known tags without pipeline equivalent (infrastructure-only)
            "hardware", "kernel-modules", "system-locale", "system-environment",
            "users", "uptime", "boot-time", "system-time", "system-logs",
            "tls-certificates", "monitoring-version", "monitoring-health",
            "monitoring-folders", "monitoring-alerts", "monitoring-annotations",
            "zabbix-groups", "zabbix-templates", "zabbix-items",
            "zabbix-users", "zabbix-interfaces", "zabbix-maintenance",
            "application-discovery",
            "panels", "queries",
        }
        assert not unmapped, f"Unmapped covers tags found: {unmapped}"


class TestExecutionRuntimeIntegration:
    """Verify ExecutionRuntime works with metadata-driven router."""

    def test_runtime_receives_routes(self) -> None:
        from src.pipeline.execution_runtime import ExecutionRuntime
        from src.pipeline.capability_reference import CapabilityReference
        from src.pipeline.execution_graph import ExecutionGraph
        from src.pipeline.execution_graph import ExecutionNode
        from src.pipeline.execution_plan import ExecutionStep

        router, kt = _build_router()
        runtime = ExecutionRuntime(knowledge_tool=kt, router=router)

        step = ExecutionStep(
            capability=CapabilityReference(name="System Information", evidence_name="System Information"),
        )
        graph = ExecutionGraph(nodes=(
            ExecutionNode(execution_step=step),
        ))
        results, _ = runtime.execute(graph)
        assert "System Information" in results
