from __future__ import annotations

from collections.abc import Mapping

from orion.contracts import ModelToolCall, RuntimeScope
from orion.integrations.infrastructure import Target, TargetCatalog
from orion.tool_runtime.infrastructure import (
    infrastructure_definitions,
    infrastructure_registrations,
)
from orion.tool_runtime.registry import ToolRegistryBuilder
from orion.tool_runtime.runner import ToolRunner


class FakeLinux:
    def __init__(self) -> None:
        self.calls = 0
        self.package = {"installed": False, "version": None}

    def inspect(
        self, target: Target, credential: object, sections: tuple[str, ...]
    ) -> Mapping[str, object]:
        self.calls += 1
        return {section: {"ok": True} for section in sections}

    def read_file(
        self, target: Target, credential: object, path: str, offset: int, length: int
    ) -> bytes:
        self.calls += 1
        return b"bounded text"

    def service_status(
        self, target: Target, credential: object, service: str
    ) -> Mapping[str, object]:
        self.calls += 1
        return {"service": service, "load_state": "loaded", "active_state": "active"}

    def package_status(
        self, target: Target, credential: object, package: str
    ) -> Mapping[str, object]:
        self.calls += 1
        return self.package

    def service_preflight(self, target: Target, credential: object, service: str) -> None:
        self.calls += 1

    def restart_service(self, target: Target, credential: object, service: str) -> None:
        self.calls += 100

    def install_package(
        self, target: Target, credential: object, package: str, version: str | None
    ) -> None:
        self.calls += 100
        self.package = {"installed": True, "version": version or "1.0"}

    def health(self, target: Target, credential: object) -> None:
        pass


class FakeGrafana:
    def dashboard_get(self, target: Target, credential: object, uid: str) -> Mapping[str, object]:
        return {"uid": uid, "url": "https://secret.example"}

    def datasource_query(
        self,
        target: Target,
        credential: object,
        uid: str,
        query: str,
        start: str,
        end: str,
        maximum: int,
    ) -> object:
        return {"series": [{"name": "cpu", "values": [1]}]}

    def alert_list(self, target: Target, credential: object) -> object:
        return [{"state": "firing", "name": "CPU"}]

    def annotation_create(
        self, target: Target, credential: object, payload: Mapping[str, object]
    ) -> str:
        return "42"

    def annotation_verify(
        self, target: Target, credential: object, annotation_id: str
    ) -> bool | None:
        return True

    def health(self, target: Target, credential: object) -> None:
        pass


class FakeZabbix:
    def __init__(self) -> None:
        self.ack_calls: list[dict[str, object]] = []
        self.acknowledged = False

    def call(
        self, target: Target, credential: object, method: str, params: Mapping[str, object]
    ) -> object:
        if method == "event.acknowledge":
            self.ack_calls.append(dict(params))
            self.acknowledged = True
            return {"eventids": params["eventids"]}
        if method == "event.get":
            return [
                {"eventid": event_id, "acknowledged": "1" if self.acknowledged else "0"}
                for event_id in params["eventids"]
            ]
        return [{"hostid": "1", "name": "host"}]

    def health(self, target: Target, credential: object) -> None:
        pass


def _catalog() -> TargetCatalog:
    return TargetCatalog.from_mapping(
        {
            "credentials": {"linux-key": "not-printed", "api": "not-printed"},
            "targets": {
                "linux": [
                    {
                        "target_ref": "node",
                        "display_name": "Node",
                        "credential_ref": "linux-key",
                        "host": "internal",
                    }
                ],
                "grafana": [
                    {
                        "target_ref": "observability",
                        "credential_ref": "api",
                        "base_url": "https://private",
                        "datasources": {"prom": "prometheus"},
                    }
                ],
                "zabbix": [
                    {
                        "target_ref": "monitoring",
                        "credential_ref": "api",
                        "base_url": "https://private",
                    }
                ],
            },
        }
    )


def _runner(linux: FakeLinux, grafana: FakeGrafana, zabbix: FakeZabbix) -> ToolRunner:
    builder = ToolRegistryBuilder()
    for registration in infrastructure_registrations(
        _catalog(), linux=linux, grafana=grafana, zabbix=zabbix
    ):
        builder.register(registration.definition, registration.handler)
    return ToolRunner(builder.freeze())


def _call(name: str, arguments: dict[str, object], call_id: str = "call") -> ModelToolCall:
    return ModelToolCall(call_id=call_id, tool_name=name, arguments=arguments)


def _scope() -> RuntimeScope:
    return RuntimeScope(session_id="session", principal_id="local", workspace_id="local")


def test_all_frozen_infrastructure_schemas_are_closed() -> None:
    names = {definition.name for definition in infrastructure_definitions()}
    assert names == {
        "linux.system.inspect",
        "linux.file.read",
        "linux.service.status",
        "linux.package.status",
        "linux.service.restart",
        "linux.package.install",
        "grafana.dashboard.get",
        "grafana.datasource.query",
        "grafana.alert.list",
        "grafana.annotation.create",
        "zabbix.host.get",
        "zabbix.event.list",
        "zabbix.history.get",
        "zabbix.trigger.get",
        "zabbix.template.get",
        "zabbix.event.acknowledge",
    }
    assert all(
        definition.input_schema["additionalProperties"] is False
        for definition in infrastructure_definitions()
    )


def test_unknown_target_is_rejected_before_credentials_or_executor() -> None:
    linux, grafana, zabbix = FakeLinux(), FakeGrafana(), FakeZabbix()
    result = _runner(linux, grafana, zabbix).run(
        _call("linux.system.inspect", {"target_ref": "forged"}), _scope()
    )
    assert result.error is not None and result.error.code == "unknown_target"
    assert linux.calls == 0


def test_successful_read_per_family_is_sanitized_and_source_bearing() -> None:
    linux, grafana, zabbix = FakeLinux(), FakeGrafana(), FakeZabbix()
    runner = _runner(linux, grafana, zabbix)
    results = [
        runner.run(
            _call("linux.file.read", {"target_ref": "node", "path": "/etc/hosts"}), _scope()
        ),
        runner.run(
            _call(
                "grafana.dashboard.get", {"target_ref": "observability", "dashboard_uid": "home"}
            ),
            _scope(),
        ),
        runner.run(_call("zabbix.host.get", {"target_ref": "monitoring"}), _scope()),
    ]
    assert all(result.status == "success" and result.sources for result in results)
    assert {result.sources[0].source_kind for result in results} == {"linux", "grafana", "zabbix"}
    assert "private" not in str(results) and "not-printed" not in str(results)


def test_cancellation_between_preflight_and_dispatch_issues_no_restart() -> None:
    linux, grafana, zabbix = FakeLinux(), FakeGrafana(), FakeZabbix()
    cancelled = False

    def cancel_after_preflight() -> bool:
        return cancelled or linux.calls >= 1

    result = _runner(linux, grafana, zabbix).run(
        _call("linux.service.restart", {"target_ref": "node", "service": "nginx"}),
        _scope(),
        cancel_after_preflight,
    )
    assert result.error is not None and result.error.code == "cancelled"
    assert linux.calls == 1


def test_package_convergence_and_zabbix_acknowledgement_dispatch_once() -> None:
    linux, grafana, zabbix = FakeLinux(), FakeGrafana(), FakeZabbix()
    runner = _runner(linux, grafana, zabbix)
    install = runner.run(
        _call("linux.package.install", {"target_ref": "node", "package": "curl"}), _scope()
    )
    ack = runner.run(
        _call("zabbix.event.acknowledge", {"target_ref": "monitoring", "event_ids": ["1", "2"]}),
        _scope(),
    )
    assert install.status == "success" and install.data["changed"] is True
    assert ack.status == "success" and ack.data["changed"] is True
    assert len(zabbix.ack_calls) == 1
    assert zabbix.ack_calls[0]["eventids"] == ["1", "2"]
