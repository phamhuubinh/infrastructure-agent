from __future__ import annotations

import os
import threading
import uuid
from pathlib import Path

from src.agent.conversation_store import ConversationStoreProtocol
from src.agent.deterministic_agent import DeterministicAgent
from src.agent.runtime_factory import create_deterministic_agent
from src.backend.db import (
    PostgresConversationStore,
    _get_dsn,
    _mask_dsn,
    init_db,
    init_documents_db,
)
from src.backend.sqlite_store import SQLiteConversationStore
from src.model.config_store import ModelConfigStore
from src.shared.logger import info as _info


class AppState:
    def __init__(
        self,
        target_store_path: str = "targets.json",
        server_name: str | None = None,
        model: str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.target_store_path = target_store_path
        self._state_lock = threading.RLock()
        self.model_store = ModelConfigStore()
        self.model_store.ensure_exists()
        self._model_config_stamp = self._current_model_config_stamp()
        self.dsn = database_url or _get_dsn()
        self.use_postgresql = bool(self.dsn)
        self.agent = create_deterministic_agent(
            target_store_path=target_store_path,
            server_name=server_name,
            model=model,
        )
        active = self.model_store.active()
        self._server_name = server_name or (active[0] if active is not None else "")
        self._model = model
        if self.dsn:
            init_db(self.dsn)
            init_documents_db(self.dsn)
            _info(
                "database",
                message="PostgreSQL session store initialized",
                dsn=_mask_dsn(self.dsn),
            )
        else:
            _info(
                "database",
                message="SQLite session store used (default)",
            )

        self.sessions_dir = str(Path.home() / ".orion" / "sessions")
        self.web_sessions: dict[str, ConversationStoreProtocol] = {}
        self.web_agents: dict[tuple[str, str, str | None], DeterministicAgent] = {}
        self._session_locks: dict[str, threading.RLock] = {}
        self.rag_service_url = os.environ.get(
            "RAG_SERVICE_URL", "http://127.0.0.1:8080"
        )

    def switch_server(self, server_name: str, model: str | None = None) -> None:
        """Switch the default health-check agent without mutating session agents."""
        with self._state_lock:
            self._server_name = server_name
            self._model = model
            self.agent = create_deterministic_agent(
                target_store_path=self.target_store_path,
                server_name=server_name,
                model=model,
            )

    def reload_models(self) -> None:
        """Reload persisted model configuration and invalidate session adapters."""
        from src.shared.config import _reset_config

        with self._state_lock:
            _reset_config()
            active = self.model_store.active()
            self._server_name = active[0] if active is not None else ""
            self._model = None
            self.agent = create_deterministic_agent(
                target_store_path=self.target_store_path,
                server_name=self._server_name or None,
            )
            self.web_agents.clear()
            self._model_config_stamp = self._current_model_config_stamp()

    def reload_models_if_changed(self) -> None:
        """Pick up model changes written by a separate CLI process."""
        if self._current_model_config_stamp() != self._model_config_stamp:
            self.reload_models()

    def _current_model_config_stamp(self) -> tuple[int, int, int]:
        try:
            stat = self.model_store.path.stat()
        except OSError:
            return (0, 0, 0)
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino)

    def get_or_create_session(
        self, session_id: str | None
    ) -> ConversationStoreProtocol:
        sid = session_id or uuid.uuid4().hex[:12]
        with self._state_lock:
            if sid not in self.web_sessions:
                if self.dsn:
                    store: ConversationStoreProtocol = PostgresConversationStore(
                        session_id=sid,
                        dsn=self.dsn,
                        source="api",
                        summarize_fn=self.agent.assessment_model.assess_raw,
                    )
                else:
                    store = SQLiteConversationStore(
                        session_id=sid,
                        source="api",
                        summarize_fn=self.agent.assessment_model.assess_raw,
                    )
                self.web_sessions[sid] = store
                self._session_locks[sid] = threading.RLock()
            return self.web_sessions[sid]

    def prepare_query(
        self,
        session_id: str | None,
        server_name: str | None = None,
        model: str | None = None,
    ) -> tuple[str, DeterministicAgent, threading.RLock]:
        """Return an agent and lock owned exclusively by one chat session."""
        self.reload_models_if_changed()
        sid = session_id or uuid.uuid4().hex[:12]
        store = self.get_or_create_session(sid)
        selected_server = server_name or self._server_name
        selected_model = model if model is not None else self._model
        key = (sid, selected_server, selected_model)
        with self._state_lock:
            agent = self.web_agents.get(key)
            if agent is None:
                agent = create_deterministic_agent(
                    target_store_path=self.target_store_path,
                    server_name=selected_server,
                    model=selected_model,
                    conversation_store=store,
                )
                self.web_agents[key] = agent
            lock = self._session_locks.setdefault(sid, threading.RLock())
        return sid, agent, lock

    def drop_session(self, session_id: str) -> None:
        with self._state_lock:
            self.web_sessions.pop(session_id, None)
            self._session_locks.pop(session_id, None)
            keys = [key for key in self.web_agents if key[0] == session_id]
            for key in keys:
                self.web_agents.pop(key, None)
