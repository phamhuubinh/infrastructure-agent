from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass

from src.shared.execution.command_result import CommandResult
from src.tool.execution_backend import (
    ExecutionBackend,
    LocalExecutionBackend,
    SSHExecutionBackend,
)

# One bounded probe discovers command support without executing a command per
# binary.  Entries are trusted source constants; user input is never inserted
# into the shell program.
PREFLIGHT_BINARY_CATALOG: tuple[str, ...] = (
    "cat",
    "df",
    "dmidecode",
    "docker",
    "ip",
    "iostat",
    "iptables",
    "journalctl",
    "lsblk",
    "lscpu",
    "lspci",
    "lsusb",
    "nproc",
    "nvme",
    "nft",
    "pgrep",
    "ping",
    "ps",
    "rc-service",
    "rc-status",
    "sar",
    "service",
    "sh",
    "smartctl",
    "ss",
    "systemctl",
    "tail",
    "top",
    "ufw",
    "uname",
    "who",
)


@dataclass(frozen=True, slots=True)
class EnvironmentFingerprint:
    """A safe, short-lived description of one execution environment."""

    target: str
    config_hash: str
    reachable: bool
    backend_type: str
    os_family: str = "unknown"
    os_name: str = "unknown"
    init_system: str = "unknown"
    privilege_level: str = "unknown"
    available_binaries: frozenset[str] = frozenset()
    has_procfs: bool = False
    has_sysfs: bool = False
    command_results: tuple[CommandResult, ...] = ()
    limitation: str | None = None
    collected_at: float = 0.0

    def supports_binary(self, name: str) -> bool:
        return name in self.available_binaries

    def to_safe_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "config_hash": self.config_hash,
            "reachable": self.reachable,
            "backend_type": self.backend_type,
            "os_family": self.os_family,
            "os_name": self.os_name,
            "init_system": self.init_system,
            "privilege_level": self.privilege_level,
            "available_binaries": sorted(self.available_binaries),
            "has_procfs": self.has_procfs,
            "has_sysfs": self.has_sysfs,
            "limitation": self.limitation,
            "collected_at": self.collected_at,
        }


def backend_config_hash(backend: ExecutionBackend) -> str:
    """Hash non-secret backend routing fields for preflight cache isolation."""

    if isinstance(backend, SSHExecutionBackend):
        material = (
            f"ssh|{backend._host}|{backend._port}|{backend._user}|"
            f"{backend._strict_host_key_checking}"
        )
    elif isinstance(backend, LocalExecutionBackend):
        material = "local"
    else:
        material = type(backend).__qualname__
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _output(result: CommandResult) -> str:
    return result.stdout.strip() if result.stdout else result.stderr.strip()


def _parse_os_release(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("PRETTY_NAME="):
            return line.partition("=")[2].strip().strip('"') or "unknown"
    for line in output.splitlines():
        if line.startswith("NAME="):
            return line.partition("=")[2].strip().strip('"') or "unknown"
    return "unknown"


class TargetPreflight:
    """Collect and cache target reachability and environment support.

    A failed connectivity probe stops immediately, so an unavailable SSH
    target creates one transport attempt rather than one failure per planned
    capability.  Per-key locks make concurrent graph nodes share that result.
    """

    def __init__(self, ttl_seconds: float = 30.0, failure_ttl_seconds: float = 5.0):
        self._ttl_seconds = ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds
        self._cache: dict[tuple[str, str], EnvironmentFingerprint] = {}
        self._cache_lock = threading.Lock()
        self._key_locks: dict[tuple[str, str], threading.Lock] = {}

    def inspect(
        self,
        target: str,
        backend: ExecutionBackend,
        *,
        force: bool = False,
    ) -> EnvironmentFingerprint:
        config_hash = backend_config_hash(backend)
        key = (target, config_hash)
        if not force:
            cached = self._get_fresh(key)
            if cached is not None:
                return cached

        with self._cache_lock:
            key_lock = self._key_locks.setdefault(key, threading.Lock())
        with key_lock:
            if not force:
                cached = self._get_fresh(key)
                if cached is not None:
                    return cached
            fingerprint = self._collect(target, backend, config_hash)
            with self._cache_lock:
                self._cache[key] = fingerprint
            return fingerprint

    def invalidate(self, target: str | None = None) -> None:
        with self._cache_lock:
            if target is None:
                self._cache.clear()
                return
            for key in tuple(self._cache):
                if key[0] == target:
                    del self._cache[key]

    def _get_fresh(
        self, key: tuple[str, str]
    ) -> EnvironmentFingerprint | None:
        with self._cache_lock:
            cached = self._cache.get(key)
        if cached is None:
            return None
        ttl = self._ttl_seconds if cached.reachable else self._failure_ttl_seconds
        if time.monotonic() - cached.collected_at <= ttl:
            return cached
        return None

    def _collect(
        self, target: str, backend: ExecutionBackend, config_hash: str
    ) -> EnvironmentFingerprint:
        command_results: list[CommandResult] = []
        backend_type = "ssh" if isinstance(backend, SSHExecutionBackend) else "local"

        connectivity = backend.run(["uname", "-s"], timeout=12)
        command_results.append(connectivity)
        if not connectivity.success:
            return EnvironmentFingerprint(
                target=target,
                config_hash=config_hash,
                reachable=False,
                backend_type=backend_type,
                command_results=tuple(command_results),
                limitation=(
                    "Target preflight failed; dependent capability commands were "
                    f"skipped ({connectivity.status.value})."
                ),
                collected_at=time.monotonic(),
            )

        kernel_name = _output(connectivity).lower()
        os_family = "linux" if kernel_name == "linux" else kernel_name or "unknown"

        os_result = backend.run(["cat", "/etc/os-release"], timeout=5)
        command_results.append(os_result)
        os_name = _parse_os_release(_output(os_result)) if os_result.success else "unknown"

        init_result = backend.run(["cat", "/proc/1/comm"], timeout=5)
        command_results.append(init_result)
        init_raw = _output(init_result).strip().lower() if init_result.success else ""
        if init_raw == "systemd":
            init_system = "systemd"
        elif init_raw in {"init", "runit"}:
            init_system = "sysv"
        elif init_raw in {"openrc", "openrc-init"}:
            init_system = "openrc"
        elif init_raw:
            init_system = init_raw[:40]
        else:
            init_system = "unknown"

        privilege_result = backend.run(["id", "-u"], timeout=5)
        command_results.append(privilege_result)
        uid = _output(privilege_result).strip() if privilege_result.success else ""
        privilege = "root" if uid == "0" else "user" if uid.isdigit() else "unknown"

        binary_script = (
            "for cmd in "
            + " ".join(PREFLIGHT_BINARY_CATALOG)
            + '; do command -v "$cmd" >/dev/null 2>&1 && printf "%s\\n" "$cmd"; done; '
            + 'test -r /proc/stat && printf "__PROCFS__\\n"; '
            + 'test -d /sys/class/net && printf "__SYSFS__\\n"'
        )
        binary_result = backend.run(["sh", "-c", binary_script], timeout=8)
        command_results.append(binary_result)
        tokens = set(_output(binary_result).splitlines()) if binary_result.success else set()
        available = frozenset(tokens.intersection(PREFLIGHT_BINARY_CATALOG))

        limitations: list[str] = []
        for result in command_results[1:]:
            if not result.success:
                limitations.append(result.status.value)

        return EnvironmentFingerprint(
            target=target,
            config_hash=config_hash,
            reachable=True,
            backend_type=backend_type,
            os_family=os_family,
            os_name=os_name,
            init_system=init_system,
            privilege_level=privilege,
            available_binaries=available,
            has_procfs="__PROCFS__" in tokens,
            has_sysfs="__SYSFS__" in tokens,
            command_results=tuple(command_results),
            limitation=(
                "Some optional preflight probes failed: " + ", ".join(limitations)
                if limitations
                else None
            ),
            collected_at=time.monotonic(),
        )


# Registries in the same Orion process share short-lived fingerprints. The
# cache key contains both target name and backend config hash.
DEFAULT_TARGET_PREFLIGHT = TargetPreflight()
