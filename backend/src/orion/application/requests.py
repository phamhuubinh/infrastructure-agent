"""Application-owned background admissions; reconnect observes instead of replaying."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime, RequestOutcome
from orion.contracts import RuntimeScope
from orion.persistence.sqlite import SQLiteStore


class RequestAdmissionError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__("Request admission unavailable: " + category)


class RequestService:
    def __init__(
        self, store: SQLiteStore, runtime: ChatRuntime, access: LocalAccessAdapter
    ) -> None:
        self.store, self.runtime, self.access = store, runtime, access
        self.tasks: dict[str, asyncio.Task[RequestOutcome]] = {}
        self.closed = False
        self.owner_loop: asyncio.AbstractEventLoop | None = None

    def _scope(self, scope: RuntimeScope) -> None:
        identity = self.store.session_identity(scope.session_id)
        if identity is None or any(
            identity[key] != getattr(scope, key)
            for key in ("principal_id", "workspace_id", "project_id", "endpoint_id")
        ):
            raise RequestAdmissionError("scope")
        try:
            self.access.principal_for_session(scope.principal_id, scope.workspace_id)
        except PermissionError:
            raise RequestAdmissionError("scope") from None
        if scope.project_id and self.store.project(scope.project_id) is None:
            raise RequestAdmissionError("project_unavailable")

    @staticmethod
    def _identity(scope: RuntimeScope, content: str, key: str) -> str:
        try:
            parsed = uuid.UUID(key)
        except (ValueError, AttributeError):
            raise RequestAdmissionError("client_key") from None
        if (
            parsed.version != 4
            or str(parsed) != key
            or not content
            or len(content.encode()) > 1_048_576
        ):
            raise RequestAdmissionError("input")
        return hashlib.sha256(
            json.dumps(
                {
                    "session_id": scope.session_id,
                    "principal_id": scope.principal_id,
                    "workspace_id": scope.workspace_id,
                    "project_id": scope.project_id,
                    "endpoint_id": scope.endpoint_id,
                    "content": content,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def admit(self, scope: RuntimeScope, content: str, client_key: str) -> tuple[str, bool]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            raise RequestAdmissionError("event_loop") from None
        if self.owner_loop is not None and self.owner_loop is not loop:
            raise RequestAdmissionError("event_loop")
        self.owner_loop = loop
        self._scope(scope)
        digest = self._identity(scope, content, client_key)
        if self.closed:
            raise RequestAdmissionError("closed")
        previous = self.store.request_admission(scope.principal_id, scope.workspace_id, client_key)
        if previous is None and len(self.tasks) >= 64:
            raise RequestAdmissionError("capacity")
        try:
            identity, created = self.store.admit_request(scope, client_key, digest)
        except PermissionError:
            raise RequestAdmissionError("identity_conflict") from None
        if created:
            try:
                self.runtime.adopt_admitted_request(scope.session_id, identity, content)
                task = loop.create_task(self.runtime.run(scope.session_id, identity))
                self.tasks[identity] = task
                task.add_done_callback(lambda result: self._finished(identity, result))
            except BaseException:
                self.store.complete_request(
                    identity, "failed", "Request admission interrupted before execution."
                )
                raise
        return identity, created

    def _finished(self, request_id: str, task: asyncio.Task[RequestOutcome]) -> None:
        if self.tasks.get(request_id) is task:
            self.tasks.pop(request_id)
        if not task.cancelled():
            # Runtime already records bounded failures; consume the task exception.
            task.exception()

    def cancel_admission(self, scope: RuntimeScope, content: str, client_key: str) -> str:
        """Reserve a cancelled nonce before a delayed/lost admission can execute it."""
        loop = asyncio.get_running_loop()
        if self.closed or (self.owner_loop is not None and self.owner_loop is not loop):
            raise RequestAdmissionError("closed_or_event_loop")
        self.owner_loop = loop
        self._scope(scope)
        digest = self._identity(scope, content, client_key)
        try:
            identity, created = self.store.admit_request(
                scope, client_key, digest, initial_status="cancelled"
            )
        except PermissionError:
            raise RequestAdmissionError("identity_conflict") from None
        if created:
            self.store.emit_event(identity, "request.cancelled", {})
        else:
            self.runtime.cancel(identity)
        return identity

    def running(self, request_id: str) -> bool:
        task = self.tasks.get(request_id)
        return task is not None and not task.done()

    async def close(self) -> None:
        self.closed = True
        tasks = tuple(self.tasks.values())
        for identity in tuple(self.tasks):
            self.runtime.cancel(identity)
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=30)
        for task in pending:
            task.cancel()
        if pending:
            _, remaining = await asyncio.wait(pending, timeout=30)
            if remaining:
                raise RuntimeError("Admitted request shutdown did not finish")
