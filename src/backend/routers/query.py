from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.model.output_sanitizer import sanitize_api_response
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
    regenerate_turn_index = body.get("regenerate_turn_index")
    if regenerate_turn_index is not None and (
        isinstance(regenerate_turn_index, bool)
        or not isinstance(regenerate_turn_index, int)
        or regenerate_turn_index < 0
    ):
        raise HTTPException(400, "regenerate_turn_index must be a non-negative integer")
    set_context(request_id=request_id, session_id=session_id)

    try:
        deps = request.app.state.deps
        server_name = body.get("server_name") or body.get("active_server")
        asked_at = body.get("asked_at")
        if not isinstance(asked_at, str) or len(asked_at) > 64:
            asked_at = datetime.now(timezone.utc).isoformat()
        else:
            try:
                datetime.fromisoformat(asked_at.replace("Z", "+00:00"))
            except ValueError:
                asked_at = datetime.now(timezone.utc).isoformat()
        session_id, agent, session_lock = deps.prepare_query(
            session_id,
            server_name=server_name,
        )
        set_context(request_id=request_id, session_id=session_id)
        with session_lock:
            store = agent.conversation_store
            snapshot = None
            if regenerate_turn_index is not None:
                if store is None:
                    raise HTTPException(409, "Conversation history is unavailable")
                snapshot = store.truncate_for_regeneration(regenerate_turn_index)
                if snapshot is None:
                    raise HTTPException(409, "Conversation turn was not found")
            try:
                started_at = time.perf_counter()
                result = agent.run_with_steps(question)
                # Final defense-in-depth output boundary (GA2-B05).  Every
                # user-visible response — normal answer, deterministic
                # refusal, external-verification answer, fallback — converges
                # on the same sanitizer so no channel can leak hidden
                # reasoning, mixed scripts, or an empty response.
                result["response"] = sanitize_api_response(
                    str(result.get("response", "")),
                    question,
                )
                response_time_ms = round((time.perf_counter() - started_at) * 1000)
                if store is not None:
                    store.set_last_response_time(response_time_ms, asked_at=asked_at)
            except Exception:
                if snapshot is not None and store is not None:
                    store.restore_messages(snapshot)
                raise

        return {
            "session_id": session_id,
            "steps": result["steps"],
            "assessment": result["response"],
            "response_time_ms": response_time_ms,
            "asked_at": asked_at,
            # Additive observability contract for QA/UI consumers.  The trace
            # serializer is credential-safe and never includes raw tool
            # output, so it is safe to return beside the existing steps.
            "trace_id": result.get("trace_id"),
            "execution_trace": result.get("execution_trace"),
        }
    finally:
        set_context(request_id=None, session_id=None)
