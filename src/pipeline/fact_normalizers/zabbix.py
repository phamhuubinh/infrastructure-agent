from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from src.pipeline.fact import Fact, FactFreshness, FactValidity, utc_datetime
from src.pipeline.provenance import Provenance
from src.shared.execution.command_result import CommandResult


def _numeric(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def _unit(value: object) -> tuple[str, float]:
    raw = str(value or "").strip().casefold()
    mapping = {
        "%": ("percent", 1.0),
        "percent": ("percent", 1.0),
        "b": ("byte", 1.0),
        "bytes": ("byte", 1.0),
        "kb": ("byte", 1024.0),
        "mb": ("byte", 1024.0**2),
        "gb": ("byte", 1024.0**3),
        "bps": ("byte_per_second", 1.0),
        "b/s": ("byte_per_second", 1.0),
        "s": ("second", 1.0),
        "ms": ("millisecond", 1.0),
    }
    return mapping.get(raw, (raw or "count", 1.0))


def _records(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _timestamp(value: object, fallback: datetime) -> datetime | int | float | str:
    return value if isinstance(value, (datetime, int, float, str)) else fallback


def _item_metric(key: str) -> str:
    lower = key.casefold()
    if lower.startswith("system.cpu.util"):
        return "cpu.usage"
    if lower.startswith("system.cpu.num"):
        return "cpu.logical_cores"
    if lower.startswith("system.cpu.load"):
        return "system.load_1m"
    if lower.startswith("vm.memory.size"):
        return (
            "memory.usage"
            if "pused" in lower
            else "memory.available"
            if "available" in lower
            else "memory.total"
        )
    if lower.startswith("vfs.fs.size"):
        return (
            "filesystem.usage"
            if "pused" in lower
            else "filesystem.available"
            if "free" in lower
            else "filesystem.size"
        )
    if lower.startswith("vfs.fs.inode"):
        return "filesystem.inode_usage"
    if lower.startswith("net.if.in"):
        return "network.rx_rate"
    if lower.startswith("net.if.out"):
        return "network.tx_rate"
    if lower.startswith("icmppingloss"):
        return "network.packet_loss"
    if lower.startswith("icmppingsec"):
        return "network.latency"
    if lower.startswith("icmpping"):
        return "network.availability"
    if lower.startswith("system.uptime"):
        return "system.uptime"
    if lower.startswith("proc.num"):
        return "process.count"
    safe = re.sub(r"[^a-z0-9_]+", "_", lower).strip("_")
    return f"zabbix.item_{safe or 'unknown'}"


class ZabbixFactNormalizer:
    schema_version = "zabbix.v1"

    def normalize(
        self,
        capability: str,
        data: object,
        *,
        target: str = "zabbix",
        collected_at: datetime | int | float | str | None = None,
        command_results: Iterable[CommandResult] = (),
        parameters: Iterable[tuple[str, object]] = (),
        schema_version: str | None = None,
    ) -> tuple[Fact, ...]:
        collected = utc_datetime(collected_at)
        context = {
            "target": target,
            "capability": capability,
            "collected_at": collected,
            "command_results": tuple(command_results),
            "parameters": tuple(parameters),
            "schema_version": schema_version,
        }
        if not isinstance(data, dict):
            return (
                self._fact(
                    "zabbix.schema",
                    None,
                    "unknown",
                    validity=FactValidity.SCHEMA_INVALID,
                    dimensions={"error": "expected object payload"},
                    target=target,
                    capability=capability,
                    collected_at=collected,
                    command_results=command_results,
                    parameters=parameters,
                    schema_version=schema_version,
                ),
            )
        if capability == "get_items" or "items" in data:
            return tuple(self._items(data, context))
        if capability in {"get_problems", "get_problem_timeline"} or "problems" in data:
            return tuple(self._problems(data, context))
        if capability in {"get_events", "get_event_summary"} or "events" in data:
            return tuple(self._events(data, context))
        if capability in {"get_hosts", "get_host", "search_hosts"} or "hosts" in data:
            return tuple(self._hosts(data, context))
        if capability == "get_triggers" or "triggers" in data:
            return tuple(self._triggers(data, context))
        return ()

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
        source_reference: str | None = None,
        validity: FactValidity = FactValidity.VALID,
        dimensions: dict[str, object] | None = None,
    ) -> Fact:
        observed = utc_datetime(observed_at or collected_at)
        provenance = Provenance(
            source="zabbix",
            capability=capability,
            target=target,
            observed_at=observed,
            source_reference=source_reference,
            command_ids=tuple(result.command_id for result in command_results),
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
            source="zabbix",
            target=target,
            validity=validity,
            freshness=FactFreshness.FRESH,
            confidence=1.0,
            provenance=provenance,
            dimensions=dimensions or {},
        )

    def _items(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for item in _records(data, "items"):
            item_id = str(item.get("itemid", "unknown"))
            key = str(item.get("key_", ""))
            metric = _item_metric(key)
            value = _numeric(item.get("lastvalue"))
            canonical_unit, multiplier = _unit(item.get("units"))
            observed = _timestamp(item.get("lastclock"), context["collected_at"])
            dimensions = {"item_id": item_id, "item_key": key, "name": item.get("name")}
            if value is None:
                facts.append(
                    self._fact(
                        metric,
                        None,
                        canonical_unit,
                        subject="system",
                        observed_at=observed,
                        source_reference=f"/items.php?form=update&itemid={item_id}",
                        validity=FactValidity.SCHEMA_INVALID,
                        dimensions=dimensions,
                        **context,
                    )
                )
                continue
            converted = float(value) * multiplier
            if converted.is_integer():
                converted = int(converted)
            facts.append(
                self._fact(
                    metric,
                    converted,
                    canonical_unit,
                    subject="system",
                    observed_at=observed,
                    source_reference=f"/history.php?action=showgraph&itemids[]={item_id}",
                    dimensions=dimensions,
                    **context,
                )
            )
        return facts or [
            self._fact(
                "monitoring.item",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _problems(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.problem_active",
                {
                    "active": True,
                    "name": item.get("name"),
                    "severity": item.get("severity_label", item.get("severity")),
                    "severity_code": item.get("severity"),
                    "acknowledged": item.get("acknowledged"),
                },
                "event",
                subject=f"problem:{item.get('eventid', 'unknown')}",
                observed_at=_timestamp(item.get("clock"), context["collected_at"]),
                source_reference=f"/tr_events.php?eventid={item.get('eventid', '')}",
                dimensions={
                    "event_id": item.get("eventid"),
                    "severity": item.get("severity"),
                },
                **context,
            )
            for item in _records(data, "problems")
        ]
        return facts or [
            self._fact(
                "monitoring.problem_active",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _events(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.event",
                {
                    "name": item.get("name"),
                    "value": item.get("value"),
                    "severity": item.get("severity_label", item.get("severity")),
                },
                "event",
                subject=f"event:{item.get('eventid', 'unknown')}",
                observed_at=_timestamp(item.get("clock"), context["collected_at"]),
                source_reference=f"/tr_events.php?eventid={item.get('eventid', '')}",
                dimensions={"event_id": item.get("eventid")},
                **context,
            )
            for item in _records(data, "events")
        ]
        return facts or [
            self._fact(
                "monitoring.event",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _hosts(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts: list[Fact] = []
        for item in _records(data, "hosts"):
            host_id = str(item.get("hostid", "unknown"))
            subject = f"host:{item.get('host', item.get('name', host_id))}"
            status = item.get("status")
            if status is not None:
                facts.append(
                    self._fact(
                        "monitoring.host_enabled",
                        str(status) == "0",
                        "boolean",
                        subject=subject,
                        source_reference=f"/zabbix.php?action=host.edit&hostid={host_id}",
                        dimensions={"host_id": host_id},
                        **context,
                    )
                )
            if item.get("available") is not None:
                facts.append(
                    self._fact(
                        "monitoring.agent_availability",
                        str(item["available"]),
                        "state_code",
                        subject=subject,
                        source_reference=f"/zabbix.php?action=host.edit&hostid={host_id}",
                        dimensions={"host_id": host_id},
                        **context,
                    )
                )
        return facts or [
            self._fact(
                "monitoring.host_enabled",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _triggers(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.trigger_active",
                {
                    "active": str(item.get("value")) == "1",
                    "description": item.get("description"),
                    "severity": item.get("severity"),
                },
                "event",
                subject=f"trigger:{item.get('triggerid', 'unknown')}",
                observed_at=_timestamp(item.get("lastchange"), context["collected_at"]),
                source_reference=f"/triggers.php?form=update&triggerid={item.get('triggerid', '')}",
                dimensions={"trigger_id": item.get("triggerid")},
                **context,
            )
            for item in _records(data, "triggers")
        ]
        return facts or [
            self._fact(
                "monitoring.trigger_active",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]
