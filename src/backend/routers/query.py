from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from src.shared.logger import set_context

router = APIRouter(tags=["query"])


@router.post("/api/query")
def query(body: dict, request: Request):
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Question is required")

    # Set request and session context for all downstream log calls
    request_id = uuid.uuid4().hex[:6]
    session_id = body.get("session_id")
    set_context(request_id=request_id, session_id=session_id)

    try:
        deps = request.app.state.deps
        session_id = body.get("session_id")
        deps.get_or_create_session(session_id)

        # Switch server if requested
        server_name = body.get("server_name") or body.get("active_server")
        if server_name:
            deps.switch_server(server_name)

        result = deps.agent.run_with_steps(question)

        return {
            "steps": result["steps"],
            "assessment": result["response"],
        }
    finally:
        set_context(request_id=None, session_id=None)
