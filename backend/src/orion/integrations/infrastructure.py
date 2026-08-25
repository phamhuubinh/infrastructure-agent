"""Server-side infrastructure target configuration and narrow transport clients.

Nothing in this module is model-facing: target connection material and credentials
are resolved only after a semantic tool has passed registry validation.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx


class InfrastructureError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code, self.message, self.retryable = code, message, retryable


@dataclass(frozen=True)
class Target:
    family: str
    target_ref: str
    display_name: str
    connection: Mapping[str, object]
    credential_ref: str | None
    datasource_types: Mapping[str, str]


@dataclass(frozen=True)
class IntegrationStatus:
    status: str
    message: str | None = None


class CredentialResolver:
    """Small local configuration boundary; values never leave integration code."""

    def __init__(self, credentials: Mapping[str, object]) -> None:
        self._credentials = credentials

    def resolve(self, reference: str | None) -> object:
        if not reference or reference not in self._credentials:
            raise InfrastructureError(
                "credential_unavailable", "Configured credentials are unavailable."
            )
        value = self._credentials[reference]
        if value is None or value == "":
            raise InfrastructureError(
                "credential_unavailable", "Configured credentials are unavailable."
            )
        return value


class TargetCatalog:
    def __init__(
        self, targets: tuple[Target, ...] = (), credentials: Mapping[str, object] | None = None
    ) -> None:
        self._targets = targets
        self.credentials = CredentialResolver(credentials or {})

    @classmethod
    def from_environment(cls) -> TargetCatalog:
        path = os.getenv("ORION_INFRASTRUCTURE_CONFIG")
        if not path:
            return cls()
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A malformed local configuration must never make ordinary Chat unusable.
            return cls()
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: object) -> TargetCatalog:
        if not isinstance(raw, dict):
            return cls()
        credentials = raw.get("credentials", {})
        if not isinstance(credentials, dict):
            credentials = {}
        entries = raw.get("targets", raw.get("integrations", {}))
        targets: list[Target] = []
        # A flat list is convenient for hand-written local config; normalize it
        # to the same family map without widening the model-facing contract.
        if isinstance(entries, list):
            grouped: dict[str, list[object]] = {"linux": [], "grafana": [], "zabbix": []}
            for entry in entries:
                if isinstance(entry, dict) and entry.get("family") in grouped:
                    grouped[str(entry["family"])].append(entry)
            entries = grouped
        if isinstance(entries, dict):
            for family in ("linux", "grafana", "zabbix"):
                values = entries.get(family, [])
                if isinstance(values, dict):
                    values = [values]
                if not isinstance(values, list):
                    continue
                for value in values:
                    if not isinstance(value, dict):
                        continue
                    reference = value.get("target_ref")
                    if not isinstance(reference, str) or not _target_ref_valid(reference):
                        continue
                    display = value.get("display_name", value.get("display", reference))
                    if not isinstance(display, str) or not re.fullmatch(
                        r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,127}", display
                    ):
                        display = reference
                    credential_ref = value.get("credential_ref")
                    datasources = value.get("datasources", {})
                    datasource_types: dict[str, str] = {}
                    if isinstance(datasources, dict):
                        for uid, kind in datasources.items():
                            if isinstance(uid, str) and isinstance(kind, str):
                                datasource_types[uid] = kind
                    connection = {
                        key: item
                        for key, item in value.items()
                        if key
                        not in {
                            "target_ref",
                            "display_name",
                            "display",
                            "credential_ref",
                            "datasources",
                        }
                    }
                    targets.append(
                        Target(
                            family,
                            reference,
                            display[:128],
                            connection,
                            credential_ref if isinstance(credential_ref, str) else None,
                            datasource_types,
                        )
                    )
        return cls(tuple(targets), credentials)

    def configured(self, family: str) -> bool:
        return any(target.family == family for target in self._targets)

    def targets(self, family: str) -> tuple[Target, ...]:
        return tuple(target for target in self._targets if target.family == family)

    def resolve(self, family: str, target_ref: str) -> Target:
        for target in self._targets:
            if target.family == family and target.target_ref == target_ref:
                return target
        raise InfrastructureError("unknown_target", "Unknown configured infrastructure target.")

    def model_context(self) -> tuple[tuple[str, str, str], ...]:
        return tuple(
            (target.family, target.target_ref, target.display_name) for target in self._targets
        )


def _target_ref_valid(value: str) -> bool:
    import re

    return bool(re.fullmatch(r"[a-z][a-z0-9._-]{0,63}", value))


class LinuxExecutor(Protocol):
    def inspect(
        self, target: Target, credential: object, sections: tuple[str, ...]
    ) -> Mapping[str, object]: ...
    def read_file(
        self, target: Target, credential: object, path: str, offset: int, length: int
    ) -> bytes: ...
    def service_status(
        self, target: Target, credential: object, service: str
    ) -> Mapping[str, object]: ...
    def package_status(
        self, target: Target, credential: object, package: str
    ) -> Mapping[str, object]: ...
    def service_preflight(self, target: Target, credential: object, service: str) -> None: ...
    def restart_service(self, target: Target, credential: object, service: str) -> None: ...
    def install_package(
        self, target: Target, credential: object, package: str, version: str | None
    ) -> None: ...
    def health(self, target: Target, credential: object) -> None: ...


class SshLinuxExecutor:
    """Concrete fixed-command SSH executor.  Model values never form a shell command."""

    def _run(self, target: Target, credential: object, command: list[str]) -> str:
        host = target.connection.get("host")
        user = target.connection.get("ssh_user")
        if not isinstance(host, str) or not isinstance(user, str):
            raise InfrastructureError("unavailable", "Linux target transport is incomplete.")
        argv = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
        port = target.connection.get("port")
        if isinstance(port, int):
            argv += ["-p", str(port)]
        # A configured key path is server-side material. It is never returned/logged.
        if isinstance(credential, str) and credential:
            argv += ["-i", credential]
        # ssh delivers a command to a remote shell. Quote every fixed semantic
        # argument there too, so model paths remain data rather than command text.
        argv += [f"{user}@{host}", "--", " ".join(shlex.quote(part) for part in command)]
        try:
            return subprocess.run(
                argv, check=True, capture_output=True, text=True, timeout=15
            ).stdout
        except subprocess.TimeoutExpired as error:
            raise InfrastructureError("timeout", "Linux target timed out.", True) from error
        except subprocess.CalledProcessError as error:
            raise InfrastructureError("upstream_error", "Linux operation failed.") from error

    def inspect(
        self, target: Target, credential: object, sections: tuple[str, ...]
    ) -> Mapping[str, object]:
        # Fixed, bounded semantic probes; parse only safe summaries.
        data: dict[str, object] = {}
        if "cpu" in sections:
            data["cpu"] = {
                "loadavg": self._run(target, credential, ["cat", "/proc/loadavg"]).split()[:3]
            }
        if "memory" in sections:
            data["memory"] = {
                "meminfo": self._run(target, credential, ["head", "-n", "20", "/proc/meminfo"])[
                    :4096
                ]
            }
        if "disk" in sections:
            data["disk"] = {
                "filesystems": self._run(target, credential, ["df", "-P", "-B1"])[:8192]
            }
        if "network" in sections:
            data["network"] = {
                "interfaces": self._run(target, credential, ["ip", "-brief", "address"])[:8192]
            }
        return data

    def read_file(
        self, target: Target, credential: object, path: str, offset: int, length: int
    ) -> bytes:
        # dd receives a fixed argument vector, not shell text.
        output = self._run(
            target,
            credential,
            ["dd", f"if={path}", "bs=1", f"skip={offset}", f"count={length}", "status=none"],
        )
        return output.encode()

    def service_status(
        self, target: Target, credential: object, service: str
    ) -> Mapping[str, object]:
        value = self._run(
            target,
            credential,
            [
                "systemctl",
                "show",
                service,
                "--property=LoadState,ActiveState,SubState,UnitFileState",
                "--no-page",
            ],
        )
        return _key_values(value, service)

    def package_status(
        self, target: Target, credential: object, package: str
    ) -> Mapping[str, object]:
        value = self._run(
            target, credential, ["dpkg-query", "-W", "-f=${Status} ${Version}", "--", package]
        ).strip()
        parts = value.split()
        return {
            "installed": len(parts) >= 4 and parts[:3] == ["install", "ok", "installed"],
            "version": parts[-1] if len(parts) >= 4 else None,
        }

    def service_preflight(self, target: Target, credential: object, service: str) -> None:
        status = self.service_status(target, credential, service)
        if status.get("load_state") != "loaded":
            raise InfrastructureError("not_found", "Service was not found.")

    def restart_service(self, target: Target, credential: object, service: str) -> None:
        self._run(target, credential, ["systemctl", "restart", "--", service])

    def install_package(
        self, target: Target, credential: object, package: str, version: str | None
    ) -> None:
        requested = f"{package}={version}" if version else package
        self._run(target, credential, ["apt-get", "install", "--yes", "--", requested])

    def health(self, target: Target, credential: object) -> None:
        self._run(target, credential, ["true"])


def _key_values(value: str, service: str) -> Mapping[str, object]:
    fields = dict(line.split("=", 1) for line in value.splitlines() if "=" in line)
    return {
        "service": service,
        "load_state": fields.get("LoadState"),
        "active_state": fields.get("ActiveState"),
        "sub_state": fields.get("SubState"),
        "enabled_state": fields.get("UnitFileState"),
    }


class GrafanaClient(Protocol):
    def dashboard_get(
        self, target: Target, credential: object, uid: str
    ) -> Mapping[str, object]: ...
    def datasource_query(
        self,
        target: Target,
        credential: object,
        uid: str,
        query: str,
        start: str,
        end: str,
        maximum: int,
    ) -> object: ...
    def alert_list(self, target: Target, credential: object) -> object: ...
    def annotation_create(
        self, target: Target, credential: object, payload: Mapping[str, object]
    ) -> str: ...
    def annotation_verify(
        self, target: Target, credential: object, annotation_id: str
    ) -> bool | None: ...
    def health(self, target: Target, credential: object) -> None: ...


class HttpGrafanaClient:
    def _client(self, target: Target, credential: object) -> httpx.Client:
        base_url = target.connection.get("base_url")
        if not isinstance(base_url, str):
            raise InfrastructureError("unavailable", "Grafana target transport is incomplete.")
        return httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {credential}"},
            timeout=10,
        )

    def _request(
        self, target: Target, credential: object, method: str, url: str, **kwargs: Any
    ) -> object:
        try:
            with self._client(target, credential) as client:
                response = client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException as error:
            raise InfrastructureError("timeout", "Grafana request timed out.", True) from error
        except httpx.HTTPStatusError as error:
            raise InfrastructureError("upstream_error", "Grafana request failed.") from error
        except httpx.HTTPError as error:
            raise InfrastructureError(
                "connection_error", "Grafana is unavailable.", True
            ) from error

    def dashboard_get(self, target: Target, credential: object, uid: str) -> Mapping[str, object]:
        response = self._request(target, credential, "GET", f"/api/dashboards/uid/{uid}")
        return response if isinstance(response, dict) else {}

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
        return self._request(
            target,
            credential,
            "POST",
            "/api/ds/query",
            json={
                "from": start,
                "to": end,
                "maxDataPoints": maximum,
                "queries": [{"refId": "A", "datasource": {"uid": uid}, "expr": query}],
            },
        )

    def alert_list(self, target: Target, credential: object) -> object:
        return self._request(target, credential, "GET", "/api/v1/provisioning/alert-rules")

    def annotation_create(
        self, target: Target, credential: object, payload: Mapping[str, object]
    ) -> str:
        response = self._request(target, credential, "POST", "/api/annotations", json=dict(payload))
        if not isinstance(response, dict) or not isinstance(response.get("id"), (str, int)):
            raise InfrastructureError(
                "upstream_error", "Grafana did not return an annotation identity."
            )
        return str(response["id"])

    def annotation_verify(
        self, target: Target, credential: object, annotation_id: str
    ) -> bool | None:
        return True

    def health(self, target: Target, credential: object) -> None:
        self._request(target, credential, "GET", "/api/health")


class ZabbixClient(Protocol):
    def call(
        self, target: Target, credential: object, method: str, params: Mapping[str, object]
    ) -> object: ...
    def health(self, target: Target, credential: object) -> None: ...


class HttpZabbixClient:
    def call(
        self, target: Target, credential: object, method: str, params: Mapping[str, object]
    ) -> object:
        base_url = target.connection.get("base_url")
        if not isinstance(base_url, str):
            raise InfrastructureError("unavailable", "Zabbix target transport is incomplete.")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": dict(params),
            "auth": credential,
        }
        try:
            response = httpx.post(base_url, json=payload, timeout=10)
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as error:
            raise InfrastructureError("timeout", "Zabbix request timed out.", True) from error
        except httpx.HTTPError as error:
            raise InfrastructureError("connection_error", "Zabbix is unavailable.", True) from error
        if not isinstance(body, dict) or "error" in body:
            raise InfrastructureError("upstream_error", "Zabbix request failed.")
        return body.get("result")

    def health(self, target: Target, credential: object) -> None:
        self.call(target, credential, "apiinfo.version", {})


class InfrastructureIntegrations:
    """Sanitized, bounded integration health facade for API and Settings."""

    def __init__(
        self,
        catalog: TargetCatalog,
        linux: LinuxExecutor | None = None,
        grafana: GrafanaClient | None = None,
        zabbix: ZabbixClient | None = None,
    ) -> None:
        self._catalog = catalog
        self._linux = linux or SshLinuxExecutor()
        self._grafana = grafana or HttpGrafanaClient()
        self._zabbix = zabbix or HttpZabbixClient()

    def status(self, family: str) -> IntegrationStatus:
        targets = self._catalog.targets(family)
        if not targets:
            return IntegrationStatus("unconfigured", "Integration is not configured.")
        try:
            for target in targets:
                credential = self._catalog.credentials.resolve(target.credential_ref)
                if family == "linux":
                    self._linux.health(target, credential)
                elif family == "grafana":
                    self._grafana.health(target, credential)
                elif family == "zabbix":
                    self._zabbix.health(target, credential)
                else:
                    raise ValueError(family)
        except (InfrastructureError, OSError):
            return IntegrationStatus(
                "unhealthy", "Configured integration is currently unavailable."
            )
        return IntegrationStatus("healthy")
