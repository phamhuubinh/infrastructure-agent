from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from orion.contracts import AssistantMessage, ModelTurn, ModelTurnCompleted
from orion.models.backend import ModelSettings


@pytest.mark.anyio
async def test_small_live_harness_uses_profile_and_eight_isolated_readonly_cases(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "targeted_live_validation.py"
    spec = importlib.util.spec_from_file_location("targeted_live", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen = []

    class Provider:
        async def stream(self, messages, tools, settings, cancellation):  # type: ignore[no-untyped-def]
            seen.append(settings.model_id)
            yield ModelTurnCompleted(
                turn=ModelTurn(assistant=AssistantMessage(content="Fixture answer."))
            )

    monkeypatch.setattr(module, "OpenAICompatibleBackend", Provider)
    monkeypatch.setattr(
        module,
        "active_model_settings",
        lambda: ModelSettings(
            provider_type="openai_compatible",
            base_url="http://profile.invalid/v1",
            model_id="persisted-fixture",
        ),
    )
    output = tmp_path / "report.json"
    results = await module.validate(output)
    assert len(results) == 8
    assert {result["case"] for result in results} == {
        "direct",
        "linux_read",
        "independent_reads",
        "tool_roundtrip",
        "stale_refresh",
        "service_not_found",
        "unknown_recovery",
        "ssh_commented",
    }
    assert set(seen) == {"persisted-fixture"}
    recovery = next(result for result in results if result["case"] == "unknown_recovery")
    assert recovery["fault_injected"] is True
    assert recovery["model_attempt_count"] == 2
    assert recovery["tool_results"][0]["error_code"] == "not_found"
    assert all(result["summary_model_calls"] == 0 for result in results)
    assert "api_key" not in output.read_text()
    assert json.loads(output.read_text())["model_id"] == "persisted-fixture"
