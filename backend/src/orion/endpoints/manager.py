"""Process-local bounded RPC state; no scope, credentials or payloads persisted."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from orion.endpoints.persistence import EndpointStore
from orion_endpoint.protocol import (
    MAX_INFLIGHT,
    MAX_MESSAGE,
    OPERATIONS,
    TRANSFERS,
    Cancel,
    Hello,
    Ping,
    Request,
    Result,
    ScreenFrame,
    Welcome,
    decode,
)


class EndpointError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Connection:
    socket: WebSocket
    hello: Hello
    pending: dict[str, tuple[asyncio.Future[Result], bool]] = field(default_factory=dict)
    mutation_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_pong: float = field(default_factory=time.monotonic)

    async def send(self, message: Request | Cancel | Ping | Welcome) -> None:
        async with self.send_lock:
            await self.socket.send_text(message.model_dump_json())


class EndpointManager:
    def __init__(
        self,
        store: EndpointStore,
        *,
        timeout: float = 20,
        heartbeat: float = 15,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self.timeout, self.heartbeat, self.clock = timeout, heartbeat, clock
        self.connections: dict[str, Connection] = {}
        self.controllers: dict[str, str] = {}
        self.views: dict[str, dict[str, Any]] = {}
        self.observations: dict[str, tuple[float, dict[str, int]]] = {}
        self.closed = False

    def list(self) -> list[dict[str, Any]]:
        return [
            {
                **row,
                "target_ref": row["endpoint_id"],
                "system_summary": self.observations[row["endpoint_id"]][1]
                if row["endpoint_id"] in self.observations
                and self.clock() - self.observations[row["endpoint_id"]][0] < 300
                else None,
                "online": row["endpoint_id"] in self.connections and row["revoked_at"] is None,
                "geometry": [
                    display.model_dump()
                    for display in self.connections[row["endpoint_id"]].hello.geometry
                ]
                if row["endpoint_id"] in self.connections
                else [],
            }
            for row in self.store.list()
        ]

    def configured(self, target_ref: str) -> bool:
        row = self.store.get(target_ref)
        return row is not None and row["revoked_at"] is None

    async def attach(self, endpoint_id: str, socket: WebSocket) -> None:
        if self.closed or endpoint_id in self.connections:
            await socket.close(code=1008)
            return
        await socket.accept()
        connection: Connection | None = None
        ping_task: asyncio.Task[None] | None = None
        try:
            message = decode(await asyncio.wait_for(socket.receive_text(), 10))
            if not isinstance(message, Hello) or not set(message.capabilities) <= OPERATIONS.keys():
                raise ValueError("handshake")
            # Recheck after the handshake await; two simultaneous connections cannot win.
            if endpoint_id in self.connections or not self.configured(endpoint_id):
                raise ValueError("identity")
            connection = Connection(socket, message, last_pong=self.clock())
            self.connections[endpoint_id] = connection
            self.store.update_connection(endpoint_id, message, "connected")
            await connection.send(Welcome())

            async def heartbeat() -> None:
                assert connection is not None
                while True:
                    await asyncio.sleep(self.heartbeat)
                    if self.clock() - connection.last_pong > self.heartbeat * 3:
                        await socket.close(code=1001)
                        return
                    await connection.send(Ping(type="ping"))

            ping_task = asyncio.create_task(heartbeat())
            while True:
                incoming = decode(await asyncio.wait_for(socket.receive_text(), self.heartbeat * 4))
                if isinstance(incoming, Ping) and incoming.type == "pong":
                    connection.last_pong = self.clock()
                    self.store.update_connection(endpoint_id, None, "connected")
                elif isinstance(incoming, Result):
                    waiting = connection.pending.get(incoming.request_id)
                    if waiting is not None and not waiting[0].done():
                        waiting[0].set_result(incoming)
                    # Late cancelled responses are data to discard, never new work.
                else:
                    raise ValueError("protocol")
        except Exception:
            pass
        finally:
            if ping_task:
                ping_task.cancel()
                await asyncio.gather(ping_task, return_exceptions=True)
            if connection is not None:
                await self.detach(endpoint_id, connection)
            with contextlib.suppress(Exception):
                await socket.close()

    async def detach(self, endpoint_id: str, connection: Connection) -> None:
        if self.connections.get(endpoint_id) is connection:
            del self.connections[endpoint_id]
            self.controllers.pop(endpoint_id, None)
            self.observations.pop(endpoint_id, None)
            for key, row in list(self.views.items()):
                if row["endpoint_id"] == endpoint_id:
                    del self.views[key]
                    self.store.audit(endpoint_id, "manual_session_stopped")
            self.store.update_connection(endpoint_id, None, "disconnected")
        for future, mutation in connection.pending.values():
            if not future.done():
                future.set_exception(
                    EndpointError("outcome_unknown" if mutation else "interrupted")
                )
        with contextlib.suppress(Exception):
            await connection.socket.close(code=1001)

    async def dispatch(
        self,
        endpoint_id: str,
        operation: str,
        arguments: dict[str, Any],
        cancellation: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        if cancellation and cancellation():
            raise EndpointError("cancelled")
        if self.closed or not self.configured(endpoint_id):
            raise EndpointError("unavailable")
        connection = self.connections.get(endpoint_id)
        entry = (OPERATIONS | TRANSFERS).get(operation)
        if connection is None or entry is None:
            raise EndpointError("unavailable")
        model, kind = entry
        arguments = model.model_validate(arguments).model_dump()
        if operation not in TRANSFERS and operation not in connection.hello.capabilities:
            raise EndpointError("unavailable")
        if operation in TRANSFERS and "file.write" not in connection.hello.capabilities:
            raise EndpointError("policy_denied")
        if len(connection.pending) >= MAX_INFLIGHT:
            raise EndpointError("busy")
        mutation = kind == "mutation"
        # Queue admission is bounded by the same pending capacity, including lock waiters.
        request_id = uuid.uuid4().hex
        future: asyncio.Future[Result] = asyncio.get_running_loop().create_future()
        connection.pending[request_id] = (future, False)
        dispatched = False
        lock_acquired = False
        try:
            if mutation:
                await asyncio.wait_for(connection.mutation_lock.acquire(), self.timeout)
                lock_acquired = True
            if cancellation and cancellation():
                raise EndpointError("cancelled")
            if self.connections.get(endpoint_id) is not connection or not self.configured(
                endpoint_id
            ):
                raise EndpointError("unavailable")
            outgoing = Request(request_id=request_id, operation=operation, arguments=arguments)
            if len(outgoing.model_dump_json().encode()) > MAX_MESSAGE:
                raise EndpointError("invalid_input")
            # From the send attempt onward delivery may have happened, even if it raises.
            dispatched = True
            connection.pending[request_id] = (future, mutation)
            await connection.send(outgoing)
            started = self.clock()
            while not future.done():
                if cancellation and cancellation():
                    raise EndpointError("outcome_unknown" if mutation else "cancelled")
                if self.clock() - started >= self.timeout:
                    raise EndpointError("outcome_unknown" if mutation else "timeout")
                # Cancellation predicate belongs to the runtime; wait on the response future.
                await asyncio.wait({future}, timeout=min(0.1, self.timeout))
            result = future.result()
            if result.error:
                raise EndpointError(result.error)
            if operation == "system.inspect":
                safe = {
                    key: result.data[key]
                    for key in ("cpu_count", "memory_total", "memory_available")
                    if type(result.data.get(key)) is int and 0 <= result.data[key] <= 2**63 - 1
                }
                self.observations[endpoint_id] = (self.clock(), safe)
            if operation == "screen.capture":
                frame = ScreenFrame.model_validate(result.data)
                raw = base64.b64decode(frame.image_b64, validate=True)
                if len(raw) > 900_000 or not raw.startswith(b"\xff\xd8"):
                    raise EndpointError("invalid_result")
                return frame.model_dump()
            return result.data
        except asyncio.CancelledError:
            if dispatched and mutation:
                raise EndpointError("outcome_unknown") from None
            raise
        except EndpointError:
            raise
        except Exception:
            raise EndpointError(
                "outcome_unknown" if dispatched and mutation else "interrupted"
            ) from None
        finally:
            if dispatched and not future.done():
                with contextlib.suppress(Exception):
                    await connection.send(Cancel(request_id=request_id))
            connection.pending.pop(request_id, None)
            if not future.done():
                future.cancel()
            else:
                # Retrieve disconnect exceptions even for cancelled/queued calls.
                with contextlib.suppress(BaseException):
                    future.exception()
            if lock_acquired:
                connection.mutation_lock.release()

    async def revoke(self, endpoint_id: str) -> None:
        self.store.revoke(endpoint_id)
        connection = self.connections.get(endpoint_id)
        if connection:
            await self.detach(endpoint_id, connection)

    async def close(self) -> None:
        self.closed = True
        for endpoint_id, connection in list(self.connections.items()):
            await self.detach(endpoint_id, connection)
        self.controllers.clear()
        self.views.clear()
