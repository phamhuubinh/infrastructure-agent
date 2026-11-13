"""Semantic Linux tools backed by configured SSH targets.

Transport clients receive only configured targets and server-side credentials.  The
handlers below are deliberately the only place operation data maps to those clients.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from weakref import WeakKeyDictionary

from orion.contracts import ReadProgress, SourceRef, ToolCall, ToolDefinition, ToolError, ToolResult
from orion.integrations.documents import (
    MAX_DOCUMENT_BYTES,
    DocumentCodecError,
    edit_document,
    read_document,
    verify_document_edit,
)
from orion.integrations.infrastructure import (
    InfrastructureError,
    LinuxExecutor,
    SshLinuxExecutor,
    Target,
    TargetCatalog,
)
from orion.tool_runtime.registry import ToolHandler, ToolRegistration

TARGET = {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"}
IDENTIFIER = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"}
VERSION = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,127}$"}
TEXT128 = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[^\\u0000-\\u001f]+$"}
PATH = {"type": "string", "minLength": 1, "maxLength": 4096, "pattern": "^/[^\\u0000-\\u001f]*$"}
DOCUMENT_TEXT = {"type": "string", "maxLength": 16000}
CELL = {"type": "string", "pattern": "^[A-Z]{1,3}[1-9][0-9]{0,6}$"}

# The SSH transport is synchronous but bounded (operations have
# operation timeouts). The shared per-event-loop semaphore bounds active workers at
# eight. Threads end when their bounded handler returns, so shutdown never needs to
# terminate a running thread unsafely.
_INFRASTRUCTURE_WORKERS: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    WeakKeyDictionary()
)


def infrastructure_registrations(
    catalog: TargetCatalog,
    *,
    linux: LinuxExecutor | None = None,
) -> tuple[ToolRegistration, ...]:
    """Register Linux tools when an SSH target is configured."""
    registrations: list[ToolRegistration] = []
    if catalog.configured("linux"):
        registrations += _linux_registrations(catalog, linux or SshLinuxExecutor())
    return tuple(
        ToolRegistration(registration.definition, _blocking_handler(registration.handler))
        for registration in registrations
    )


def _blocking_handler(handler: ToolHandler) -> ToolHandler:
    async def dispatch(call: ToolCall) -> object:
        loop = asyncio.get_running_loop()
        completion: asyncio.Future[object] = loop.create_future()
        workers = _INFRASTRUCTURE_WORKERS.get(loop)
        if workers is None:
            workers = asyncio.Semaphore(8)
            _INFRASTRUCTURE_WORKERS[loop] = workers
        await workers.acquire()

        def work() -> None:
            try:
                result = handler(call)
            except BaseException as error:
                loop.call_soon_threadsafe(_complete_with_error, completion, error)
            else:
                loop.call_soon_threadsafe(_complete_with_result, completion, result)
            finally:
                loop.call_soon_threadsafe(workers.release)

        threading.Thread(target=work, name="orion-tool", daemon=True).start()
        return await completion

    return dispatch


def _complete_with_result(completion: asyncio.Future[object], result: object) -> None:
    if not completion.done():
        completion.set_result(result)


def _complete_with_error(completion: asyncio.Future[object], error: BaseException) -> None:
    if not completion.done():
        completion.set_exception(error)


def infrastructure_definitions() -> tuple[ToolDefinition, ...]:
    """All frozen definitions, useful for contract tests without configured targets."""
    return tuple(_definitions().values())


def _definitions() -> dict[str, ToolDefinition]:
    closed = {"additionalProperties": False}
    return {
        "linux.system.inspect": ToolDefinition(
            name="linux.system.inspect",
            description="Inspect bounded structured Linux CPU, memory, disk, or network state.",
            handler_key="linux.system.inspect",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "sections": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["cpu", "memory", "disk", "network"]},
                        "minItems": 1,
                        "maxItems": 4,
                        "uniqueItems": True,
                        "default": ["cpu", "memory", "disk", "network"],
                    },
                },
                "required": ["target_ref"],
                **closed,
            },
        ),
        "linux.file.read": ToolDefinition(
            name="linux.file.read",
            description=(
                "Read one bounded range from an explicit path on a configured Linux "
                "infrastructure target. Never use for Orion session attachments or Project "
                "documents."
            ),
            handler_key="linux.file.read",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "path": PATH,
                    "offset": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 1073741824,
                        "default": 0,
                    },
                    "length": {"type": "integer", "minimum": 1, "maximum": 65536, "default": 16384},
                },
                "required": ["target_ref", "path"],
                **closed,
            },
        ),
        "linux.document.read": ToolDefinition(
            name="linux.document.read",
            description=(
                "Read bounded structured text, Word DOCX, or Excel XLSX at an explicit path on "
                "a configured Linux infrastructure target, never an Orion document."
            ),
            handler_key="linux.document.read",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "path": PATH,
                    "cursor": {"type": "integer", "minimum": 0, "maximum": 100000, "default": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
                    "sheet": TEXT128,
                    "range": {
                        "type": "string",
                        "maxLength": 32,
                        "pattern": "^[A-Z]+[1-9][0-9]*(?::[A-Z]+[1-9][0-9]*)?$",
                    },
                },
                "required": ["target_ref", "path"],
                **closed,
            },
        ),
        "linux.file.edit": ToolDefinition(
            name="linux.file.edit",
            description=(
                "Apply bounded structured edits to a UTF-8 text, Word DOCX, or Excel XLSX file "
                "and verify the final result."
            ),
            handler_key="linux.file.edit",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "path": PATH,
                    "operations": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 32,
                        "items": {
                            "oneOf": [
                                {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"const": "replace_text"},
                                        "old_text": DOCUMENT_TEXT,
                                        "new_text": DOCUMENT_TEXT,
                                    },
                                    "required": ["kind", "old_text", "new_text"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"const": "set_paragraph"},
                                        "paragraph_index": {"type": "integer", "minimum": 0},
                                        "text": DOCUMENT_TEXT,
                                    },
                                    "required": ["kind", "paragraph_index", "text"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"const": "set_table_cell"},
                                        "table_index": {"type": "integer", "minimum": 0},
                                        "row": {"type": "integer", "minimum": 0},
                                        "column": {"type": "integer", "minimum": 0},
                                        "text": DOCUMENT_TEXT,
                                    },
                                    "required": ["kind", "table_index", "row", "column", "text"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"const": "set_cell"},
                                        "sheet": TEXT128,
                                        "cell": CELL,
                                        "value": {"type": ["string", "number", "boolean", "null"]},
                                    },
                                    "required": ["kind", "sheet", "cell", "value"],
                                    "additionalProperties": False,
                                },
                                {
                                    "type": "object",
                                    "properties": {
                                        "kind": {"const": "set_formula"},
                                        "sheet": TEXT128,
                                        "cell": CELL,
                                        "formula": {
                                            "type": "string",
                                            "minLength": 2,
                                            "maxLength": 16000,
                                            "pattern": "^=",
                                        },
                                    },
                                    "required": ["kind", "sheet", "cell", "formula"],
                                    "additionalProperties": False,
                                },
                            ]
                        },
                    },
                },
                "required": ["target_ref", "path", "operations"],
                **closed,
            },
        ),
        "linux.service.status": ToolDefinition(
            name="linux.service.status",
            description="Inspect one Linux service state.",
            handler_key="linux.service.status",
            input_schema={
                "type": "object",
                "properties": {"target_ref": TARGET, "service": IDENTIFIER},
                "required": ["target_ref", "service"],
                **closed,
            },
        ),
        "linux.package.status": ToolDefinition(
            name="linux.package.status",
            description="Inspect one Linux package installation state.",
            handler_key="linux.package.status",
            input_schema={
                "type": "object",
                "properties": {"target_ref": TARGET, "package": IDENTIFIER},
                "required": ["target_ref", "package"],
                **closed,
            },
        ),
        "linux.service.restart": ToolDefinition(
            name="linux.service.restart",
            description="Restart one configured Linux service and verify it is active.",
            handler_key="linux.service.restart",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {"target_ref": TARGET, "service": IDENTIFIER},
                "required": ["target_ref", "service"],
                **closed,
            },
        ),
        "linux.package.install": ToolDefinition(
            name="linux.package.install",
            description="Converge one Linux package to installed state.",
            handler_key="linux.package.install",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {"target_ref": TARGET, "package": IDENTIFIER, "version": VERSION},
                "required": ["target_ref", "package"],
                **closed,
            },
        ),
    }


def _linux_registrations(catalog: TargetCatalog, executor: LinuxExecutor) -> list[ToolRegistration]:
    definitions = _definitions()
    handlers = {
        "linux.system.inspect": lambda call: _linux_inspect(call, catalog, executor),
        "linux.file.read": lambda call: _linux_read(call, catalog, executor),
        "linux.document.read": lambda call: _linux_document_read(call, catalog, executor),
        "linux.file.edit": lambda call: _linux_file_edit(call, catalog, executor),
        "linux.service.status": lambda call: _linux_service(call, catalog, executor),
        "linux.package.status": lambda call: _linux_package(call, catalog, executor),
        "linux.service.restart": lambda call: _linux_restart(call, catalog, executor),
        "linux.package.install": lambda call: _linux_install(call, catalog, executor),
    }
    return [ToolRegistration(definitions[name], handler) for name, handler in handlers.items()]


def _target(call: ToolCall, catalog: TargetCatalog, family: str) -> tuple[Target, object]:
    target = catalog.resolve(family, str(call.arguments["target_ref"]))
    return target, catalog.credentials.resolve(target.credential_ref)


def _failure(call: ToolCall, error: InfrastructureError) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="error",
        error=ToolError(code=error.code, message=error.message, retryable=error.retryable),
    )


def _cancelled(call: ToolCall) -> bool:
    return bool(call.cancellation_requested and call.cancellation_requested())


def _source(family: str, target: Target, section: str) -> SourceRef:
    return SourceRef(
        source_ref_id=str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"orion:{family}:{target.target_ref}:{section}")
        ),
        source_kind=family,
        source_id=target.target_ref,
        label=target.display_name,
        section=section,
        retrieved_at=datetime.now(UTC),
    )


def _success(call: ToolCall, data: object, target: Target, section: str) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="success",
        data=data,
        sources=(_source(target.family, target, section),),
        read_progress=ReadProgress(
            observation_id=f"{target.family}:{target.target_ref}:{section}",
            coverage=call.arguments,
            certainty="confirmed",
        ),
    )


def _with_errors(call: ToolCall, operation: Callable[[], ToolResult]) -> ToolResult:
    try:
        return operation()
    except InfrastructureError as error:
        return _failure(call, error)


def _linux_inspect(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "linux")
        sections = tuple(call.arguments.get("sections", ["cpu", "memory", "disk", "network"]))
        observed = _bound(executor.inspect(target, credential, sections))
        returned_sections = (
            sorted(str(section) for section in observed if str(section) in sections)
            if isinstance(observed, dict)
            else []
        )
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "sections": observed,
                "evidence_scope": {
                    "kind": "point_in_time_snapshot",
                    "requested_sections": list(sections),
                    "returned_sections": returned_sections,
                    "missing_sections": [
                        section for section in sections if section not in returned_sections
                    ],
                    "limitations": [
                        "No history, baseline, workload requirements, or thresholds/SLOs were "
                        "collected; this snapshot cannot establish health, sustained utilization, "
                        "or workload capacity.",
                        "Memory totals and SwapFree do not measure current swap-in/swap-out "
                        "activity.",
                    ],
                },
            },
            target,
            "system.inspect",
        )

    return _with_errors(call, operation)


def _linux_read(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    def operation() -> ToolResult:
        path = str(call.arguments["path"])
        _validate_path(path)
        target, credential = _target(call, catalog, "linux")
        payload = executor.read_file(
            target,
            credential,
            path,
            int(call.arguments.get("offset", 0)),
            int(call.arguments.get("length", 16384)),
        )
        try:
            text = payload.decode("utf-8")
            data: object = {
                "target_ref": target.target_ref,
                "path": path,
                "text": text[:65536],
                "binary": False,
            }
        except UnicodeDecodeError:
            data = {
                "target_ref": target.target_ref,
                "path": path,
                "binary": True,
                "bytes_read": len(payload),
            }
        return _success(call, data, target, "file.read")

    return _with_errors(call, operation)


def _linux_document_read(
    call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor
) -> ToolResult:
    def operation() -> ToolResult:
        path = str(call.arguments["path"])
        _validate_path(path)
        target, credential = _target(call, catalog, "linux")
        payload = _read_document_bytes(executor, target, credential, path)
        try:
            document = read_document(
                path,
                payload,
                cursor=int(call.arguments.get("cursor", 0)),
                limit=int(call.arguments.get("limit", 50)),
                sheet=str(call.arguments["sheet"]) if "sheet" in call.arguments else None,
                cell_range=str(call.arguments["range"]) if "range" in call.arguments else None,
            )
        except DocumentCodecError as error:
            raise InfrastructureError(error.code, error.message) from error
        return _success(
            call,
            {"target_ref": target.target_ref, "path": path, **document},
            target,
            "document.read",
        )

    return _with_errors(call, operation)


def _linux_file_edit(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    def operation() -> ToolResult:
        path = str(call.arguments["path"])
        _validate_path(path)
        target, credential = _target(call, catalog, "linux")
        payload = _read_document_bytes(executor, target, credential, path, require_regular=True)
        raw_operations = call.arguments["operations"]
        if not isinstance(raw_operations, list) or not all(
            isinstance(item, dict) for item in raw_operations
        ):
            raise InfrastructureError("invalid_input", "Document edit operations are invalid.")
        operations = [dict(item) for item in raw_operations]
        try:
            edited, summary = edit_document(path, payload, operations)
        except DocumentCodecError as error:
            raise InfrastructureError(error.code, error.message) from error
        if not summary["changed"]:
            return _success(
                call,
                {
                    "target_ref": target.target_ref,
                    "path": path,
                    "changed": False,
                    **summary,
                    "verification": {"status": "verified"},
                },
                target,
                "file.edit",
            )
        if _cancelled(call):
            raise InfrastructureError("cancelled", "Operation cancelled before dispatch.")
        temporary_path = str(PurePosixPath(path).parent / f".orion-{uuid.uuid4().hex}.tmp")
        try:
            try:
                executor.write_file(target, credential, temporary_path, edited)
                temporary = _read_document_bytes(
                    executor, target, credential, temporary_path, require_regular=True
                )
                if temporary != edited:
                    raise InfrastructureError(
                        "verification_failed", "Temporary file content did not match the edit."
                    )
                verify_document_edit(path, temporary, operations)
            except DocumentCodecError as error:
                raise InfrastructureError(error.code, error.message) from error
            # Preserve the target mode before the replace.  This remains a distinct stage so a
            # preparation failure proves the original destination was not replaced.
            executor.prepare_file_replacement(target, credential, temporary_path, path)
            try:
                executor.replace_file(target, credential, temporary_path, path)
            except InfrastructureError:
                return _unknown(call, target, path, None)
            try:
                final = _read_document_bytes(
                    executor, target, credential, path, require_regular=True
                )
                if final != edited:
                    return _unknown(call, target, path, None)
                verification = verify_document_edit(path, final, operations)
            except (InfrastructureError, DocumentCodecError):
                return _unknown(call, target, path, None)
            return _success(
                call,
                {
                    "target_ref": target.target_ref,
                    "path": path,
                    "changed": True,
                    **summary,
                    "verification": verification,
                },
                target,
                "file.edit",
            )
        finally:
            # mv removes the candidate on success.  On every other path this is best-effort
            # cleanup of only Orion's UUID-generated sibling temporary file.
            _cleanup_temporary(executor, target, credential, temporary_path)

    return _with_errors(call, operation)


def _read_document_bytes(
    executor: LinuxExecutor,
    target: Target,
    credential: object,
    path: str,
    *,
    require_regular: bool = False,
) -> bytes:
    metadata = executor.file_metadata(target, credential, path)
    if require_regular and metadata.file_type != "regular":
        raise InfrastructureError(
            "unsupported_file_type", "Document editing requires a regular file."
        )
    if metadata.size > MAX_DOCUMENT_BYTES:
        raise InfrastructureError("too_large", "Document exceeds Orion's safe read limit.")
    payload = executor.read_file(target, credential, path, 0, MAX_DOCUMENT_BYTES + 1)
    if len(payload) > MAX_DOCUMENT_BYTES:
        raise InfrastructureError("too_large", "Document exceeds Orion's safe read limit.")
    return payload


def _cleanup_temporary(
    executor: LinuxExecutor, target: Target, credential: object, temporary_path: str
) -> None:
    try:
        executor.remove_file(target, credential, temporary_path)
    except InfrastructureError:
        pass


def _linux_service(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    return _with_errors(call, lambda: _linux_status_result(call, catalog, executor, "service"))


def _linux_package(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    return _with_errors(call, lambda: _linux_status_result(call, catalog, executor, "package"))


def _linux_status_result(
    call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor, kind: str
) -> ToolResult:
    target, credential = _target(call, catalog, "linux")
    name = str(call.arguments[kind])
    observed = (
        executor.service_status(target, credential, name)
        if kind == "service"
        else executor.package_status(target, credential, name)
    )
    return _success(
        call,
        {"target_ref": target.target_ref, kind: name, "observed": _bound(observed)},
        target,
        f"{kind}.status",
    )


def _linux_restart(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "linux")
        service = str(call.arguments["service"])
        executor.service_preflight(target, credential, service)
        if _cancelled(call):
            raise InfrastructureError("cancelled", "Operation cancelled before dispatch.")
        try:
            executor.restart_service(target, credential, service)
        except InfrastructureError:
            observed = _try_service(executor, target, credential, service)
            return _unknown(call, target, service, observed)
        observed = _try_service(executor, target, credential, service)
        if observed is None:
            return _unknown(call, target, service, None)
        if observed.get("active_state") not in {"active", "running"}:
            raise InfrastructureError(
                "verification_failed", "Service did not reach an active state."
            )
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "changed": True,
                "service": service,
                "observed_state": _bound(observed),
                "verification": {"status": "verified"},
            },
            target,
            "service.restart",
        )

    return _with_errors(call, operation)


def _linux_install(call: ToolCall, catalog: TargetCatalog, executor: LinuxExecutor) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "linux")
        package = str(call.arguments["package"])
        version = call.arguments.get("version")
        requested = str(version) if version is not None else None
        current = executor.package_status(target, credential, package)
        if current.get("installed") and (requested is None or current.get("version") == requested):
            return _success(
                call,
                {
                    "target_ref": target.target_ref,
                    "changed": False,
                    "package": package,
                    "requested_version": requested,
                    "observed_version": current.get("version"),
                    "verification": {"status": "verified"},
                },
                target,
                "package.install",
            )
        if _cancelled(call):
            raise InfrastructureError("cancelled", "Operation cancelled before dispatch.")
        try:
            executor.install_package(target, credential, package, requested)
        except InfrastructureError:
            return _unknown(
                call, target, package, _try_package(executor, target, credential, package)
            )
        final = _try_package(executor, target, credential, package)
        if final is None:
            return _unknown(call, target, package, None)
        if not final.get("installed") or (
            requested is not None and final.get("version") != requested
        ):
            raise InfrastructureError(
                "verification_failed", "Package did not reach the requested installed state."
            )
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "changed": True,
                "package": package,
                "requested_version": requested,
                "observed_version": final.get("version"),
                "verification": {"status": "verified"},
            },
            target,
            "package.install",
        )

    return _with_errors(call, operation)


def _try_service(
    executor: LinuxExecutor, target: Target, credential: object, service: str
) -> dict[str, object] | None:
    try:
        return dict(executor.service_status(target, credential, service))
    except InfrastructureError:
        return None


def _try_package(
    executor: LinuxExecutor, target: Target, credential: object, package: str
) -> dict[str, object] | None:
    try:
        return dict(executor.package_status(target, credential, package))
    except InfrastructureError:
        return None


def _unknown(call: ToolCall, target: Target, name: str, observed: object) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="error",
        error=ToolError(
            code="outcome_unknown",
            message="The side effect may have happened; final state is unknown.",
        ),
        data={
            "target_ref": target.target_ref,
            "subject": name,
            "observed": _bound(observed) if observed else None,
        },
    )


def _validate_path(path: str) -> None:
    parts = PurePosixPath(path).parts
    if not path.startswith("/") or any(part in {".", ".."} for part in parts):
        raise InfrastructureError(
            "invalid_input", "Path must be absolute and cannot contain dot components."
        )


def _sanitize(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key)[:128]: _sanitize(item)
            for key, item in value.items()
            if str(key).lower()
            not in {
                "url",
                "token",
                "password",
                "authorization",
                "securejsondata",
                "secure_json_data",
            }
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value[:200]]
    if isinstance(value, str):
        return value[:4000]
    return value


def _bound(value: object) -> object:
    return _sanitize(value)
