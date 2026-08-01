from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from src.backend.dependencies import AppState
from src.backend.routers.query import query


class _Store:
    def __init__(self, session_id: str, **_kwargs: object) -> None:
        self.session_id = session_id


def _state() -> AppState:
    state = AppState.__new__(AppState)
    state.target_store_path = "targets.json"
    state._state_lock = threading.RLock()
    state.dsn = None
    state.use_postgresql = False
    state._server_name = "sv1"
    state._model = None
    state.agent = mock.MagicMock()
    state.agent.assessment_model.assess_raw = mock.MagicMock()
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
            "src.backend.dependencies.create_deterministic_agent",
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
