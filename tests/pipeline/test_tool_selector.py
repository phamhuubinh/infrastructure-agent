from __future__ import annotations

from src.pipeline.tool_selector import ToolCategory, ToolSelector


def test_select_linux_by_concept_cpu() -> None:
    s = ToolSelector()
    assert s.select("cho tôi xem CPU", "cpu") == ToolCategory.LINUX


def test_select_zabbix_by_concept_alerts() -> None:
    s = ToolSelector()
    assert s.select("alerts status", "alerts") == ToolCategory.ZABBIX


def test_select_grafana_by_concept_dashboards() -> None:
    s = ToolSelector()
    assert s.select("show dashboards", "dashboards") == ToolCategory.GRAFANA


def test_select_grafana_by_directive() -> None:
    s = ToolSelector()
    assert s.select("CPU sử dụng grafana", "cpu") == ToolCategory.GRAFANA


def test_select_zabbix_by_directive() -> None:
    s = ToolSelector()
    assert s.select("memory dùng zabbix", "memory") == ToolCategory.ZABBIX


def test_select_knowledge_base_by_directive() -> None:
    s = ToolSelector()
    assert (
        s.select("tìm kiếm kubernetes architecture", "kubernetes")
        == ToolCategory.KNOWLEDGE_BASE
    )


def test_select_internet_by_directive() -> None:
    s = ToolSelector()
    assert (
        s.select("search online for nginx config", "unknown") == ToolCategory.INTERNET
    )


def test_select_default_to_linux() -> None:
    s = ToolSelector()
    assert s.select("random unknown concept", "unknown") == ToolCategory.LINUX


def test_select_hostname_is_linux() -> None:
    s = ToolSelector()
    assert s.select("hostname?", "hostname") == ToolCategory.LINUX


def test_select_uptime_is_linux() -> None:
    s = ToolSelector()
    assert s.select("uptime máy", "uptime") == ToolCategory.LINUX
