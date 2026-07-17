from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from src.agent.conversation_store import (
    ConversationStore,
    list_sessions as list_file_sessions,
)
from src.agent.runtime_factory import create_deterministic_agent
from src.backend.db import (
    PostgresConversationStore,
    _get_dsn,
    delete_session as db_delete_session,
    init_db,
    init_documents_db,
    list_sessions_db,
    rename_session_db,
)
from src.backend.dify_client import DifyClient
from src.backend.document_service import (
    delete_file as doc_delete_file,
    get_file as doc_get_file,
    list_files as doc_list_files,
    read_file_content as doc_read_file_content,
    store_file as doc_store_file,
)
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
                _info("cleanup", message="failed to kill web process")
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
    database_url: str | None = None,
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

    dsn = database_url or _get_dsn()
    if dsn:
        init_db(dsn)
        init_documents_db(dsn)
        _info(
            "database",
            message="PostgreSQL session store initialized",
            dsn=dsn.split("@")[-1] if "@" in dsn else "default",
        )

    _info("dify", message="Initializing Dify conversational layer")
    _dify_client: DifyClient | None = None
    try:
        from src.backend.dify_setup import setup_dify

        if setup_dify():
            dify_api_url = os.environ.get("DIFY_API_URL", "http://dify-api:5001")
            _dify_client = DifyClient(api_url=dify_api_url)
            _info("dify", message="Dify conversational layer active")
    except Exception:
        _info("dify", message="Dify not available, skipping setup")

    sessions_dir = str(Path.home() / ".orion" / "sessions")
    web_sessions: dict[str, ConversationStore] = {}

    def _get_or_create_session(session_id: str | None) -> ConversationStore:
        sid = session_id or uuid.uuid4().hex[:12]
        if sid not in web_sessions:
            if dsn:
                cs = PostgresConversationStore(
                    session_id=sid,
                    dsn=dsn,
                    source="api",
                    summarize_fn=agent._assessment_model.assess_raw,
                )
            else:
                cs = ConversationStore(
                    session_id=sid,
                    store_dir=sessions_dir,
                    source="api",
                    summarize_fn=agent._assessment_model.assess_raw,
                )
            web_sessions[sid] = cs
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
        if dsn:
            return {"sessions": list_sessions_db(dsn)}
        return {"sessions": list_file_sessions(sessions_dir)}

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        if dsn:
            deleted = db_delete_session(dsn, session_id)
            web_sessions.pop(session_id, None)
            if not deleted:
                from fastapi import HTTPException

                raise HTTPException(404, f"Session '{session_id}' not found")
            return {"status": "deleted", "session_id": session_id}
        path = Path(sessions_dir) / f"{session_id}.json"
        if not path.exists():
            from fastapi import HTTPException

            raise HTTPException(404, f"Session '{session_id}' not found")
        path.unlink()
        web_sessions.pop(session_id, None)
        return {"status": "deleted", "session_id": session_id}

    @app.patch("/api/sessions/{session_id}")
    def rename_session(session_id: str, body: dict):
        if dsn:
            new_title = body.get("title", "").strip()
            if not new_title:
                from fastapi import HTTPException

                raise HTTPException(400, "title is required")
            renamed = rename_session_db(dsn, session_id, new_title)
            if not renamed:
                from fastapi import HTTPException

                raise HTTPException(404, f"Session '{session_id}' not found")
            return {"status": "renamed", "session_id": session_id, "title": new_title}
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

    rag_service_url = os.environ.get("RAG_SERVICE_URL", "http://rag-service:8080")

    @app.get("/api/knowledge/health")
    def knowledge_health():
        try:
            import urllib.request

            resp = urllib.request.urlopen(f"{rag_service_url}/health", timeout=5)
            return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200]}

    @app.post("/api/knowledge/query")
    def knowledge_query(body: dict):
        query_text = (body.get("query") or "").strip()
        if not query_text:
            from fastapi import HTTPException

            raise HTTPException(400, "Query is required")
        try:
            import urllib.request

            payload = json.dumps(
                {"query": query_text, "top_k": body.get("top_k", 5)}
            ).encode("utf-8")
            req = urllib.request.Request(
                f"{rag_service_url}/query",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:200]}

    @app.get("/api/dify/health")
    def dify_health():
        return (
            _dify_client.health()
            if _dify_client
            else {"status": "error", "error": "Dify not initialized"}
        )

    @app.post("/api/dify/chat")
    def dify_chat(body: dict):
        question = (body.get("question") or "").strip()
        if not question:
            from fastapi import HTTPException

            raise HTTPException(400, "Question is required")

        user = body.get("user", "orion-user")
        conversation_id = body.get("conversation_id", "")

        if not _dify_client:
            return {"status": "error", "error": "Dify not initialized"}

        result = _dify_client.chat(
            query=question,
            user=user,
            conversation_id=conversation_id,
        )
        if "error" in result:
            return {"status": "error", "error": result["error"]}

        return {
            "answer": result.get("answer", ""),
            "conversation_id": result.get("conversation_id", ""),
            "message_id": result.get("message_id", ""),
        }

    @app.post("/api/dify/chat/stream")
    def dify_chat_stream(body: dict):
        question = (body.get("question") or "").strip()
        if not question:
            from fastapi import HTTPException

            raise HTTPException(400, "Question is required")

        if not _dify_client:
            return {"status": "error", "error": "Dify not initialized"}

        chunks = _dify_client.chat_stream(
            query=question,
            user=body.get("user", "orion-user"),
            conversation_id=body.get("conversation_id", ""),
        )
        return {"chunks": chunks}

    @app.get("/api/dify/conversations")
    def dify_list_conversations(limit: int = 20, cursor: str = ""):
        if not _dify_client:
            return {"status": "error", "error": "Dify not initialized"}
        return _dify_client.list_conversations(limit=limit, cursor=cursor)

    @app.delete("/api/dify/conversations/{conversation_id}")
    def dify_delete_conversation(conversation_id: str):
        if not _dify_client:
            return {"status": "error", "error": "Dify not initialized"}
        result = _dify_client.delete_conversation(conversation_id=conversation_id)
        if "error" in result:
            return {"status": "error", "error": result["error"]}
        return {"status": "deleted", "conversation_id": conversation_id}

    @app.post("/api/documents/upload")
    def document_upload(body: dict):
        content = (body.get("content") or "").encode("utf-8")
        filename = (body.get("filename") or "untitled.txt").strip()
        content_type = body.get("content_type")
        session_id = body.get("session_id")
        metadata = body.get("metadata")

        result = doc_store_file(
            dsn=dsn,
            filename=filename,
            content=content,
            content_type=content_type,
            session_id=session_id,
            metadata=metadata,
        )
        return result

    @app.get("/api/documents")
    def document_list(session_id: str | None = None, limit: int = 50):
        return {
            "documents": doc_list_files(dsn=dsn, session_id=session_id, limit=limit)
        }

    @app.get("/api/documents/{doc_id}")
    def document_get(doc_id: str):
        doc = doc_get_file(dsn=dsn, doc_id=doc_id)
        if doc is None:
            from fastapi import HTTPException

            raise HTTPException(404, f"Document '{doc_id}' not found")
        return doc

    @app.get("/api/documents/{doc_id}/download")
    def document_download(doc_id: str):
        from fastapi.responses import Response

        doc = doc_get_file(dsn=dsn, doc_id=doc_id)
        if doc is None:
            from fastapi import HTTPException

            raise HTTPException(404, f"Document '{doc_id}' not found")
        content = doc_read_file_content(doc["storage_path"])
        if content is None:
            raise HTTPException(404, "File content not found on disk")
        return Response(
            content=content,
            media_type=doc.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{doc["filename"]}"'
            },
        )

    @app.delete("/api/documents/{doc_id}")
    def document_delete(doc_id: str):
        deleted = doc_delete_file(dsn=dsn, doc_id=doc_id)
        if not deleted:
            from fastapi import HTTPException

            raise HTTPException(404, f"Document '{doc_id}' not found")
        return {"status": "deleted", "doc_id": doc_id}

    return app, sessions_dir, web_sessions


def run_web(
    port: int = 61888,
    target_store_path: str = "targets.json",
    server_name: str = "sv1",
    model: str | None = None,
    database_url: str | None = None,
) -> None:
    import atexit
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
