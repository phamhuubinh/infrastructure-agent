from __future__ import annotations

import json

import pytest

from orion.benchmarks.model_context import (
    OFFLINE_BUDGETS,
    benchmark_scenarios,
    provider_payload,
    run_offline_benchmark,
)
from orion.contracts import ContextMessage


@pytest.mark.anyio
async def test_offline_benchmark_measures_direct_registry_baseline() -> None:
    report = await run_offline_benchmark()

    assert [scenario.name for scenario in benchmark_scenarios()] == [
        "fresh_hello",
        "direct_non_tool",
        "direct_registry",
        "ten_turn_ordinary",
        "single_read",
        "dependent_tools",
    ]
    assert all(item.status == "PASS" for item in report.measurements)
    assert all(item.summary_calls == 0 for item in report.measurements)
    assert [item.main_calls for item in report.measurements] == [1, 1, 2, 1, 2, 3]
    assert all(item.catalog_bytes == 12_503 for item in report.measurements)
    assert all(len(item.visible_tools_by_call[0]) == 25 for item in report.measurements)
    assert report.measurements[2].returned_tool_calls_by_call[0] == (
        "linux.system.inspect",
        "linux.system.inspect",
        "linux.system.inspect",
        "linux.file.read",
    )
    assert report.measurements[3].message_count > report.measurements[0].message_count
    assert report.measurements[3].payload_bytes > report.measurements[0].payload_bytes
    assert all(
        item.metrics["context_bytes"] <= OFFLINE_BUDGETS["fresh_payload_bytes"]
        for item in report.measurements
    )
    assert json.loads(report.to_json())["mode"] == "offline"


def test_empty_tools_provider_projection_omits_tools_key() -> None:
    payload = provider_payload(
        (
            ContextMessage(role="system", content="system"),
            ContextMessage(role="user", content="hello"),
        ),
        (),
    )

    assert "tools" not in payload


@pytest.mark.anyio
async def test_live_benchmark_uses_persisted_profile_and_real_backend_boundary(
    store, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    from orion.benchmarks import model_context as benchmark
    from orion.contracts import AssistantMessage, ModelTurn, ModelTurnCompleted

    settings_seen = []

    class Provider:
        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            settings_seen.append(settings)
            yield ModelTurnCompleted(
                turn=ModelTurn(assistant=AssistantMessage(content="Live provider fixture."))
            )

    profile = store.active_model_config()
    monkeypatch.setattr(benchmark.SQLiteStore, "read_active_model_config", lambda path: profile)
    monkeypatch.setattr(benchmark, "OpenAICompatibleBackend", Provider)
    # Serializer remains real: patch only the factory by preserving the static method.
    from orion.models.providers.openai_compatible import OpenAICompatibleBackend

    Provider._provider_messages = staticmethod(OpenAICompatibleBackend._provider_messages)
    monkeypatch.delenv("ORION_MODEL_BASE_URL", raising=False)
    monkeypatch.delenv("ORION_MODEL_ID", raising=False)

    report = await benchmark.run_live_benchmark()

    assert report.mode == "live"
    assert len(settings_seen) == len(benchmark.benchmark_scenarios())
    assert all(settings.model_id == profile["model_id"] for settings in settings_seen)


def test_readonly_profile_loading_never_creates_an_absent_database(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    from orion.persistence.sqlite import SQLiteStore

    path = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        SQLiteStore.read_active_model_config(path)
    assert not path.exists()
