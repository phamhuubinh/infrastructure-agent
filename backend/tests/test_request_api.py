"""Lost admission responses and disconnected observation cannot duplicate model work."""

import asyncio
import uuid

import httpx
import pytest
from conftest import ScriptedBackend
from starlette.requests import Request

from orion.api.app import create_app
from orion.chat.runtime import RequestCancelled
from orion.contracts import AssistantMessage, ModelTurn


@pytest.mark.anyio
async def test_stop_before_lost_admission_response_reserves_nonce_without_starting_model(tmp_path):
    backend = ScriptedBackend([ModelTurn(assistant=AssistantMessage(content="Must not execute"))])
    api = create_app(tmp_path / "orion.db", backend)
    app = api.state.application
    session = app.store.create_session()
    intent = {"content": "Cancel this exact intent", "client_request_id": str(uuid.uuid4())}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            stopped = await http.post(f"/api/sessions/{session}/request-cancellations", json=intent)
            assert stopped.status_code == 202 and stopped.json()["status"] == "cancelled"
            identity = stopped.json()["request_id"]
            # Delayed delivery or a lost-response retry must find the terminal nonce.
            delayed = await http.post(f"/api/sessions/{session}/requests", json=intent)
            assert delayed.status_code == 202 and delayed.json()["request_id"] == identity
            assert delayed.json()["status"] == "cancelled" and not app.requests.tasks
            duplicate = await http.post(
                f"/api/sessions/{session}/request-cancellations", json=intent
            )
            assert duplicate.json()["request_id"] == identity
            changed = await http.post(
                f"/api/sessions/{session}/request-cancellations",
                json={**intent, "content": "Other intent"},
            )
            assert changed.status_code == 409
            other = app.store.create_session()
            assert (
                await http.post(f"/api/sessions/{other}/request-cancellations", json=intent)
            ).status_code == 409
            assert len(app.store.events(identity)) == 1 and not backend.calls
    finally:
        await app.requests.close()
        app.store.close()


@pytest.mark.anyio
async def test_durable_admission_resume_pages_and_observer_disconnect_do_not_replay(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):
            entered.set()
            await release.wait()
            async for event in super().stream(messages, tools, settings, cancellation):
                yield event

    backend = WaitingBackend([ModelTurn(assistant=AssistantMessage(content="Completed once."))])
    api = create_app(tmp_path / "orion.db", backend)
    application = api.state.application
    application.store.upsert_model_config("openai_compatible", "http://model.test", "fixture", None)
    session = application.store.create_session()
    body = {"content": "Complete this once", "client_request_id": str(uuid.uuid4())}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            first = await http.post(f"/api/sessions/{session}/requests", json=body)
            assert first.status_code == 202
            identity = first.json()["request_id"]
            task = application.requests.tasks[identity]
            await asyncio.wait_for(entered.wait(), 5)
            repeated = await http.post(f"/api/sessions/{session}/requests", json=body)
            assert repeated.status_code == 202 and repeated.json()["request_id"] == identity
            conflict = await http.post(
                f"/api/sessions/{session}/requests", json={**body, "content": "Different"}
            )
            assert conflict.status_code == 409
            first_page = (await http.get(f"/api/requests/{identity}/event-page?limit=1")).json()
            assert len(first_page["events"]) == 1 and first_page["has_more"]
            cursor = first_page["next_cursor"]
            # ASGITransport buffers complete streams. Drive one response iterator
            # directly to exercise disconnect while the admitted model still waits.
            endpoint = next(
                route.endpoint
                for route in api.routes
                if getattr(route, "path", "") == "/api/requests/{request_id}/stream"
            )
            response = await endpoint(
                identity,
                Request({"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}}),
                after=None,
            )
            iterator = response.body_iterator
            assert "id: " in await anext(iterator)
            await iterator.aclose()
            assert application.requests.running(identity)
            release.set()
            await asyncio.wait_for(task, 5)
            final = await http.get(f"/api/requests/{identity}")
            assert final.json()["status"] == "completed" and len(backend.calls) == 1
            replay = await http.post(f"/api/sessions/{session}/requests", json=body)
            assert replay.json()["request_id"] == identity and len(backend.calls) == 1
            remaining = (
                await http.get(f"/api/requests/{identity}/event-page?after={cursor}")
            ).json()
            assert all(event["event_id"] != cursor for event in remaining["events"])
            stream = await http.get(f"/api/requests/{identity}/stream?after={cursor}")
            assert stream.status_code == 200 and "request.completed" in stream.text
            resumed = await http.get(
                f"/api/requests/{identity}/stream", headers={"Last-Event-ID": cursor}
            )
            assert resumed.status_code == 200 and resumed.text == stream.text
            conflict = await http.get(
                f"/api/requests/{identity}/stream?after={uuid.uuid4()}",
                headers={"Last-Event-ID": cursor},
            )
            assert conflict.status_code == 409
            assert (
                await http.get(
                    f"/api/requests/{identity}/stream", headers={"Last-Event-ID": "invalid"}
                )
            ).status_code == 422
            assert len(backend.calls) == 1
    finally:
        release.set()
        await application.requests.close()
        application.store.close()


@pytest.mark.anyio
async def test_pending_nonce_cancellation_stops_the_already_admitted_runtime(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()

    class WaitingBackend(ScriptedBackend):
        async def stream(self, messages, tools, settings, cancellation):
            entered.set()
            await release.wait()
            async for event in super().stream(messages, tools, settings, cancellation):
                yield event

    backend = WaitingBackend([ModelTurn(assistant=AssistantMessage(content="Too late"))])
    api = create_app(tmp_path / "orion.db", backend)
    app = api.state.application
    app.store.upsert_model_config("openai_compatible", "http://model.test", "fixture", None)
    session = app.store.create_session()
    intent = {"content": "Stop this active intent", "client_request_id": str(uuid.uuid4())}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            admitted = await http.post(f"/api/sessions/{session}/requests", json=intent)
            identity = admitted.json()["request_id"]
            task = app.requests.tasks[identity]
            await asyncio.wait_for(entered.wait(), 5)
            stopped = await http.post(f"/api/sessions/{session}/request-cancellations", json=intent)
            assert stopped.status_code == 202 and stopped.json()["request_id"] == identity
            with pytest.raises(RequestCancelled):
                await asyncio.wait_for(asyncio.shield(task), 5)
            assert app.store.request(identity)["status"] == "cancelled"
            retry = await http.post(f"/api/sessions/{session}/requests", json=intent)
            assert retry.json()["status"] == "cancelled" and not backend.calls
    finally:
        release.set()
        await app.requests.close()
        app.store.close()


@pytest.mark.anyio
async def test_event_cursor_is_request_scoped_and_native_admission_has_no_scope_override(tmp_path):
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    app = api.state.application
    session = app.store.create_session()
    first, second = (
        app.store.create_request(session, "completed"),
        app.store.create_request(session, "completed"),
    )
    app.store.emit_event(second, "request.failed", {"message": "Other request"})
    cursor = app.store.request_event_page(second, None)[0][0]["event_id"]
    foreign = app.store.create_session(principal_id="foreign")
    hidden = app.store.create_request(foreign, "completed")
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test"
        ) as http:
            assert (
                await http.get(f"/api/requests/{first}/event-page?after={cursor}")
            ).status_code == 409
            assert (
                await http.get(f"/api/requests/{first}/stream?after={cursor}")
            ).status_code == 409
            assert (await http.get(f"/api/requests/{hidden}")).status_code == 404
            body = {
                "content": "work",
                "client_request_id": str(uuid.uuid4()),
                "project_id": "forged",
            }
            assert (
                await http.post(f"/api/sessions/{session}/requests", json=body)
            ).status_code == 422
    finally:
        await app.requests.close()
        app.store.close()


def test_event_pages_use_stable_uuid_anchor_and_bound_payload_reads(store):
    session = store.create_session()
    request = store.create_request(session)
    for index in range(300):
        store.emit_event(request, "assistant.delta", {"content": str(index)})
    first, more = store.request_event_page(request, None, 256)
    assert len(first) == 256 and more
    anchor = first[-1]["event_id"]
    with store._connection:
        store._connection.execute(
            "DELETE FROM request_events WHERE event_id IN "
            "(SELECT event_id FROM request_events ORDER BY rowid LIMIT 100)"
        )
    store._connection.execute("VACUUM")
    final, more = store.request_event_page(request, anchor, 256)
    assert len(final) == 44 and not more and final[0]["payload"]["content"] == "256"
    large = store.create_request(session)
    store.emit_event(large, "assistant.delta", {"content": "x" * 1_048_577})
    with pytest.raises(ValueError, match="transport bound"):
        store.request_event_page(large, None)
