from __future__ import annotations

import json
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from src.agent.conversation_store import list_sessions as list_file_sessions
from src.backend.db import (
    delete_session as db_delete_session,
)
from src.backend.db import (
    list_sessions_db,
    rename_session_db,
    save_session,
)

router = APIRouter(tags=["sessions"])


@router.post("/api/sessions")
def create_session(request: Request):
    deps = request.app.state.deps
    session_id = uuid.uuid4().hex[:12]
    if deps.dsn:
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
        path = Path(deps.sessions_dir) / f"{session_id}.json"
        path.write_text(
            json.dumps(
                {
                    "session_id": session_id,
                    "source": "api",
                    "messages": [],
                }
            )
        )
    deps.get_or_create_session(session_id)
    return {"session_id": session_id}


@router.get("/api/sessions")
def list_sessions(request: Request):
    deps = request.app.state.deps
    if deps.dsn:
        all_sessions = list_sessions_db(deps.dsn)
    else:
        all_sessions = list_file_sessions(deps.sessions_dir)
    web_sessions = [s for s in all_sessions if s.get("source") != "terminal"]
    return {"sessions": web_sessions}


@router.delete("/api/sessions/{session_id}")
def delete_session(session_id: str, request: Request):
    deps = request.app.state.deps
    if deps.dsn:
        deleted = db_delete_session(deps.dsn, session_id)
        deps.web_sessions.pop(session_id, None)
        if not deleted:
            raise HTTPException(404, f"Session '{session_id}' not found")
        return {"status": "deleted", "session_id": session_id}
    path = Path(deps.sessions_dir) / f"{session_id}.json"
    if not path.exists():
        raise HTTPException(404, f"Session '{session_id}' not found")
    path.unlink()
    deps.web_sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}


@router.patch("/api/sessions/{session_id}")
def rename_session(session_id: str, body: dict, request: Request):
    deps = request.app.state.deps
    new_title = body.get("title", "").strip()
    if not new_title:
        raise HTTPException(400, "title is required")
    if deps.dsn:
        renamed = rename_session_db(deps.dsn, session_id, new_title)
        if not renamed:
            raise HTTPException(404, f"Session '{session_id}' not found")
    else:
        path = Path(deps.sessions_dir) / f"{session_id}.json"
        if not path.exists():
            raise HTTPException(404, f"Session '{session_id}' not found")
        data = json.loads(path.read_text())
        data["title"] = new_title
        path.write_text(json.dumps(data, indent=2))
    # Update in-memory store so subsequent _save() preserves the title
    cs = deps.web_sessions.get(session_id)
    if cs is not None:
        cs.set_title(new_title)
    return {"status": "renamed", "session_id": session_id, "title": new_title}
