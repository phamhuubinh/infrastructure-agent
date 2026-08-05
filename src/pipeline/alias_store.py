"""Scoped, lifecycle-aware aliases for deterministic target resolution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from enum import Enum, auto


class AliasScope(Enum):
    SESSION = auto()
    USER = auto()
    PROJECT = auto()
    GLOBAL = auto()


class AliasLifecycle(Enum):
    OBSERVED = auto()
    SUGGESTED = auto()
    APPROVED = auto()
    ACTIVE = auto()
    DEPRECATED = auto()


@dataclass(frozen=True, slots=True)
class AliasRecord:
    alias: str
    target: str
    scope: AliasScope
    lifecycle: AliasLifecycle
    scope_id: str | None = None
    reviewer: str | None = None
    evidence_count: int = 0

    def __post_init__(self) -> None:
        if self.scope is not AliasScope.GLOBAL and not self.scope_id:
            raise ValueError("scoped aliases require scope_id")
        if self.scope is AliasScope.GLOBAL and self.lifecycle in {
            AliasLifecycle.APPROVED,
            AliasLifecycle.ACTIVE,
        }:
            if not self.reviewer or self.evidence_count < 1:
                raise ValueError(
                    "approved/active global aliases require reviewer and evidence_count"
                )


class AliasStore:
    """In-memory alias registry with explicit scope and promotion lifecycle."""

    _PRECEDENCE = {
        AliasScope.SESSION: 4,
        AliasScope.USER: 3,
        AliasScope.PROJECT: 2,
        AliasScope.GLOBAL: 1,
    }

    def __init__(self, records: Iterable[AliasRecord] = ()) -> None:
        self._records: list[AliasRecord] = list(records)

    def add(self, record: AliasRecord) -> None:
        self._records.append(record)

    def observe(
        self,
        alias: str,
        target: str,
        *,
        session_id: str,
    ) -> AliasRecord:
        """Record transcript evidence locally; it is not active automatically."""
        record = AliasRecord(
            alias=alias.casefold(),
            target=target,
            scope=AliasScope.SESSION,
            lifecycle=AliasLifecycle.OBSERVED,
            scope_id=session_id,
            evidence_count=1,
        )
        self.add(record)
        return record

    def suggest(self, record: AliasRecord) -> AliasRecord:
        suggested = replace(record, lifecycle=AliasLifecycle.SUGGESTED)
        self.add(suggested)
        return suggested

    def resolve(
        self,
        alias: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        project_id: str | None = None,
    ) -> AliasRecord | None:
        context = {
            AliasScope.SESSION: session_id,
            AliasScope.USER: user_id,
            AliasScope.PROJECT: project_id,
            AliasScope.GLOBAL: None,
        }
        matches: list[AliasRecord] = []
        for record in self._records:
            if record.alias.casefold() != alias.casefold():
                continue
            if record.lifecycle is not AliasLifecycle.ACTIVE:
                continue
            if record.scope is not AliasScope.GLOBAL and (
                context[record.scope] is None
                or record.scope_id != context[record.scope]
            ):
                continue
            matches.append(record)
        if not matches:
            return None
        return max(matches, key=lambda item: self._PRECEDENCE[item.scope])

    @classmethod
    def from_config(cls, aliases: Mapping[str, object]) -> AliasStore:
        records: list[AliasRecord] = []
        for alias, raw in aliases.items():
            if isinstance(raw, str):
                # Backward-compatible config form.  It remains active but is
                # marked as reviewed by the legacy migration.
                records.append(
                    AliasRecord(
                        alias=alias,
                        target=raw,
                        scope=AliasScope.GLOBAL,
                        lifecycle=AliasLifecycle.ACTIVE,
                        reviewer="legacy-config-migration",
                        evidence_count=1,
                    )
                )
                continue
            if not isinstance(raw, Mapping):
                continue
            try:
                scope = AliasScope[str(raw.get("scope", "global")).upper()]
                lifecycle = AliasLifecycle[
                    str(raw.get("lifecycle", "active")).upper()
                ]
                records.append(
                    AliasRecord(
                        alias=alias,
                        target=str(raw["target"]),
                        scope=scope,
                        lifecycle=lifecycle,
                        scope_id=(
                            str(raw["scope_id"])
                            if raw.get("scope_id") is not None
                            else None
                        ),
                        reviewer=(
                            str(raw["reviewer"])
                            if raw.get("reviewer") is not None
                            else None
                        ),
                        evidence_count=int(raw.get("evidence_count", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return cls(records)
