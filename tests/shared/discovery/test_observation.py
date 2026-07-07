from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.discovery.observation import Observation


def test_observation_stores_data() -> None:
    observation = Observation(data="sample")

    assert observation.data == "sample"


def test_observation_defaults_to_success_with_no_error() -> None:
    observation = Observation(data="sample")

    assert observation.success is True
    assert observation.error is None


def test_observation_defaults_tool_and_arguments_to_empty() -> None:
    observation = Observation(data="sample")

    assert observation.tool == ""
    assert observation.arguments == {}


def test_observation_stores_tool_and_arguments() -> None:
    observation = Observation(
        data=[],
        tool="knowledge",
        arguments={"source": "linux", "resource": "docker_version"},
    )

    assert observation.tool == "knowledge"
    assert observation.arguments == {
        "source": "linux",
        "resource": "docker_version",
    }


def test_observation_stores_failure_details() -> None:
    observation = Observation(
        data=None,
        success=False,
        error="command not found",
    )

    assert observation.success is False
    assert observation.error == "command not found"


def test_observation_is_immutable() -> None:
    observation = Observation(data="sample")

    with pytest.raises(FrozenInstanceError):
        observation.data = "modified"  # type: ignore[misc]
