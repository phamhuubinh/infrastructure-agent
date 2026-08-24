from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid

from fastapi import APIRouter, HTTPException, Request, UploadFile

router = APIRouter(tags=["rag-projects"])
_MAX_UPLOAD_BYTES = 50 * 1024 * 1024


def _segment(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _json_request(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    timeout: int = 30,
    token: str = "",
):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    if token:
        headers["X-Orion-Rag-Token"] = token
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
            message = parsed.get("detail", detail)
        except json.JSONDecodeError:
            message = detail
        raise HTTPException(exc.code, str(message)[:500]) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise HTTPException(503, f"RAG service unavailable: {exc}") from exc


def _multipart_body(file: UploadFile, content: bytes) -> tuple[bytes, str]:
    boundary = f"----OrionRag{uuid.uuid4().hex}"
    filename = (
        (file.filename or "upload").replace('"', "").replace("\r", "").replace("\n", "")
    )
    content_type = (
        (file.content_type or "application/octet-stream")
        .replace("\r", "")
        .replace("\n", "")
    )
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    return head + content + tail, boundary


def _rag_url(request: Request) -> str:
    configured = request.app.state.deps.rag_service_url
    if not configured:
        raise HTTPException(503, "RAG service is not configured")
    return str(configured).rstrip("/")


def _rag_token(request: Request) -> str:
    token = str(getattr(request.app.state.deps, "rag_internal_token", "")).strip()
    if not token:
        raise HTTPException(503, "RAG proxy token is not configured")
    return token


def _analysis_model_config(request: Request) -> dict:
    active = request.app.state.deps.model_store.active()
    if active is None:
        raise HTTPException(
            503,
            "No model configured. Configure and test a model in Orion Settings first.",
        )
    _name, config = active
    provider = str(config.get("provider", "openai")).lower()
    if provider == "anthropic":
        raise HTTPException(
            400,
            "The selected model is not OpenAI-compatible and cannot synthesize RAG analyses.",
        )
    base_url = str(config["base_url"]).rstrip("/")
    rag_base_url = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    return {
        "base_url": rag_base_url,
        "model": config.get("model", ""),
        "api_key": config.get("api_key", ""),
        "timeout": config.get("timeout", 180),
    }


@router.get("/api/knowledge/health")
@router.get("/api/rag/health")
def knowledge_health(request: Request):
    result = _json_request(_rag_url(request), "/health", timeout=5)
    if isinstance(result, dict):
        result["llm_configured"] = (
            request.app.state.deps.model_store.active() is not None
        )
        result["llm_scope"] = "request"
    return result


@router.get("/api/rag/projects")
def list_projects(request: Request):
    return _json_request(_rag_url(request), "/projects", token=_rag_token(request))


@router.post("/api/rag/projects")
def create_project(body: dict, request: Request):
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "Project name is required")
    return _json_request(
        _rag_url(request),
        "/projects",
        method="POST",
        body={"name": name, "description": str(body.get("description", ""))},
        token=_rag_token(request),
    )


@router.get("/api/rag/projects/{project_id}")
def get_project(project_id: str, request: Request):
    return _json_request(_rag_url(request), f"/projects/{_segment(project_id)}", token=_rag_token(request))


@router.delete("/api/rag/projects/{project_id}")
def delete_project(project_id: str, request: Request):
    return _json_request(
        _rag_url(request), f"/projects/{_segment(project_id)}", method="DELETE", token=_rag_token(request)
    )


@router.post("/api/rag/projects/{project_id}/documents")
def upload_project_document(
    project_id: str,
    request: Request,
    file: UploadFile,
):
    content = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Document exceeds the 50 MiB upload limit")
    body, boundary = _multipart_body(file, content)
    upstream = urllib.request.Request(
        f"{_rag_url(request)}/projects/{_segment(project_id)}/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "X-Orion-Rag-Token": _rag_token(request)},
        method="POST",
    )
    try:
        with urllib.request.urlopen(upstream, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(exc.code, detail[:500]) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise HTTPException(503, f"RAG service unavailable: {exc}") from exc


@router.delete("/api/rag/projects/{project_id}/documents/{doc_id}")
def delete_project_document(project_id: str, doc_id: str, request: Request):
    return _json_request(
        _rag_url(request),
        f"/projects/{_segment(project_id)}/documents/{_segment(doc_id)}",
        method="DELETE",
        token=_rag_token(request),
    )


@router.post("/api/rag/projects/{project_id}/analyses")
def analyze_project(project_id: str, body: dict, request: Request):
    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(400, "Analysis request is required")
    try:
        top_k = int(body.get("top_k", 5))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "top_k must be an integer") from exc
    if not 1 <= top_k <= 20:
        raise HTTPException(400, "top_k must be between 1 and 20")
    model_config = _analysis_model_config(request)
    return _json_request(
        _rag_url(request),
        f"/projects/{_segment(project_id)}/analyses",
        method="POST",
        body={"query": query, "top_k": top_k, "model_config": model_config},
        timeout=120,
        token=_rag_token(request),
    )


# Compatibility route for older clients. It remains outside the chat endpoint.
# Calls the RAG /query endpoint directly (not /projects/default/analyses) because
# the RAG tool's /query endpoint uses its own internal LLM client when no
# analysis_model is provided in the body, without needing Orion's model config.
@router.post("/api/knowledge/query")
def knowledge_query(body: dict, request: Request):
    query = str(body.get("query", "")).strip()
    if not query:
        raise HTTPException(400, "Query is required")
    try:
        top_k = int(body.get("top_k", 5))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "top_k must be an integer") from exc
    if not 1 <= top_k <= 20:
        raise HTTPException(400, "top_k must be between 1 and 20")
    return _json_request(
        _rag_url(request),
        "/query",
        method="POST",
        body={"query": query, "top_k": top_k},
        timeout=120,
        token=_rag_token(request),
    )
