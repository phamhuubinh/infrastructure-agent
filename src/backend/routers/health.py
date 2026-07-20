from __future__ import annotations

import time

from fastapi import APIRouter, Request

from src.backend.db import _get_dsn, _import_driver

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/api/check-model")
def check_model(request: Request):
    agent = request.app.state.deps.agent
    try:
        ok = agent._assessment_model._client.health_check(timeout=5)
        return {"status": "ok" if ok else "error"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


@router.get("/api/status")
def service_status(request: Request):
    deps = request.app.state.deps
    components = {}

    # App info
    components["app"] = {"status": "ok", "version": "1.0.0"}

    # Database check
    db_status = "ok"
    db_error = None
    dsn = deps.dsn or _get_dsn()
    if dsn:
        driver, err = _import_driver()
        if err:
            db_status = "unavailable"
            db_error = err
        else:
            try:
                conn = driver.connect(dsn)
                conn.close()
            except Exception as exc:
                db_status = "error"
                db_error = str(exc)[:120]
    else:
        db_status = "not_configured"
    components["database"] = {"status": db_status}
    if db_error:
        components["database"]["error"] = db_error

    # LLM check
    llm_status = "ok"
    llm_error = None
    try:
        ok = deps.agent._assessment_model._client.health_check(timeout=5)
        if not ok:
            llm_status = "error"
            llm_error = "health check returned false"
    except Exception as exc:
        llm_status = "error"
        llm_error = str(exc)[:120]
    components["llm"] = {"status": llm_status}
    if llm_error:
        components["llm"]["error"] = llm_error

    # RAG service check
    rag_status = "ok"
    rag_error = None
    if hasattr(deps, "rag_service_url") and deps.rag_service_url:
        try:
            import urllib.request

            urllib.request.urlopen(f"{deps.rag_service_url}/health", timeout=5)
        except Exception as exc:
            rag_status = "error"
            rag_error = str(exc)[:120]
    else:
        rag_status = "not_configured"
    components["rag"] = {"status": rag_status}
    if rag_error:
        components["rag"]["error"] = rag_error

    overall = "ok"
    for _name, info in components.items():
        if info["status"] not in ("ok", "not_configured"):
            overall = "degraded"
            break

    return {
        "status": overall,
        "timestamp": time.time(),
        "components": components,
    }
