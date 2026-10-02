"""Scope-bound scheduler management, independent of the execution engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from orion.contracts import RuntimeScope
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.contracts import TaskInput
from orion.security import redact_public


class SchedulerService:
    def __init__(
        self, store: SQLiteStore, clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    ) -> None:
        self.store = store
        self.clock = clock
        self.wake: Callable[[], None] = lambda: None

    def create(self, scope: RuntimeScope, task: TaskInput) -> dict[str, Any]:
        result = self.store.create_scheduled_task(scope, task, self.clock())
        self.wake()
        return self._public_task(result)

    def list_tasks(self, scope: RuntimeScope, limit: int = 50) -> list[dict[str, Any]]:
        return [self._public_task(task) for task in self.store.scheduled_tasks(scope, limit)]

    def get(self, scope: RuntimeScope, task_id: str) -> dict[str, Any]:
        return self._public_task(self.store.scheduled_task(scope, task_id))

    def history(self, scope: RuntimeScope, task_id: str, limit: int = 50) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]], redact_public(self.store.scheduled_history(scope, task_id, limit))
        )

    def change(self, scope: RuntimeScope, task_id: str, action: str) -> dict[str, Any]:
        result = self.store.change_scheduled_task(scope, task_id, action, self.clock())
        self.wake()
        return self._public_task(result)

    @staticmethod
    def _public_task(task: dict[str, Any]) -> dict[str, Any]:
        return cast(dict[str, Any], redact_public(task))
