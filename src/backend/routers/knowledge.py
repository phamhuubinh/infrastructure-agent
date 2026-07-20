from __future__ import annotations

import json
import urllib.request

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["knowledge"])


@router.get("/api/knowledge/health")
def knowledge_health(request: Request):
    rag_url = request.app.state.deps.rag_service_url
    try:
        resp = urllib.request.urlopen(f"{rag_url}/health", timeout=5)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200]}


@router.post("/api/knowledge/query")
def knowledge_query(body: dict, request: Request):
    query_text = (body.get("query") or "").strip()
    if not query_text:
        raise HTTPException(400, "Query is required")
    rag_url = request.app.state.deps.rag_service_url
    try:
        payload = json.dumps(
            {"query": query_text, "top_k": body.get("top_k", 5)}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{rag_url}/query",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:200]}
