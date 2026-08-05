from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from src.pipeline.fact import Fact, FactFreshness, FactValidity, utc_datetime
from src.pipeline.provenance import Provenance
from src.shared.execution.command_result import CommandResult
from src.tool.capability_result import CapabilityStatus

from .grafana import GrafanaFactNormalizer
from .linux import LinuxFactNormalizer
from .zabbix import ZabbixFactNormalizer


def _canonical_metric(value: str) -> str:
    candidate = value.strip().casefold().replace(" ", "_").replace("-", "_")
    return candidate if "." in candidate else f"evidence.{candidate or 'unknown'}"


class FactNormalizerRegistry:
    """Deterministically select a schema-versioned source normalizer."""

    def __init__(self) -> None:
        self._linux = LinuxFactNormalizer()
        self._zabbix = ZabbixFactNormalizer()
        self._grafana = GrafanaFactNormalizer()

    def normalize(
        self,
        *,
        source_kind: str | None,
        capability: str,
        resource: str | None,
        data: object,
        status: CapabilityStatus,
        target: str,
        collected_at: datetime | int | float | str | None = None,
        command_results: Iterable[CommandResult] = (),
        parameters: Iterable[tuple[str, object]] = (),
        produced_fact_names: Iterable[str] = (),
        schema_version: str = "1",
    ) -> tuple[Fact, ...]:
        provider = (source_kind or "").casefold().removesuffix("tool")
        observed = utc_datetime(collected_at)
        names = tuple(
            dict.fromkeys(_canonical_metric(name) for name in produced_fact_names)
        )
        if status not in {CapabilityStatus.VALID, CapabilityStatus.VALID_EMPTY}:
            return self._invalid_facts(
                names or (f"evidence.{provider or 'collection'}",),
                provider=provider or "unknown",
                capability=resource or capability,
                target=target,
                observed_at=observed,
                status=status,
                command_results=command_results,
                parameters=parameters,
                schema_version=schema_version,
            )

        commands = tuple(command_results)
        normalized_parameters = tuple(parameters)
        selected = resource or capability
        if provider == "linux":
            facts = self._linux.normalize(
                selected,
                data,
                target=target,
                collected_at=observed,
                command_results=commands,
                parameters=normalized_parameters,
                schema_version=schema_version,
            )
        elif provider == "zabbix":
            facts = self._zabbix.normalize(
                selected,
                data,
                target=target,
                collected_at=observed,
                command_results=commands,
                parameters=normalized_parameters,
                schema_version=schema_version,
            )
        elif provider == "grafana":
            facts = self._grafana.normalize(
                selected,
                data,
                target=target,
                collected_at=observed,
                command_results=commands,
                parameters=normalized_parameters,
                schema_version=schema_version,
            )
        else:
            facts = ()
        if facts:
            return facts
        if status is CapabilityStatus.VALID_EMPTY:
            return tuple(
                self._generic_fact(
                    metric,
                    None,
                    validity=FactValidity.VALID_EMPTY,
                    provider=provider or "unknown",
                    capability=selected,
                    target=target,
                    observed_at=observed,
                    command_results=command_results,
                    parameters=parameters,
                    schema_version=schema_version,
                )
                for metric in names
            )
        return tuple(
            self._generic_fact(
                metric,
                data,
                validity=FactValidity.VALID,
                provider=provider or "unknown",
                capability=selected,
                target=target,
                observed_at=observed,
                command_results=command_results,
                parameters=parameters,
                schema_version=schema_version,
            )
            for metric in names
        )

    @staticmethod
    def _generic_fact(
        metric: str,
        value: object,
        *,
        validity: FactValidity,
        provider: str,
        capability: str,
        target: str,
        observed_at: datetime,
        command_results: Iterable[CommandResult],
        parameters: Iterable[tuple[str, object]],
        schema_version: str,
    ) -> Fact:
        provenance = Provenance(
            source=provider,
            capability=capability,
            target=target,
            observed_at=observed_at,
            command_ids=tuple(result.command_id for result in command_results),
            parameters=tuple(parameters),
            schema_version=schema_version,
        )
        return Fact(
            subject="system",
            metric=metric,
            value=value,
            unit="record" if value is not None else "empty",
            observed_at=observed_at,
            collected_at=observed_at,
            source=provider,
            target=target,
            validity=validity,
            freshness=FactFreshness.FRESH,
            confidence=1.0,
            provenance=provenance,
        )

    @classmethod
    def _invalid_facts(
        cls,
        metrics: tuple[str, ...],
        *,
        provider: str,
        capability: str,
        target: str,
        observed_at: datetime,
        status: CapabilityStatus,
        command_results: Iterable[CommandResult],
        parameters: Iterable[tuple[str, object]],
        schema_version: str,
    ) -> tuple[Fact, ...]:
        validity = {
            CapabilityStatus.UNSUPPORTED: FactValidity.UNSUPPORTED,
            CapabilityStatus.PARSE_FAILED: FactValidity.SCHEMA_INVALID,
        }.get(status, FactValidity.COMMAND_FAILED)
        return tuple(
            cls._generic_fact(
                metric,
                None,
                validity=validity,
                provider=provider,
                capability=capability,
                target=target,
                observed_at=observed_at,
                command_results=command_results,
                parameters=parameters,
                schema_version=schema_version,
            )
            for metric in metrics
        )


__all__ = [
    "FactNormalizerRegistry",
    "GrafanaFactNormalizer",
    "LinuxFactNormalizer",
    "ZabbixFactNormalizer",
]
