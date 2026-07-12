from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import webbrowser

from src.agent.runtime_factory import create_deterministic_agent
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore


def _add_target(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.target_file)
    registry = TargetRegistry(store=store)

    parts = args.spec.split("@", 1)
    if len(parts) != 2:
        print(f"Invalid format: '{args.spec}'. Expected name@host or name@host:port")
        sys.exit(1)
    name, host_port = parts
    if ":" in host_port:
        host, port_str = host_port.rsplit(":", 1)
        port = int(port_str)
    else:
        host = host_port
        port = 22
    registry.add(
        name=name,
        backend=SSHExecutionBackend(
            host=host,
            user=args.ssh_user,
            port=port,
            identity_file=args.ssh_identity_file,
        ),
    )
    print(f"Target '{name}' added.")


def _remove_target(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.target_file)
    registry = TargetRegistry(store=store)
    try:
        registry.remove(args.name)
        print(f"Target '{args.name}' removed.")
    except KeyError:
        print(f"Target '{args.name}' not found.")
        sys.exit(1)


def _list_targets(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.target_file)
    registry = TargetRegistry(store=store)
    names = registry.target_names()
    if not names:
        print("No targets configured.")
        return
    for name in names:
        print(name)


_last_request = None


_WEB_PROCESSES: list[subprocess.Popen] = []


def _cleanup_web() -> None:
    for p in _WEB_PROCESSES:
        try:
            p.terminate()
            p.wait(timeout=3)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
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


def _run_web(args: argparse.Namespace) -> None:
    import atexit
    atexit.register(_cleanup_web)

    try:
        from fastapi import FastAPI
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.staticfiles import StaticFiles
        import uvicorn
    except ImportError:
        print("Web UI requires: pip install fastapi uvicorn")
        sys.exit(1)

    from src.agent.runtime_factory import create_deterministic_agent

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ui_dir = os.path.join(project_root, "ui")
    dist_dir = os.path.join(ui_dir, "dist")
    client_dir = os.path.join(dist_dir, "client")
    is_prod = os.path.isfile(os.path.join(dist_dir, "index.html")) or os.path.isfile(os.path.join(client_dir, "index.html"))

    backend_port = args.port

    app = FastAPI(title="Infrastructure Agent", version="1.0.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    agent = create_deterministic_agent(
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
    )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": "1.0.0"}

    @app.post("/api/query")
    def query(body: dict):
        from src.model.llm_assessment_adapter import LLMAssessmentAdapter
        from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
        import json as _json

        question = (body.get("question") or "").strip()
        if not question:
            from fastapi import HTTPException
            raise HTTPException(400, "Question is required")

        def _safe_data(val: object) -> object:
            """Recursively sanitize data for JSON serialization."""
            import typing
            if val is None or isinstance(val, (bool, int, float, str)):
                return val
            if isinstance(val, (list, tuple)):
                return [_safe_data(v) for v in val]
            if isinstance(val, dict):
                return {str(k): _safe_data(v) for k, v in val.items()}
            return str(val)

        # Step 1: Resolve intent
        investigation = agent.execute_pipeline_only(question)

        steps: list[dict] = []

        plan_steps = []
        if investigation.execution_plan:
            for step in investigation.execution_plan.steps:
                plan_steps.append({
                    "capability": step.capability.name,
                    "evidence": step.capability.evidence_name,
                })

        steps.append({
            "type": "intent",
            "intent": investigation.intent.name if investigation.intent else "N/A",
            "confidence": investigation.confidence.name if investigation.confidence else "N/A",
            "target": investigation.target or "localhost",
            "matched_keywords": list(investigation.matched_keywords),
            "required_evidence": [e.name for e in investigation.required_evidence],
            "optional_evidence": [e.name for e in investigation.optional_evidence],
            "planned_capabilities": plan_steps,
        })

        # Step 2: Evidence collection
        evidence_list = []
        for pkg in investigation.evidence:
            data_str = str(pkg.data) if pkg.data is not None else None
            evidence_list.append({
                "capability": pkg.capability_name,
                "evidence": pkg.evidence_name,
                "success": pkg.success,
                "error": pkg.error if not pkg.success else None,
                "data_preview": data_str[:500] if data_str else None,
                "data": _safe_data(pkg.data),
            })

        metrics = investigation.runtime_metrics
        steps.append({
            "type": "evidence",
            "collected": len(investigation.evidence),
            "successful": sum(1 for p in investigation.evidence if p.success),
            "failed": sum(1 for p in investigation.evidence if not p.success),
            "items": evidence_list,
            "complete": investigation.evidence_complete,
            "missing_evidence": list(investigation.missing_evidence),
            "runtime_metrics": {
                "execution_duration": round(getattr(metrics, 'execution_duration', 0), 3) if metrics else 0,
                "total_nodes": getattr(metrics, 'total_nodes', 0) if metrics else 0,
                "successful_nodes": getattr(metrics, 'successful_nodes', 0) if metrics else 0,
                "failed_nodes": getattr(metrics, 'failed_nodes', 0) if metrics else 0,
                "parallel_ratio": round(getattr(metrics, 'parallel_ratio', 0), 2) if metrics else 0,
                "tool_calls": getattr(metrics, 'tool_calls', 0) if metrics else 0,
            },
        })

        # Step 3: Build prompt
        from src.pipeline.assessment_adapter import AssessmentAdapter
        adapter = AssessmentAdapter()
        req = adapter.build(investigation)
        prompt = build_assessment_prompt(req)

        steps.append({
            "type": "prompt",
            "size": len(prompt),
            "preview": prompt[:500],
        })

        # Step 4: LLM assessment (streaming)
        import time as _time
        llm_adapter = agent._assessment_model
        result = llm_adapter.assess_with_result(req) if hasattr(llm_adapter, 'assess_with_result') else None

        if result:
            steps.append({
                "type": "assessment",
                "model": result.model,
                "latency_ms": result.latency_ms,
                "success": result.success,
                "error": result.error,
                "content": result.content,
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
            })
        else:
            steps.append({
                "type": "assessment",
                "content": agent.run(question),
            })

        return {
            "steps": steps,
            "assessment": steps[-1].get("content", ""),
        }

    if is_prod:
        static_root = client_dir if os.path.isfile(os.path.join(client_dir, "index.html")) else dist_dir
        app.mount("/", StaticFiles(directory=static_root, html=True), name="frontend")

        open_url = f"http://127.0.0.1:{backend_port}"
        print("Starting Infrastructure Agent...", flush=True)
        print(f"  Backend + Frontend: {open_url}", flush=True)
        print(flush=True)
        webbrowser.open(open_url)
        uvicorn.run(app, host="127.0.0.1", port=backend_port)
        return

    # --- Development mode ---
    print("Starting Infrastructure Agent...", flush=True)

    frontend_port = 5173

    vite_proc = subprocess.Popen(
        [os.path.join(ui_dir, "node_modules", ".bin", "vite"), "dev", "--port", str(frontend_port)],
        cwd=ui_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _WEB_PROCESSES.append(vite_proc)

    backend_url = f"http://127.0.0.1:{backend_port}"
    open_url = f"http://127.0.0.1:{frontend_port}"

    if not _wait_for_server(f"http://127.0.0.1:{frontend_port}/"):
        print("ERROR: Frontend dev server did not start in time.", flush=True)
        _cleanup_web()
        sys.exit(1)
    print("  ✓ Frontend started", flush=True)

    print(f"  ✓ Backend starting on {backend_url}", flush=True)
    print(f"  ✓ Opening browser at {open_url}", flush=True)
    print(flush=True)
    webbrowser.open(open_url)

    try:
        uvicorn.run(app, host="127.0.0.1", port=backend_port)
    finally:
        _cleanup_web()


def _run_agent(args: argparse.Namespace) -> None:
    agent = create_deterministic_agent(
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
    )

    print("Infrastructure Investigation Agent")
    print("=" * 36)
    print("  /help    Commands")
    print("  Ctrl+D   Exit")
    print("  Enter    Submit")
    print("  Ctrl+C   Cancel")
    print()

    while True:
        try:
            sys.stdout.write("> ")
            sys.stdout.flush()
            line = sys.stdin.readline()
            if not line:
                print()
                break
        except KeyboardInterrupt:
            print()
            continue
        except EOFError:
            print()
            break

        raw_input = line.rstrip("\r\n")

        if not raw_input:
            continue

        # --- Built-in commands ---
        if raw_input.lower() in {"/exit", "/quit", "exit", "quit"}:
            break

        if raw_input.lower() == "/help":
            print()
            print("  /exit       Exit")
            print("  /help       Show this help")
            print("  /model      Show current model")
            print("  /evidence   Show evidence from last request")
            print("  /intent     Show intent from last request")
            print("  /target     Show target from last request")
            print()
            continue

        if raw_input.lower() == "/model":
            print(f"  Model: {args.server or 'mock'}")
            if args.model:
                print(f"  Override: {args.model}")
            continue

        if raw_input.lower() == "/evidence":
            if _last_request is None:
                print("  No previous request.")
                continue
            print(f"  Evidence collected: {len(_last_request.evidence)} items")
            print(f"  Complete: {_last_request.evidence_complete}")
            for pkg in _last_request.evidence:
                status = "✓" if pkg.success else "✗"
                print(f"    {status} {pkg.capability_name}")
            continue

        if raw_input.lower() == "/intent":
            if _last_request is None:
                print("  No previous request.")
                continue
            print(f"  Intent: {_last_request.intent.name if _last_request.intent else 'N/A'}")
            continue

        if raw_input.lower() == "/target":
            if _last_request is None:
                print("  No previous request.")
                continue
            print(f"  Target: {_last_request.target or 'N/A'}")
            continue

        if raw_input.startswith("/"):
            print(f"  Unknown command: {raw_input}. Type /help.")
            continue

        # --- Execute question ---
        print()
        print("  [Sending...]")
        sys.stdout.flush()
        import signal as _sig
        _old_sigint = _sig.signal(_sig.SIGINT, lambda *_: (_sig.default_int_handler(), None))
        try:
            is_infra, _ = agent.classify(raw_input)
            if is_infra:
                _last_request = agent.execute_pipeline_only(raw_input)
                answer = agent.run(raw_input)
            else:
                answer = agent.chat(raw_input)
            print()
            print(answer)
        except KeyboardInterrupt:
            print()
            print("  Cancelled.")
        except Exception as e:
            print()
            print(f"  Error: {e}")
        finally:
            _sig.signal(_sig.SIGINT, _old_sigint)
            print("---")


def main() -> None:
    parser = argparse.ArgumentParser(description="Infrastructure Agent")
    parser.add_argument(
        "--target-file", type=str, default="targets.json",
        help="Execution target configuration file"
    )
    parser.add_argument(
        "--server", type=str, default="sv1",
        help="Model server name from servers.json (default: sv1)"
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override model name (overrides servers.json)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show detailed debug output (prompt stats, timings, raw responses)"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="Show one-line per iteration status"
    )
    parser.add_argument(
        "--web", action="store_true",
        help="Start web UI server instead of terminal mode"
    )
    parser.add_argument(
        "--port", type=int, default=61888,
        help="Port for web UI server (default: 61888)"
    )
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add-target", help="Add a remote target")
    add_parser.add_argument(
        "spec", type=str, help="Target spec in format name@host or name@host:port"
    )
    add_parser.add_argument("--ssh-user", type=str, default="root", help="SSH user")
    add_parser.add_argument(
        "--ssh-identity-file", type=str, default=None, help="SSH identity file path"
    )

    rem_parser = subparsers.add_parser("remove-target", help="Remove a target")
    rem_parser.add_argument("name", type=str, help="Target name")

    subparsers.add_parser("list-targets", help="List all targets")

    args = parser.parse_args()

    if args.command == "add-target":
        _add_target(args)
    elif args.command == "remove-target":
        _remove_target(args)
    elif args.command == "list-targets":
        _list_targets(args)
    elif args.web:
        _run_web(args)
    else:
        _run_agent(args)


if __name__ == "__main__":
    main()
