from __future__ import annotations

import json

import pytest

from src.tool.zabbix_tool import ZabbixTool


class _MockZabbix:
    """
    Mock the Zabbix API at the HTTP layer.

    Verifies the auth field is present in every request,
    inspects the JSON-RPC method, and returns configured results.
    """

    def __init__(self, result: object = None) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []
        self.last_auth: str | None = None

    def handle(self, body: bytes) -> bytes:
        req: dict[str, object] = json.loads(body.decode("utf-8"))
        self.calls.append(req)
        self.last_auth = req.get("auth")

        method: str = req.get("method", "")

        if method == "apiinfo.version":
            return json.dumps(
                {"jsonrpc": "2.0", "result": self._result or "1.0.0"}
            ).encode("utf-8")

        return json.dumps({"jsonrpc": "2.0", "result": self._result}).encode("utf-8")


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
def mock_zabbix(monkeypatch) -> _MockZabbix:
    mock = _MockZabbix()
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, **kw: _MockResponse(mock.handle(req.data)),
    )
    return mock


def test_sends_auth_token_in_every_request(mock_zabbix) -> None:
    mock_zabbix._result = []
    tool = ZabbixTool(token="my-token")
    tool.execute({"action": "get_hosts"})

    assert mock_zabbix.last_auth == "my-token"


def test_execute_returns_api_version(mock_zabbix) -> None:
    mock_zabbix._result = "7.0.0"
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_api_version"})
    assert result.success is True
    assert result.data == {"version": "7.0.0"}


def test_execute_returns_hosts(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"hostid": "1", "host": "server01", "name": "Server 01", "status": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_hosts"})
    assert result.success is True
    assert result.data["total_hosts"] == 1
    assert result.data["enabled_hosts"] == 1
    assert result.data["disabled_hosts"] == 0
    assert result.data["hosts"] == [
        {
            "hostid": "1",
            "host": "server01",
            "name": "Server 01",
            "status": "0",
            "groups": "",
            "ip": "",
        }
    ]


def test_execute_returns_host_groups(mock_zabbix) -> None:
    mock_zabbix._result = [{"groupid": "1", "name": "Linux servers"}]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_host_groups"})
    assert result.success is True
    assert result.data["groups"] == [{"groupid": "1", "name": "Linux servers"}]


def test_search_hosts_uses_server_side_search(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"hostid": "10644", "host": "Switch T3_Cisco Core", "name": "Switch T3_Cisco Core", "status": "0"},
        {"hostid": "10649", "host": "Switch T3_Technical", "name": "Switch T3_Technical", "status": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "search_hosts", "query": "Switch T3"})

    assert result.success is True
    assert len(result.data["hosts"]) == 2

    call = mock_zabbix.calls[0]
    assert call["method"] == "host.get"
    assert call["params"]["search"] == {"name": "Switch T3", "host": "Switch T3"}
    assert call["params"]["searchWildcardsEnabled"] is True


def test_search_hosts_returns_empty_when_no_match(mock_zabbix) -> None:
    mock_zabbix._result = []
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "search_hosts", "query": "NonExistent"})

    assert result.success is True
    assert result.data == {"hosts": []}


def test_search_hosts_handles_ip_query(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"hostid": "10643", "host": "Firewall_Pfsense", "name": "Firewall_Pfsense", "status": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "search_hosts", "query": "192.168.10.248"})

    assert result.success is True
    assert result.data["hosts"][0]["hostid"] == "10643"


def test_execute_returns_templates(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"templateid": "1", "host": "Template OS Linux", "name": "Template OS Linux"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_templates"})
    assert result.success is True
    assert result.data["templates"] == [
        {"templateid": "1", "host": "Template OS Linux", "name": "Template OS Linux"},
    ]


def test_execute_returns_items(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"itemid": "1", "name": "CPU utilization", "key_": "system.cpu.util", "lastvalue": "15", "units": "%"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_items"})
    assert result.success is True
    assert result.data["total_items"] == 1
    assert result.data["items"] == [
        {"itemid": "1", "name": "CPU utilization", "key_": "system.cpu.util", "lastvalue": "15", "units": "%"},
    ]


def test_get_items_filters_by_host_id(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"itemid": "10", "name": "Uptime", "key_": "system.uptime", "lastvalue": "3600", "units": "s"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_items", "hostid": "10644"})
    assert result.success is True
    assert mock_zabbix.calls[0]["params"].get("hostids") == "10644"


def test_execute_returns_triggers(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"triggerid": "1", "description": "High CPU", "priority": "4", "status": "0", "value": "1", "hosts": []},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_triggers"})
    assert result.success is True
    assert len(result.data["triggers"]) == 1
    t = result.data["triggers"][0]
    assert t["triggerid"] == "1"
    assert t["priority"] == "4"
    assert t["severity"] in ("high", "average")


def test_execute_returns_events(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"eventid": "1", "name": "CPU overload", "clock": "1700000000", "severity": "3", "value": "1"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_events"})
    assert result.success is True
    assert result.data["total_events"] == 1
    assert result.data["events"][0]["eventid"] == "1"
    assert result.data["events"][0]["severity_label"] == "average"


def test_execute_returns_problems(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"eventid": "1", "name": "Disk full", "clock": "1700000000", "severity": "3"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_problems"})
    assert result.success is True
    assert result.data["total_problems"] == 1
    assert result.data["problems"][0]["eventid"] == "1"
    assert result.data["problems"][0]["severity_label"] == "average"


def test_execute_returns_users(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"userid": "1", "alias": "Admin", "name": "Admin", "surname": "User", "roleid": "3"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_users"})
    assert result.success is True
    assert result.data["users"] == [
        {"userid": "1", "alias": "Admin", "name": "Admin", "surname": "User", "roleid": "3"},
    ]


def test_get_host_with_host_name_filter(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"hostid": "2", "host": "web01", "name": "Web Server 01", "status": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_host", "host": "web01"})

    assert result.success is True
    assert result.data["hosts"] == [
        {"hostid": "2", "host": "web01", "name": "Web Server 01", "status": "0", "groups": "", "ip": ""},
    ]

    call = mock_zabbix.calls[0]
    assert call["method"] == "host.get"
    assert call["params"]["filter"] == {"host": "web01"}


def test_handle_auth_error(mock_zabbix) -> None:
    mock_zabbix.handle = lambda body: json.dumps(
        {"jsonrpc": "2.0", "error": {"message": "Not authorised", "data": "invalid token"}}
    ).encode("utf-8")

    tool = ZabbixTool(token="bad-token")
    result = tool.execute({"action": "get_hosts"})
    assert result.success is False
    assert "Not authorised" in result.error


def test_handle_connection_error(monkeypatch) -> None:
    def fake_urlopen(req, **kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_hosts"})
    assert result.success is False
    assert "Connection refused" in result.error or "Zabbix" in result.error


def test_reports_unknown_action() -> None:
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "does_not_exist"})
    assert result.success is False
    assert "Unknown action" in result.error
    assert "get_api_version" in result.error


def test_raises_on_missing_action() -> None:
    tool = ZabbixTool(token="test-token")
    result = tool.execute({})
    assert result.success is False
    assert "Missing action" in result.error


def test_returns_empty_list_for_empty_result(mock_zabbix) -> None:
    mock_zabbix._result = []
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_hosts"})
    assert result.success is True
    assert result.data.get("hosts") == []
    assert result.data.get("total_hosts") == 0


def test_get_problem_timeline_returns_problems_sorted(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"eventid": "3", "name": "P3", "clock": "1700000000", "severity": "3", "acknowledged": "0"},
        {"eventid": "2", "name": "P2", "clock": "1600000000", "severity": "2", "acknowledged": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_problem_timeline", "limit": "50"})

    assert result.success is True
    assert result.data["total"] == 2


def test_get_host_inventory_returns_hosts(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"hostid": "1", "host": "s1", "name": "Server 1", "status": "0"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_host_inventory"})

    assert result.success is True
    assert result.data["total_hosts"] == 1


def test_get_host_interfaces_returns_interfaces(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"interfaceid": "1", "ip": "10.0.0.1", "port": "161", "type": "2"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_host_interfaces", "hostid": "10644"})

    assert result.success is True
    assert result.data["total_interfaces"] == 1


def test_get_maintenance_status_returns_maintenances(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"maintenanceid": "1", "name": "Scheduled", "active_since": "1700000000", "active_till": "1700100000"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_maintenance_status"})

    assert result.success is True
    assert result.data["total_maintenances"] == 1


def test_get_event_summary_returns_events(mock_zabbix) -> None:
    mock_zabbix._result = [
        {"eventid": "1", "name": "CPU overload", "clock": "1700000000", "severity": "4", "value": "1"},
    ]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_event_summary", "limit": "100"})

    assert result.success is True
    assert result.data["total"] == 1
    assert "severity_summary" in result.data


def test_passes_extra_arguments_to_handler(mock_zabbix) -> None:
    mock_zabbix._result = [{"hostid": "3", "host": "db01"}]
    tool = ZabbixTool(token="test-token")
    result = tool.execute({"action": "get_host", "host": "db01"})
    assert result.success is True
    assert result.data["hosts"][0]["host"] == "db01"
