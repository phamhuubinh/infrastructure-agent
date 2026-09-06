"""Bounded, request-local detection of recurring recoverable failures."""

from __future__ import annotations

from dataclasses import dataclass

# A state represents every recoverable failure returned by one model turn. The
# enclosing tuple is sorted by the runtime, so parallel call ordering has no
# semantic effect.
RecoveryFingerprint = tuple[str, str, str]
RecoveryFailureState = tuple[RecoveryFingerprint, ...]

# This is a storage bound, not a recovery or tool-call limit. It retains enough
# evidence for supported repeat limits and useful multi-state cycles while
# keeping request-local state predictably small.
MAX_RECOVERABLE_FAILURE_HISTORY = 64


@dataclass(frozen=True)
class RecoveryStallEvidence:
    """Safe terminal-integration evidence; never includes arguments or call IDs."""

    reason: str
    occurrences: int
    cycle_length: int | None = None


class RecoverableFailureTracker:
    """Track unresolved normalized failure states within one request/barrier.

    The tracker intentionally knows nothing about tools, model choices, or retry
    arguments. A successful ordinary result with no simultaneous recoverable
    error resolves the current chain. Expansion/control results and ambiguous
    outcomes preserve it. A mixed success/error turn remains unresolved so an
    unrelated success cannot conceal a recurring recoverable error.
    """

    def __init__(
        self,
        *,
        repeat_limit: int,
        cycle_repeat_limit: int,
        maximum_history: int = MAX_RECOVERABLE_FAILURE_HISTORY,
    ) -> None:
        if repeat_limit < 2:
            raise ValueError("repeat_limit must be at least 2.")
        if cycle_repeat_limit < 2:
            raise ValueError("cycle_repeat_limit must be at least 2.")
        if maximum_history < cycle_repeat_limit * 2:
            raise ValueError("maximum_history is too small for cycle detection.")
        self._repeat_limit = repeat_limit
        self._cycle_repeat_limit = cycle_repeat_limit
        self._maximum_history = maximum_history
        self._history: list[RecoveryFailureState] = []

    @property
    def history_size(self) -> int:
        return len(self._history)

    def observe(
        self,
        state: RecoveryFailureState,
        *,
        failure_resolved: bool,
    ) -> RecoveryStallEvidence | None:
        """Apply one deterministic transition and return terminal evidence, if any."""
        if failure_resolved:
            self._history.clear()
            return None
        if not state:
            return None

        self._history.append(state)
        if len(self._history) > self._maximum_history:
            del self._history[: len(self._history) - self._maximum_history]

        state_occurrences = self._history.count(state)
        if state_occurrences >= self._repeat_limit:
            return RecoveryStallEvidence(
                reason="repeated_recoverable_state",
                occurrences=state_occurrences,
            )

        cycle = self._shortest_repeated_cycle()
        if cycle is not None:
            return RecoveryStallEvidence(
                reason="repeated_recoverable_cycle",
                occurrences=self._cycle_repeat_limit,
                cycle_length=len(cycle),
            )
        return None

    def _shortest_repeated_cycle(self) -> tuple[RecoveryFailureState, ...] | None:
        required_length = self._cycle_repeat_limit * 2
        if len(self._history) < required_length:
            return None
        maximum_period = len(self._history) // self._cycle_repeat_limit
        for period in range(2, maximum_period + 1):
            repeated_length = period * self._cycle_repeat_limit
            suffix = self._history[-repeated_length:]
            cycle = tuple(suffix[:period])
            if all(
                tuple(suffix[index : index + period]) == cycle
                for index in range(0, repeated_length, period)
            ):
                return cycle
        return None
