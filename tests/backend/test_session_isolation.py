from __future__ import annotations

import json
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.agent.conversation_store import ConversationStore
from src.agent.contracts import AgentAction, AgentDecision, DecisionKind
from src.agent.canonical_factory import create_canonical_session_agent
from src.backend.dependencies import AppState
from src.backend.routers.query import query
from src.model.agent_backend import AgentModelBackend
from src.shared.config import OrionConfig
from src.shared.execution.tool_result import ToolResult
from src.tool.capability_result import CapabilityStatus
from src.tool.target_preflight import EnvironmentFingerprint


class _Store:
    def __init__(self, session_id: str, **_kwargs: object) -> None:
        self.session_id = session_id


class _QueuedAssessmentModel(AgentModelBackend):
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses

    def assess(self, _request: object) -> str:
        raise AssertionError("configured Agent v2 must use controller calls")

    def complete(self, _prompt: str) -> str:
        return self.responses.pop(0)


def _wire(
    kind: str,
    *,
    capability_id: str | None = None,
    target_ref: str | None = None,
    answer: str | None = None,
) -> str:
    if kind == "action":
        if capability_id is None:
            raise ValueError(
                "action requires capability_id"
            )

        decision = AgentDecision(
            kind=DecisionKind.ACTION,
            goal="Follow the request.",
            action=AgentAction(
                capability_id=capability_id,
                target_ref=target_ref,
            ),
        )
    elif kind == "final":
        if answer is None:
            raise ValueError(
                "final requires answer"
            )

        decision = AgentDecision(
            kind=DecisionKind.FINAL,
            goal="Follow the request.",
            answer=answer,
        )
    else:
        raise ValueError(
            f"unsupported test decision: {kind}"
        )

    return json.dumps(
        decision.to_wire()
    )

def _reachable_monitor(*_args: object, **_kwargs: object) -> EnvironmentFingerprint:
    return EnvironmentFingerprint(
        target="monitor",
        config_hash="test",
        reachable=True,
        backend_type="local",
        os_family="linux",
        init_system="systemd",
        privilege_level="test",
        available_binaries=frozenset({"lscpu", "free"}),
        has_procfs=True,
        has_sysfs=True,
    )


def _state() -> AppState:
    state = AppState.__new__(AppState)
    state.target_store_path = "targets.json"
    state._state_lock = threading.RLock()
    state.dsn = None
    state.use_postgresql = False
    state._server_name = "sv1"
    state._model = None
    state.agent = mock.MagicMock()
    state.agent.model_backend.complete = mock.MagicMock()
    state.web_sessions = {}
    state.web_agents = {}
    state._session_locks = {}
    state.rag_service_url = "http://rag-service:8080"
    state.reload_models_if_changed = mock.MagicMock()
    return state


def test_prepare_query_reuses_only_the_same_session_agent() -> None:
    state = _state()
    created_agents: list[mock.MagicMock] = []

    def build_agent(**kwargs: object) -> mock.MagicMock:
        agent = mock.MagicMock()
        agent.conversation_store = kwargs["conversation_store"]
        created_agents.append(agent)
        return agent

    with (
        mock.patch("src.backend.dependencies.SQLiteConversationStore", _Store),
        mock.patch(
            "src.backend.dependencies.create_canonical_session_agent",
            side_effect=build_agent,
        ),
    ):
        _, alpha_agent, alpha_lock = state.prepare_query("alpha")
        _, alpha_agent_again, alpha_lock_again = state.prepare_query("alpha")
        _, beta_agent, beta_lock = state.prepare_query("beta")

    assert alpha_agent is alpha_agent_again
    assert alpha_lock is alpha_lock_again
    assert beta_agent is not alpha_agent
    assert beta_lock is not alpha_lock
    assert alpha_agent.conversation_store is state.web_sessions["alpha"]
    assert beta_agent.conversation_store is state.web_sessions["beta"]
    assert len(created_agents) == 2


def test_web_session_factory_isolates_v2_target_context_and_runtime_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_store = tmp_path / "targets.json"
    target_store.write_text(json.dumps({"targets": {"monitor": {"backend": "local"}}}))
    alpha = create_canonical_session_agent(
        target_store_path=str(target_store),
        config=OrionConfig(
            servers={},
            active_server_name="",
            tools={},
        ),
        model_backend=_QueuedAssessmentModel(
            [
                _wire(
                    "action",
                    capability_id="host.get_cpu",
                ),
                _wire(
                    "action",
                    capability_id="host.get_cpu",
                    target_ref="monitor",
                ),
                _wire(
                    "final",
                    answer="CPU observed for monitor.",
                ),
                _wire(
                    "action",
                    capability_id="host.get_memory",
                ),
                _wire(
                    "action",
                    capability_id="host.get_memory",
                    target_ref="monitor",
                ),
                _wire(
                    "final",
                    answer="Memory observed for monitor.",
                ),
            ]
        ),
    )
    beta = create_canonical_session_agent(
        target_store_path=str(target_store),
        config=OrionConfig(
            servers={},
            active_server_name="",
            tools={},
        ),
        model_backend=_QueuedAssessmentModel(
            [_wire("final", answer="Beta has no inherited target.")]
        ),
    )
    state = _state()
    state.target_store_path = str(target_store)
    agents = [alpha, beta]

    def build_agent(**kwargs: object):
        agent = agents.pop(0)
        agent.conversation_store = kwargs["conversation_store"]
        return agent

    def execute_linux(_tool: object, arguments: dict[str, object]) -> ToolResult:
        data = (
            {"logical_cores": 4}
            if arguments["action"] == "get_cpu"
            else {"total_bytes": 100, "used_bytes": 40, "available_bytes": 60}
        )
        return ToolResult(
            success=True,
            data=data,
            capability_status=CapabilityStatus.VALID,
        )

    monkeypatch.setattr(
        "src.tool.target_registry.TargetRegistry.preflight", _reachable_monitor
    )
    monkeypatch.setattr("src.tool.linux_tool.LinuxTool.execute", execute_linux)
    with (
        mock.patch(
            "src.backend.dependencies.SQLiteConversationStore",
            side_effect=lambda session_id, **_kwargs: ConversationStore(
                session_id, store_dir=str(tmp_path)
            ),
        ),
        mock.patch(
            "src.backend.dependencies.create_canonical_session_agent",
            side_effect=build_agent,
        ),
    ):
        _, alpha_agent, alpha_lock = state.prepare_query("alpha")
        _, beta_agent, beta_lock = state.prepare_query("beta")

    assert (
        alpha_agent.run_with_steps("Inspect monitor.")["response"]
        == "CPU observed for monitor."
    )
    alpha_follow_up = alpha_agent.run_with_steps("What about memory?")
    beta_result = beta_agent.run_with_steps("What about memory?")

    assert alpha_follow_up["response"] == "Memory observed for monitor."
    assert beta_result["response"] == "Beta has no inherited target."
    alpha_history = state.web_sessions[
        "alpha"
    ].history
    beta_history = state.web_sessions[
        "beta"
    ].history

    assert [
        item["content"]
        for item in alpha_history
        if item.get("role") == "user"
    ] == [
        "Inspect monitor.",
        "What about memory?",
    ]

    assert [
        item["content"]
        for item in beta_history
        if item.get("role") == "user"
    ] == [
        "What about memory?",
    ]

    assert (
        alpha_follow_up["steps"][0]["target_id"]
        == "monitor"
    )
    assert beta_result["steps"] == []

    alpha_runtime = (
        alpha_follow_up["execution_trace"]
        ["runtime_metrics"]
        ["canonical_runtime"]
    )
    beta_runtime = (
        beta_result["execution_trace"]
        ["runtime_metrics"]
        ["canonical_runtime"]
    )

    assert alpha_runtime["action_attempts"] == 1
    assert beta_runtime["action_attempts"] == 0

    assert alpha_agent is not beta_agent
    assert alpha_lock is not beta_lock
    assert alpha_agent._runtime is not beta_agent._runtime


def test_query_returns_generated_session_id_from_isolated_agent() -> None:
    state = _state()
    agent = mock.MagicMock()
    agent.run_with_steps.return_value = {"steps": [], "response": "ok"}
    state.prepare_query = mock.MagicMock(
        return_value=("generated-session", agent, threading.RLock())
    )
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(deps=state)))

    response = query({"question": "hello"}, request)

    assert response["session_id"] == "generated-session"
    assert response["assessment"] == "ok"
    state.prepare_query.assert_called_once_with(None, server_name=None)


def test_model_file_change_triggers_runtime_reload(tmp_path: Path) -> None:
    model_file = tmp_path / "servers.json"
    model_file.write_text("{}", encoding="utf-8")
    state = AppState.__new__(AppState)
    state.model_store = SimpleNamespace(path=model_file)
    state._model_config_stamp = state._current_model_config_stamp()
    state.reload_models = mock.MagicMock()

    state.reload_models_if_changed()
    state.reload_models.assert_not_called()

    model_file.write_text('{"servers":{}}', encoding="utf-8")
    state.reload_models_if_changed()
    state.reload_models.assert_called_once_with()
