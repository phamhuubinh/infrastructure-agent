from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from src.agent.canonical_factory import create_canonical_session_agent
from src.agent.conversation_store import ConversationStoreProtocol
from src.agent.session_agent import CanonicalSessionAgent
from src.backend.db import (
    PostgresConversationStore,
    _get_dsn,
    _mask_dsn,
    init_db,
    init_documents_db,
)
from src.backend.session_document_evidence import SessionDocumentEvidenceService
from src.backend.sqlite_store import SQLiteConversationStore
from src.model.config_store import ModelConfigStore
from src.shared.logger import info as _info


@dataclass(slots=True)
class _SessionLifecycle:
    generation: int
    lock: threading.RLock = field(default_factory=threading.RLock)
    deleting: bool = False


class SessionLease:
    """A query lease that cannot begin after its lifecycle was deleted."""

    def __init__(self, state: AppState, session_id: str, lifecycle: _SessionLifecycle):
        self._state = state
        self._session_id = session_id
        self._lifecycle = lifecycle

    def __enter__(self) -> threading.RLock:
        self._lifecycle.lock.acquire()
        with self._state._state_lock:
            valid = (
                self._state._lifecycles.get(self._session_id) is self._lifecycle
                and not self._lifecycle.deleting
            )
        if not valid:
            self._lifecycle.lock.release()
            raise KeyError(f"Session '{self._session_id}' was deleted")
        return self._lifecycle.lock

    def __exit__(self, *_args: object) -> None:
        self._lifecycle.lock.release()


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
        self.agent = create_canonical_session_agent(
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
        self.web_agents: dict[tuple[str, str, str | None], CanonicalSessionAgent] = {}
        self._lifecycles: dict[str, _SessionLifecycle] = {}
        self._next_session_generation = 1
        self._deleting_all_sessions = False
        # Kept as an inspectable compatibility view; lifecycle ownership is
        # authoritative and callers must use SessionLease/delete_session.
        self._session_locks: dict[str, threading.RLock] = {}
        self.rag_service_url = os.environ.get(
            "RAG_SERVICE_URL", "http://127.0.0.1:8080"
        )
        self.rag_internal_token = os.environ.get("RAG_INTERNAL_TOKEN", "").strip()
        self.session_document_evidence = SessionDocumentEvidenceService(self.dsn)

    def switch_server(self, server_name: str, model: str | None = None) -> None:
        """Switch the default health-check agent without mutating session agents."""
        with self._state_lock:
            self._server_name = server_name
            self._model = model
            self.agent = create_canonical_session_agent(
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
            self.agent = create_canonical_session_agent(
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
            if self._deleting_all_sessions:
                raise KeyError("Session cleanup is in progress")
            lifecycle = self._lifecycles.get(sid)
            if lifecycle is not None and lifecycle.deleting:
                raise KeyError(f"Session '{sid}' is being deleted")
            if lifecycle is None:
                lifecycle = _SessionLifecycle(self._next_session_generation)
                self._next_session_generation += 1
                self._lifecycles[sid] = lifecycle
                self._session_locks[sid] = lifecycle.lock
            if sid not in self.web_sessions:
                if self.dsn:
                    store: ConversationStoreProtocol = PostgresConversationStore(
                        session_id=sid,
                        dsn=self.dsn,
                        source="api",
                    )
                else:
                    store = SQLiteConversationStore(
                        session_id=sid,
                        source="api",
                    )
                self.web_sessions[sid] = store
            return self.web_sessions[sid]

    def prepare_query(
        self,
        session_id: str | None,
        server_name: str | None = None,
        model: str | None = None,
    ) -> tuple[str, CanonicalSessionAgent, SessionLease]:
        """Return an agent plus a lifecycle lease owned by one chat session."""
        self.reload_models_if_changed()
        sid = session_id or uuid.uuid4().hex[:12]
        store = self.get_or_create_session(sid)
        selected_server = server_name or self._server_name
        selected_model = model if model is not None else self._model
        key = (sid, selected_server, selected_model)
        with self._state_lock:
            lifecycle = self._lifecycles.get(sid)
            if lifecycle is None or lifecycle.deleting:
                raise KeyError(f"Session '{sid}' was deleted")
            agent = self.web_agents.get(key)
            if agent is None:
                agent = create_canonical_session_agent(
                    target_store_path=self.target_store_path,
                    server_name=selected_server,
                    model=selected_model,
                    conversation_store=store,
                )
                self.web_agents[key] = agent
        return sid, agent, SessionLease(self, sid, lifecycle)

    def delete_session(
        self, session_id: str, delete_persisted: Callable[[], bool]
    ) -> bool:
        """Serialize deletion with queries and invalidate the old lifecycle.

        A same-ID query may create a new lifecycle only after this method
        returns.  A queued old lease observes the invalidation and cannot
        persist after deletion.
        """
        with self._state_lock:
            lifecycle = self._lifecycles.get(session_id)
            if lifecycle is None:
                lifecycle = _SessionLifecycle(self._next_session_generation)
                self._next_session_generation += 1
                self._lifecycles[session_id] = lifecycle
                self._session_locks[session_id] = lifecycle.lock
            lifecycle.deleting = True
        with lifecycle.lock:
            deleted = bool(delete_persisted())
            with self._state_lock:
                if self._lifecycles.get(session_id) is lifecycle:
                    self._lifecycles.pop(session_id, None)
                    self._session_locks.pop(session_id, None)
            self.web_sessions.pop(session_id, None)
            keys = [key for key in self.web_agents if key[0] == session_id]
            for key in keys:
                self.web_agents.pop(key, None)
        return deleted

    def delete_all_sessions(self, delete_persisted: Callable[[], int]) -> int:
        """Tombstone every lifecycle before one persistent clean-all mutation."""
        with self._state_lock:
            if self._deleting_all_sessions:
                raise KeyError("Session cleanup is already in progress")
            self._deleting_all_sessions = True
            lifecycles = tuple(
                lifecycle
                for _, lifecycle in sorted(self._lifecycles.items())
            )
            for lifecycle in lifecycles:
                lifecycle.deleting = True
        acquired: list[_SessionLifecycle] = []
        try:
            for lifecycle in lifecycles:
                lifecycle.lock.acquire()
                acquired.append(lifecycle)
            deleted = int(delete_persisted())
            with self._state_lock:
                self.web_sessions.clear()
                self.web_agents.clear()
                self._lifecycles.clear()
                self._session_locks.clear()
            return deleted
        except Exception:
            with self._state_lock:
                for lifecycle in lifecycles:
                    lifecycle.deleting = False
            raise
        finally:
            for lifecycle in reversed(acquired):
                lifecycle.lock.release()
            with self._state_lock:
                self._deleting_all_sessions = False
