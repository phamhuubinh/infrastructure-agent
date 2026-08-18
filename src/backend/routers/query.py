from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from src.model.output_sanitizer import sanitize_api_response
from src.shared.execution.command_result import redact_sensitive
from src.shared.logger import set_context

router = APIRouter(tags=["query"])

_MAX_API_TRACE_DEPTH = 8
_MAX_API_TRACE_DICT_ITEMS = 128
_MAX_API_TRACE_LIST_ITEMS = 64
_MAX_API_TRACE_TEXT_CHARS = 4096
_MAX_API_TRACE_NODES = 512
_MAX_API_TRACE_BYTES = 128 * 1024

_SENSITIVE_TRACE_KEYS = frozenset(
    {
        "analysis",
        "authorization",
        "chain_of_thought",
        "credential",
        "credentials",
        "hidden_reasoning",
        "password",
        "passwd",
        "private_key",
        "prompt",
        "raw_output",
        "raw_response",
        "raw_usage",
        "reasoning_text",
        "secret",
        "system_prompt",
        "thinking",
        "thoughts",
        "token",
        "access_token",
        "api_key",
        "user_prompt",
    }
)


def _trace_key_is_sensitive(key: str) -> bool:
    normalized = key.strip().casefold().replace("-", "_")
    return normalized in _SENSITIVE_TRACE_KEYS or normalized.endswith(
        ("_prompt", "_password", "_secret", "_api_key", "_access_token")
    )


def _sanitize_trace_text(value: str) -> str:
    redacted = redact_sensitive(value)
    if len(redacted) <= _MAX_API_TRACE_TEXT_CHARS:
        return redacted
    return redacted[:_MAX_API_TRACE_TEXT_CHARS] + "…"


def _sanitize_trace_value(
    value: object,
    *,
    depth: int,
    remaining_nodes: list[int],
) -> object:
    if depth > _MAX_API_TRACE_DEPTH or remaining_nodes[0] <= 0:
        return None
    remaining_nodes[0] -= 1

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_trace_text(value)
    if isinstance(value, dict):
        safe: dict[str, object] = {}
        for raw_key, item in list(value.items())[:_MAX_API_TRACE_DICT_ITEMS]:
            key = str(raw_key)
            if _trace_key_is_sensitive(key):
                continue
            safe[key] = _sanitize_trace_value(
                item,
                depth=depth + 1,
                remaining_nodes=remaining_nodes,
            )
        return safe
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_trace_value(
                item,
                depth=depth + 1,
                remaining_nodes=remaining_nodes,
            )
            for item in value[:_MAX_API_TRACE_LIST_ITEMS]
        ]
    return None


def _sanitize_execution_trace(value: object) -> dict[str, object] | None:
    """Return a bounded, credential-safe copy of an agent execution trace."""

    if not isinstance(value, dict):
        return None
    sanitized = _sanitize_trace_value(
        value,
        depth=0,
        remaining_nodes=[_MAX_API_TRACE_NODES],
    )
    if not isinstance(sanitized, dict):
        return None

    encoded = json.dumps(
        sanitized,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(encoded) <= _MAX_API_TRACE_BYTES:
        return sanitized

    # Pathological/custom-agent traces fail closed to a stable summary.
    summary_keys = (
        "trace_id",
        "answer_strategy",
        "llm_usage_reason",
        "routing_status",
        "evidence_status",
        "response_strategy",
        "total_duration_ms",
    )
    summary = {key: sanitized[key] for key in summary_keys if key in sanitized}
    summary["truncated"] = True
    return summary


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
            "execution_trace": _sanitize_execution_trace(result.get("execution_trace")),
        }
    finally:
        set_context(request_id=None, session_id=None)
