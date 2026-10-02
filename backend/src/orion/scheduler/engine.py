"""One in-process execution at a time, woken by edits or the next UTC due instant."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from orion.chat.runtime import ChatRuntime, RequestCancelled
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.service import SchedulerService


async def wait_for_wake(event: asyncio.Event, delay: float | None) -> None:
    if delay is None:
        await event.wait()
    else:
        try:
            await asyncio.wait_for(event.wait(), timeout=max(0, delay))
        except TimeoutError:
            pass


class SchedulerEngine:
    def __init__(
        self,
        store: SQLiteStore,
        runtime: ChatRuntime,
        service: SchedulerService,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        waiter: Callable[[asyncio.Event, float | None], Awaitable[None]] = wait_for_wake,
    ) -> None:
        self.store, self.runtime = store, runtime
        self.clock, self.waiter = clock, waiter
        self._wake = asyncio.Event()
        self._worker: asyncio.Task[None] | None = None
        self._stopping = False
        self._request_id: str | None = None
        self._tick_lock = asyncio.Lock()
        service.wake = self._wake.set

    def start(self) -> None:
        if self._worker is not None:
            return
        self.store.reconcile_scheduled_runs(self.clock())
        self._stopping = False
        self._worker = asyncio.create_task(self._serve(), name="orion-scheduler")

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._request_id is not None:
            self.runtime.cancel(self._request_id)
        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker, timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                pass
            finally:
                self._worker = None

    async def _serve(self) -> None:
        while not self._stopping:
            self._wake.clear()
            if await self.tick():
                continue
            next_due = self.store.next_scheduled_due()
            delay = None if next_due is None else (next_due - self.clock()).total_seconds()
            if not self._stopping:
                await self.waiter(self._wake, delay)

    async def tick(self) -> bool:
        """Injectable deterministic boundary: at most one claim and one runtime call."""
        async with self._tick_lock:
            if self._stopping:
                return False
            task = self.store.claim_scheduled_run(self.clock())
            if task is None:
                return False
            status = "failed"
            error_kind: str | None = None
            error_message: str | None = None
            try:
                self._request_id = self.store.create_and_link_scheduled_request(
                    task["run_id"], task["execution_session_id"]
                )
                self.runtime.begin_scheduled(
                    task["execution_session_id"], task["prompt"], self._request_id
                )
                outcome = await self.runtime.run(task["execution_session_id"], self._request_id)
                status = "completed" if outcome.status == "completed" else "failed"
                if status == "failed":
                    error_kind, error_message = "runtime_incomplete", "Execution did not complete."
            except asyncio.CancelledError:
                status = "interrupted"
                error_kind, error_message = "shutdown_interrupted", "Execution interrupted."
                raise
            except RequestCancelled:
                status = "interrupted"
                error_kind, error_message = "execution_cancelled", "Execution interrupted."
            except Exception:
                # Raw model/provider/tool exceptions can contain secrets or prompt data.
                error_kind, error_message = "runtime_failed", "Scheduled execution failed."
            finally:
                if self._request_id is not None:
                    request = self.store.request(self._request_id)
                    if request is not None and request["status"] in {"queued", "running"}:
                        self.store.complete_request(
                            self._request_id,
                            "failed",
                            error_message or "Scheduled execution failed.",
                        )
                self.store.finish_scheduled_run(
                    task["run_id"], status, self.clock(), error_kind, error_message
                )
                self._request_id = None
            return True
