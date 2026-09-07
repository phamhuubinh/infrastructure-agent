from __future__ import annotations

import json

import httpx
import pytest
from conftest import ScriptedBackend

from orion import bootstrap
from orion.api.app import create_app
from orion.contracts import AssistantMessage, ModelToolCall, ModelTurn, ToolCall, ToolResult
from orion.tool_runtime.infrastructure import infrastructure_definitions
from orion.tool_runtime.mutation_authorization import MutationAuthorizationConfigurationError
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistration


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
                    ModelToolCall(
                        call_id="expand",
                        tool_name=EXPAND_TOOL_NAME,
                        arguments={"tool_names": sorted(names)},
                    ),
                )
            ),
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
    if extra:
        # Invalid schema arguments trigger the existing recoverable-error loop.
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
        assert results[0]["error"]["model_recovery_required"] is False
    assert [call.call_id for call in seen] == (
        ["mutation", "read"]
        if expected is None
        else ["read", "recovery-read"]
        if extra
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
            "decision": "allow" if expected is None else "deny",
        }
    text = log.read_text(encoding="utf-8")
    assert "ORION_TEST_SECRET_TOKEN" not in text
    assert str(path) not in text
    assert "mutation_allowlist" not in "\n".join(
        line for line in text.splitlines() if "tool.authorization" in line
    )
    assembled.store.close()
