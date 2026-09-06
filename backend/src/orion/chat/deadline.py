"""Provider-neutral monotonic request budget primitives."""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar


class RequestDeadlineExceeded(RuntimeError):
    """The request work budget expired before an operation completed."""

    def __init__(self, phase: str) -> None:
        super().__init__("Request deadline exceeded before a terminal response was available.")
        self.phase = phase


class MutationOutcomeUnknown(RuntimeError):
    """A dispatched mutation did not finish bounded verification in time."""

    def __init__(self, phase: str, *, cancelled: bool) -> None:
        super().__init__("Mutation outcome could not be verified before the request deadline.")
        self.phase = phase
        self.cancelled = cancelled


@dataclass(frozen=True)
class RequestBudgetSettings:
    """Validated production request-deadline configuration."""

    request_deadline_seconds: float = 120
    finalization_reserve_seconds: float = 5

    def __post_init__(self) -> None:
        _validate_range(
            "ORION_REQUEST_DEADLINE_SECONDS", self.request_deadline_seconds, minimum=10, maximum=900
        )
        _validate_range(
            "ORION_REQUEST_FINALIZATION_RESERVE_SECONDS",
            self.finalization_reserve_seconds,
            minimum=1,
            maximum=60,
        )
        if self.finalization_reserve_seconds >= self.request_deadline_seconds:
            raise ValueError(
                "ORION_REQUEST_FINALIZATION_RESERVE_SECONDS must be less than "
                "ORION_REQUEST_DEADLINE_SECONDS."
            )

    @classmethod
    def from_environment(cls) -> RequestBudgetSettings:
        return cls(
            request_deadline_seconds=_environment_seconds("ORION_REQUEST_DEADLINE_SECONDS", 120),
            finalization_reserve_seconds=_environment_seconds(
                "ORION_REQUEST_FINALIZATION_RESERVE_SECONDS", 5
            ),
        )


def _environment_seconds(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"{name} must be a number of seconds.") from error


def _validate_range(name: str, value: float, *, minimum: float, maximum: float) -> None:
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g} seconds.")


T = TypeVar("T")
Clock = Callable[[], float]
Sleeper = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RequestBudget:
    """One request's immutable monotonic deadline and work boundary."""

    started_monotonic: float
    deadline_monotonic: float
    work_deadline_monotonic: float
    clock: Clock
    sleeper: Sleeper

    @classmethod
    def start(
        cls,
        settings: RequestBudgetSettings,
        *,
        clock: Clock = time.monotonic,
        sleeper: Sleeper = asyncio.sleep,
    ) -> RequestBudget:
        started = clock()
        deadline = started + settings.request_deadline_seconds
        return cls(
            started_monotonic=started,
            deadline_monotonic=deadline,
            work_deadline_monotonic=deadline - settings.finalization_reserve_seconds,
            clock=clock,
            sleeper=sleeper,
        )

    def elapsed_ms(self) -> int:
        return max(0, round((self.clock() - self.started_monotonic) * 1000))

    def remaining_work_seconds(self) -> float:
        return self.work_deadline_monotonic - self.clock()

    def ensure_work_available(self, phase: str) -> None:
        if self.remaining_work_seconds() <= 0:
            raise RequestDeadlineExceeded(phase)

    async def await_work(
        self,
        operation: Awaitable[T],
        cancellation: asyncio.Event,
        *,
        phase: str,
        preserve_on_interrupt: bool = False,
    ) -> T:
        """Await work or cancel and drain it at the common work deadline."""
        if cancellation.is_set():
            close = getattr(operation, "close", None)
            if callable(close):
                close()
            raise asyncio.CancelledError
        self.ensure_work_available(phase)
        operation_task = asyncio.ensure_future(operation)
        cancellation_task = asyncio.create_task(cancellation.wait())
        deadline_task = asyncio.ensure_future(self.sleeper(self.remaining_work_seconds()))
        try:
            done, _ = await asyncio.wait(
                {operation_task, cancellation_task, deadline_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            interrupted_by_cancellation = cancellation_task in done or cancellation.is_set()
            if interrupted_by_cancellation:
                if preserve_on_interrupt:
                    return await self._drain_mutation(operation_task, phase, cancelled=True)
                await _cancel_and_drain(operation_task)
                raise asyncio.CancelledError
            if deadline_task in done or self.remaining_work_seconds() <= 0:
                if preserve_on_interrupt:
                    return await self._drain_mutation(operation_task, phase, cancelled=False)
                await _cancel_and_drain(operation_task)
                raise RequestDeadlineExceeded(phase)
            return await operation_task
        finally:
            for task in (cancellation_task, deadline_task):
                if not task.done():
                    task.cancel()
            for task in (cancellation_task, deadline_task):
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def _drain_mutation(
        self, operation_task: asyncio.Future[T], phase: str, *, cancelled: bool
    ) -> T:
        """Preserve a dispatched mutation result, but never beyond absolute deadline."""
        remaining = self.deadline_monotonic - self.clock()
        if remaining <= 0:
            await _cancel_and_drain(operation_task)
            raise MutationOutcomeUnknown(phase, cancelled=cancelled)
        absolute_deadline_task = asyncio.ensure_future(self.sleeper(remaining))
        try:
            waitables: set[asyncio.Future[Any]] = {operation_task, absolute_deadline_task}
            done, _ = await asyncio.wait(
                waitables,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if operation_task in done:
                return await operation_task
            await _cancel_and_drain(operation_task)
            raise MutationOutcomeUnknown(phase, cancelled=cancelled)
        finally:
            if not absolute_deadline_task.done():
                absolute_deadline_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await absolute_deadline_task


async def _cancel_and_drain(task: asyncio.Future[Any]) -> None:
    if not task.done():
        task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
