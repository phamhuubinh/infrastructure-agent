from __future__ import annotations

import time

from src.runtime.transition_policy import TransitionPolicy
from src.shared.execution.execution_state import ExecutionState
from src.shared.execution.lifecycle_transition import LifecycleTransition


class LifecycleManager:
    """
    LifecycleManager manages the lifecycle of a single execution.
    It guarantees that execution state changes occur in a controlled,
    deterministic, and consistent manner.
    """

    def __init__(self) -> None:
        """
        Create an uninitialized lifecycle manager.
        """
        self._execution_reference: str | None = None

        self._current_state: ExecutionState = ExecutionState.CREATED

        self._history: tuple[LifecycleTransition, ...] = ()

        self._initialized: bool = False

    def initialize(self, execution_reference: str) -> None:
        """
        Initialize the execution lifecycle.

        This operation may only be called once.

        Args:
            execution_reference: Unique execution identifier.

        Raises:
            ValueError:
                If the lifecycle has already been initialized.
        """
        if self._initialized:
            raise ValueError("Lifecycle has already been initialized.")

        self._execution_reference = execution_reference
        self._current_state: ExecutionState = ExecutionState.CREATED
        self._history = ()
        self._initialized = True
        
    def transition(
        self,
        requested_state: ExecutionState,
        metadata: dict[str, object] | None = None,
    ) -> ExecutionState:
        """
        Attempt to transition the execution lifecycle.

        A successful transition is recorded in the lifecycle history.

        Args:
            requested_state: Requested execution state.
            metadata: Optional transition metadata.

        Returns:
            The resulting execution state.

        Raises:
            ValueError:
                If the requested transition is invalid.
        """
        if not self._initialized:
            raise ValueError("Lifecycle has not been initialized.")

        if not TransitionPolicy.can_transition(
            self._current_state,
            requested_state,
        ):
            raise ValueError(
                f"Invalid lifecycle transition: "
                f"{self._current_state.name} -> "
                f"{requested_state.name}"
            )

        transition = LifecycleTransition(
            from_state=self._current_state,
            to_state=requested_state,
            timestamp=time.time(),
            metadata=metadata,
        )

        self._history = self._history + (transition,)

        self._current_state = requested_state

        return self._current_state
        
    def get_state(self) -> ExecutionState:
        """
        Return the current execution state.

        Returns:
            The current execution state.
        """
        return self._current_state

    def get_history(self) -> tuple[LifecycleTransition, ...]:
        """
        Return the lifecycle transition history.

        Returns:
            An immutable tuple containing every successful lifecycle
            transition ordered chronologically.
        """
        return self._history

    def is_terminal(self) -> bool:
        """
        Determine whether the current execution state is terminal.

        Returns:
            True if the current execution state is terminal.
            False otherwise.
        """
        return self._current_state in {
            ExecutionState.COMPLETED,
            ExecutionState.FAILED,
            ExecutionState.CANCELLED,
            ExecutionState.TIMEOUT,
        }
