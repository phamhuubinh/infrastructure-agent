from __future__ import annotations

from orion.chat.recovery import (
    ReadProgressEvidence,
    RecoverableFailureTracker,
)


def _state(value: str) -> tuple[tuple[str, str, str], ...]:
    return (("test.recover", value, "needs_correction"),)


def _progress(tool_name: str = "test.recover") -> tuple[ReadProgressEvidence, ...]:
    return (ReadProgressEvidence(tool_name, "confirmed_progress"),)


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
        assert tracker.observe(state) is None

    evidence = tracker.observe(states[-1])

    assert evidence is not None
    assert evidence.reason == "repeated_recoverable_cycle"
    assert evidence.occurrences == 2
    assert evidence.cycle_length == 3


def test_tracker_is_order_independent_after_batch_normalization() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)
    first_batch = tuple(sorted((_state("a")[0], _state("b")[0])))
    reordered_batch = tuple(sorted(reversed(first_batch)))

    assert tracker.observe(first_batch) is None
    assert tracker.observe(reordered_batch) is None
    evidence = tracker.observe(first_batch)

    assert evidence is not None
    assert evidence.reason == "repeated_recoverable_state"


def test_tracker_keeps_control_history_and_resets_on_relevant_progress() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)

    assert tracker.observe(_state("a")) is None
    assert tracker.observe(()) is None
    assert tracker.observe(_state("a")) is None
    assert tracker.observe((), read_progress=_progress()) is None
    assert tracker.observe(_state("a")) is None


def test_tracker_does_not_reset_for_unrelated_progress() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)

    assert tracker.observe(_state("a")) is None
    assert tracker.observe((), read_progress=_progress("test.unrelated")) is None
    assert tracker.observe(_state("a")) is None
    assert tracker.observe(_state("a")) is not None


def test_tracker_history_is_bounded() -> None:
    tracker = RecoverableFailureTracker(repeat_limit=5, cycle_repeat_limit=5, maximum_history=10)

    for index in range(30):
        assert tracker.observe(_state(str(index))) is None

    assert tracker.history_size == 10


def test_trackers_are_request_local() -> None:
    first = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)
    second = RecoverableFailureTracker(repeat_limit=3, cycle_repeat_limit=2)

    assert first.observe(_state("a")) is None
    assert first.observe(_state("a")) is None
    assert second.observe(_state("a")) is None
