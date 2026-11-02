"""Device scheduler authority must not collapse into ordinary Chat scope."""

from __future__ import annotations

from datetime import UTC, datetime
from functools import partial
from pathlib import Path

import pytest

from orion.contracts import RuntimeScope
from orion.persistence.sqlite import SQLiteStore
from orion.scheduler.contracts import TaskInput
from orion.scheduler.service import SchedulerService


def test_scheduler_device_scope_isolated_for_list_read_history_and_mutation(tmp_path: Path) -> None:
    store = SQLiteStore(tmp_path / "scope.db")
    now = datetime(2026, 10, 29, tzinfo=UTC)
    service = SchedulerService(store, lambda: now)

    def scope(endpoint: str | None) -> RuntimeScope:
        return RuntimeScope(
            session_id=store.create_session(endpoint_id=endpoint),
            endpoint_id=endpoint,
            principal_id="local",
            workspace_id="local",
        )

    try:
        ordinary, first, second = scope(None), scope("a" * 32), scope("b" * 32)
        tasks = [
            service.create(
                owner,
                TaskInput(
                    prompt="Read this scope",
                    schedule_kind="once",
                    run_at=now.isoformat(),
                ),
            )
            for owner in (ordinary, first, second)
        ]
        # The execution conversation retains the originating device scope.
        same_device = first.model_copy(update={"session_id": tasks[1]["execution_session_id"]})
        assert service.get(same_device, tasks[1]["task_id"]) == tasks[1]
        for index, owner in enumerate((ordinary, first, second)):
            assert service.list_tasks(owner) == [tasks[index]]
            for other_index, task in enumerate(tasks):
                if index == other_index:
                    assert service.get(owner, task["task_id"]) == task
                    assert service.history(owner, task["task_id"]) == []
                    continue
                for operation in (
                    partial(service.get, owner, task["task_id"]),
                    partial(service.history, owner, task["task_id"]),
                    partial(service.change, owner, task["task_id"], "pause"),
                    partial(service.change, owner, task["task_id"], "resume"),
                    partial(service.change, owner, task["task_id"], "delete"),
                ):
                    with pytest.raises(KeyError):
                        operation()
        assert all(
            service.get(owner, task["task_id"])["state"] == "enabled"
            for owner, task in zip((ordinary, first, second), tasks, strict=True)
        )
        store.close()
        store = SQLiteStore(tmp_path / "scope.db")
        service = SchedulerService(store, lambda: now)
        for index, owner in enumerate((ordinary, first, second)):
            assert service.list_tasks(owner) == [tasks[index]]
    finally:
        store.close()
