from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from src.pipeline.fact import Fact, FactFreshness, FactValidity, utc_datetime
from src.pipeline.provenance import Provenance
from src.shared.execution.command_result import CommandResult
from src.tool.linux.output_schema import validate_linux_output

_ALIASES = {
    "CPU Information": "get_cpu",
    "CPU Utilization": "get_cpu_usage",
    "System Load Assessment": "get_system_load",
    "Memory Information": "get_memory",
    "Memory Utilization": "get_memory",
    "Swap Information": "get_swap",
    "Storage Information": "get_disk",
    "Disk Utilization": "get_disk_usage",
    "Filesystem Information": "get_filesystem",
    "Filesystem Discovery": "get_filesystem",
    "Service Status": "get_service",
    "Service Discovery": "get_services",
    "Network Information": "get_network",
    "Network Interface Discovery": "get_network",
    "Interface Statistics": "get_interface_stats",
    "Process Discovery": "get_process",
    "System Information": "get_system",
}


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _float_value(value: object) -> float:
    if not _number(value):
        raise TypeError("expected numeric value")
    return float(value)  # type: ignore[arg-type]


def _int_value(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("expected integer value")
    return value


def _records(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


class LinuxFactNormalizer:
    schema_version = "linux.v1"

    def normalize(
        self,
        capability: str,
        data: object,
        *,
        target: str = "localhost",
        collected_at: datetime | int | float | str | None = None,
        command_results: Iterable[CommandResult] = (),
        parameters: Iterable[tuple[str, object]] = (),
        schema_version: str | None = None,
    ) -> tuple[Fact, ...]:
        action = _ALIASES.get(capability, capability)
        collected = utc_datetime(collected_at)
        if not isinstance(data, dict):
            return (
                self._fact(
                    "linux.schema",
                    None,
                    "unknown",
                    target=target,
                    capability=action,
                    collected_at=collected,
                    command_results=command_results,
                    parameters=parameters,
                    schema_version=schema_version,
                    validity=FactValidity.SCHEMA_INVALID,
                ),
            )
        violations = validate_linux_output(action, data)
        if violations:
            metric = {
                "get_cpu": "cpu.usage",
                "get_cpu_usage": "cpu.usage",
                "get_memory": "memory.usage",
                "get_swap": "swap.usage",
                "get_disk": "filesystem.usage",
                "get_disk_usage": "filesystem.usage",
                "get_service": "service.status",
                "get_network": "network.interface",
            }.get(action, "linux.schema")
            return (
                self._fact(
                    metric,
                    None,
                    "unknown",
                    target=target,
                    capability=action,
                    collected_at=collected,
                    command_results=command_results,
                    parameters=parameters,
                    schema_version=schema_version,
                    validity=FactValidity.SCHEMA_INVALID,
                    dimensions={"errors": violations},
                ),
            )

        dispatch = {
            "get_cpu": self._cpu,
            "get_cpu_usage": self._cpu_usage,
            "get_system_load": self._load,
            "get_memory": self._memory,
            "get_swap": self._swap,
            "get_disk": self._disk,
            "get_disk_usage": self._disk,
            "get_filesystem": self._filesystem,
            "get_filesystem_inode": self._inode,
            "get_disk_io": self._disk_io,
            "get_disk_device_health": self._disk_health,
            "get_services": self._services,
            "get_service": self._service,
            "get_network": self._network,
            "get_interface_stats": self._interface_stats,
            "get_listening_ports": self._listening_ports,
            "get_process": self._processes,
            "get_system": self._system,
        }
        handler = dispatch.get(action)
        if handler is None:
            return ()
        context = {
            "target": target,
            "capability": action,
            "collected_at": collected,
            "command_results": tuple(command_results),
            "parameters": tuple(parameters),
            "schema_version": schema_version,
        }
        return tuple(handler(data, context))

    def _fact(
        self,
        metric: str,
        value: object,
        unit: str,
        *,
        target: str,
        capability: str,
        collected_at: datetime,
        command_results: Iterable[CommandResult],
        parameters: Iterable[tuple[str, object]],
        schema_version: str | None,
        subject: str = "system",
        observed_at: datetime | int | float | str | None = None,
        confidence: float = 1.0,
        validity: FactValidity = FactValidity.VALID,
        dimensions: dict[str, object] | None = None,
    ) -> Fact:
        observed = utc_datetime(observed_at or collected_at)
        commands = tuple(command_results)
        reference = f"command:{commands[0].command_id}" if commands else None
        provenance = Provenance(
            source="linux",
            capability=capability,
            target=target,
            observed_at=observed,
            source_reference=reference,
            command_ids=tuple(result.command_id for result in commands),
            parameters=tuple(parameters),
            schema_version=schema_version or self.schema_version,
        )
        return Fact(
            subject=subject,
            metric=metric,
            value=value,
            unit=unit,
            observed_at=observed,
            collected_at=collected_at,
            source="linux",
            target=target,
            validity=validity,
            freshness=FactFreshness.FRESH,
            confidence=confidence,
            provenance=provenance,
            dimensions=dimensions or {},
        )

    def _cpu(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        if model := data.get("model"):
            facts.append(self._fact("cpu.model", str(model), "text", **context))
        cores = data.get("logical_cores", data.get("cores"))
        if isinstance(cores, int) and not isinstance(cores, bool):
            facts.append(self._fact("cpu.logical_cores", cores, "count", **context))
        usage = data.get("usage")
        if isinstance(usage, dict):
            facts.extend(self._cpu_usage(usage, context))
        load = data.get("load")
        if isinstance(load, dict):
            facts.extend(self._load(load, context))
        return facts

    def _cpu_usage(self, data: dict[str, object], context: dict) -> list[Fact]:
        mapping = {
            "usage_percent": "cpu.usage",
            "idle_percent": "cpu.idle",
            "user_percent": "cpu.user",
            "system_percent": "cpu.system",
            "iowait_percent": "cpu.iowait",
            "steal_percent": "cpu.steal",
        }
        return [
            self._fact(metric, _float_value(data[field]), "percent", **context)
            for field, metric in mapping.items()
            if _number(data.get(field))
        ]

    def _load(self, data: dict[str, object], context: dict) -> list[Fact]:
        return [
            self._fact(metric, _float_value(data[field]), "load", **context)
            for field, metric in (
                ("load_1min", "system.load_1m"),
                ("load_5min", "system.load_5m"),
                ("load_15min", "system.load_15m"),
            )
            if _number(data.get(field))
        ]

    def _memory(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(metric, _int_value(data[field]), "byte", **context)
            for field, metric in (
                ("total_bytes", "memory.total"),
                ("used_bytes", "memory.used"),
                ("available_bytes", "memory.available"),
            )
            if isinstance(data.get(field), int)
            and not isinstance(data.get(field), bool)
        ]
        if _number(data.get("usage_percent")):
            facts.append(
                self._fact(
                    "memory.usage",
                    _float_value(data["usage_percent"]),
                    "percent",
                    **context,
                )
            )
        for field, metric in (
            ("swap_total_bytes", "swap.total"),
            ("swap_used_bytes", "swap.used"),
            ("swap_free_bytes", "swap.free"),
        ):
            if isinstance(data.get(field), int) and not isinstance(
                data.get(field), bool
            ):
                facts.append(
                    self._fact(metric, _int_value(data[field]), "byte", **context)
                )
        if _number(data.get("swap_usage_percent")):
            facts.append(
                self._fact(
                    "swap.usage",
                    _float_value(data["swap_usage_percent"]),
                    "percent",
                    **context,
                )
            )
        return facts

    def _swap(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(metric, _int_value(data[field]), "byte", **context)
            for field, metric in (
                ("total_bytes", "swap.total"),
                ("used_bytes", "swap.used"),
                ("free_bytes", "swap.free"),
            )
            if isinstance(data.get(field), int)
            and not isinstance(data.get(field), bool)
        ]
        if _number(data.get("usage_percent")):
            facts.append(
                self._fact(
                    "swap.usage",
                    _float_value(data["usage_percent"]),
                    "percent",
                    **context,
                )
            )
        return facts

    def _disk(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        filesystems = data.get("filesystems", data.get("disks", []))
        if not isinstance(filesystems, list):
            return facts
        for item in filesystems:
            if not isinstance(item, dict):
                continue
            mountpoint = str(item.get("mountpoint", item.get("target", "unknown")))
            subject = f"filesystem:{mountpoint}"
            dimensions = {"mountpoint": mountpoint, "source": item.get("source")}
            for field, metric in (
                ("size_bytes", "filesystem.size"),
                ("used_bytes", "filesystem.used"),
                ("available_bytes", "filesystem.available"),
            ):
                value = item.get(field)
                if isinstance(value, int) and not isinstance(value, bool):
                    facts.append(
                        self._fact(
                            metric,
                            value,
                            "byte",
                            subject=subject,
                            dimensions=dimensions,
                            **context,
                        )
                    )
            if _number(item.get("usage_percent")):
                facts.append(
                    self._fact(
                        "filesystem.usage",
                        _float_value(item["usage_percent"]),
                        "percent",
                        subject=subject,
                        dimensions=dimensions,
                        **context,
                    )
                )
        return facts

    def _filesystem(self, data: dict[str, object], context: dict) -> list[Fact]:
        mounts = data.get("mounts", [])
        if not isinstance(mounts, list):
            return []
        if not mounts:
            return [
                self._fact(
                    "filesystem.mount",
                    None,
                    "empty",
                    validity=FactValidity.VALID_EMPTY,
                    **context,
                )
            ]
        return [
            self._fact(
                "filesystem.mount",
                {
                    "device": item.get("device"),
                    "mountpoint": item.get("mountpoint"),
                    "fstype": item.get("fstype"),
                },
                "record",
                subject=f"filesystem:{item.get('mountpoint', 'unknown')}",
                dimensions={"mountpoint": item.get("mountpoint")},
                **context,
            )
            for item in mounts
            if isinstance(item, dict)
        ]

    def _inode(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for item in _records(data, "filesystems"):
            mountpoint = str(item.get("mountpoint", "unknown"))
            for field, metric, unit in (
                ("inode_total", "filesystem.inode_total", "count"),
                ("inode_used", "filesystem.inode_used", "count"),
                ("inode_available", "filesystem.inode_available", "count"),
                ("inode_usage_percent", "filesystem.inode_usage", "percent"),
            ):
                if _number(item.get(field)):
                    facts.append(
                        self._fact(
                            metric,
                            _float_value(item[field])
                            if unit == "percent"
                            else _int_value(item[field]),
                            unit,
                            subject=f"filesystem:{mountpoint}",
                            dimensions={"mountpoint": mountpoint},
                            **context,
                        )
                    )
        return facts

    def _disk_io(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for item in _records(data, "devices"):
            device = str(item.get("device", "unknown"))
            for field, metric, unit in (
                ("read_bytes", "disk.read_bytes", "byte"),
                ("written_bytes", "disk.written_bytes", "byte"),
                ("read_time_seconds", "disk.read_time", "second"),
                ("write_time_seconds", "disk.write_time", "second"),
                ("io_time_seconds", "disk.io_time", "second"),
            ):
                if _number(item.get(field)):
                    facts.append(
                        self._fact(
                            metric,
                            item[field],
                            unit,
                            subject=f"disk:{device}",
                            dimensions={
                                "counter_semantics": data.get("counter_semantics")
                            },
                            **context,
                        )
                    )
        return facts

    def _disk_health(self, data: dict[str, object], context: dict) -> list[Fact]:
        return [
            self._fact(
                "disk.health_status",
                str(item["health_status"]),
                "state",
                subject=f"disk:{item.get('device', 'unknown')}",
                **context,
            )
            for item in _records(data, "devices")
            if item.get("health_status") is not None
        ]

    def _services(self, data: dict[str, object], context: dict) -> list[Fact]:
        services = data.get("services")
        if not isinstance(services, list):
            return []
        value = tuple(
            str(item.get("name"))
            for item in services
            if isinstance(item, dict) and item.get("name")
        )
        return [
            self._fact(
                "service.inventory",
                value if value else None,
                "service_list" if value else "empty",
                validity=FactValidity.VALID if value else FactValidity.VALID_EMPTY,
                confidence=_float_value(data.get("confidence", 1.0)),
                dimensions={"collection_strategy": data.get("collection_strategy")},
                **context,
            )
        ]

    def _service(self, data: dict[str, object], context: dict) -> list[Fact]:
        name = str(data.get("name", "")).removesuffix(".service").casefold()
        safe_name = re.sub(r"[^a-z0-9_]+", "_", name).strip("_") or "unknown"
        state = data.get("active", data.get("observed_state"))
        if state is None and "process_present" in data:
            state = (
                "process_present" if data.get("process_present") else "process_absent"
            )
        if state is None and data.get("listening_ports"):
            state = "port_listening"
        if state is None:
            return []
        confidence = _float_value(data.get("confidence", 1.0))
        dimensions = {
            "service_name": name,
            "collection_strategy": data.get("collection_strategy"),
        }
        return [
            self._fact(
                f"service.{safe_name}.status",
                str(state),
                "state",
                subject=f"service:{name}",
                confidence=confidence,
                dimensions=dimensions,
                **context,
            ),
            self._fact(
                "service.status",
                str(state),
                "state",
                subject=f"service:{name}",
                confidence=confidence,
                dimensions=dimensions,
                **context,
            ),
        ]

    def _network(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        interfaces = data.get("interfaces", [])
        if isinstance(interfaces, list):
            for item in interfaces:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "unknown"))
                facts.append(
                    self._fact(
                        "network.interface",
                        {
                            "name": name,
                            "family": item.get("family"),
                            "address": item.get("address"),
                        },
                        "record",
                        subject=f"interface:{name}",
                        dimensions={"interface": name},
                        **context,
                    )
                )
                if item.get("address") is not None:
                    facts.append(
                        self._fact(
                            "network.interface_address",
                            str(item["address"]),
                            "text",
                            subject=f"interface:{name}",
                            dimensions={
                                "interface": name,
                                "family": item.get("family"),
                            },
                            **context,
                        )
                    )
                stats = item.get("statistics")
                if isinstance(stats, dict):
                    facts.extend(self._network_counters(name, stats, context))
        routes = data.get("routes")
        if isinstance(routes, list):
            facts.append(
                self._fact(
                    "network.route",
                    tuple(str(route) for route in routes) if routes else None,
                    "route_list" if routes else "empty",
                    validity=FactValidity.VALID if routes else FactValidity.VALID_EMPTY,
                    **context,
                )
            )
        return facts

    def _network_counters(
        self, name: str, data: dict[str, object], context: dict
    ) -> list[Fact]:
        return [
            self._fact(
                metric,
                _int_value(data[field]),
                unit,
                subject=f"interface:{name}",
                dimensions={"interface": name, "counter_semantics": "cumulative"},
                **context,
            )
            for field, metric, unit in (
                ("rx_bytes", "network.rx_bytes", "byte"),
                ("tx_bytes", "network.tx_bytes", "byte"),
                ("rx_errors", "network.rx_errors", "count"),
                ("tx_errors", "network.tx_errors", "count"),
                ("rx_dropped", "network.rx_dropped", "count"),
                ("tx_dropped", "network.tx_dropped", "count"),
            )
            if isinstance(data.get(field), int)
            and not isinstance(data.get(field), bool)
        ]

    def _interface_stats(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for item in _records(data, "interface_stats"):
            facts.extend(
                self._network_counters(str(item.get("name", "unknown")), item, context)
            )
        return facts

    def _listening_ports(self, data: dict[str, object], context: dict) -> list[Fact]:
        ports = data.get("ports", [])
        if not isinstance(ports, list):
            return []
        return [
            self._fact(
                "network.listening_socket",
                item,
                "record",
                subject=f"socket:{item.get('protocol', 'unknown')}:{item.get('port_number', 'unknown')}",
                **context,
            )
            for item in ports
            if isinstance(item, dict)
        ]

    def _processes(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        if isinstance(data.get("total"), int):
            facts.append(self._fact("process.count", data["total"], "count", **context))
        if isinstance(data.get("zombie_count"), int):
            facts.append(
                self._fact(
                    "process.zombie_count", data["zombie_count"], "count", **context
                )
            )
        return facts

    def _system(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for field, metric in (
            ("hostname", "system.hostname"),
            ("kernel", "system.kernel"),
        ):
            if data.get(field) not in {None, "unknown"}:
                facts.append(self._fact(metric, str(data[field]), "text", **context))
        os_data = data.get("os")
        if isinstance(os_data, dict) and os_data:
            facts.append(self._fact("system.os", os_data, "record", **context))
        return facts
