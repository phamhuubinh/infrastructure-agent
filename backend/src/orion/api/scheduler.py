"""Authenticated task management; API scope is derived from a visible session."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Response
from pydantic import Field

from orion.contracts import RuntimeScope
from orion.scheduler.contracts import MAX_RESULTS, TaskInput
from orion.scheduler.service import SchedulerService


class CreateTask(TaskInput):
    session_id: str = Field(min_length=1, max_length=64)


def _boundary[Result](operation: Callable[[], Result]) -> Result:
    try:
        return operation()
    except KeyError:
        raise HTTPException(404, "Task or scope not found.") from None
    except RuntimeError:
        raise HTTPException(409, "Task has an active run or an exhausted schedule.") from None
    except ValueError:
        raise HTTPException(422, "Invalid scheduler input or schedule.") from None


def install_scheduler_routes(
    app: FastAPI, service: SchedulerService, scope_for_session: Callable[[str], RuntimeScope]
) -> None:
    @app.post("/api/scheduler/tasks", status_code=201)
    async def create_task(body: CreateTask) -> dict[str, Any]:
        scope = scope_for_session(body.session_id)
        task = TaskInput.model_validate(body.model_dump(exclude={"session_id"}))
        return _boundary(lambda: service.create(scope, task))

    @app.get("/api/scheduler/tasks")
    async def list_tasks(
        session_id: str, limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 50
    ) -> list[dict[str, Any]]:
        return service.list_tasks(scope_for_session(session_id), limit)

    @app.get("/api/scheduler/tasks/{task_id}")
    async def get_task(task_id: str, session_id: str) -> dict[str, Any]:
        scope = scope_for_session(session_id)
        return _boundary(lambda: service.get(scope, task_id))

    @app.post("/api/scheduler/tasks/{task_id}/pause")
    async def pause_task(task_id: str, session_id: str) -> dict[str, Any]:
        scope = scope_for_session(session_id)
        return _boundary(lambda: service.change(scope, task_id, "pause"))

    @app.post("/api/scheduler/tasks/{task_id}/resume")
    async def resume_task(task_id: str, session_id: str) -> dict[str, Any]:
        scope = scope_for_session(session_id)
        return _boundary(lambda: service.change(scope, task_id, "resume"))

    @app.delete("/api/scheduler/tasks/{task_id}", status_code=204)
    async def delete_task(task_id: str, session_id: str) -> Response:
        scope = scope_for_session(session_id)
        _boundary(lambda: service.change(scope, task_id, "delete"))
        return Response(status_code=204)

    @app.get("/api/scheduler/tasks/{task_id}/history")
    async def task_history(
        task_id: str,
        session_id: str,
        limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 50,
    ) -> list[dict[str, Any]]:
        scope = scope_for_session(session_id)
        return _boundary(lambda: service.history(scope, task_id, limit))
