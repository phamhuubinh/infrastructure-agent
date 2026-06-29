from types import MappingProxyType

import pytest

from src.runtime.execution_environment import ExecutionEnvironment
from src.shared.execution.environment_status import EnvironmentStatus


@pytest.fixture
def environment() -> ExecutionEnvironment:
    return ExecutionEnvironment()


def test_initialize_sets_ready_status(
    environment: ExecutionEnvironment,
) -> None:
    status = environment.initialize()

    assert status is EnvironmentStatus.READY
    assert environment.get_status() is EnvironmentStatus.READY


def test_initialize_may_only_be_called_once(
    environment: ExecutionEnvironment,
) -> None:
    environment.initialize()

    with pytest.raises(ValueError):
        environment.initialize()


def test_initialize_stores_resources(
    environment: ExecutionEnvironment,
) -> None:
    resources = {
        "config": object(),
        "session": object(),
    }

    environment.initialize(resources)

    returned = environment.get_resources()

    assert returned["config"] is resources["config"]
    assert returned["session"] is resources["session"]


def test_get_resources_returns_read_only_mapping(
    environment: ExecutionEnvironment,
) -> None:
    environment.initialize(
        {
            "resource": object(),
        }
    )

    resources = environment.get_resources()

    assert isinstance(resources, MappingProxyType)

    with pytest.raises(TypeError):
        resources["another"] = object()  # type: ignore[index]


def test_cleanup_releases_resources(
    environment: ExecutionEnvironment,
) -> None:
    environment.initialize(
        {
            "resource": object(),
        }
    )

    environment.cleanup()

    assert environment.get_status() is EnvironmentStatus.RELEASED
    assert len(environment.get_resources()) == 0


def test_cleanup_is_idempotent(
    environment: ExecutionEnvironment,
) -> None:
    environment.initialize()

    environment.cleanup()
    environment.cleanup()

    assert environment.get_status() is EnvironmentStatus.RELEASED


def test_cleanup_without_resources(
    environment: ExecutionEnvironment,
) -> None:
    environment.initialize()

    environment.cleanup()

    assert environment.get_status() is EnvironmentStatus.RELEASED


def test_environment_starts_uninitialized(
    environment: ExecutionEnvironment,
) -> None:
    assert environment.get_status() is EnvironmentStatus.UNINITIALIZED

    assert len(environment.get_resources()) == 0
