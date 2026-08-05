from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime

from src.pipeline.fact import Fact, FactFreshness, FactValidity, utc_datetime
from src.pipeline.provenance import Provenance
from src.shared.execution.command_result import CommandResult


def _metric(text: str) -> str | None:
    lower = text.casefold()
    if "cpu" in lower and any(
        word in lower for word in ("usage", "util", "percent", "%")
    ):
        return "cpu.usage"
    if any(word in lower for word in ("memory usage", "memory util", "mem_used")):
        return "memory.usage"
    if any(word in lower for word in ("filesystem usage", "disk usage", "fs_used")):
        return "filesystem.usage"
    if "packet" in lower and "loss" in lower:
        return "network.packet_loss"
    if "latency" in lower or "response_time" in lower:
        return "network.latency"
    if "throughput" in lower or "bytes_per_second" in lower:
        return "network.throughput"
    return None


def _unit(raw: object) -> tuple[str, float]:
    value = str(raw or "").casefold()
    if value in {"%", "percent", "percent (0-100)"}:
        return "percent", 1.0
    if value in {"percentunit", "percent (0.0-1.0)"}:
        return "percent", 100.0
    if value in {"bytes", "byte", "b"}:
        return "byte", 1.0
    if value in {"bps", "bytes/sec", "b/s"}:
        return "byte_per_second", 1.0
    if value in {"s", "seconds", "second"}:
        return "second", 1.0
    if value in {"ms", "milliseconds"}:
        return "millisecond", 1.0
    return value or "count", 1.0


def _records(data: dict[str, object], key: str) -> list[dict[str, object]]:
    value = data.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _timestamp(value: object, fallback: datetime) -> datetime | int | float | str:
    return value if isinstance(value, (datetime, int, float, str)) else fallback


class GrafanaFactNormalizer:
    schema_version = "grafana.v1"

    def normalize(
        self,
        capability: str,
        data: object,
        *,
        target: str = "grafana",
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
                    "grafana.schema",
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
        facts = self._series(data, context)
        if facts:
            return tuple(facts)
        if "dashboards" in data:
            return tuple(self._dashboards(data, context))
        if "panels" in data:
            return tuple(self._panels(data, context))
        if "alert_rules" in data:
            return tuple(self._alerts(data, context))
        if "annotations" in data:
            return tuple(self._annotations(data, context))
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
            source="grafana",
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
            source="grafana",
            target=target,
            validity=validity,
            freshness=FactFreshness.FRESH,
            confidence=1.0,
            provenance=provenance,
            dimensions=dimensions or {},
        )

    def _series(self, data: dict[str, object], context: dict) -> list[Fact]:
        raw_series = data.get("series")
        if not isinstance(raw_series, list):
            if isinstance(data.get("datapoints"), list):
                raw_series = [data]
            else:
                return []
        facts: list[Fact] = []
        for series in raw_series:
            if not isinstance(series, dict):
                continue
            descriptor = " ".join(
                str(series.get(field, ""))
                for field in (
                    "canonical_metric",
                    "metric",
                    "name",
                    "target",
                    "title",
                    "query",
                )
            )
            canonical = str(series.get("canonical_metric") or "") or _metric(descriptor)
            if not canonical or not re.fullmatch(
                r"[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+", canonical
            ):
                continue
            unit, multiplier = _unit(series.get("unit"))
            dashboard_uid = str(
                series.get("dashboard_uid", data.get("dashboard_uid", ""))
            )
            query_ref = str(series.get("ref_id", series.get("refId", "")))
            source_reference = f"/d/{dashboard_uid}" if dashboard_uid else None
            points = series.get("datapoints", series.get("points", []))
            if not isinstance(points, list):
                continue
            for point in points:
                value: object = None
                timestamp: object = None
                if isinstance(point, dict):
                    value = point.get("value", point.get("y"))
                    timestamp = point.get(
                        "timestamp", point.get("time", point.get("x"))
                    )
                elif isinstance(point, (list, tuple)) and len(point) >= 2:
                    value, timestamp = point[0], point[1]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                if isinstance(timestamp, (int, float)) and timestamp > 10_000_000_000:
                    timestamp = float(timestamp) / 1000.0
                converted = float(value) * multiplier
                converted_value: int | float = (
                    int(converted) if converted.is_integer() else converted
                )
                facts.append(
                    self._fact(
                        canonical,
                        converted_value,
                        unit,
                        observed_at=_timestamp(timestamp, context["collected_at"]),
                        source_reference=source_reference,
                        dimensions={
                            "dashboard_uid": dashboard_uid,
                            "query_ref": query_ref,
                        },
                        **context,
                    )
                )
        return facts

    def _dashboards(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.dashboard",
                {
                    "uid": item.get("uid"),
                    "title": item.get("title"),
                    "folder": item.get("folder"),
                },
                "record",
                subject=f"dashboard:{item.get('uid', 'unknown')}",
                source_reference=f"/d/{item.get('uid')}" if item.get("uid") else None,
                dimensions={"dashboard_uid": item.get("uid")},
                **context,
            )
            for item in _records(data, "dashboards")
        ]
        return facts or [
            self._fact(
                "monitoring.dashboard",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _panels(self, data: dict[str, object], context: dict) -> list[Fact]:
        uid = str(data.get("uid", ""))
        facts: list[Fact] = []
        for panel in _records(data, "panels"):
            panel_id = panel.get("id", "unknown")
            facts.append(
                self._fact(
                    "monitoring.panel",
                    {
                        "title": panel.get("title"),
                        "type": panel.get("type"),
                        "metrics": panel.get("metrics", []),
                    },
                    "record",
                    subject=f"panel:{uid}:{panel_id}",
                    source_reference=f"/d/{uid}?viewPanel={panel_id}" if uid else None,
                    dimensions={"dashboard_uid": uid, "panel_id": panel_id},
                    **context,
                )
            )
        return facts or [
            self._fact(
                "monitoring.panel",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _alerts(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.alert_rule",
                {
                    "title": item.get("title"),
                    "interval": item.get("interval"),
                    "for": item.get("for"),
                },
                "record",
                subject=f"alert_rule:{item.get('uid', 'unknown')}",
                source_reference=f"/alerting/grafana/{item.get('uid')}/view"
                if item.get("uid")
                else None,
                dimensions={"rule_uid": item.get("uid")},
                **context,
            )
            for item in _records(data, "alert_rules")
        ]
        return facts or [
            self._fact(
                "monitoring.alert_rule",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]

    def _annotations(self, data: dict[str, object], context: dict) -> list[Fact]:
        facts = [
            self._fact(
                "monitoring.annotation",
                {"text": item.get("text"), "panel_id": item.get("panel_id")},
                "event",
                subject=f"annotation:{item.get('id', 'unknown')}",
                observed_at=_timestamp(item.get("created"), context["collected_at"]),
                source_reference=f"/d/{item.get('dashboard_uid')}"
                if item.get("dashboard_uid")
                else None,
                dimensions={
                    "annotation_id": item.get("id"),
                    "dashboard_uid": item.get("dashboard_uid"),
                },
                **context,
            )
            for item in _records(data, "annotations")
        ]
        return facts or [
            self._fact(
                "monitoring.annotation",
                None,
                "empty",
                validity=FactValidity.VALID_EMPTY,
                **context,
            )
        ]
