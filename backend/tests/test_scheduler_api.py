"""Scheduler authenticated routes, exact scope boundaries and interactive tools."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from conftest import ScriptedBackend

from orion.access.remote import RemoteAccessConfig, hash_password
from orion.api.app import create_app
from orion.bootstrap import build_application
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, RuntimeScope
from orion.scheduler.contracts import TaskInput
from orion.tool_runtime.mutation_authorization import MutationMode
from orion.tool_runtime.runner import ToolRunner

NOW = datetime(2026, 1, 1, tzinfo=UTC)
ORIGIN = "https://orion.example.test"
INPUT = {"prompt": "Read current status.", "schedule_kind": "once", "run_at": NOW.isoformat()}


def _scope(app, project_id=None) -> RuntimeScope:  # type: ignore[no-untyped-def]
    return RuntimeScope(
        session_id=app.store.create_session(project_id=project_id),
        principal_id="local",
        workspace_id="local",
        project_id=project_id,
    )


@pytest.mark.anyio
async def test_task_crud_history_bounds_scope_and_conflicts(tmp_path: Path) -> None:
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]))
    app = api.state.application
    app.scheduler.clock = lambda: NOW
    plain = _scope(app)
    project = app.store.create_project("Project")["project_id"]
    owner = _scope(app, project)
    other_project = app.store.create_project("Other Project")["project_id"]
    other = _scope(app, other_project)
    foreign_session = app.store.create_session(principal_id="other")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://test"
    ) as client:
        created = await client.post(
            "/api/scheduler/tasks", json={**INPUT, "session_id": owner.session_id}
        )
        assert created.status_code == 201
        task = created.json()
        task_id = task["task_id"]
        url = f"/api/scheduler/tasks/{task_id}"
        params = {"session_id": owner.session_id}
        assert task["project_id"] == project
        assert app.store.session_identity(task["execution_session_id"])["project_id"] == project
        assert (await client.get("/api/scheduler/tasks", params=params)).json() == [task]
        assert (await client.get(url, params=params)).json() == task
        assert (await client.get(url + "/history", params=params)).json() == []
        for session in (plain.session_id, other.session_id, foreign_session):
            for method, suffix in (
                ("GET", ""),
                ("GET", "/history"),
                ("POST", "/pause"),
                ("POST", "/resume"),
                ("DELETE", ""),
            ):
                response = await client.request(
                    method, url + suffix, params={"session_id": session}
                )
                assert response.status_code == 404
        for endpoint in ("/api/scheduler/tasks", url + "/history"):
            for limit in (0, 101):
                assert (
                    await client.get(endpoint, params={**params, "limit": limit})
                ).status_code == 422
        paused = await client.post(url + "/pause", params=params)
        assert paused.status_code == 200 and paused.json()["state"] == "paused"
        assert app.store.claim_scheduled_run(NOW) is None
        assert (await client.post(url + "/resume", params=params)).json()["state"] == "enabled"
        claim = app.store.claim_scheduled_run(NOW)
        for method, suffix in (("POST", "/pause"), ("POST", "/resume"), ("DELETE", "")):
            assert (await client.request(method, url + suffix, params=params)).status_code == 409
        app.store.finish_scheduled_run(claim["run_id"], "completed", NOW)
        history = (await client.get(url + "/history", params=params)).json()
        assert len(history) == 1 and history[0]["status"] == "completed"
        assert (await client.post(url + "/resume", params=params)).status_code == 409
        assert (await client.delete(url, params=params)).status_code == 204
        assert (await client.get(url, params=params)).status_code == 404
        assert (await client.get("/api/scheduler/tasks", params=params)).json() == []
        for extra in (
            {"principal_id": "other"},
            {"mutation_mode": "auto"},
            {"prompt": "x" * 16001},
        ):
            result = await client.post(
                "/api/scheduler/tasks", json={**INPUT, **extra, "session_id": owner.session_id}
            )
            assert result.status_code == 422
        assert (await client.get("/api/scheduler/unknown")).status_code == 404
    app.store.close()


@pytest.mark.anyio
async def test_remote_scheduler_inventory_auth_and_exact_origin(tmp_path: Path) -> None:
    remote = RemoteAccessConfig(
        enabled=True,
        bind_host="0.0.0.0",
        public_origin=ORIGIN,
        password_hash=hash_password("scheduler-test-password"),
    )
    api = create_app(tmp_path / "orion.db", ScriptedBackend([]), remote_config=remote)
    app = api.state.application
    app.scheduler.clock = lambda: NOW
    owner = _scope(app)
    task = app.scheduler.create(owner, TaskInput.model_validate(INPUT))
    url = f"/api/scheduler/tasks/{task['task_id']}"
    routes = [
        ("POST", "/api/scheduler/tasks"),
        ("GET", "/api/scheduler/tasks"),
        ("GET", url),
        ("POST", url + "/pause"),
        ("POST", url + "/resume"),
        ("DELETE", url),
        ("GET", url + "/history"),
    ]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url=ORIGIN) as client:
        for method, path in routes:
            result = await client.request(
                method, path, headers={"origin": ORIGIN}, params={"session_id": owner.session_id}
            )
            assert result.status_code == 401
        login = await client.post(
            "/api/auth/login",
            headers={"origin": ORIGIN},
            json={"password": "scheduler-test-password"},
        )
        assert login.status_code == 200
        for method, path in routes:
            if method != "GET":
                for origin in (None, ORIGIN + "/", "https://evil.example"):
                    headers = {} if origin is None else {"origin": origin}
                    assert (
                        await client.request(
                            method, path, headers=headers, params={"session_id": owner.session_id}
                        )
                    ).status_code == 403
        result = await client.get("/api/scheduler/tasks", params={"session_id": owner.session_id})
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert (
            await client.post(
                url + "/pause", headers={"origin": ORIGIN}, params={"session_id": owner.session_id}
            )
        ).status_code == 200
        assert (await client.get("/api/scheduler/unknown")).status_code == 404
    app.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mode, decision",
    [
        (MutationMode.READ_ONLY, None),
        (MutationMode.AUTO, None),
        (MutationMode.CONFIRM, "allow"),
        (MutationMode.CONFIRM, "deny"),
    ],
)
async def test_interactive_scheduler_create_governance(
    tmp_path: Path, mode: MutationMode, decision: str | None
) -> None:
    call = ModelToolCall(call_id="create", tool_name="scheduler.create", arguments=INPUT)
    turns = [ModelTurn(tool_calls=(call,))]
    blocked = mode == MutationMode.READ_ONLY or decision == "deny"
    if blocked:
        turns.append(ModelTurn(tool_calls=(call.model_copy(update={"call_id": "repeat"}),)))
    turns.append(ModelTurn(assistant=AssistantMessage(content="Task management result.")))
    backend = ScriptedBackend(turns)
    app = build_application(tmp_path / "orion.db", backend)
    app.store.upsert_model_config("openai_compatible", "http://model.test", "fake", None)
    app.scheduler.clock = lambda: NOW
    owner = _scope(app)
    app.store.set_session_mutation_mode(owner.session_id, mode)
    request_id = app.runtime.begin(owner.session_id, "Create a task")
    running = asyncio.create_task(app.runtime.run(owner.session_id, request_id))
    if mode == MutationMode.CONFIRM:

        async def pending() -> None:
            while app.store.pending_authorization(request_id, call.call_id) is None:
                await asyncio.sleep(0)

        await asyncio.wait_for(pending(), timeout=5)
        assert app.scheduler.list_tasks(owner) == []
        pending_record = app.store.pending_authorization(request_id, call.call_id)
        assert pending_record["target_ref"] == "scheduler"
        assert INPUT["prompt"] not in str(pending_record)
        assert app.runtime.resolve_authorization(
            owner.session_id, request_id, call.call_id, decision == "allow"
        )
    outcome = await asyncio.wait_for(running, timeout=5)
    assert outcome.status == "completed"
    tasks = app.scheduler.list_tasks(owner)
    assert len(tasks) == (0 if blocked else 1)
    results = [
        item.payload["result"]
        for item in app.store.timeline(owner.session_id)
        if item.kind == "tool_result"
    ]
    assert results[0]["status"] == ("error" if blocked else "success")
    app.store.close()


@pytest.mark.anyio
async def test_all_scheduler_tools_classified_and_dispatch_scoped(tmp_path: Path) -> None:
    app = build_application(tmp_path / "orion.db", ScriptedBackend([]))
    app.scheduler.clock = lambda: NOW
    owner = _scope(app)
    runner = ToolRunner(app.registry)
    result = await runner.run_async(
        ModelToolCall(call_id="create", tool_name="scheduler.create", arguments=INPUT), owner
    )
    assert result.status == "success"
    task = result.data["result"]
    for action in ("list", "get", "pause", "resume", "history", "delete"):
        definition = app.registry.definition("scheduler." + action)
        assert definition.operation_kind == (
            "read" if action in {"list", "get", "history"} else "mutation"
        )
        args = {} if action == "list" else {"task_id": task["task_id"]}
        result = await runner.run_async(
            ModelToolCall(call_id=action, tool_name="scheduler." + action, arguments=args), owner
        )
        assert result.status == "success"
    assert app.registry.definition("scheduler.create").operation_kind == "mutation"
    app.store.close()
