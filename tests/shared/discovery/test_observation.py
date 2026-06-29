from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from src.shared.discovery.observation import Observation


def test_observation_stores_data() -> None:
    observation = Observation(data="sample")

    assert observation.data == "sample"


def test_observation_is_immutable() -> None:
    observation = Observation(data="sample")

    with pytest.raises(FrozenInstanceError):
        observation.data = "modified"  # type: ignore[misc]
