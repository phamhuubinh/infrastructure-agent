from __future__ import annotations

from orion.chat.recovery import (
    RecoverableFailureTracker,
)


def _state(value: str) -> tuple[tuple[str, str, str], ...]:
    return (("test.recover", value, "needs_correction"),)


def test_tracker_detects_a_longer_multi_state_cycle() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)
    states = (
        _state("a"),
        _state("b"),
        _state("c"),
        _state("a"),
        _state("b"),
        _state("c"),
    )

    for state in states[:-1]:
        assert tracker.observe(state, failure_resolved=False) is None

    evidence = tracker.observe(states[-1], failure_resolved=False)

    assert evidence is not None
    assert evidence.reason == "repeated_recoverable_cycle"
    assert evidence.occurrences == 2
    assert evidence.cycle_length == 3


def test_tracker_is_order_independent_after_batch_normalization() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)
    first_batch = tuple(sorted((_state("a")[0], _state("b")[0])))
    reordered_batch = tuple(sorted(reversed(first_batch)))

    assert tracker.observe(first_batch, failure_resolved=False) is None
    assert tracker.observe(reordered_batch, failure_resolved=False) is None
    evidence = tracker.observe(first_batch, failure_resolved=False)

    assert evidence is not None
    assert evidence.reason == "repeated_recoverable_state"


def test_tracker_keeps_control_history_but_resets_on_resolution() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)

    assert tracker.observe(_state("a"), failure_resolved=False) is None
    assert tracker.observe((), failure_resolved=False) is None
    assert tracker.observe(_state("a"), failure_resolved=False) is None
    assert tracker.observe((), failure_resolved=True) is None
    assert tracker.observe(_state("a"), failure_resolved=False) is None


def test_tracker_history_is_bounded() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=5, cycle_repeat_limit=5, maximum_history=10)

    for index in range(30):
        assert tracker.observe(_state(str(index)), failure_resolved=False) is None

    assert tracker.history_size == 10


def test_trackers_are_request_local() -> None:
    first = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)
    second = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)

    assert first.observe(_state("a"), failure_resolved=False) is None
    assert first.observe(_state("a"), failure_resolved=False) is None
    assert second.observe(_state("a"), failure_resolved=False) is None
