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
from urllib.parse import urlsplit, urlunsplit

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
            return cls._from_tool_credentials()
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # A malformed local configuration must never make ordinary Chat unusable.
            return cls()
        return cls.from_mapping(raw)

    @classmethod
    def _from_tool_credentials(cls) -> TargetCatalog:
        """Adapt the established server-only credential file without exposing it."""
        path = Path(os.getenv("ORION_TOOL_CREDENTIALS_PATH", "/etc/orion/tool-credentials.json"))
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        credentials: dict[str, object] = {}
        targets: dict[str, list[dict[str, object]]] = {"linux": [], "grafana": [], "zabbix": []}
        for family in ("grafana", "zabbix"):
            item = raw.get(family)
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("url"), str)
                or not item.get("token")
            ):
                continue
            reference = f"{family}-token"
            credentials[reference] = item["token"]
            base_url = item["url"]
            if family == "zabbix":
                normalized = _zabbix_jsonrpc_endpoint(base_url)
                if normalized is None:
                    continue
                base_url = normalized
            targets[family].append(
                {"target_ref": family, "credential_ref": reference, "base_url": base_url}
            )
        aliases = [
            item for item in os.getenv("ORION_SSH_TARGET_REFS", "monitor").split(",") if item
        ]
        ssh_config = Path(os.getenv("ORION_SSH_CONFIG_PATH", str(Path.home() / ".ssh/config")))
        if ssh_config.exists():
            targets["linux"] = [
                {
                    "target_ref": alias,
                    "display_name": alias,
                    "ssh_alias": alias,
                    "credential_ref": "ssh",
                }
                for alias in aliases
            ]
            credentials["ssh"] = "ssh-config"
        return cls.from_mapping({"credentials": credentials, "targets": targets})

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


def _zabbix_jsonrpc_endpoint(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc or parts.query or parts.fragment:
        return None
    path = parts.path.rstrip("/")
    if not path.endswith("/api_jsonrpc.php"):
        path = f"{path}/api_jsonrpc.php"
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


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
    def write_file(self, target: Target, credential: object, path: str, content: bytes) -> None: ...
    def replace_file(
        self, target: Target, credential: object, temporary_path: str, path: str
    ) -> None: ...
    def remove_file(self, target: Target, credential: object, path: str) -> None: ...
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

    def _argv(self, target: Target, credential: object, command: list[str]) -> list[str]:
        alias = target.connection.get("ssh_alias")
        if isinstance(alias, str) and alias:
            return [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=10",
                alias,
                "--",
                " ".join(shlex.quote(part) for part in command),
            ]
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
        return argv + [f"{user}@{host}", "--", " ".join(shlex.quote(part) for part in command)]

    def _run(self, target: Target, credential: object, command: list[str]) -> str:
        try:
            return subprocess.run(
                self._argv(target, credential, command),
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
        except subprocess.TimeoutExpired as error:
            raise InfrastructureError("timeout", "Linux target timed out.", True) from error
        except subprocess.CalledProcessError as error:
            raise InfrastructureError("upstream_error", "Linux operation failed.") from error

    def _run_bytes(self, target: Target, credential: object, command: list[str]) -> bytes:
        try:
            return subprocess.run(
                self._argv(target, credential, command), check=True, capture_output=True, timeout=15
            ).stdout
        except subprocess.TimeoutExpired as error:
            raise InfrastructureError("timeout", "Linux target timed out.", True) from error
        except subprocess.CalledProcessError as error:
            raise InfrastructureError("upstream_error", "Linux operation failed.") from error

    def _run_input(
        self, target: Target, credential: object, command: list[str], content: bytes
    ) -> None:
        try:
            subprocess.run(
                self._argv(target, credential, command),
                check=True,
                input=content,
                capture_output=True,
                timeout=15,
            )
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
        return self._run_bytes(
            target,
            credential,
            ["dd", f"if={path}", "bs=1", f"skip={offset}", f"count={length}", "status=none"],
        )

    def write_file(self, target: Target, credential: object, path: str, content: bytes) -> None:
        self._run_input(
            target, credential, ["dd", f"of={path}", "bs=65536", "status=none"], content
        )

    def replace_file(
        self, target: Target, credential: object, temporary_path: str, path: str
    ) -> None:
        # The temporary path is Orion-generated in the original directory. Preserve mode where
        # possible before the fixed atomic rename operation.
        self._run(target, credential, ["chmod", "--reference", path, temporary_path])
        self._run(target, credential, ["mv", "-f", "--", temporary_path, path])

    def remove_file(self, target: Target, credential: object, path: str) -> None:
        self._run(target, credential, ["rm", "-f", "--", path])

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
    def datasource_type(self, target: Target, credential: object, uid: str) -> str: ...

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
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _client(self, target: Target, credential: object) -> httpx.Client:
        base_url = target.connection.get("base_url")
        if not isinstance(base_url, str):
            raise InfrastructureError("unavailable", "Grafana target transport is incomplete.")
        return httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {credential}"},
            timeout=10,
            transport=self._transport,
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
            if error.response.status_code == 404:
                raise InfrastructureError("not_found", "Grafana resource was not found.") from error
            raise InfrastructureError("upstream_error", "Grafana request failed.") from error
        except (httpx.HTTPError, ValueError) as error:
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

    def datasource_type(self, target: Target, credential: object, uid: str) -> str:
        response = self._request(target, credential, "GET", f"/api/datasources/uid/{uid}")
        kind = response.get("type") if isinstance(response, dict) else None
        if not isinstance(kind, str):
            raise InfrastructureError("unavailable", "Grafana datasource metadata is unavailable.")
        return kind

    def alert_list(self, target: Target, credential: object) -> object:
        try:
            response = self._request(
                target, credential, "GET", "/api/prometheus/grafana/api/v1/rules"
            )
        except InfrastructureError as error:
            if error.code == "upstream_error":
                raise InfrastructureError(
                    "unavailable", "Grafana alert state API is unavailable."
                ) from error
            raise
        if not isinstance(response, dict) or not isinstance(response.get("data"), dict):
            raise InfrastructureError("unavailable", "Grafana alert state API is unavailable.")
        rules: list[object] = []
        for group in response["data"].get("groups", []):
            if isinstance(group, dict) and isinstance(group.get("rules"), list):
                rules.extend(group["rules"])
        return rules

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
    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def _request(
        self,
        target: Target,
        credential: object,
        method: str,
        params: Mapping[str, object],
        *,
        auth: bool,
    ) -> object:
        base_url = target.connection.get("base_url")
        if not isinstance(base_url, str):
            raise InfrastructureError("unavailable", "Zabbix target transport is incomplete.")
        payload: dict[str, object] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": dict(params),
        }
        if auth:
            payload["auth"] = credential
        try:
            with httpx.Client(transport=self._transport, timeout=10) as client:
                response = client.post(base_url, json=payload)
            response.raise_for_status()
            body = response.json()
        except httpx.TimeoutException as error:
            raise InfrastructureError("timeout", "Zabbix request timed out.", True) from error
        except (httpx.HTTPError, ValueError) as error:
            raise InfrastructureError("connection_error", "Zabbix is unavailable.", True) from error
        if not isinstance(body, dict) or "error" in body:
            raise InfrastructureError("upstream_error", "Zabbix request failed.")
        return body.get("result")

    def call(
        self, target: Target, credential: object, method: str, params: Mapping[str, object]
    ) -> object:
        return self._request(target, credential, method, params, auth=True)

    def health(self, target: Target, credential: object) -> None:
        self._request(target, credential, "apiinfo.version", {}, auth=False)
        self._request(target, credential, "host.get", {"output": ["hostid"], "limit": 1}, auth=True)
