from __future__ import annotations

import json
from urllib import request

import pytest

from src.tool.grafana_tool import GrafanaTool


class _MockGrafana:
    """
    Mock the Grafana REST API at the HTTP layer.

    Verifies the Bearer token is present in every request,
    inspects the URL path, and returns configured results.
    """

    def __init__(self, result: object = None) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []
        self.last_auth: str | None = None

    def handle(self, req: request.Request) -> bytes:
        self.calls.append({"url": req.full_url, "method": req.method})
        auth = req.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            self.last_auth = auth[len("Bearer ") :]
        return json.dumps(self._result).encode("utf-8")


class _MockResponse:
    def __init__(self, data: bytes) -> None:
        self.data = data

    def read(self) -> bytes:
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@pytest.fixture
def mock_grafana(monkeypatch) -> _MockGrafana:
    mock = _MockGrafana()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, **kw: _MockResponse(mock.handle(req)),
    )
    return mock


def test_uses_default_url_and_token() -> None:
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    assert tool._url == "http://localhost:3000"
    assert tool._token == "test-token"


def test_sends_bearer_token_in_every_request(mock_grafana) -> None:
    mock_grafana._result = {"database": "ok"}
    tool = GrafanaTool(url="http://localhost:3000", token="my-token")
    tool.execute({"action": "health"})
    assert mock_grafana.last_auth == "my-token"


def test_execute_returns_health(mock_grafana) -> None:
    mock_grafana._result = {"database": "ok", "version": "11.0.0"}
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "health"})
    assert result.success is True
    data = result.data
    assert isinstance(data, dict)
    health = data.get("health", {})
    assert isinstance(health, dict)
    assert health.get("database") == "ok"


def test_execute_returns_version(mock_grafana) -> None:
    mock_grafana._result = {"version": "11.0.0"}
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "version"})
    assert result.success is True
    assert result.data == {"version": "11.0.0"}


def test_execute_returns_dashboards(mock_grafana) -> None:
    mock_grafana._result = [
        {
            "title": "Server Dashboard",
            "uid": "abc123",
            "folderTitle": "Servers",
            "tags": ["production"],
            "url": "/d/abc123",
        },
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboards"})
    assert result.success is True
    assert result.data["total"] == 1
    assert result.data["dashboards"] == [
        {
            "title": "Server Dashboard",
            "uid": "abc123",
            "folder": "Servers",
            "tags": ["production"],
            "url": "/d/abc123",
        },
    ]


def test_dashboard_search_passes_query(mock_grafana) -> None:
    mock_grafana._result = []
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_search", "query": "CPU"})
    assert result.success is True
    assert result.data == {"dashboards": [], "total": 0}


def test_dashboard_summary_returns_aggregated_counts(mock_grafana) -> None:
    mock_grafana._result = [
        {"title": "A", "uid": "1", "tags": ["prod"]},
        {"title": "B", "uid": "2", "tags": ["prod", "critical"]},
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_summary"})
    assert result.success is True
    assert result.data["total"] == 2
    assert result.data["total_tags"] == 2
    assert "prod" in result.data["tag_list"]
    assert "critical" in result.data["tag_list"]


def test_dashboard_summary_handles_empty(mock_grafana) -> None:
    mock_grafana._result = []
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_summary"})
    assert result.success is True
    assert result.data["total"] == 0


def test_execute_returns_folders(mock_grafana) -> None:
    mock_grafana._result = [
        {"uid": "f1", "title": "Servers", "url": "/dashboards/f/Servers"},
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "folders"})
    assert result.success is True
    assert result.data["total"] == 1
    assert result.data["folders"][0]["title"] == "Servers"


def test_execute_returns_datasources(mock_grafana) -> None:
    mock_grafana._result = [
        {
            "name": "Prometheus",
            "type": "prometheus",
            "url": "http://prom:9090",
            "isDefault": True,
        },
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "datasources"})
    assert result.success is True
    assert result.data["total"] == 1
    assert result.data["datasources"][0]["name"] == "Prometheus"
    assert result.data["datasources"][0]["is_default"] is True


def test_dashboard_details_requires_uid(mock_grafana) -> None:
    mock_grafana._result = {}
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_details"})
    assert result.success is True
    assert "Missing uid" in str(result.data)


def test_dashboard_details_returns_panels(mock_grafana) -> None:
    mock_grafana._result = {
        "dashboard": {
            "title": "Server Overview",
            "panels": [
                {
                    "id": 1,
                    "title": "CPU",
                    "type": "timeseries",
                    "datasource": {"type": "prometheus"},
                    "targets": [{}],
                },
                {
                    "id": 2,
                    "title": "Memory",
                    "type": "stat",
                    "datasource": {"type": "prometheus"},
                    "targets": [{}, {}],
                },
                {
                    "id": 3,
                    "title": "Zabbix Status",
                    "type": "table",
                    "datasource": {"type": "zabbix-datasource"},
                    "targets": [{}],
                    "description": "Zabbix health",
                },
            ],
        },
    }
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_details", "uid": "abc123"})
    assert result.success is True
    assert result.data["uid"] == "abc123"
    assert result.data["title"] == "Server Overview"
    assert result.data["total_panels"] == 3
    assert result.data["panels"][0]["id"] == 1
    assert result.data["panels"][0]["title"] == "CPU"
    assert result.data["panels"][0]["type"] == "timeseries"
    assert result.data["panels"][0]["metric_count"] == 0
    assert result.data["panels"][1]["metric_count"] == 0
    assert result.data["panels"][2]["description"] == "Zabbix health"
    assert result.data["panel_type_summary"] == {"timeseries": 1, "stat": 1, "table": 1}


def test_dashboard_details_handles_missing_dashboard(mock_grafana) -> None:
    mock_grafana._result = {"dashboard": None}
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboard_details", "uid": "missing"})
    assert result.success is True
    assert "Dashboard payload missing" in str(result.data)


def test_dashboard_details_calls_dashboard_api(mock_grafana) -> None:
    mock_grafana._result = {"dashboard": {"title": "T", "panels": []}}
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    tool.execute({"action": "dashboard_details", "uid": "my-uid"})
    assert any("api/dashboards/uid/my-uid" in c["url"] for c in mock_grafana.calls)


def test_execute_returns_alert_rules(mock_grafana) -> None:
    mock_grafana._result = [
        {"uid": "r1", "title": "CPU > 90%", "folderUID": "f1", "intervalSeconds": 60},
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "alert_rules"})
    assert result.success is True
    assert result.data["total"] == 1
    assert result.data["alert_rules"][0]["title"] == "CPU > 90%"


def test_execute_returns_annotations(mock_grafana) -> None:
    mock_grafana._result = [
        {
            "id": 1,
            "text": "Deployed v2.0",
            "dashboardUID": "abc",
            "created": 1700000000,
            "updated": 1700000000,
        },
    ]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "annotations"})
    assert result.success is True
    assert result.data["total"] == 1
    assert result.data["annotations"][0]["text"] == "Deployed v2.0"


def test_reports_unknown_action() -> None:
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "does_not_exist"})
    assert result.success is False
    assert "Unknown action" in result.error
    assert "health" in result.error


def test_raises_on_missing_action() -> None:
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({})
    assert result.success is False
    assert "Missing action" in result.error


def test_handle_connection_error(monkeypatch) -> None:
    def fake_urlopen(req, **kwargs):
        msg = "Connection refused"
        raise OSError(msg)

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "health"})
    assert result.success is False


def test_returns_empty_list_for_empty_result(mock_grafana) -> None:
    mock_grafana._result = []
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "dashboards"})
    assert result.success is True
    assert result.data.get("dashboards") == []
    assert result.data.get("total") == 0


def test_passes_extra_arguments_to_handler(mock_grafana) -> None:
    mock_grafana._result = [{"id": 1, "text": "note"}]
    tool = GrafanaTool(url="http://localhost:3000", token="test-token")
    result = tool.execute({"action": "annotations", "limit": 100})
    assert result.success is True
    assert mock_grafana.calls[0]["url"].endswith("limit=100")
