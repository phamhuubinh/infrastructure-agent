from src.shared.execution.execution_state import ExecutionState


class TransitionPolicy:
    """
    TransitionPolicy determines whether a lifecycle transition is allowed.

    This class implements the policy defined in the Runtime Behavior Specification.
    """

    @staticmethod
    def can_transition(
        current_state: ExecutionState,
        requested_state: ExecutionState,
    ) -> bool:
        """
        Validate whether a transition from current_state to requested_state is allowed.

        This method performs pure policy evaluation and has no side effects.

        Args:
            current_state: The current execution state.
            requested_state: The state being requested.

        Returns:
            True if the transition is allowed, False otherwise.
        """

        # The allowed transitions are defined in the Runtime Behavior Specification:
        # docs/runtime_behavior/execution_state_transition_table.md
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
