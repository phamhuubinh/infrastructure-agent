from __future__ import annotations

import atexit
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

from src.backend.auth import APIKeyMiddleware
from src.backend.dependencies import AppState
from src.backend.routers import (
    documents,
    health,
    knowledge,
    query,
    sessions,
)
from src.shared.logger import info as _info

_WEB_PROCESSES: list[subprocess.Popen] = []


def cleanup_web() -> None:
    for p in _WEB_PROCESSES:
        try:
            p.terminate()
            p.wait(timeout=2)
        except (ProcessLookupError, TimeoutError, OSError):
            try:
                p.kill()
                p.wait(timeout=1)
            except (ProcessLookupError, TimeoutError, OSError):
                _info("cleanup", message="failed to kill web process")
    _WEB_PROCESSES.clear()


def _wait_for_server(url: str, timeout: float = 30.0) -> bool:
    import urllib.request

    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except Exception:
            time.sleep(1)
    return False


def _setup_middleware(app: FastAPI) -> None:
    from fastapi.middleware.cors import CORSMiddleware

    if os.environ.get("ORION_ENV", "development") != "development":
        _info(
            "cors",
            message="CORS allow-all refused: ORION_ENV is not 'development'",
        )
        raise RuntimeError(
            "CORS allow_origins=['*'] is only permitted when ORION_ENV=development. "
            "Set ORION_ENV=development for local use or configure explicit CORS origins."
        )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.add_middleware(APIKeyMiddleware)


def _register_routers(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(sessions.router)
    app.include_router(query.router)
    app.include_router(knowledge.router)
    app.include_router(documents.router)


def create_app(
    target_store_path: str = "targets.json",
    server_name: str = "sv1",
    model: str | None = None,
    database_url: str | None = None,
) -> tuple:
    try:
        from fastapi import FastAPI
    except ImportError:
        print("Web UI requires: pip install fastapi uvicorn")
        sys.exit(1)

    deps = AppState(
        target_store_path=target_store_path,
        server_name=server_name,
        model=model,
        database_url=database_url,
    )

    app = FastAPI(title="Orion", version="1.0.0")
    app.state.deps = deps

    _setup_middleware(app)
    _register_routers(app)

    return app, deps.sessions_dir, deps.web_sessions


def run_web(
    port: int = 61888,
    target_store_path: str = "targets.json",
    server_name: str = "sv1",
    model: str | None = None,
    database_url: str | None = None,
) -> None:
    import webbrowser

    try:
        import uvicorn
        from fastapi.staticfiles import StaticFiles
    except ImportError:
        print("Web UI requires: pip install fastapi uvicorn")
        sys.exit(1)

    atexit.register(cleanup_web)

    project_root = Path(__file__).resolve().parent.parent.parent
    ui_dir = project_root / "ui"
    dist_dir = ui_dir / "dist"
    client_dir = dist_dir / "client"

    _info("orion-web", message="orion-web started", port=port)

    app, sessions_dir, web_sessions = create_app(
        target_store_path=target_store_path,
        server_name=server_name,
        model=model,
        database_url=database_url,
    )

    is_prod = (Path(dist_dir) / "index.html").is_file() or (
        Path(client_dir) / "index.html"
    ).is_file()

    if is_prod:
        static_root = (
            client_dir if (Path(client_dir) / "index.html").is_file() else dist_dir
        )
        app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")

        open_url = f"http://127.0.0.1:{port}"
        print("Starting Infrastructure Agent...", flush=True)
        print(f"  Backend + Frontend: {open_url}", flush=True)
        print(flush=True)
        webbrowser.open(open_url)
        uvicorn.run(app, host="127.0.0.1", port=port)
        return

    # --- Development mode ---
    print("Starting Infrastructure Agent...", flush=True)

    frontend_port = int(os.environ.get("ORION_FRONTEND_PORT", "5173"))

    vite_proc = subprocess.Popen(
        ["npx", "vite", "dev", "--port", str(frontend_port)],
        cwd=ui_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _WEB_PROCESSES.append(vite_proc)

    backend_url = f"http://127.0.0.1:{port}"
    open_url = f"http://127.0.0.1:{frontend_port}"

    if not _wait_for_server(f"http://127.0.0.1:{frontend_port}/"):
        print("ERROR: Frontend dev server did not start in time.", flush=True)
        cleanup_web()
        sys.exit(1)
    print("  ✓ Frontend started", flush=True)
    print(f"  ✓ Backend starting on {backend_url}", flush=True)
    print(f"  ✓ Opening browser at {open_url}", flush=True)
    print(flush=True)
    webbrowser.open(open_url)

    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    finally:
        _info("orion-web", message="orion-web stopped")
        cleanup_web()
