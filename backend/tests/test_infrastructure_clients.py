from __future__ import annotations

import json

import httpx
import pytest

from orion.contracts import ModelToolCall, RuntimeScope
from orion.integrations.infrastructure import (
    HttpGrafanaClient,
    HttpZabbixClient,
    Target,
    TargetCatalog,
)
from orion.tool_runtime.infrastructure import infrastructure_registrations
from orion.tool_runtime.registry import ToolRegistryBuilder
from orion.tool_runtime.runner import ToolRunner


def _zabbix_target() -> Target:
    return Target(
        family="zabbix",
        target_ref="zabbix",
        display_name="Zabbix",
        connection={"base_url": "https://private.example/api_jsonrpc.php"},
        credential_ref="zabbix-token",
        datasource_types={},
    )


def test_zabbix_health_uses_unauthenticated_version_then_authenticated_probe() -> None:
    payloads: list[dict[str, object]] = []

    def responder(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        payloads.append(payload)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "7.0"})

    HttpZabbixClient(httpx.MockTransport(responder)).health(_zabbix_target(), "secret-token")

    assert payloads[0]["method"] == "apiinfo.version"
    assert "auth" not in payloads[0]
    assert payloads[1]["method"] == "host.get"
    assert payloads[1]["auth"] == "secret-token"


def test_credentials_adapter_normalizes_zabbix_rpc_endpoint_and_keeps_it_private(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "tool-credentials.json"
    path.write_text(
        json.dumps({"zabbix": {"url": "http://example.test/zabbix", "token": "FAKE_SECRET"}})
    )
    monkeypatch.delenv("ORION_INFRASTRUCTURE_CONFIG", raising=False)
    monkeypatch.setenv("ORION_TOOL_CREDENTIALS_PATH", str(path))
    catalog = TargetCatalog.from_environment()
    target = catalog.resolve("zabbix", "zabbix")
    paths: list[str] = []

    def responder(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "7.0"})

    HttpZabbixClient(httpx.MockTransport(responder)).health(
        target, catalog.credentials.resolve(target.credential_ref)
    )

    assert target.connection["base_url"] == "http://example.test/zabbix/api_jsonrpc.php"
    assert paths == ["/zabbix/api_jsonrpc.php", "/zabbix/api_jsonrpc.php"]
    assert "FAKE_SECRET" not in str(catalog.model_context())
    assert "example.test" not in str(catalog.model_context())


def _grafana_runner(
    client: HttpGrafanaClient, datasource_types: dict[str, str] | None = None
) -> ToolRunner:
    catalog = TargetCatalog.from_mapping(
        {
            "credentials": {"api": "FAKE_SECRET"},
            "targets": {
                "grafana": [
                    {
                        "target_ref": "grafana",
                        "credential_ref": "api",
                        "base_url": "http://private.example",
                        "datasources": datasource_types or {},
                    }
                ]
            },
        }
    )
    builder = ToolRegistryBuilder()
    for registration in infrastructure_registrations(catalog, grafana=client):
        builder.register(registration.definition, registration.handler)
    return ToolRunner(builder.freeze())


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["prometheus", "loki"])
async def test_grafana_discovers_supported_datasource_before_semantic_query(kind: str) -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.startswith("/api/datasources/"):
            return httpx.Response(
                200, json={"type": kind, "url": "http://secret", "password": "FAKE_SECRET"}
            )
        return httpx.Response(200, json={"results": {"A": {}}})

    result = await _grafana_runner(HttpGrafanaClient(httpx.MockTransport(responder))).run_async(
        ModelToolCall(
            call_id="query",
            tool_name="grafana.datasource.query",
            arguments={
                "target_ref": "grafana",
                "datasource_uid": "prom",
                "query": "up",
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-01-01T01:00:00Z",
            },
        ),
        RuntimeScope(session_id="s", principal_id="local", workspace_id="local"),
    )

    assert result.status == "success"
    assert [request.url.path for request in requests] == [
        "/api/datasources/uid/prom",
        "/api/ds/query",
    ]
    assert "FAKE_SECRET" not in str(result)
    assert "http://secret" not in str(result)


@pytest.mark.anyio
async def test_grafana_rejects_unsupported_or_missing_datasource_before_query() -> None:
    requests: list[httpx.Request] = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            404 if request.url.path.endswith("missing") else 200, json={"type": "mysql"}
        )

    runner = _grafana_runner(HttpGrafanaClient(httpx.MockTransport(responder)))
    scope = RuntimeScope(session_id="s", principal_id="local", workspace_id="local")
    unsupported = await runner.run_async(
        ModelToolCall(
            call_id="bad",
            tool_name="grafana.datasource.query",
            arguments={
                "target_ref": "grafana",
                "datasource_uid": "mysql",
                "query": "x",
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-01-01T01:00:00Z",
            },
        ),
        scope,
    )
    missing = await runner.run_async(
        ModelToolCall(
            call_id="missing",
            tool_name="grafana.datasource.query",
            arguments={
                "target_ref": "grafana",
                "datasource_uid": "missing",
                "query": "x",
                "from": "2026-01-01T00:00:00Z",
                "to": "2026-01-01T01:00:00Z",
            },
        ),
        scope,
    )
    assert unsupported.error is not None and unsupported.error.code == "invalid_input"
    assert missing.error is not None and missing.error.code == "not_found"
    assert all(request.url.path != "/api/ds/query" for request in requests)
