from __future__ import annotations

from collections.abc import Callable
from typing import Any

SchemaValidator = Callable[[dict[str, Any]], list[str]]


def _require(data: dict[str, Any], fields: dict[str, type]) -> list[str]:
    errors: list[str] = []
    for field, expected in fields.items():
        if field not in data:
            errors.append(f"missing required field '{field}'")
        elif not isinstance(data[field], expected):
            errors.append(
                f"field '{field}' must be {expected.__name__}, "
                f"got {type(data[field]).__name__}"
            )
    return errors


def _number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _cpu_usage(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"collection_strategy": str})
    for field in ("usage_percent", "idle_percent"):
        if field not in data or not _number(data[field]):
            errors.append(f"field '{field}' must be numeric percent")
        elif not 0 <= float(data[field]) <= 100:
            errors.append(f"field '{field}' must be between 0 and 100")
    return errors


def _cpu(data: dict[str, Any]) -> list[str]:
    usage = data.get("usage")
    if usage is not None:
        if not isinstance(usage, dict):
            return ["field 'usage' must be dict"]
        return _cpu_usage(usage)
    if not any(key in data for key in ("model", "logical_cores", "load")):
        return ["CPU output contains no identity, core, load, or usage fact"]
    return []


def _memory(data: dict[str, Any]) -> list[str]:
    return _require(
        data,
        {
            "total_bytes": int,
            "used_bytes": int,
            "available_bytes": int,
        },
    )


def _swap(data: dict[str, Any]) -> list[str]:
    return _require(data, {"total_bytes": int, "used_bytes": int, "free_bytes": int})


def _system_load(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("load_1min", "load_5min", "load_15min"):
        if not _number(data.get(field)):
            errors.append(f"field '{field}' must be numeric")
    return errors


def _filesystem_capacity(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"filesystems": list, "fact_type": str})
    for index, item in enumerate(data.get("filesystems", [])):
        if not isinstance(item, dict):
            errors.append(f"filesystems[{index}] must be dict")
            continue
        for field in ("size_bytes", "used_bytes", "available_bytes"):
            if not isinstance(item.get(field), int):
                errors.append(f"filesystems[{index}].{field} must be int bytes")
        if not _number(item.get("usage_percent")):
            errors.append(f"filesystems[{index}].usage_percent must be numeric")
    return errors


def _filesystem_inode(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"filesystems": list, "fact_type": str})
    for index, item in enumerate(data.get("filesystems", [])):
        if not isinstance(item, dict):
            errors.append(f"filesystems[{index}] must be dict")
            continue
        for field in ("inode_total", "inode_used", "inode_available"):
            if not isinstance(item.get(field), int):
                errors.append(f"filesystems[{index}].{field} must be int")
        if not _number(item.get("inode_usage_percent")):
            errors.append(f"filesystems[{index}].inode_usage_percent must be numeric")
    return errors


def _filesystem_mount(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"mounts": list})
    for index, item in enumerate(data.get("mounts", [])):
        if not isinstance(item, dict):
            errors.append(f"mounts[{index}] must be dict")
            continue
        for field in ("device", "mountpoint", "fstype"):
            if not isinstance(item.get(field), str):
                errors.append(f"mounts[{index}].{field} must be str")
    return errors


def _disk_io(data: dict[str, Any]) -> list[str]:
    errors = _require(
        data,
        {"devices": list, "fact_type": str, "counter_semantics": str},
    )
    for index, item in enumerate(data.get("devices", [])):
        if not isinstance(item, dict):
            errors.append(f"devices[{index}] must be dict")
            continue
        for field in ("read_bytes", "written_bytes"):
            if not isinstance(item.get(field), int):
                errors.append(f"devices[{index}].{field} must be int bytes")
        for field in ("read_time_seconds", "write_time_seconds", "io_time_seconds"):
            if not _number(item.get(field)):
                errors.append(f"devices[{index}].{field} must be numeric seconds")
    return errors


def _device_health(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"devices": list, "fact_type": str})
    for index, item in enumerate(data.get("devices", [])):
        if not isinstance(item, dict):
            errors.append(f"devices[{index}] must be dict")
            continue
        if not isinstance(item.get("device"), str):
            errors.append(f"devices[{index}].device must be str")
        if not isinstance(item.get("health_status"), str):
            errors.append(f"devices[{index}].health_status must be str")
    return errors


def _network(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"collection_sources": dict})
    if "interfaces" in data and not isinstance(data["interfaces"], list):
        errors.append("field 'interfaces' must be list")
    if "routes" in data and not isinstance(data["routes"], list):
        errors.append("field 'routes' must be list")
    return errors


def _interface_stats(data: dict[str, Any]) -> list[str]:
    errors = _require(
        data,
        {
            "interface_stats": list,
            "interface_stat_count": int,
            "collection_strategy": str,
        },
    )
    for index, item in enumerate(data.get("interface_stats", [])):
        if not isinstance(item, dict):
            errors.append(f"interface_stats[{index}] must be dict")
            continue
        if not isinstance(item.get("name"), str):
            errors.append(f"interface_stats[{index}].name must be str")
        for field in ("rx_bytes", "tx_bytes"):
            if field in item and not isinstance(item[field], int):
                errors.append(f"interface_stats[{index}].{field} must be int bytes")
    return errors


def _listening_ports(data: dict[str, Any]) -> list[str]:
    errors = _require(
        data,
        {"ports": list, "port_count": int, "collection_strategy": str},
    )
    for index, item in enumerate(data.get("ports", [])):
        if not isinstance(item, dict):
            errors.append(f"ports[{index}] must be dict")
            continue
        if not isinstance(item.get("protocol"), str):
            errors.append(f"ports[{index}].protocol must be str")
        port = item.get("port_number")
        if port is not None and not isinstance(port, int):
            errors.append(f"ports[{index}].port_number must be int or null")
    return errors


def _service_inventory(data: dict[str, Any]) -> list[str]:
    if data.get("collection_strategy") == "process_inventory":
        return _require(data, {"processes": list, "confidence": float})
    return _require(
        data,
        {"services": list, "total": int, "collection_strategy": str},
    )


def _service_status(data: dict[str, Any]) -> list[str]:
    errors = _require(data, {"name": str})
    status_fields = {
        "active",
        "observed_state",
        "process_present",
        "listening_ports",
    }
    if not status_fields.intersection(data):
        errors.append("service status contains no observed state fact")
    return errors


def _service_logs(data: dict[str, Any]) -> list[str]:
    return _require(
        data,
        {
            "service_name": str,
            "entries": list,
            "limit": int,
            "collection_strategy": str,
        },
    )


_SCHEMAS: dict[str, SchemaValidator] = {
    "get_cpu": _cpu,
    "get_cpu_usage": _cpu_usage,
    "get_system_load": _system_load,
    "get_memory": _memory,
    "get_swap": _swap,
    "get_disk": _filesystem_capacity,
    "get_disk_usage": _filesystem_capacity,
    "get_filesystem": _filesystem_mount,
    "get_filesystem_inode": _filesystem_inode,
    "get_disk_io": _disk_io,
    "get_disk_device_health": _device_health,
    "get_network": _network,
    "get_interface_stats": _interface_stats,
    "get_listening_ports": _listening_ports,
    "get_services": _service_inventory,
    "get_service": _service_status,
    "get_service_logs": _service_logs,
}


def validate_linux_output(action: str, data: object) -> tuple[str, ...]:
    """Return bounded schema violations for a Linux capability payload."""

    if not isinstance(data, dict):
        return (f"Linux capability '{action}' must return a dict payload",)
    validator = _SCHEMAS.get(action)
    if validator is None:
        return ()
    return tuple(validator(data)[:20])


def registered_linux_schemas() -> frozenset[str]:
    return frozenset(_SCHEMAS)
