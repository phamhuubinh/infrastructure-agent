from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["query"])


@router.post("/api/query")
def query(body: dict, request: Request):
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(400, "Question is required")

    deps = request.app.state.deps
    session_id = body.get("session_id")
    deps.get_or_create_session(session_id)

    result = deps.agent.run_with_steps(question)

    return {
        "steps": result["steps"],
        "assessment": result["response"],
    }
