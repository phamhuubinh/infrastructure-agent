from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from src.agent.conversation_store import ConversationStore, list_sessions
from src.agent.runtime_factory import create_deterministic_agent
from src.shared.logger import info as _info


_WEB_PROCESSES: list[subprocess.Popen] = []


def cleanup_web() -> None:
    for p in _WEB_PROCESSES:
        try:
            p.terminate()
            p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
                p.wait(timeout=1)
            except Exception:
                pass
    subprocess.run(["pkill", "-f", "vite"], capture_output=True)
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


def create_app(
    target_store_path: str = "targets.json",
    server_name: str = "sv1",
    model: str | None = None,
) -> tuple:
    """Create FastAPI app and return (app, sessions_dir, web_sessions).

    Caller is responsible for mounting static files and starting uvicorn.
    """
    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
    except ImportError:
        print("Web UI requires: pip install fastapi uvicorn")
        sys.exit(1)

    agent = create_deterministic_agent(
        target_store_path=target_store_path,
        server_name=server_name,
        model=model,
    )

    sessions_dir = str(Path.home() / ".orion" / "sessions")
    web_sessions: dict[str, ConversationStore] = {}

    def _get_or_create_session(session_id: str | None) -> ConversationStore:
        sid = session_id or uuid.uuid4().hex[:12]
        if sid not in web_sessions:
            cs = ConversationStore(
                session_id=sid,
                store_dir=sessions_dir,
                source="web",
                summarize_fn=agent._assessment_model.assess_raw,
            )
            web_sessions[sid] = cs
            cs._save()
        cs = web_sessions[sid]
        agent._conversation_store = cs
        return cs

    app = FastAPI(title="Orion", version="1.0.0")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.get("/api/check-model")
    def check_model():
        try:
            ok = agent._assessment_model._client.health_check(timeout=5)
            return {"status": "ok" if ok else "error"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:120]}

    @app.get("/api/sessions")
    def list_sessions_api():
        return {"sessions": list_sessions(sessions_dir)}

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        path = Path(sessions_dir) / f"{session_id}.json"
        if not path.exists():
            from fastapi import HTTPException

            raise HTTPException(404, f"Session '{session_id}' not found")
        path.unlink()
        web_sessions.pop(session_id, None)
        return {"status": "deleted", "session_id": session_id}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(session_id: str, body: dict):
        path = Path(sessions_dir) / f"{session_id}.json"
        if not path.exists():
            from fastapi import HTTPException

            raise HTTPException(404, f"Session '{session_id}' not found")
        new_title = body.get("title", "").strip()
        if not new_title:
            from fastapi import HTTPException

            raise HTTPException(400, "title is required")
        data = json.loads(path.read_text())
        data["title"] = new_title
        path.write_text(json.dumps(data, indent=2))
        return {"status": "renamed", "session_id": session_id, "title": new_title}

    @app.post("/api/query")
    def query(body: dict):
        question = (body.get("question") or "").strip()
        if not question:
            from fastapi import HTTPException

            raise HTTPException(400, "Question is required")

        session_id = body.get("session_id")
        _get_or_create_session(session_id)

        result = agent.run_with_steps(question)

        return {
            "steps": result["steps"],
            "assessment": result["response"],
        }

    return app, sessions_dir, web_sessions


def run_web(
    port: int = 61888,
    target_store_path: str = "targets.json",
    server_name: str = "sv1",
    model: str | None = None,
) -> None:
    import atexit
    import webbrowser

    try:
        from fastapi.staticfiles import StaticFiles
        import uvicorn
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
    )

    is_prod = (Path(dist_dir) / "index.html").is_file() or (Path(client_dir) / "index.html").is_file()

    if is_prod:
        static_root = (
            client_dir
            if (Path(client_dir) / "index.html").is_file()
            else dist_dir
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

    frontend_port = 5173

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
