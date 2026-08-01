from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.backend.sqlite_store import SQLiteConversationStore

router = APIRouter(tags=["sessions"])


@router.post("/api/sessions")
def create_session(request: Request):
    deps = request.app.state.deps
    session_id = uuid.uuid4().hex[:12]
    if deps.dsn:
        from src.backend.db import save_session

        save_session(
            deps.dsn,
            session_id,
            {
                "session_id": session_id,
                "source": "api",
                "messages": [],
            },
        )
    else:
        # SQLite is the default. No explicit create needed — the store
        # creates the row on first save. But we ensure the session exists.
        pass
    store = deps.get_or_create_session(session_id)
    if isinstance(store, SQLiteConversationStore):
        store.persist()
    return {"session_id": session_id}


@router.get("/api/sessions")
def list_sessions(request: Request):
    deps = request.app.state.deps
    if deps.dsn:
        from src.backend.db import list_sessions_db

        all_sessions = list_sessions_db(deps.dsn)
    else:
        all_sessions = SQLiteConversationStore.list_sessions()
    web_sessions = [s for s in all_sessions if s.get("source") != "terminal"]
    return {"sessions": web_sessions}


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    deps = request.app.state.deps
    if deps.dsn:
        from src.backend.db import delete_session as db_delete_session

        deleted = db_delete_session(deps.dsn, session_id)
        deps.drop_session(session_id)
        if not deleted:
            raise HTTPException(404, f"Session '{session_id}' not found")
        return {"status": "deleted", "session_id": session_id}

    deleted = SQLiteConversationStore.delete_session(session_id)
    deps.drop_session(session_id)
    if not deleted:
        raise HTTPException(404, f"Session '{session_id}' not found")
    return {"status": "deleted", "session_id": session_id}


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, body: dict, request: Request):
    deps = request.app.state.deps
    new_title = body.get("title", "").strip()
    if not new_title:
        raise HTTPException(400, "title is required")

    if deps.dsn:
        from src.backend.db import rename_session_db

        renamed = rename_session_db(deps.dsn, session_id, new_title)
        if not renamed:
            raise HTTPException(404, f"Session '{session_id}' not found")
    else:
        renamed = SQLiteConversationStore.rename_session(session_id, new_title)
        if not renamed:
            raise HTTPException(404, f"Session '{session_id}' not found")

    # Update in-memory store so subsequent _save() preserves the title
    cs = deps.web_sessions.get(session_id)
    if cs is not None:
        cs.set_title(new_title)
    return {"status": "renamed", "session_id": session_id, "title": new_title}
