from __future__ import annotations

import json

import httpx
import pytest

from orion.integrations.infrastructure import (
    HttpZabbixClient,
    InfrastructureIntegrations,
    Target,
    TargetCatalog,
)


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


@pytest.mark.parametrize("failure", ["bad_credential", "timeout"])
def test_zabbix_health_is_unhealthy_and_redacts_credentials(failure: str) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-token", request=request)
        if payload["method"] == "host.get":
            return httpx.Response(
                200, json={"jsonrpc": "2.0", "id": 1, "error": {"data": "secret-token"}}
            )
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": "7.0"})

    catalog = TargetCatalog((_zabbix_target(),), {"zabbix-token": "secret-token"})
    integration = InfrastructureIntegrations(
        catalog, zabbix=HttpZabbixClient(httpx.MockTransport(responder))
    )

    result = integration.status("zabbix")

    assert result.status == "unhealthy"
    assert "secret-token" not in str(result)
