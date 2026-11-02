"""Canonical read tools for already trusted scoped packages, never installation/exec."""

from __future__ import annotations

from orion.contracts import ToolCall, ToolDefinition, ToolResult
from orion.skills.service import SkillError, SkillService
from orion.tool_runtime.registry import ToolRegistration


def skill_registrations(service: SkillService) -> tuple[ToolRegistration, ...]:
    identity = {
        "name": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,63}$"},
        "package_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    }
    schemas = {
        "list": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "offset": {"type": "integer", "minimum": 0, "maximum": 64},
                "limit": {"type": "integer", "minimum": 1, "maximum": 16},
            },
        },
        "load": {
            "type": "object",
            "additionalProperties": False,
            "properties": identity,
            "required": ["name", "package_sha256"],
        },
        "read": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                **identity,
                "path": {"type": "string", "minLength": 1, "maxLength": 512},
                "offset": {"type": "integer", "minimum": 0, "maximum": 262144},
                "length": {"type": "integer", "minimum": 1, "maximum": 8192},
            },
            "required": ["name", "package_sha256", "path"],
        },
    }
    registrations = []
    for operation, schema in schemas.items():

        def handle(call: ToolCall, action: str = operation) -> ToolResult:
            try:
                request, scope, arguments = (
                    call.request_id or "",
                    call.runtime_scope,
                    call.arguments,
                )
                if action == "list":
                    data = service.list(
                        request, scope, arguments.get("offset", 0), arguments.get("limit", 8)
                    )
                elif action == "load":
                    package = service.load(
                        request, scope, arguments["name"], arguments["package_sha256"]
                    )
                    data = {
                        "name": package.descriptor.name,
                        "version": package.descriptor.version,
                        "package_sha256": package.descriptor.package_sha256,
                        "guidance_in_current_context": True,
                        "resources": [
                            {"path": path, "bytes": len(content)}
                            for path, content in sorted(package.resources.items())
                        ],
                    }
                else:
                    data = service.read(
                        request,
                        scope,
                        arguments["name"],
                        arguments["package_sha256"],
                        arguments["path"],
                        arguments.get("offset", 0),
                        arguments.get("length", 8192),
                    )
                return ToolResult(
                    call_id=call.call_id, tool_name=call.tool_name, status="success", data=data
                )
            except SkillError as error:
                return ToolResult.failure(
                    call.call_id,
                    call.tool_name,
                    "skill_unavailable",
                    "Skill unavailable: " + error.category,
                )

        registrations.append(
            ToolRegistration(
                ToolDefinition(
                    name="skill." + operation,
                    handler_key="skill." + operation,
                    operation_kind="read",
                    input_schema=schema,
                    description=(
                        f"{operation} an existing trusted skill in this request's "
                        "scoped pinned catalog. "
                        "Guidance stays below user/scope/policy. Resource reads never "
                        "execute scripts; use ordinary "
                        "authorized tools for actions. No skill grants permission "
                        "or accesses another Project."
                    ),
                ),
                handle,
            )
        )
    return tuple(registrations)
