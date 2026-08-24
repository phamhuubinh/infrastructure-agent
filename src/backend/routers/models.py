from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/models", tags=["models"])


def _reload(request: Request) -> dict:
    request.app.state.deps.reload_models()
    return request.app.state.deps.model_store.list_public()


@router.get("")
def list_models(request: Request):
    return request.app.state.deps.model_store.list_public()


@router.post("")
def save_model(body: dict, request: Request):
    name = str(body.get("name", "")).strip()
    existing = request.app.state.deps.model_store.get(name) or {}
    api_key = body.get("api_key")
    config = {
        "provider": str(body.get("provider", existing.get("provider", "openai"))),
        "base_url": str(body.get("base_url", existing.get("base_url", ""))).strip(),
        "model": str(body.get("model", existing.get("model", ""))).strip(),
        "timeout": body.get("timeout", existing.get("timeout", 180)),
        "temperature": body.get("temperature", existing.get("temperature", 0.0)),
    }
    if api_key is not None and str(api_key).strip():
        config["api_key"] = str(api_key).strip()
    elif existing.get("api_key"):
        config["api_key"] = existing["api_key"]
    activate = bool(body.get("activate", True))
    try:
        request.app.state.deps.model_store.upsert(
            name,
            config,
            # A newly saved connection is unverified.  Test it before making
            # it the active runtime connection.
            activate=False,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if activate:
        result = request.app.state.deps.model_store.test(name)
        if result["status"] != "ok":
            raise HTTPException(
                503, str(result.get("error", "Model connection test failed"))
            )
        try:
            request.app.state.deps.model_store.set_active(name)
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
    return _reload(request)


@router.post("/{name}/activate")
def activate_model(name: str, request: Request):
    try:
        result = request.app.state.deps.model_store.test(name)
        if result["status"] != "ok":
            raise HTTPException(
                503, str(result.get("error", "Model connection test failed"))
            )
        request.app.state.deps.model_store.set_active(name)
    except KeyError as exc:
        raise HTTPException(404, f"Model connection '{name}' not found") from exc
    except ValueError as exc:
        raise HTTPException(503, str(exc)) from exc
    return _reload(request)


@router.post("/{name}/test")
def test_model(name: str, request: Request, body: dict | None = None):
    timeout = 30
    if body is not None:
        try:
            timeout = int(body.get("timeout", 30))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, "timeout must be an integer") from exc
    try:
        result = request.app.state.deps.model_store.test(name, timeout=timeout)
    except KeyError as exc:
        raise HTTPException(404, f"Model connection '{name}' not found") from exc
    if result["status"] != "ok":
        raise HTTPException(
            503, str(result.get("error", "Model connection test failed"))
        )
    return result


@router.delete("/{name}")
def delete_model(name: str, request: Request):
    if not request.app.state.deps.model_store.delete(name):
        raise HTTPException(404, f"Model connection '{name}' not found")
    return _reload(request)
