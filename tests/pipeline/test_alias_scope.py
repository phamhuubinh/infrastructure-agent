from __future__ import annotations

import pytest

from src.pipeline.alias_store import (
    AliasLifecycle,
    AliasRecord,
    AliasScope,
    AliasStore,
)


def test_session_alias_does_not_leak_to_another_session() -> None:
    store = AliasStore(
        [
            AliasRecord(
                alias="web",
                target="server01",
                scope=AliasScope.SESSION,
                lifecycle=AliasLifecycle.ACTIVE,
                scope_id="session-a",
            )
        ]
    )

    assert store.resolve("web", session_id="session-a") is not None
    assert store.resolve("web", session_id="session-b") is None


def test_transcript_observation_is_not_automatically_active() -> None:
    store = AliasStore()
    record = store.observe("db", "postgres01", session_id="session-a")

    assert record.lifecycle is AliasLifecycle.OBSERVED
    assert store.resolve("db", session_id="session-a") is None


def test_active_global_alias_requires_review_metadata() -> None:
    with pytest.raises(ValueError, match="reviewer"):
        AliasRecord(
            alias="mon",
            target="zabbix",
            scope=AliasScope.GLOBAL,
            lifecycle=AliasLifecycle.ACTIVE,
        )


def test_scoped_alias_precedes_global_alias() -> None:
    store = AliasStore(
        [
            AliasRecord(
                alias="web",
                target="server-global",
                scope=AliasScope.GLOBAL,
                lifecycle=AliasLifecycle.ACTIVE,
                reviewer="reviewer",
                evidence_count=2,
            ),
            AliasRecord(
                alias="web",
                target="server-session",
                scope=AliasScope.SESSION,
                lifecycle=AliasLifecycle.ACTIVE,
                scope_id="session-a",
            ),
        ]
    )

    assert store.resolve("web", session_id="session-a").target == "server-session"
    assert store.resolve("web", session_id="session-b").target == "server-global"
