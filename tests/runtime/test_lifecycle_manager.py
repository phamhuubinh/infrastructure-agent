import pytest

from src.runtime.lifecycle_manager import LifecycleManager
from src.shared.execution.execution_state import ExecutionState


@pytest.fixture
def manager() -> LifecycleManager:
    lifecycle_manager = LifecycleManager()
    lifecycle_manager.initialize("execution-001")
    return lifecycle_manager


def test_initialize_sets_created_state() -> None:
    manager = LifecycleManager()

    manager.initialize("execution-001")

    assert manager.get_state() is ExecutionState.CREATED
    assert manager.get_history() == ()


def test_initialize_may_only_be_called_once() -> None:
    manager = LifecycleManager()

    manager.initialize("execution-001")

    with pytest.raises(ValueError):
        manager.initialize("execution-002")


def test_transition_created_to_ready(manager: LifecycleManager) -> None:
    state = manager.transition(ExecutionState.READY)

    assert state is ExecutionState.READY
    assert manager.get_state() is ExecutionState.READY
    assert len(manager.get_history()) == 1


def test_transition_ready_to_running(manager: LifecycleManager) -> None:
    manager.transition(ExecutionState.READY)

    state = manager.transition(ExecutionState.RUNNING)

    assert state is ExecutionState.RUNNING
    assert manager.get_state() is ExecutionState.RUNNING
    assert len(manager.get_history()) == 2


def test_transition_running_to_completed(manager: LifecycleManager) -> None:
    manager.transition(ExecutionState.READY)
    manager.transition(ExecutionState.RUNNING)

    state = manager.transition(ExecutionState.COMPLETED)

    assert state is ExecutionState.COMPLETED
    assert manager.is_terminal()


def test_invalid_transition_raises_value_error(
    manager: LifecycleManager,
) -> None:
    with pytest.raises(ValueError):
        manager.transition(ExecutionState.RUNNING)


def test_history_is_immutable(manager: LifecycleManager) -> None:
    history = manager.get_history()

    assert isinstance(history, tuple)

    history = manager.get_history()


assert isinstance(history, tuple)
assert len(history) == 0


def test_transition_records_metadata(
    manager: LifecycleManager,
) -> None:
    metadata = {"source": "pytest"}

    manager.transition(
        ExecutionState.READY,
        metadata=metadata,
    )

    transition = manager.get_history()[0]

    assert transition.metadata == metadata


def test_terminal_state_returns_true(
    manager: LifecycleManager,
) -> None:
    manager.transition(ExecutionState.READY)
    manager.transition(ExecutionState.RUNNING)
    manager.transition(ExecutionState.COMPLETED)

    assert manager.is_terminal() is True


def test_non_terminal_state_returns_false(
    manager: LifecycleManager,
) -> None:
    assert manager.is_terminal() is False
