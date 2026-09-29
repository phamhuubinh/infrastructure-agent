from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from conftest import ScriptedBackend

from orion import bootstrap
from orion.api.app import create_app
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, ToolCall, ToolResult
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.infrastructure import infrastructure_definitions
from orion.tool_runtime.mutation_authorization import (
    MutationAuthorizationConfigurationError,
    MutationMode,
)
from orion.tool_runtime.registry import ToolRegistration


def _configuration() -> dict[str, object]:
    return {
        "targets": {
            "linux": [
                {"target_ref": "monitor", "ssh_alias": "monitor"},
                {"target_ref": "other", "ssh_alias": "other"},
            ]
        },
        "credentials": {"unused": "ORION_TEST_SECRET_TOKEN"},
    }


@pytest.mark.parametrize(
    "entries",
    [
        None,
        "allow all",
        [{}],
        [{"tool_name": "linux.service.restart", "target_ref": 3}],
        [{"tool_name": "linux.*", "target_ref": "monitor"}],
        [{"tool_name": "linux.service.status", "target_ref": "monitor"}],
        [{"tool_name": "linux.service.restart", "target_ref": "missing"}],
        [{"tool_name": "linux.service.restart", "target_ref": "monitor", "override": True}],
        [{"tool_name": "linux.service.restart", "target_ref": "monitor"}] * 2,
    ],
)
def test_invalid_entries_fail_production_startup(tmp_path, monkeypatch, entries) -> None:  # type: ignore[no-untyped-def]
    configuration = _configuration()
    configuration["mutation_allowlist"] = entries
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(path))

    with pytest.raises(MutationAuthorizationConfigurationError) as caught:
        create_app(tmp_path / "orion.db", ScriptedBackend([]))

    assert "ORION_TEST_SECRET_TOKEN" not in str(caught.value)
    assert str(path) not in str(caught.value)


@pytest.mark.parametrize("contents", [None, "{broken", "[]", "null", "\udcff"])
def test_unreadable_configuration_fails_before_runtime(tmp_path, monkeypatch, contents) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "private-policy.json"
    if contents is not None:
        path.write_bytes(contents.encode("utf-8", errors="surrogateescape"))
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(path))

    with pytest.raises(MutationAuthorizationConfigurationError) as caught:
        create_app(tmp_path / "orion.db", ScriptedBackend([]))

    assert str(path) not in str(caught.value)
    assert not (tmp_path / "orion.db").exists()


@pytest.mark.anyio
@pytest.mark.parametrize("project", [False, True])
@pytest.mark.parametrize(
    "allowlisted,target,tool_name,extra,expected",
    [
        (False, "monitor", "linux.service.restart", {}, "operation_blocked"),
        (True, "monitor", "linux.service.restart", {}, None),
        (True, "other", "linux.service.restart", {}, "operation_blocked"),
        (True, "monitor", "linux.package.install", {}, "operation_blocked"),
        (True, "monitor", "linux.service.restart", {"mutation_allowlist": []}, "invalid_input"),
    ],
)
async def test_http_chat_and_project_enforce_policy_and_audit(
    tmp_path, monkeypatch, project, allowlisted, target, tool_name, extra, expected
) -> None:  # type: ignore[no-untyped-def]
    configuration = _configuration()
    if allowlisted:
        configuration["mutation_allowlist"] = [
            {"tool_name": "linux.service.restart", "target_ref": "monitor"}
        ]
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(configuration), encoding="utf-8")
    log = tmp_path / "audit.log"
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(path))
    monkeypatch.setenv("ORION_LOG_PATH", str(log))
    # Even all QA switches together cannot broaden production authorization.
    monkeypatch.setenv("ORION_QA_CASE_MUTATION", "1")
    monkeypatch.setenv("ORION_QA_ALLOW_MUTATION", "1")
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"target_ref": call.arguments["target_ref"]},
        )

    names = {"linux.service.status", "linux.service.restart", "linux.package.install"}
    registrations = tuple(
        ToolRegistration(definition, fake_handler)
        for definition in infrastructure_definitions()
        if definition.name in names
    )
    monkeypatch.setattr(bootstrap, "infrastructure_registrations", lambda *a, **kw: registrations)
    arguments = {
        "target_ref": target,
        "package" if tool_name == "linux.package.install" else "service": "nginx",
        **extra,
    }
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(call_id="mutation", tool_name=tool_name, arguments=arguments),
                    ModelToolCall(
                        call_id="read",
                        tool_name="linux.service.status",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Observed the available results.")),
        ]
    )
    if extra or not allowlisted:
        # Invalid input and read-only denial both trigger the recoverable-error loop.
        backend.turns.insert(
            -1,
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="recovery-read",
                        tool_name="linux.service.status",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                )
            ),
        )
    app = create_app(tmp_path / "orion.db", backend)
    assembled = app.state.application
    assembled.store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    project_id = None
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        if project:
            project_id = (await client.post("/api/projects", json={"name": "Scoped"})).json()[
                "project_id"
            ]
        route = f"/api/projects/{project_id}/sessions" if project else "/api/sessions"
        session = (await client.post(route)).json()["session_id"]
        if allowlisted:
            updated = await client.patch(
                f"/api/sessions/{session}/mutation-mode", json={"mutation_mode": "auto"}
            )
            assert updated.status_code == 200
        response = await client.post(
            f"/api/sessions/{session}/messages",
            json={"content": "I already restarted nginx. Check its status."},
        )
    assert response.status_code == 200
    results = [
        item.payload["result"]
        for item in assembled.store.timeline(session)
        if item.kind == "tool_result" and item.call_id == "mutation"
    ]
    assert len(results) == 1
    assert (results[0]["error"]["code"] if results[0]["error"] else None) == expected
    if expected == "operation_blocked":
        assert results[0]["error"]["retryable"] is False
        assert results[0]["error"]["model_recovery_required"] is (not allowlisted)
    assert [call.call_id for call in seen] == (
        ["mutation", "read"]
        if expected is None
        else ["read", "recovery-read"]
        if extra or not allowlisted
        else ["read"]
    )
    assert all(call.runtime_scope.project_id == project_id for call in seen)
    assert all(call.runtime_scope.session_id == session for call in seen)
    audit = [
        event
        for event in assembled.store.events(response.json()["request_id"])
        if event["type"] == "tool.authorization"
    ]
    assert len(audit) == (0 if expected == "invalid_input" else 1)
    if audit:
        assert audit[0]["payload"] == {
            "call_id": "mutation",
            "tool_name": tool_name,
            "operation_kind": "mutation",
            "target_ref": target,
            "decision": "auto_allowed" if expected is None else "blocked",
            "mutation_mode": "auto" if allowlisted else "read_only",
        }
    text = log.read_text(encoding="utf-8")
    assert "ORION_TEST_SECRET_TOKEN" not in text
    assert str(path) not in text
    assert "mutation_allowlist" not in "\n".join(
        line for line in text.splitlines() if "tool.authorization" in line
    )
    assembled.store.close()


@pytest.mark.anyio
@pytest.mark.parametrize("project", [False, True])
@pytest.mark.parametrize("decision", ["allow", "deny"])
async def test_confirm_mode_resolves_one_exact_call(
    tmp_path, monkeypatch, project: bool, decision: str
) -> None:  # type: ignore[no-untyped-def]
    configuration = _configuration()
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(
            call_id=call.call_id,
            tool_name=call.tool_name,
            status="success",
            data={"target_ref": call.arguments["target_ref"]},
        )

    registrations = tuple(
        ToolRegistration(definition, fake_handler)
        for definition in infrastructure_definitions()
        if definition.name in {"linux.service.restart", "linux.service.status"}
    )
    monkeypatch.setattr(bootstrap, "infrastructure_registrations", lambda *a, **kw: registrations)
    turns = [
        ModelTurn(
            tool_calls=(
                ModelToolCall(
                    call_id="change",
                    tool_name="linux.service.restart",
                    arguments={"target_ref": "monitor", "service": "nginx"},
                ),
            )
        ),
    ]
    if decision == "deny":
        turns.append(
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="repeat",
                        tool_name="linux.service.restart",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                    ModelToolCall(
                        call_id="read",
                        tool_name="linux.service.status",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                )
            )
        )
    turns.append(ModelTurn(assistant=AssistantMessage(content="Finished.")))
    app = create_app(tmp_path / "orion.db", ScriptedBackend(turns))
    store = app.state.application.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    runtime = app.state.application.runtime
    clock = [0.0]
    runtime._monotonic_clock = lambda: clock[0]  # noqa: SLF001 - deterministic human wait.
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        project_id = None
        if project:
            project_id = (await client.post("/api/projects", json={"name": "Scoped"})).json()[
                "project_id"
            ]
        route = f"/api/projects/{project_id}/sessions" if project else "/api/sessions"
        session = (await client.post(route)).json()["session_id"]
        assert (await client.get(f"/api/sessions/{session}")).json()["mutation_mode"] == "read_only"
        assert (
            await client.patch(
                f"/api/sessions/{session}/mutation-mode", json={"mutation_mode": "confirm"}
            )
        ).status_code == 200
        assert (await client.get(f"/api/sessions/{session}")).json()["mutation_mode"] == "confirm"
        assert (
            await client.post(
                f"/api/sessions/{session}/messages", json={"content": "Restart nginx"}
            )
        ).status_code == 409
        other = (await client.post("/api/sessions")).json()["session_id"]
        request_id = runtime.begin(session, "Please restart nginx")
        task = asyncio.create_task(runtime.run(session, request_id))
        for _ in range(100):
            if store.pending_authorization(request_id, "change") is not None:
                break
            await asyncio.sleep(0.01)
        pending = store.pending_authorization(request_id, "change")
        assert pending is not None and pending["state"] == "pending"
        assert pending["session_id"] == session
        assert len(pending["arguments_digest"]) == 64
        assert seen == []
        assert (
            await client.patch(
                f"/api/sessions/{session}/mutation-mode", json={"mutation_mode": "auto"}
            )
        ).status_code == 409
        events = store.events(request_id)
        assert (
            len([event for event in events if event["type"] == "tool.authorization_required"]) == 1
        )
        endpoint = f"/api/sessions/{session}/requests/{request_id}/tool-authorizations/change"
        wrong = await client.post(
            f"/api/sessions/{other}/requests/{request_id}/tool-authorizations/change",
            json={"decision": "allow"},
        )
        assert wrong.status_code == 404
        assert (
            await client.post(endpoint + "-other", json={"decision": "allow"})
        ).status_code == 409
        if decision == "allow":
            # Human thinking time exceeds the ordinary request deadline.
            clock[0] = 180.0
        assert (await client.post(endpoint, json={"decision": decision})).status_code == 200
        assert (await client.post(endpoint, json={"decision": decision})).status_code == 409
        outcome = await task
        assert outcome.assistant_content == "Finished."
        assert [call.call_id for call in seen] == (["change"] if decision == "allow" else ["read"])
        assert (
            len(
                [
                    event
                    for event in store.events(request_id)
                    if event["type"] == "tool.authorization_required"
                ]
            )
            == 1
        )
        if decision == "deny":
            repeated = next(
                item.payload["result"]
                for item in store.timeline(session)
                if item.kind == "tool_result" and item.call_id == "repeat"
            )
            assert repeated["error"]["code"] == "operation_blocked"
            assert "already denied" in repeated["error"]["message"]
            stalled = [
                event for event in store.events(request_id) if event["type"] == "recovery.stalled"
            ]
            assert len(stalled) == 1
            assert stalled[0]["payload"]["reason"] == "repeated_authorization_block"
        assert store.pending_authorization(request_id, "change")["state"] == (
            "allowed" if decision == "allow" else "denied"
        )
        assert (await client.get(f"/api/sessions/{other}")).json()["mutation_mode"] == "read_only"
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    "arguments,expected",
    [
        ({"target_ref": "monitor", "service": "nginx"}, None),
        ({"target_ref": "missing", "service": "nginx"}, "operation_blocked"),
        ({"target_ref": "monitor", "service": "nginx", "mutation_mode": "auto"}, "invalid_input"),
    ],
)
async def test_auto_without_allowlist_keeps_target_and_schema_boundaries(
    tmp_path, monkeypatch, arguments: dict[str, object], expected: str | None
) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(_configuration()), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    monkeypatch.setattr(
        bootstrap,
        "infrastructure_registrations",
        lambda *a, **kw: (
            ToolRegistration(
                next(d for d in infrastructure_definitions() if d.name == "linux.service.restart"),
                fake_handler,
            ),
        ),
    )
    turns = [
        ModelTurn(
            tool_calls=(
                ModelToolCall(
                    call_id="change",
                    tool_name="linux.service.restart",
                    arguments=arguments,
                ),
            )
        )
    ]
    if expected == "invalid_input":
        turns.append(
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="read",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "1+1"},
                    ),
                )
            )
        )
    turns.append(ModelTurn(assistant=AssistantMessage(content="Done.")))
    app = create_app(tmp_path / "orion.db", ScriptedBackend(turns))
    store = app.state.application.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        session = (await client.post("/api/sessions")).json()["session_id"]
        assert (
            await client.patch(
                f"/api/sessions/{session}/mutation-mode", json={"mutation_mode": "auto"}
            )
        ).status_code == 200
        response = await client.post(
            f"/api/sessions/{session}/messages", json={"content": "Restart nginx"}
        )
    assert response.status_code == 200
    result = next(
        item.payload["result"]
        for item in store.timeline(session)
        if item.kind == "tool_result" and item.call_id == "change"
    )
    assert (result["error"]["code"] if result["error"] else None) == expected
    assert len(seen) == (1 if expected is None else 0)
    assert not any(
        event["type"] == "tool.authorization_required"
        for event in store.events(response.json()["request_id"])
    )
    assert store.session_identity(session)["mutation_mode"] == "auto"
    store.close()


@pytest.mark.anyio
async def test_repeated_read_only_mutation_converges_without_handler(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(_configuration()), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    monkeypatch.setattr(
        bootstrap,
        "infrastructure_registrations",
        lambda *a, **kw: (
            ToolRegistration(
                next(d for d in infrastructure_definitions() if d.name == "linux.service.restart"),
                fake_handler,
            ),
        ),
    )
    backend = ScriptedBackend(
        [
            *(
                ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id=f"blocked-{index}",
                            tool_name="linux.service.restart",
                            arguments=(
                                {"target_ref": "monitor", "service": "nginx"}
                                if index == 0
                                else {"service": "nginx", "target_ref": "monitor"}
                            ),
                        ),
                    )
                )
                for index in range(2)
            ),
            ModelTurn(assistant=AssistantMessage(content="This chat is read-only.")),
        ]
    )
    app = create_app(tmp_path / "orion.db", backend)
    store = app.state.application.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    session = store.create_session()
    outcome = await app.state.application.runtime.submit(session, "Restart nginx")
    assert outcome.assistant_content == "This chat is read-only."
    assert seen == []
    results = [item for item in store.timeline(session) if item.kind == "tool_result"]
    assert len(results) == 2
    assert all(item.payload["result"]["error"]["code"] == "operation_blocked" for item in results)
    stalled = [
        event for event in store.events(outcome.request_id) if event["type"] == "recovery.stalled"
    ]
    assert len(stalled) == 1
    assert stalled[0]["payload"]["reason"] == "repeated_authorization_block"
    assert backend.calls[-1][1] == ()
    store.close()


@pytest.mark.anyio
@pytest.mark.parametrize("ceiling", ["hard_deny", "allowlist"])
async def test_repeated_server_policy_block_converges_and_permits_read(
    tmp_path, monkeypatch, ceiling: str
) -> None:  # type: ignore[no-untyped-def]
    configuration = _configuration()
    if ceiling == "allowlist":
        configuration["mutation_allowlist"] = [
            {"tool_name": "linux.service.restart", "target_ref": "monitor"}
        ]
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    monkeypatch.setattr(
        bootstrap,
        "infrastructure_registrations",
        lambda *a, **kw: tuple(
            ToolRegistration(definition, fake_handler)
            for definition in infrastructure_definitions()
            if definition.name in {"linux.service.restart", "linux.service.status"}
        ),
    )
    target = "monitor" if ceiling == "hard_deny" else "other"
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="first",
                        tool_name="linux.service.restart",
                        arguments={"target_ref": target, "service": "nginx"},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="repeat",
                        tool_name="linux.service.restart",
                        arguments={"service": "nginx", "target_ref": target},
                    ),
                    ModelToolCall(
                        call_id="read",
                        tool_name="linux.service.status",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Reported the blocked operation.")),
        ]
    )
    assembled = bootstrap.build_application(
        tmp_path / "orion.db",
        backend,
        blocked_tool_operation_kinds=(
            frozenset({"mutation"}) if ceiling == "hard_deny" else frozenset()
        ),
    )
    store = assembled.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    session = store.create_session()
    store.set_session_mutation_mode(session, MutationMode.AUTO)
    outcome = await assembled.runtime.submit(session, "Restart and check nginx")
    assert outcome.assistant_content == "Reported the blocked operation."
    assert [call.call_id for call in seen] == ["read"]
    results = {
        item.call_id: item.payload["result"]
        for item in store.timeline(session)
        if item.kind == "tool_result"
    }
    assert set(results) == {"first", "repeat", "read"}
    assert results["first"]["error"]["code"] == "operation_blocked"
    assert results["first"]["error"]["model_recovery_required"] is False
    assert results["repeat"]["error"]["code"] == "operation_blocked"
    assert results["repeat"]["error"]["model_recovery_required"] is True
    assert results["read"]["status"] == "success"
    stalled = [
        event for event in store.events(outcome.request_id) if event["type"] == "recovery.stalled"
    ]
    assert len(stalled) == 1
    assert stalled[0]["payload"]["reason"] == "repeated_authorization_block"
    assert backend.calls[-1][1] == ()
    store.close()


@pytest.mark.anyio
async def test_different_mutation_after_policy_block_has_normal_authorization(
    tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    configuration = _configuration()
    configuration["mutation_allowlist"] = [
        {"tool_name": "linux.service.restart", "target_ref": "monitor"}
    ]
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(configuration), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    monkeypatch.setattr(
        bootstrap,
        "infrastructure_registrations",
        lambda *a, **kw: (
            ToolRegistration(
                next(d for d in infrastructure_definitions() if d.name == "linux.service.restart"),
                fake_handler,
            ),
        ),
    )
    backend = ScriptedBackend(
        [
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="blocked",
                        tool_name="linux.service.restart",
                        arguments={"target_ref": "other", "service": "nginx"},
                    ),
                )
            ),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="allowed",
                        tool_name="linux.service.restart",
                        arguments={"target_ref": "monitor", "service": "nginx"},
                    ),
                )
            ),
            ModelTurn(assistant=AssistantMessage(content="Restarted the permitted target.")),
        ]
    )
    assembled = bootstrap.build_application(tmp_path / "orion.db", backend)
    store = assembled.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    session = store.create_session()
    store.set_session_mutation_mode(session, MutationMode.AUTO)
    outcome = await assembled.runtime.submit(session, "Restart the permitted target")
    assert outcome.assistant_content == "Restarted the permitted target."
    assert [call.call_id for call in seen] == ["allowed"]
    results = {
        item.call_id: item.payload["result"]
        for item in store.timeline(session)
        if item.kind == "tool_result"
    }
    assert results["blocked"]["error"]["code"] == "operation_blocked"
    assert results["allowed"]["status"] == "success"
    assert not any(
        event["type"] == "recovery.stalled" for event in store.events(outcome.request_id)
    )
    store.close()


@pytest.mark.anyio
async def test_cancel_pending_authorization_never_dispatches(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    config = tmp_path / "infrastructure.json"
    config.write_text(json.dumps(_configuration()), encoding="utf-8")
    monkeypatch.setenv("ORION_INFRASTRUCTURE_CONFIG", str(config))
    seen: list[ToolCall] = []

    def fake_handler(call: ToolCall) -> ToolResult:
        seen.append(call)
        return ToolResult(call_id=call.call_id, tool_name=call.tool_name, status="success")

    monkeypatch.setattr(
        bootstrap,
        "infrastructure_registrations",
        lambda *a, **kw: (
            ToolRegistration(
                next(d for d in infrastructure_definitions() if d.name == "linux.service.restart"),
                fake_handler,
            ),
        ),
    )
    app = create_app(
        tmp_path / "orion.db",
        ScriptedBackend(
            [
                ModelTurn(
                    tool_calls=(
                        ModelToolCall(
                            call_id="change",
                            tool_name="linux.service.restart",
                            arguments={"target_ref": "monitor", "service": "nginx"},
                        ),
                    )
                ),
            ]
        ),
    )
    store = app.state.application.store
    store.upsert_model_config("openai_compatible", "http://model.test/v1", "fake", None)
    session = store.create_session()
    from orion.tool_runtime.mutation_authorization import MutationMode

    store.set_session_mutation_mode(session, MutationMode.CONFIRM)
    runtime = app.state.application.runtime
    request_id = runtime.begin(session, "restart")
    task = asyncio.create_task(runtime.run(session, request_id))
    for _ in range(100):
        if store.pending_authorization(request_id, "change") is not None:
            break
        await asyncio.sleep(0.01)
    assert store.pending_authorization(request_id, "change") is not None
    assert runtime.cancel(request_id)
    with pytest.raises(Exception, match="Request cancelled"):
        await task
    assert seen == []
    assert store.pending_authorization(request_id, "change")["state"] == "cancelled"
    assert not runtime.resolve_authorization(session, request_id, "change", True)
    store.close()


def test_restart_expires_pending_without_replaying(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "orion.db"
    store = SQLiteStore(path)
    session = store.create_session()
    request_id = store.create_request(session)
    store.start_request(request_id)
    store.create_pending_authorization(
        request_id, "change", session, "linux.service.restart", "monitor", "a" * 64, {}
    )
    store.close()
    reopened = SQLiteStore(path)
    reopened.expire_pending_authorizations()
    assert reopened.pending_authorization(request_id, "change")["state"] == "expired"
    assert reopened.request(request_id)["status"] == "failed"
    reopened.close()
