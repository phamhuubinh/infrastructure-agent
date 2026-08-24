from __future__ import annotations

import json
import os
from pathlib import Path

from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
    SSHExecutionBackend,
)
from src.tool.ssh_target_discovery import discover_ssh_targets

DEFAULT_TARGETS: dict[str, ExecutionBackend] = {
    "localhost": LocalExecutionBackend(),
}

DEFAULT_TARGET_METADATA: dict[str, dict[str, str]] = {
    "localhost": {
        "display_name": "orion-api",
        "execution_scope": "orion-runtime",
        "description": (
            "The Orion process environment; in Docker this is the API container, "
            "not the physical Docker host."
        ),
    }
}


class TargetConfigurationError(ValueError):
    """The configured target authority file is malformed or unavailable.

    Target configuration is execution authority.  In particular, this error
    must never be converted into an implicit local backend: doing so changes a
    configuration typo into authority to execute in the Orion process.
    """


class TargetStore:
    def __init__(
        self,
        path: str = "targets.json",
        *,
        discover_ssh_targets_enabled: bool = False,
        ssh_config_path: str | Path | None = None,
        allow_missing_bootstrap: bool | None = None,
    ) -> None:
        self._path = Path(path)
        self._discover_ssh_targets_enabled = discover_ssh_targets_enabled
        self._ssh_config_path = (
            Path(ssh_config_path) if ssh_config_path is not None else None
        )
        # The packaged entrypoint materializes an explicit targets.json before
        # the application starts.  A developer using the conventional default
        # can also start from the documented localhost bootstrap.  A custom
        # authority path, especially ORION_TARGETS_FILE, is never silently
        # replaced with that bootstrap.
        self._allow_missing_bootstrap = (
            allow_missing_bootstrap
            if allow_missing_bootstrap is not None
            else (
                self._path.name == "targets.json"
                and os.environ.get("ORION_TARGETS_FILE", "").strip()
                not in {str(self._path), str(self._path.resolve())}
            )
        )

    def load(self) -> dict[str, ExecutionBackend]:
        if not self._path.exists():
            if self._allow_missing_bootstrap:
                return dict(DEFAULT_TARGETS)
            raise TargetConfigurationError(
                f"Configured targets file does not exist: {self._path}"
            )

        try:
            parsed: object = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TargetConfigurationError(
                f"Configured targets file is not valid JSON: {self._path}"
            ) from exc
        if not isinstance(parsed, dict):
            raise TargetConfigurationError(
                "Target configuration must be a JSON object."
            )
        entries = parsed.get("targets", parsed)
        if not isinstance(entries, dict):
            raise TargetConfigurationError(
                "Target configuration 'targets' must be an object."
            )
        targets: dict[str, ExecutionBackend] = {}
        for raw_name, cfg in entries.items():
            if not isinstance(raw_name, str) or not raw_name.strip():
                raise TargetConfigurationError(
                    "Target names must be non-empty strings."
                )
            if not isinstance(cfg, dict):
                raise TargetConfigurationError(
                    f"Target {raw_name!r} must be an object."
                )
            backend_type = cfg.get("backend")
            if backend_type == "local":
                targets[raw_name] = LocalExecutionBackend()
                continue
            if backend_type != "ssh":
                raise TargetConfigurationError(
                    f"Target {raw_name!r} has unsupported backend {backend_type!r}."
                )

            host = cfg.get("host")
            if not isinstance(host, str) or not host.strip():
                raise TargetConfigurationError(
                    f"SSH target {raw_name!r} requires a non-empty host."
                )
            user = cfg.get("user", "root")
            if not isinstance(user, str) or not user.strip():
                raise TargetConfigurationError(
                    f"SSH target {raw_name!r} has an invalid user."
                )
            port = cfg.get("port", 22)
            if (
                not isinstance(port, int)
                or isinstance(port, bool)
                or not 1 <= port <= 65535
            ):
                raise TargetConfigurationError(
                    f"SSH target {raw_name!r} has an invalid port."
                )
            identity_file = cfg.get("identity_file")
            if identity_file is not None and not isinstance(identity_file, str):
                raise TargetConfigurationError(
                    f"SSH target {raw_name!r} has an invalid identity_file."
                )
            strict = cfg.get("strict_host_key_checking", True)
            if not isinstance(strict, bool):
                raise TargetConfigurationError(
                    f"SSH target {raw_name!r} has an invalid "
                    "strict_host_key_checking value."
                )
            targets[raw_name] = SSHExecutionBackend(
                host=host,
                user=user,
                port=port,
                identity_file=identity_file,
                strict_host_key_checking=strict,
            )
        return targets

    def load_discovered_ssh_targets(self) -> dict[str, SSHExecutionBackend]:
        """Load runtime SSH aliases without persisting them to targets.json."""

        if not self._discover_ssh_targets_enabled:
            return {}
        return {
            target.alias: SSHExecutionBackend(
                host=target.host,
                user=target.user,
                port=target.port,
                identity_file=target.identity_file,
                strict_host_key_checking=target.strict_host_key_checking,
            )
            for target in discover_ssh_targets(self._ssh_config_path)
        }

    def load_metadata(self) -> dict[str, dict[str, str]]:
        """Load non-secret target identity fields independently of backends."""
        # Parse through the same fail-closed authority boundary as backends.
        # This also prevents a caller that only renders metadata from masking a
        # broken configured targets file.
        self.load()
        if not self._path.exists():
            return {
                name: dict(value) for name, value in DEFAULT_TARGET_METADATA.items()
            }
        try:
            parsed = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:  # defended by load()
            raise TargetConfigurationError(
                f"Configured targets file is not valid JSON: {self._path}"
            ) from exc
        entries = parsed.get("targets", parsed)
        if not isinstance(entries, dict):  # defended by load()
            raise TargetConfigurationError(
                "Target configuration 'targets' must be an object."
            )
        metadata: dict[str, dict[str, str]] = {}
        for raw_name, raw_cfg in entries.items():
            if not isinstance(raw_cfg, dict) or not isinstance(raw_name, str):
                raise TargetConfigurationError("Target metadata is invalid.")
            name = raw_name
            defaults = DEFAULT_TARGET_METADATA.get(name, {})
            metadata[name] = {
                "display_name": str(
                    raw_cfg.get("display_name", defaults.get("display_name", name))
                ),
                "execution_scope": str(
                    raw_cfg.get(
                        "execution_scope",
                        defaults.get("execution_scope", "remote-host"),
                    )
                ),
                "description": str(
                    raw_cfg.get("description", defaults.get("description", ""))
                ),
            }
        return metadata

    def save(self, backends: dict[str, ExecutionBackend]) -> None:
        existing_metadata = self.load_metadata() if self._path.exists() else {}
        data: dict[str, dict[str, object]] = {}
        for name, backend in backends.items():
            if isinstance(backend, SSHExecutionBackend):
                data[name] = {
                    "backend": "ssh",
                    "host": backend._host,
                    "port": backend._port,
                    "user": backend._user,
                    "identity_file": backend._identity_file,
                    "strict_host_key_checking": backend._strict_host_key_checking,
                }
            else:
                data[name] = {"backend": "local"}
            metadata = existing_metadata.get(name, {})
            for key in ("display_name", "execution_scope", "description"):
                if metadata.get(key):
                    data[name][key] = metadata[key]
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(json.dumps({"targets": data}, indent=2), encoding="utf-8")
        temporary.replace(self._path)
