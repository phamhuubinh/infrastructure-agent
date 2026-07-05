from __future__ import annotations

from src.model.ollama_model_adapter import OllamaModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action


class FakeOllamaClient:
    def generate(
        self,
        prompt: str,
    ) -> str:
        return """
        {
            "type":"action",
            "tool":"knowledge",
            "arguments":{
                "source":"linux",
                "resource":"system_info"
            }
        }
        """


def test_reason_returns_action() -> None:
    adapter = OllamaModelAdapter(
        FakeOllamaClient(),
    )

    result = adapter.reason(
        user_request="Show system information.",
        observations=(),
    )

    assert isinstance(result, Action)

    assert result.tool == "knowledge"

    assert result.arguments == {
        "source": "linux",
        "resource": "system_info",
    }


def test_reason_includes_observations() -> None:
    adapter = OllamaModelAdapter(
        FakeOllamaClient(),
    )

    result = adapter.reason(
        user_request="Show system information.",
        observations=(
            Observation(
                data={
                    "hostname": "server01",
                },
            ),
        ),
    )

    assert isinstance(result, Action)
