"""Outbound-only authenticated worker channel. Reconnect never replays work."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from orion_endpoint.executor import Executor
from orion_endpoint.protocol import (
    MAX_INFLIGHT,
    MAX_MESSAGE,
    OPERATIONS,
    TRANSFERS,
    Cancel,
    Ping,
    Request,
    Result,
    Welcome,
    decode,
    validate_url,
)

LOG = logging.getLogger("orion.worker")


async def serve_connection(socket: Any, executor: Executor) -> None:
    await socket.send((await executor.hello()).model_dump_json())
    welcome = decode(await asyncio.wait_for(socket.recv(), 10))
    if not isinstance(welcome, Welcome):
        raise ValueError("handshake")
    tasks: dict[str, asyncio.Task[None]] = {}
    seen: set[str] = set()

    async def execute(message: Request) -> None:
        mutation = False
        entry = (OPERATIONS | TRANSFERS).get(message.operation)
        mutation = entry is not None and entry[1] == "mutation"
        result = Result(request_id=message.request_id)
        try:
            result.data = await executor.execute(message.operation, message.arguments)
        except asyncio.CancelledError:
            result.error = "outcome_unknown" if mutation else "cancelled"
        except PermissionError:
            result.error = "policy_denied"
        except FileExistsError:
            result.error = "conflict"
        except (ValueError, KeyError):
            result.error = "invalid_input"
        except Exception:
            result.error = "outcome_unknown" if mutation else "unavailable"
        try:
            encoded = result.model_dump_json()
            if len(encoded.encode()) > MAX_MESSAGE:
                encoded = Result(
                    request_id=message.request_id, error="unavailable"
                ).model_dump_json()
            await socket.send(encoded)
        except Exception:
            LOG.info("result_transport_unavailable")
        finally:
            tasks.pop(message.request_id, None)

    try:
        while True:
            message = decode(await asyncio.wait_for(socket.recv(), 45))
            if isinstance(message, Ping) and message.type == "ping":
                await socket.send(Ping(type="pong").model_dump_json())
            elif isinstance(message, Cancel):
                if message.request_id in tasks:
                    tasks[message.request_id].cancel()
            elif isinstance(message, Request):
                if message.operation not in OPERATIONS | TRANSFERS:
                    raise ValueError("unknown_operation")
                if message.request_id in seen or len(tasks) >= MAX_INFLIGHT:
                    raise ValueError("duplicate_or_capacity")
                # Bounded replay window: close and re-handshake instead of forgetting IDs.
                if len(seen) >= 4096:
                    raise ValueError("connection_rotation")
                seen.add(message.request_id)
                tasks[message.request_id] = asyncio.create_task(execute(message))
                LOG.info("operation %s %s", message.operation, message.request_id)
            else:
                raise ValueError("protocol")
    finally:
        for task in list(tasks.values()):
            task.cancel()
        await asyncio.gather(*list(tasks.values()), return_exceptions=True)
        await executor.close()


async def run(server: str, endpoint_id: str, credential: str, executor: Executor) -> None:
    server = validate_url(server)
    channel = server.replace("https://", "wss://").replace("http://", "ws://")
    delay = 1
    try:
        while True:
            try:
                async with connect(
                    f"{channel}/api/endpoints/{endpoint_id}/worker",
                    additional_headers={"Authorization": f"Bearer {credential}"},
                    compression=None,
                    max_size=MAX_MESSAGE,
                    max_queue=4,
                    ping_interval=15,
                    ping_timeout=15,
                    close_timeout=3,
                ) as socket:
                    LOG.info("connected")
                    delay = 1
                    await serve_connection(socket, executor)
            except asyncio.CancelledError:
                raise
            except (ConnectionClosed, OSError, ValueError, TimeoutError):
                LOG.info("disconnected")
            except Exception:
                # Authentication/transport errors never include a credential-bearing repr.
                LOG.info("connection_unavailable")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    finally:
        with contextlib.suppress(Exception):
            await executor.close()
