from __future__ import annotations

import inspect
import json
import os
from urllib import error as urlerror
from urllib import request

from src.shared.capability import Capability
from src.shared.execution.tool_result import ToolResult
from src.tool.tool import Tool

_RAG_SERVICE_URL: str = os.environ.get("RAG_SERVICE_URL", "http://rag-service:8080")
_DEFAULT_TIMEOUT = 30


def _rag_health() -> dict[str, object]:
    try:
        req = request.Request(f"{_RAG_SERVICE_URL}/health", method="GET")
        with request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (
        urlerror.URLError,
        urlerror.HTTPError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        return {"status": "error", "error": str(exc)[:200]}


def _rag_ingest(filepath: str = "") -> dict[str, object]:
    if not filepath:
        return {"error": "Missing filepath parameter."}

    import email.message
    from urllib.parse import urlencode

    boundary = "----OrionFormBoundary"
    filename = os.path.basename(filepath)

    try:
        with open(filepath, "rb") as f:
            file_data = f.read()
    except OSError as exc:
        return {"error": f"Cannot read file: {exc}"}

    body = b""
    body += f"--{boundary}\r\n".encode("utf-8")
    body += (
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
    ).encode("utf-8")
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += file_data
    body += b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")

    msg = email.message.Message()
    msg["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    content_type = msg["Content-Type"]

    try:
        req = request.Request(
            f"{_RAG_SERVICE_URL}/ingest",
            data=body,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return {"error": f"HTTP {exc.code}: {detail}"}
    except (urlerror.URLError, OSError) as exc:
        return {"error": str(exc)[:200]}


def _rag_query(query: str = "", top_k: int = 5) -> dict[str, object]:
    if not query.strip():
        return {"error": "Missing query parameter."}

    payload = json.dumps({"query": query, "top_k": top_k}).encode("utf-8")

    try:
        req = request.Request(
            f"{_RAG_SERVICE_URL}/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urlerror.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        return {"error": f"HTTP {exc.code}: {detail}"}
    except (urlerror.URLError, OSError) as exc:
        return {"error": str(exc)[:200]}


_CAPABILITIES: dict[str, Capability] = {
    "kb_health": Capability(
        name="kb_health",
        handler=_rag_health,
        category="knowledge",
        intents=("investigate",),
        related=(),
        covers=("knowledge-base-health",),
        description="Check the Knowledge Base (RAG) service health and capabilities",
        supported_targets=("knowledge-base",),
        parameters=(),
        estimated_cost=0.1,
    ),
    "kb_ingest": Capability(
        name="kb_ingest",
        handler=_rag_ingest,
        category="knowledge",
        intents=("discovery", "investigate"),
        related=(),
        covers=("knowledge-base-ingest",),
        description="Ingest a document into the Knowledge Base (RAG index)",
        supported_targets=("knowledge-base",),
        parameters=("filepath",),
        estimated_cost=0.5,
    ),
    "kb_query": Capability(
        name="kb_query",
        handler=_rag_query,
        category="knowledge",
        intents=("investigate", "discovery"),
        related=(),
        covers=("knowledge-base-query", "documentation", "runbook"),
        description="Query the Knowledge Base (RAG) for relevant document chunks",
        supported_targets=("knowledge-base",),
        parameters=("query", "top_k"),
        estimated_cost=0.3,
    ),
}


class KnowledgeBaseTool(Tool):
    def execute(self, arguments: dict[str, object]) -> ToolResult:
        action = arguments.get("action")
        if not isinstance(action, str):
            return ToolResult(success=False, error="Missing action.")

        cap = _CAPABILITIES.get(action)
        if cap is None:
            available = ", ".join(sorted(_CAPABILITIES))
            return ToolResult(
                success=False,
                error=f"Unknown action: '{action}'. Available actions: {available}.",
            )

        handler = cap.handler if isinstance(cap, Capability) else cap
        extra = {k: v for k, v in arguments.items() if k != "action"}

        try:
            sig = inspect.signature(handler)
            filtered: dict[str, object] = {
                k: v for k, v in extra.items() if k in sig.parameters
            }
            data = handler(**filtered)
        except (ValueError, TypeError, RuntimeError, OSError) as exc:
            return ToolResult(success=False, error=f"KnowledgeBaseTool error: {exc}")

        return ToolResult(success=True, data=data)
