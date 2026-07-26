from __future__ import annotations

import os
import uuid
from pathlib import Path

from src.agent.conversation_store import ConversationStore, ConversationStoreProtocol
from src.agent.runtime_factory import create_deterministic_agent
from src.backend.db import (
    PostgresConversationStore,
    _get_dsn,
    _mask_dsn,
    init_db,
    init_documents_db,
)
from src.backend.sqlite_store import SQLiteConversationStore
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
        self.use_postgresql = bool(self.dsn)
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
        else:
            _info(
                "database",
                message="SQLite session store used (default)",
            )

        self.sessions_dir = str(Path.home() / ".orion" / "sessions")
        self.web_sessions: dict[
            str, ConversationStoreProtocol
        ] = {}
        self.rag_service_url = os.environ.get(
            "RAG_SERVICE_URL", "http://rag-service:8080"
        )

    def switch_server(self, server_name: str, model: str | None = None) -> None:
        """Switch the active LLM server, recreating the agent."""
        # Preserve the current conversation store so conversations
        # continue to accrue in the same session after agent recreation.
        old_cs = self.agent.conversation_store
        self._server_name = server_name
        self._model = model
        self.agent = create_deterministic_agent(
            target_store_path=self.target_store_path,
            server_name=server_name,
            model=model,
        )
        if old_cs is not None:
            self.agent.conversation_store = old_cs

    def get_or_create_session(self, session_id: str | None) -> ConversationStoreProtocol:
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
                # SQLite is the default persistence backend
                cs = SQLiteConversationStore(
                    session_id=sid,
                    source="api",
                    summarize_fn=self.agent.assessment_model.assess_raw,
                )
            self.web_sessions[sid] = cs
        cs = self.web_sessions[sid]
        self.agent.conversation_store = cs
        return cs
