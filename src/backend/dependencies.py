from __future__ import annotations

import os
import uuid
from pathlib import Path

from src.agent.conversation_store import ConversationStore
from src.agent.runtime_factory import create_deterministic_agent
from src.backend.db import (
    PostgresConversationStore,
    _get_dsn,
    _mask_dsn,
    init_db,
    init_documents_db,
)
from src.shared.logger import info as _info


class AppState:
    def __init__(
        self,
        target_store_path: str = "targets.json",
        server_name: str = "sv1",
        model: str | None = None,
        database_url: str | None = None,
    ) -> None:
        self.target_store_path = target_store_path
        self.dsn = database_url or _get_dsn()
        self.agent = create_deterministic_agent(
            target_store_path=target_store_path,
            server_name=server_name,
            model=model,
        )
        self._server_name = server_name
        self._model = model
        if self.dsn:
            init_db(self.dsn)
            init_documents_db(self.dsn)
            _info(
                "database",
                message="PostgreSQL session store initialized",
                dsn=_mask_dsn(self.dsn),
            )

        self.sessions_dir = str(Path.home() / ".orion" / "sessions")
        self.web_sessions: dict[str, ConversationStore] = {}
        self.rag_service_url = os.environ.get(
            "RAG_SERVICE_URL", "http://rag-service:8080"
        )

    def switch_server(self, server_name: str, model: str | None = None) -> None:
        """Switch the active LLM server, recreating the agent."""
        self._server_name = server_name
        self._model = model
        self.agent = create_deterministic_agent(
            target_store_path=self.target_store_path,
            server_name=server_name,
            model=model,
        )
        # Re-attach active session stores to the new agent
        for sid, cs in self.web_sessions.items():
            self.agent.conversation_store = cs

    def get_or_create_session(self, session_id: str | None) -> ConversationStore:
        sid = session_id or uuid.uuid4().hex[:12]
        if sid not in self.web_sessions:
            if self.dsn:
                cs = PostgresConversationStore(
                    session_id=sid,
                    dsn=self.dsn,
                    source="api",
                    summarize_fn=self.agent.assessment_model.assess_raw,
                )
            else:
                cs = ConversationStore(
                    session_id=sid,
                    store_dir=self.sessions_dir,
                    source="api",
                    summarize_fn=self.agent.assessment_model.assess_raw,
                )
            self.web_sessions[sid] = cs
        cs = self.web_sessions[sid]
        self.agent.conversation_store = cs
        return cs
