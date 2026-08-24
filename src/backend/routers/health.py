from __future__ import annotations

import shutil
import time

from fastapi import APIRouter, Request

from src.backend.db import _get_dsn, _import_driver
from src.observability.events import get_event_store

router = APIRouter(tags=["health"])


event_store = get_event_store()

CORE_RUNTIME_BINARIES: tuple[str, ...] = (
    "df",
    "ip",
    "lsblk",
    "ping",
    "ps",
    "ssh",
    "ss",
    "top",
)


def _runtime_dependency_status() -> dict[str, object]:
    missing = [name for name in CORE_RUNTIME_BINARIES if shutil.which(name) is None]
    return {
        "ready": not missing,
        "required_binaries": list(CORE_RUNTIME_BINARIES),
        "missing_binaries": missing,
    }


@router.get("/api/health")
def health():
    return {
        "status": "ok",
        "version": "1.0.0",
        "runtime_dependencies": _runtime_dependency_status(),
    }


@router.get("/api/metrics")
def get_metrics():
    return {
        "metrics": event_store.metrics_snapshot(),
    }


@router.get("/api/check-model")
def check_model(request: Request):
    request.app.state.deps.reload_models_if_changed()
    if request.app.state.deps.model_store.active() is None:
        return {"status": "not_configured", "health_state": "not_configured"}
    agent = request.app.state.deps.agent
    try:
        ok = agent.health_check(timeout=5)
        return {
            "status": "ok" if ok else "error",
            "health_state": "healthy" if ok else "unhealthy",
        }
    except Exception as exc:
        return {
            "status": "error",
            "health_state": "unhealthy",
            "error": str(exc)[:120],
        }


@router.get("/api/status")
def service_status(request: Request):
    deps = request.app.state.deps
    deps.reload_models_if_changed()
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
    llm_status = "not_configured"
    llm_error = None
    if deps.model_store.active() is not None:
        try:
            ok = deps.agent.health_check(timeout=5)
            llm_status = "ok" if ok else "error"
            if not ok:
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
