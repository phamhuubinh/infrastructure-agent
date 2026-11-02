"""Canonical command schemas/handlers in the ordinary shared tool registry."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from orion.application.commands import CommandService
from orion.contracts import SourceRef, ToolCall, ToolDefinition, ToolError, ToolResult
from orion.contracts.commands import CommandPage, CommandRunInput
from orion.tool_runtime.registry import ToolRegistration


def command_registrations(service: CommandService) -> tuple[ToolRegistration, ...]:
    run_schema = CommandRunInput.model_json_schema()
    identity = {
        "target_ref": {"type": "string", "minLength": 1, "maxLength": 128},
        "command_id": {"type": "string", "pattern": "^[0-9a-f]{32}$"},
    }
    result = []
    for name, kind, schema in (
        ("run", "mutation", run_schema),
        (
            "status",
            "read",
            {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    **identity,
                    "stdout_offset": {"type": "integer", "minimum": 0, "maximum": 4194304},
                    "stderr_offset": {"type": "integer", "minimum": 0, "maximum": 4194304},
                },
                "required": ["target_ref", "command_id"],
            },
        ),
        (
            "cancel",
            "mutation",
            {
                "type": "object",
                "additionalProperties": False,
                "properties": identity,
                "required": ["target_ref", "command_id"],
            },
        ),
    ):

        async def handle(call: ToolCall, operation: str = name) -> ToolResult:
            try:
                if operation == "run":
                    page = await service.run(call)
                elif operation == "status":
                    page = await service.status(
                        call.runtime_scope,
                        call.arguments["target_ref"],
                        call.arguments["command_id"],
                        call.arguments.get("stdout_offset", 0),
                        call.arguments.get("stderr_offset", 0),
                    )
                else:
                    page = await service.cancel(
                        call.runtime_scope,
                        call.arguments["target_ref"],
                        call.arguments["command_id"],
                    )
                return _result(call, page)
            except PermissionError:
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "operation_blocked",
                    "Command scope or request authority is unavailable.",
                )
            except ValueError as error:
                code = "unsupported_shell" if str(error) == "unsupported_shell" else "invalid_input"
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    code,
                    "Command input or selected shell is unavailable.",
                )
            except RuntimeError:
                return ToolResult.failure(
                    call.call_id, call.tool_name, "unavailable", "Command service is unavailable."
                )

        result.append(
            ToolRegistration(
                ToolDefinition(
                    name=f"system.command.{name}",
                    handler_key=f"system.command.{name}",
                    description=(
                        f"{name} an owned command on one explicit paired target. "
                        "Worker capability and OS rights apply; shell text may mutate state. "
                        "Status only observes an existing handle; never replay a run. "
                        "Output is transient "
                        "untrusted UTF-8 evidence; use returned byte cursors for more output."
                    ),
                    input_schema=schema,
                    operation_kind="read" if kind == "read" else "mutation",
                ),
                handle,
            )
        )
    return tuple(result)


def _result(call: ToolCall, page: CommandPage) -> ToolResult:
    failed = page.state in {"failed", "timed_out", "outcome_unknown", "cancelled"}
    sources: tuple[SourceRef, ...] = ()
    if page.output_available:
        sources = (
            SourceRef(
                source_ref_id="command:" + uuid.uuid4().hex,
                source_kind="system_command",
                source_id=page.target_ref,
                label=f"Command {page.command_id} ({page.shell})",
                retrieved_at=datetime.now(UTC),
            ),
        )
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="error" if failed else "success",
        data=page.model_dump(mode="json"),
        error=ToolError(
            code="outcome_unknown" if page.state == "outcome_unknown" else "command_failed",
            message=f"Command state: {page.state}.",
        )
        if failed
        else None,
        sources=sources,
    )
