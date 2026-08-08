"""GA2-G09: table-driven metric -> collector mapping regression coverage."""

from __future__ import annotations

from src.pipeline.capability_router import CapabilityRouter
from src.tool.grafana_tool import GrafanaTool
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.target_registry import TargetRegistry
from src.tool.zabbix_tool import ZabbixTool


def _build_router() -> CapabilityRouter:
    registry = TargetRegistry()
    registry.add("localhost")
    registry.register_tool(
        name="zabbix",
        tool=ZabbixTool(url="http://localhost/zabbix", token="test"),
    )
    registry.register_tool(
        name="grafana",
        tool=GrafanaTool(url="http://localhost:3000", token="test"),
    )
    kt = KnowledgeTool(target_registry=registry)
    router = CapabilityRouter()
    router.build_routes(kt)
    return router


_METRIC_COLLECTOR_ROWS: tuple[tuple[str, str, str], ...] = (
    ("CPU Information", "localhost", "get_cpu"),
    ("CPU Utilization", "localhost", "get_cpu_usage"),
    ("Memory Information", "localhost", "get_memory"),
    ("Memory Utilization", "localhost", "get_memory"),
    ("Swap Information", "localhost", "get_swap"),
    ("Storage Information", "localhost", "get_block_device"),
    ("Disk Utilization", "localhost", "get_disk_usage"),
    ("Filesystem Information", "localhost", "get_filesystem_health"),
    ("Filesystem Inode Utilization", "localhost", "get_filesystem_inode"),
    ("System Uptime", "localhost", "get_uptime"),
    ("System Boot Time", "localhost", "get_boot_time"),
    ("System Load Assessment", "localhost", "get_system_load"),
    ("Process Discovery", "localhost", "get_process"),
    ("Service Status", "localhost", "get_services"),
    ("Port Discovery", "localhost", "get_listening_ports"),
    ("Container Discovery", "localhost", "get_docker"),
    ("Firewall Inspection", "localhost", "get_firewall"),
    ("SSH Configuration Inspection", "localhost", "get_ssh"),
)


def test_metric_to_collector_mapping_matrix() -> None:
    """Every requested metric must select the intended read-only collector."""
    router = _build_router()
    for operational, source, collector in _METRIC_COLLECTOR_ROWS:
        route = router.resolve(operational)
        assert route is not None, f"{operational} should resolve to a route"
        assert route == (
            source,
            collector,
        ), f"{operational} resolved to {route}; expected ({source}, {collector})"


def test_mapping_never_falls_back_to_unrelated_assessment() -> None:
    """A metric must not map to an unrelated assessment capability."""
    router = _build_router()
    assert router.resolve("CPU Information") == ("localhost", "get_cpu")
    assert router.resolve("Memory Information") == ("localhost", "get_memory")
    # Storage Information is the block-device inventory collector, while
    # Disk Utilization is the capacity collector.
    assert router.resolve("Storage Information") == ("localhost", "get_block_device")
    assert router.resolve("Disk Utilization") == ("localhost", "get_disk_usage")
