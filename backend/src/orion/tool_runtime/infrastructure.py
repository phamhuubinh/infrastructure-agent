"""Frozen semantic Linux, Grafana, and Zabbix tool families.

Transport clients receive only configured targets and server-side credentials.  The
handlers below are deliberately the only place operation data maps to those clients.
"""

from __future__ import annotations

import asyncio
import re
import threading
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath
from weakref import WeakKeyDictionary

from orion.contracts import SourceRef, ToolCall, ToolDefinition, ToolError, ToolResult
from orion.integrations.infrastructure import (
    GrafanaClient,
    HttpGrafanaClient,
    HttpZabbixClient,
    InfrastructureError,
    LinuxExecutor,
    SshLinuxExecutor,
    Target,
    TargetCatalog,
    ZabbixClient,
)
from orion.tool_runtime.registry import ToolHandler, ToolRegistration

TARGET = {"type": "string", "pattern": "^[a-z][a-z0-9._-]{0,63}$"}
IDENTIFIER = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9@+_.:-]{0,127}$"}
VERSION = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9.+:~_-]{0,127}$"}
UID = {"type": "string", "pattern": "^[A-Za-z0-9_-]{1,40}$"}
ID = {"type": "string", "pattern": "^[1-9][0-9]{0,18}$"}
DATE = {"type": "string", "format": "date-time", "maxLength": 40}
TEXT128 = {"type": "string", "minLength": 1, "maxLength": 128, "pattern": "^[^\\u0000-\\u001f]+$"}

# Infrastructure transports are synchronous but bounded (SSH and HTTP clients have
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
    grafana: GrafanaClient | None = None,
    zabbix: ZabbixClient | None = None,
) -> tuple[ToolRegistration, ...]:
    """Register whole configured families in the ordinary immutable snapshot."""
    registrations: list[ToolRegistration] = []
    if catalog.configured("linux"):
        registrations += _linux_registrations(catalog, linux or SshLinuxExecutor())
    if catalog.configured("grafana"):
        registrations += _grafana_registrations(catalog, grafana or HttpGrafanaClient())
    if catalog.configured("zabbix"):
        registrations += _zabbix_registrations(catalog, zabbix or HttpZabbixClient())
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
            description="Read one bounded range of a validated Linux file.",
            handler_key="linux.file.read",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "path": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 4096,
                        "pattern": "^/[^\\u0000-\\u001f]*$",
                    },
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
        "grafana.dashboard.get": ToolDefinition(
            name="grafana.dashboard.get",
            description="Get one bounded, sanitized Grafana dashboard.",
            handler_key="grafana.dashboard.get",
            input_schema={
                "type": "object",
                "properties": {"target_ref": TARGET, "dashboard_uid": UID},
                "required": ["target_ref", "dashboard_uid"],
                **closed,
            },
        ),
        "grafana.datasource.query": ToolDefinition(
            name="grafana.datasource.query",
            description="Run a bounded read-only query on an approved Grafana datasource.",
            handler_key="grafana.datasource.query",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "datasource_uid": UID,
                    "query": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 4000,
                        "pattern": "^[^\\u0000-\\u001f]+$",
                    },
                    "from": DATE,
                    "to": DATE,
                    "max_data_points": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "default": 500,
                    },
                },
                "required": ["target_ref", "datasource_uid", "query", "from", "to"],
                **closed,
            },
        ),
        "grafana.alert.list": ToolDefinition(
            name="grafana.alert.list",
            description="List bounded normalized Grafana alert states.",
            handler_key="grafana.alert.list",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "states": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "normal",
                                "alerting",
                                "pending",
                                "no_data",
                                "error",
                                "recovering",
                            ],
                        },
                        "minItems": 1,
                        "maxItems": 6,
                        "uniqueItems": True,
                    },
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
                },
                "required": ["target_ref"],
                **closed,
            },
        ),
        "grafana.annotation.create": ToolDefinition(
            name="grafana.annotation.create",
            description="Create one bounded Grafana annotation.",
            handler_key="grafana.annotation.create",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "time": DATE,
                    "time_end": DATE,
                    "text": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1000,
                        "pattern": "^[^\\u0000-\\u001f]+$",
                    },
                    "tags": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                            "pattern": "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,63}$",
                        },
                        "maxItems": 10,
                        "uniqueItems": True,
                        "default": [],
                    },
                    "dashboard_uid": UID,
                    "panel_id": {"type": "integer", "minimum": 1, "maximum": 2147483647},
                },
                "required": ["target_ref", "time", "text"],
                **closed,
            },
        ),
        "zabbix.host.get": ToolDefinition(
            name="zabbix.host.get",
            description="Get bounded Zabbix host summaries.",
            handler_key="zabbix.host.get",
            input_schema=_zabbix_list_schema(
                "host_ids", "name_contains", "monitored_only", 100, 50
            ),
        ),
        "zabbix.event.list": ToolDefinition(
            name="zabbix.event.list",
            description="List bounded normalized Zabbix events.",
            handler_key="zabbix.event.list",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "host_ids": _ids(50),
                    "severities": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": [
                                "not_classified",
                                "information",
                                "warning",
                                "average",
                                "high",
                                "disaster",
                            ],
                        },
                        "minItems": 1,
                        "maxItems": 6,
                        "uniqueItems": True,
                    },
                    "acknowledged": {"type": "boolean"},
                    "from": DATE,
                    "to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
                },
                "required": ["target_ref"],
                "additionalProperties": False,
            },
        ),
        "zabbix.history.get": ToolDefinition(
            name="zabbix.history.get",
            description="Get bounded history for explicit Zabbix item IDs.",
            handler_key="zabbix.history.get",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "item_ids": _ids(10),
                    "from": DATE,
                    "to": DATE,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500},
                },
                "required": ["target_ref", "item_ids", "from", "to"],
                "additionalProperties": False,
            },
        ),
        "zabbix.trigger.get": ToolDefinition(
            name="zabbix.trigger.get",
            description="Get bounded normalized Zabbix triggers.",
            handler_key="zabbix.trigger.get",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "trigger_ids": _ids(50),
                    "host_ids": _ids(50),
                    "only_problem": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
                },
                "required": ["target_ref"],
                "additionalProperties": False,
            },
        ),
        "zabbix.template.get": ToolDefinition(
            name="zabbix.template.get",
            description="Get bounded safe Zabbix template summaries.",
            handler_key="zabbix.template.get",
            input_schema=_zabbix_list_schema("template_ids", "name_contains", None, 100, 50),
        ),
        "zabbix.event.acknowledge": ToolDefinition(
            name="zabbix.event.acknowledge",
            description="Acknowledge specific Zabbix events and verify their state.",
            handler_key="zabbix.event.acknowledge",
            operation_kind="mutation",
            input_schema={
                "type": "object",
                "properties": {
                    "target_ref": TARGET,
                    "event_ids": _ids(50),
                    "message": {
                        "type": "string",
                        "maxLength": 500,
                        "pattern": "^[^\\u0000-\\u001f]*$",
                        "default": "",
                    },
                },
                "required": ["target_ref", "event_ids"],
                "additionalProperties": False,
            },
        ),
    }


def _ids(maximum: int) -> dict[str, object]:
    return {"type": "array", "items": ID, "minItems": 1, "maxItems": maximum, "uniqueItems": True}


def _zabbix_list_schema(
    ids: str, text: str, boolean: str | None, maximum: int, default: int
) -> dict[str, object]:
    properties: dict[str, object] = {
        "target_ref": TARGET,
        ids: _ids(50),
        text: TEXT128,
        "limit": {"type": "integer", "minimum": 1, "maximum": maximum, "default": default},
    }
    if boolean:
        properties[boolean] = {"type": "boolean", "default": True}
    return {
        "type": "object",
        "properties": properties,
        "required": ["target_ref"],
        "additionalProperties": False,
    }


def _linux_registrations(catalog: TargetCatalog, executor: LinuxExecutor) -> list[ToolRegistration]:
    definitions = _definitions()
    handlers = {
        "linux.system.inspect": lambda call: _linux_inspect(call, catalog, executor),
        "linux.file.read": lambda call: _linux_read(call, catalog, executor),
        "linux.service.status": lambda call: _linux_service(call, catalog, executor),
        "linux.package.status": lambda call: _linux_package(call, catalog, executor),
        "linux.service.restart": lambda call: _linux_restart(call, catalog, executor),
        "linux.package.install": lambda call: _linux_install(call, catalog, executor),
    }
    return [ToolRegistration(definitions[name], handler) for name, handler in handlers.items()]


def _grafana_registrations(catalog: TargetCatalog, client: GrafanaClient) -> list[ToolRegistration]:
    definitions = _definitions()
    handlers = {
        "grafana.dashboard.get": lambda call: _grafana_dashboard(call, catalog, client),
        "grafana.datasource.query": lambda call: _grafana_query(call, catalog, client),
        "grafana.alert.list": lambda call: _grafana_alerts(call, catalog, client),
        "grafana.annotation.create": lambda call: _grafana_annotation(call, catalog, client),
    }
    return [ToolRegistration(definitions[name], handler) for name, handler in handlers.items()]


def _zabbix_registrations(catalog: TargetCatalog, client: ZabbixClient) -> list[ToolRegistration]:
    definitions = _definitions()
    handlers = {
        "zabbix.host.get": lambda call: _zabbix_read(call, catalog, client, "host.get"),
        "zabbix.event.list": lambda call: _zabbix_read(call, catalog, client, "event.get"),
        "zabbix.history.get": lambda call: _zabbix_read(call, catalog, client, "history.get"),
        "zabbix.trigger.get": lambda call: _zabbix_read(call, catalog, client, "trigger.get"),
        "zabbix.template.get": lambda call: _zabbix_read(call, catalog, client, "template.get"),
        "zabbix.event.acknowledge": lambda call: _zabbix_ack(call, catalog, client),
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
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "sections": _bound(executor.inspect(target, credential, sections)),
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


def _grafana_dashboard(call: ToolCall, catalog: TargetCatalog, client: GrafanaClient) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "grafana")
        uid = str(call.arguments["dashboard_uid"])
        raw = client.dashboard_get(target, credential, uid)
        return _success(
            call,
            {"target_ref": target.target_ref, "dashboard_uid": uid, "dashboard": _sanitize(raw)},
            target,
            "dashboard.get",
        )

    return _with_errors(call, operation)


def _grafana_query(call: ToolCall, catalog: TargetCatalog, client: GrafanaClient) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "grafana")
        uid = str(call.arguments["datasource_uid"])
        kind = target.datasource_types.get(uid)
        if kind is None:
            kind = client.datasource_type(target, credential, uid)
        if kind not in {"prometheus", "loki"}:
            raise InfrastructureError(
                "invalid_input", "Datasource is not configured for a supported read-only adapter."
            )
        start, end = _interval(call.arguments["from"], call.arguments["to"], 31)
        result: object | None = None
        for attempt in range(3):
            try:
                result = client.datasource_query(
                    target,
                    credential,
                    uid,
                    str(call.arguments["query"]),
                    start,
                    end,
                    int(call.arguments.get("max_data_points", 500)),
                )
                break
            except InfrastructureError as error:
                if not error.retryable or attempt == 2:
                    raise
        return _success(
            call,
            {"target_ref": target.target_ref, "datasource_uid": uid, "result": _bound(result)},
            target,
            "datasource.query",
        )

    return _with_errors(call, operation)


def _grafana_alerts(call: ToolCall, catalog: TargetCatalog, client: GrafanaClient) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "grafana")
        raw = client.alert_list(target, credential)
        states = set(call.arguments.get("states", []))
        limit = int(call.arguments.get("limit", 100))
        items = raw if isinstance(raw, list) else []
        alerts = [_normalize_alert(_sanitize(item)) for item in items if isinstance(item, dict)][
            :limit
        ]
        if states:
            alerts = [
                item for item in alerts if isinstance(item, dict) and item.get("state") in states
            ]
        return _success(
            call, {"target_ref": target.target_ref, "alerts": alerts}, target, "alert.list"
        )

    return _with_errors(call, operation)


def _grafana_annotation(
    call: ToolCall, catalog: TargetCatalog, client: GrafanaClient
) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "grafana")
        start = str(call.arguments["time"])
        _parse_time(start)
        end = call.arguments.get("time_end")
        if end is not None:
            _interval(start, end, 31)
        if "panel_id" in call.arguments and "dashboard_uid" not in call.arguments:
            raise InfrastructureError("invalid_input", "panel_id requires dashboard_uid.")
        if _cancelled(call):
            raise InfrastructureError("cancelled", "Operation cancelled before dispatch.")
        payload = {key: value for key, value in call.arguments.items() if key != "target_ref"}
        try:
            annotation_id = client.annotation_create(target, credential, payload)
        except InfrastructureError:
            return _unknown(call, target, "annotation", None)
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "changed": True,
                "annotation_id": annotation_id,
                "time": start,
                **({"time_end": end} if end is not None else {}),
                "verification": {"status": "accepted", "annotation_id": annotation_id},
            },
            target,
            "annotation.create",
        )

    return _with_errors(call, operation)


def _zabbix_read(
    call: ToolCall, catalog: TargetCatalog, client: ZabbixClient, method: str
) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "zabbix")
        args = dict(call.arguments)
        args.pop("target_ref")
        _validate_zabbix_interval(call.tool_name, args)
        result: object | None = None
        for attempt in range(3):
            try:
                result = client.call(
                    target, credential, method, _zabbix_params(call.tool_name, args)
                )
                break
            except InfrastructureError as error:
                if not error.retryable or attempt == 2:
                    raise
        return _success(
            call,
            {"target_ref": target.target_ref, "results": _normalize_zabbix(call.tool_name, result)},
            target,
            call.tool_name.rsplit(".", 1)[-1],
        )

    return _with_errors(call, operation)


def _zabbix_ack(call: ToolCall, catalog: TargetCatalog, client: ZabbixClient) -> ToolResult:
    def operation() -> ToolResult:
        target, credential = _target(call, catalog, "zabbix")
        event_ids = [str(value) for value in call.arguments["event_ids"]]
        raw = client.call(
            target,
            credential,
            "event.get",
            {"eventids": event_ids, "output": ["eventid", "acknowledged"]},
        )
        records = raw if isinstance(raw, list) else []
        found = {
            str(item.get("eventid"))
            for item in records
            if isinstance(item, dict) and isinstance(item.get("eventid"), (str, int))
        }
        missing = [event_id for event_id in event_ids if event_id not in found]
        if missing:
            raise InfrastructureError("not_found", "One or more requested events were not found.")
        pending = [
            str(item.get("eventid"))
            for item in records
            if isinstance(item, dict) and str(item.get("acknowledged")) not in {"1", "true", "True"}
        ]
        if not pending:
            return _success(
                call,
                {
                    "target_ref": target.target_ref,
                    "changed": False,
                    "event_ids": event_ids,
                    "acknowledged_event_ids": event_ids,
                    "verification": {"status": "verified"},
                },
                target,
                "event.acknowledge",
            )
        if _cancelled(call):
            raise InfrastructureError("cancelled", "Operation cancelled before dispatch.")
        try:
            client.call(
                target,
                credential,
                "event.acknowledge",
                {
                    "eventids": pending,
                    "message": str(call.arguments.get("message", "")),
                    "action": 6,
                },
            )
        except InfrastructureError:
            return _unknown(call, target, "events", None)
        try:
            verified = client.call(
                target,
                credential,
                "event.get",
                {"eventids": pending, "output": ["eventid", "acknowledged"]},
            )
        except InfrastructureError:
            return _unknown(call, target, "events", None)
        confirmed = (
            [
                str(item.get("eventid"))
                for item in verified
                if isinstance(item, dict) and str(item.get("acknowledged")) in {"1", "true", "True"}
            ]
            if isinstance(verified, list)
            else []
        )
        if set(confirmed) != set(pending):
            return _unknown(call, target, "events", {"acknowledged_event_ids": confirmed})
        return _success(
            call,
            {
                "target_ref": target.target_ref,
                "changed": True,
                "event_ids": event_ids,
                "acknowledged_event_ids": confirmed,
                "verification": {"status": "verified"},
            },
            target,
            "event.acknowledge",
        )

    return _with_errors(call, operation)


def _validate_path(path: str) -> None:
    parts = PurePosixPath(path).parts
    if not path.startswith("/") or any(part in {".", ".."} for part in parts):
        raise InfrastructureError(
            "invalid_input", "Path must be absolute and cannot contain dot components."
        )


def _interval(start: object, end: object, max_days: int) -> tuple[str, str]:
    first = _parse_time(start)
    second = _parse_time(end)
    if second <= first or second - first > timedelta(days=max_days):
        raise InfrastructureError(
            "invalid_input", "Timestamp interval is outside the allowed bound."
        )
    return str(start), str(end)


def _validate_zabbix_interval(name: str, args: dict[str, object]) -> None:
    has_start, has_end = "from" in args, "to" in args
    if has_start != has_end:
        raise InfrastructureError("invalid_input", "Both from and to are required together.")
    if has_start:
        _interval(args["from"], args["to"], 7 if name == "zabbix.history.get" else 31)


def _zabbix_params(name: str, args: dict[str, object]) -> dict[str, object]:
    """Map each semantic operation to fixed Zabbix JSON-RPC parameters."""
    raw_limit = args.get("limit", 100)
    if not isinstance(raw_limit, int):
        raise InfrastructureError("invalid_input", "Invalid result limit.")
    limit = raw_limit
    if name == "zabbix.host.get":
        params = {
            "output": ["hostid", "host", "name", "status"],
            "limit": limit,
        }
        if "host_ids" in args:
            params["hostids"] = args["host_ids"]
        if "name_contains" in args:
            params["search"] = {"host": args["name_contains"]}
        if args.get("monitored_only", True):
            params["filter"] = {"status": "0"}
        return params
    if name == "zabbix.event.list":
        params = {
            "output": ["eventid", "name", "severity", "clock", "acknowledged"],
            "limit": limit,
        }
        if "host_ids" in args:
            params["hostids"] = args["host_ids"]
        if "severities" in args:
            severity_map = {
                "not_classified": 0,
                "information": 1,
                "warning": 2,
                "average": 3,
                "high": 4,
                "disaster": 5,
            }
            severities = args["severities"]
            if not isinstance(severities, list) or not all(
                isinstance(value, str) for value in severities
            ):
                raise InfrastructureError("invalid_input", "Invalid event severities.")
            params["severities"] = [
                severity_map[value] for value in severities if value in severity_map
            ]
        if "acknowledged" in args:
            params["acknowledged"] = args["acknowledged"]
        _add_zabbix_time(params, args)
        return params
    if name == "zabbix.history.get":
        params = {
            "output": ["itemid", "clock", "value", "ns"],
            "itemids": args["item_ids"],
            "limit": limit,
        }
        _add_zabbix_time(params, args)
        return params
    if name == "zabbix.trigger.get":
        params = {
            "output": ["triggerid", "description", "priority", "value"],
            "limit": limit,
        }
        if "trigger_ids" in args:
            params["triggerids"] = args["trigger_ids"]
        if "host_ids" in args:
            params["hostids"] = args["host_ids"]
        if args.get("only_problem", False):
            params["only_true"] = True
        return params
    if name == "zabbix.template.get":
        params = {
            "output": ["templateid", "host", "name"],
            "limit": limit,
        }
        if "template_ids" in args:
            params["templateids"] = args["template_ids"]
        if "name_contains" in args:
            params["search"] = {"host": args["name_contains"]}
        return params
    raise InfrastructureError("invalid_input", "Unsupported Zabbix semantic operation.")


def _add_zabbix_time(params: dict[str, object], args: dict[str, object]) -> None:
    if "from" not in args:
        return
    params["time_from"] = int(_parse_time(args["from"]).timestamp())
    params["time_till"] = int(_parse_time(args["to"]).timestamp())


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


def _normalize_alert(value: object) -> object:
    if not isinstance(value, dict):
        return value
    raw = str(value.get("state", value.get("ruleState", ""))).lower().replace(" ", "_")
    aliases = {
        "ok": "normal",
        "inactive": "normal",
        "firing": "alerting",
        "nodata": "no_data",
    }
    state = aliases.get(raw, raw)
    if state not in {"normal", "alerting", "pending", "no_data", "error", "recovering"}:
        raise InfrastructureError("unavailable", "Grafana alert state is unavailable.")
    value["state"] = state
    return value


def _parse_time(value: object) -> datetime:
    text = str(value)
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?(?:Z|[+-]\d{2}:\d{2})", text
    ):
        raise InfrastructureError(
            "invalid_input", "Timestamps must be timezone-aware RFC 3339 values."
        )
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise InfrastructureError(
            "invalid_input", "Timestamps must be valid RFC 3339 values."
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InfrastructureError(
            "invalid_input", "Timestamps must be timezone-aware RFC 3339 values."
        )
    return parsed


def _normalize_zabbix(name: str, value: object) -> object:
    records = value if isinstance(value, list) else []
    if name == "zabbix.event.list":
        severity = {
            0: "not_classified",
            1: "information",
            2: "warning",
            3: "average",
            4: "high",
            5: "disaster",
        }
        return [
            {
                "event_id": str(item.get("eventid", ""))[:128],
                "name": str(item.get("name", ""))[:4000],
                "severity": severity.get(int(item.get("severity", -1)), "not_classified"),
                "acknowledged": str(item.get("acknowledged", "0")).lower() in {"1", "true"},
                "clock": str(item.get("clock", ""))[:64],
            }
            for item in records
            if isinstance(item, dict)
        ]
    if name == "zabbix.trigger.get":
        severity = {
            0: "not_classified",
            1: "information",
            2: "warning",
            3: "average",
            4: "high",
            5: "disaster",
        }
        return [
            {
                "trigger_id": str(item.get("triggerid", ""))[:128],
                "description": str(item.get("description", ""))[:4000],
                "severity": severity.get(int(item.get("priority", -1)), "not_classified"),
                "state": "problem" if str(item.get("value", "0")) == "1" else "normal",
            }
            for item in records
            if isinstance(item, dict)
        ]
    return _bound(records)
