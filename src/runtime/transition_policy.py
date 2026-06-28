from enum import Enum
from src.shared.execution.execution_state import ExecutionState

class TransitionPolicy:
    """
    TransitionPolicy determines whether a lifecycle transition is allowed.

    This class contains no state and performs no mutation. It only validates
    transitions between ExecutionState values.
    """

    @staticmethod
    def can_transition(
        current_state: ExecutionState,
        requested_state: ExecutionState,
    ) -> bool:
        """
        Validate whether a transition from current_state to requested_state is allowed.

        Args:
            current_state: The current execution state.
            requested_state: The state being requested.

        Returns:
            True if the transition is allowed, False otherwise.
        """

        # Define allowed transitions
        allowed_transitions = {
            ExecutionState.CREATED: {ExecutionState.READY},
            ExecutionState.READY: {ExecutionState.RUNNING},
            ExecutionState.RUNNING: {
                ExecutionState.COMPLETED,
                ExecutionState.FAILED,
                ExecutionState.CANCELLED,
                ExecutionState.TIMEOUT,
            },
        }

        return requested_state in allowed_transitions.get(current_state, set())
