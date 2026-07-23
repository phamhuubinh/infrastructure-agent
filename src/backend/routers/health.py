from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Request

from src.backend.db import _get_dsn, _import_driver

router = APIRouter(tags=["health"])


class MetricsCollector:
    """Simple thread-safe in-memory metrics collector (singleton)."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._counters = {
            "execution_count": 0,
            "evidence_count": 0,
            "error_count": 0,
            "tool_call_count": 0,
        }
        self._active_sessions = 0

    @classmethod
    def get(cls) -> MetricsCollector:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def increment(self, metric: str, delta: int = 1) -> None:
        with self._lock:
            if metric in self._counters:
                self._counters[metric] += delta

    def set_active_sessions(self, count: int) -> None:
        with self._lock:
            self._active_sessions = count

    def snapshot(self) -> dict:
        with self._lock:
            return {
                **self._counters,
                "active_sessions": self._active_sessions,
            }


metrics = MetricsCollector.get()


@router.get("/api/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@router.get("/api/metrics")
def get_metrics():
    return {
        "metrics": metrics.snapshot(),
    }


@router.get("/api/check-model")
def check_model(request: Request):
    agent = request.app.state.deps.agent
    try:
        ok = agent.health_check(timeout=5)
        return {"status": "ok" if ok else "error"}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


@router.get("/api/models")
def list_models():
    import json
    from pathlib import Path
    from urllib import request as ur

    config_path = Path(__file__).resolve().parent.parent.parent.parent / "servers.json"
    servers_data = {}
    active = ""
    if config_path.exists():
        try:
            raw = json.loads(config_path.read_text())
            servers_data = raw.get("servers", {})
            active = raw.get("active_server", "")
        except (json.JSONDecodeError, OSError):
            pass

    models = []
    for name, cfg in servers_data.items():
        model_name = cfg.get("model", "unknown")
        base_url = str(cfg.get("base_url", ""))
        provider = cfg.get("provider", "unknown")

        # Health-check: try /health or /models endpoint
        available = False
        try:
            url = f"{base_url}/health"
            req = ur.Request(url)
            api_key = cfg.get("api_key")
            if api_key and str(api_key) not in ("EMPTY", ""):
                req.add_header("Authorization", f"Bearer {api_key}")
            res = ur.urlopen(req, timeout=3)
            available = res.status == 200
        except Exception:
            # Try /v1/models for OpenAI-compatible
            try:
                url = f"{base_url}/v1/models"
                req = ur.Request(url)
                api_key = cfg.get("api_key")
                if api_key and str(api_key) not in ("EMPTY", ""):
                    req.add_header("Authorization", f"Bearer {api_key}")
                res = ur.urlopen(req, timeout=3)
                available = res.status == 200
            except Exception:
                available = False

        models.append(
            {
                "name": name,
                "model": model_name,
                "provider": provider,
                "base_url": base_url,
                "available": available,
            }
        )

    return {"models": models, "active_server": active}


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
        ok = deps.agent.health_check(timeout=5)
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
