from __future__ import annotations

from src.model.mock_model_adapter import MockModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse


def test_reason_returns_action_on_first_iteration() -> None:
    model = MockModelAdapter()

    result = model.reason(
        "hello",
        (),
    )

    assert isinstance(result, Action)
    assert result.tool == "shell"
    assert result.arguments == {
        "command": "echo hello",
    }


def test_reason_returns_final_after_observation() -> None:
    model = MockModelAdapter()

    result = model.reason(
        "hello",
        (
            Observation(
                data="hello\n",
            ),
        ),
    )

    assert isinstance(result, FinalResponse)
    assert result.content == "hello\n"
