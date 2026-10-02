"""One canonical scheduler tool family using normal tool mutation governance."""

from __future__ import annotations

from typing import Literal

from pydantic import ValidationError

from orion.contracts import ToolCall, ToolDefinition, ToolResult
from orion.scheduler.contracts import TaskHistory, TaskInput, TaskList, TaskLookup
from orion.scheduler.service import SchedulerService
from orion.tool_runtime.registry import ToolRegistration


def scheduler_registrations(service: SchedulerService) -> tuple[ToolRegistration, ...]:
    registrations: list[ToolRegistration] = []
    for action in ("create", "list", "get", "pause", "resume", "delete", "history"):
        model = (
            TaskInput
            if action == "create"
            else TaskList
            if action == "list"
            else TaskHistory
            if action == "history"
            else TaskLookup
        )
        kind: Literal["read", "mutation"] = (
            "read" if action in {"list", "get", "history"} else "mutation"
        )
        definition = ToolDefinition(
            name=f"scheduler.{action}",
            handler_key=f"scheduler.{action}",
            description=(
                f"{action.capitalize()} scheduled Orion tasks in the current scope. "
                "Executions use Chat and are always read-only. "
                "Use five-field cron with IANA timezone or aware RFC3339 run_at."
            ),
            input_schema=model.model_json_schema(),
            operation_kind=kind,
        )

        def handle(call: ToolCall, action: str = action) -> ToolResult:
            try:
                scope, args = call.runtime_scope, call.arguments
                if action == "create":
                    data: object = service.create(scope, TaskInput.model_validate(args))
                elif action == "list":
                    data = service.list_tasks(scope, TaskList.model_validate(args).limit)
                elif action == "get":
                    data = service.get(scope, TaskLookup.model_validate(args).task_id)
                elif action == "history":
                    history = TaskHistory.model_validate(args)
                    data = service.history(scope, history.task_id, history.limit)
                else:
                    data = service.change(scope, TaskLookup.model_validate(args).task_id, action)
                return ToolResult(
                    call_id=call.call_id,
                    tool_name=call.tool_name,
                    status="success",
                    data={"result": data},
                )
            except KeyError:
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "not_found",
                    "Task or creating scope is unavailable.",
                )
            except RuntimeError:
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "conflict",
                    "Task has an active run or an exhausted schedule.",
                )
            except (ValidationError, ValueError):
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "invalid_input",
                    "Invalid scheduler input or schedule.",
                )

        registrations.append(ToolRegistration(definition, handle))
    return tuple(registrations)
