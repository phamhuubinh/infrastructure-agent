from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from src.agent.runtime_factory import create_deterministic_agent
from src.backend.app import run_web
from src.backend.sqlite_store import (
    SQLiteConversationStore,
    migrate_json_to_sqlite,
)
from src.model.config_store import ModelConfigStore
from src.shared.logger import info as _info
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore

_last_request = None


def _list_saved_sessions() -> list[dict]:
    """List sessions from every persistence backend active in this runtime."""
    sessions_by_id = {
        str(session["id"]): session
        for session in SQLiteConversationStore.list_sessions()
    }

    # Packaged Orion stores Web sessions in PostgreSQL while terminal sessions
    # created by older/current CLI runs may still live in SQLite. Merge both so
    # `orion session list` reflects what users see across Web and terminal.
    from src.backend.db import _get_dsn, list_sessions_db

    dsn = _get_dsn()
    if dsn:
        for session in list_sessions_db(dsn):
            sessions_by_id[str(session["id"])] = session

    return sorted(
        sessions_by_id.values(),
        key=lambda session: str(session.get("updated", "")),
        reverse=True,
    )[:50]


def _print_saved_sessions(sessions: list[dict]) -> None:
    if not sessions:
        print("No sessions found.")
        return
    print(f"{'ID':<24} {'Source':<10} {'Turns':<6} {'Updated':<20} Title / Preview")
    print("-" * 110)
    for session in sessions:
        label = str(session.get("title") or session.get("preview") or "")[:60]
        print(
            f"{str(session['id']):<24} "
            f"{str(session.get('source', '')):<10} "
            f"{str(session.get('turns', 0)):<6} "
            f"{str(session.get('updated', ''))[:19]:<20} "
            f"{label}"
        )


def _run_web_command(args: argparse.Namespace) -> None:
    packaged_url = os.environ.get("ORION_PACKAGED_WEB_URL", "").strip()
    if packaged_url:
        print(f"Orion Web UI is already running at {packaged_url}")
        return
    run_web(
        port=args.port,
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
    )


# ============================================================
# Model management
# ============================================================


def _manage_model(args: argparse.Namespace) -> None:
    store = ModelConfigStore()
    action = args.model_action
    if action == "list":
        data = store.list_public()
        if not data["models"]:
            print("No model configured. Orion is available in setup mode.")
            return
        for item in data["models"]:
            marker = "*" if item["active"] else " "
            print(
                f"{marker} {item['name']}: {item['provider']} / "
                f"{item['model']} @ {item['base_url']}"
            )
        return

    if action == "add":
        api_key = args.api_key
        if args.api_key_stdin:
            api_key = sys.stdin.readline().rstrip("\r\n")
        try:
            store.upsert(
                args.name,
                {
                    "provider": args.provider,
                    "base_url": args.base_url,
                    "model": args.model_name,
                    "api_key": api_key or None,
                    "timeout": args.timeout,
                    "temperature": args.temperature,
                    "max_tokens": args.max_tokens,
                },
                activate=not args.no_activate,
            )
        except ValueError as exc:
            print(f"Model configuration error: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Model connection '{args.name}' saved.")
        print(f"Run: orion model test {args.name}")
        return

    if action == "test":
        try:
            result = store.test(args.name, timeout=args.timeout)
        except KeyError as exc:
            print(f"Model connection '{args.name}' not found.", file=sys.stderr)
            raise SystemExit(1) from exc
        if result["status"] != "ok":
            print(f"Connection failed: {result.get('error', 'unknown error')}")
            raise SystemExit(1)
        print(f"Connection '{args.name}' is healthy.")
        return

    if action == "use":
        try:
            store.set_active(args.name)
        except KeyError as exc:
            print(f"Model connection '{args.name}' not found.", file=sys.stderr)
            raise SystemExit(1) from exc
        print(f"Model connection '{args.name}' selected.")
        return

    if action == "remove":
        if not store.delete(args.name):
            print(f"Model connection '{args.name}' not found.", file=sys.stderr)
            raise SystemExit(1)
        print(f"Model connection '{args.name}' removed.")
        return

    raise SystemExit("Choose a model action: list, add, test, use, or remove")


# ============================================================
# Target management
# ============================================================


def _add_target(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.target_file, discover_ssh_targets_enabled=True)
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
        strict_host_key_checking=args.strict_host_key_checking,
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
    store = TargetStore(path=args.target_file, discover_ssh_targets_enabled=True)
    registry = TargetRegistry(store=store)
    names = registry.target_names()
    if not names:
        print("No targets configured.")
        return
    for name in names:
        backend = registry.backend(name)
        if backend is None:
            print(name)
            continue
        identity = registry.identity(name)
        print(
            f"{identity.name}\t{identity.display_name}\t"
            f"{identity.backend_type}\t{identity.execution_scope}"
        )


# ============================================================
# Log tail
# ============================================================


def _run_log() -> None:
    from pathlib import Path

    _log_path = str(Path.home() / ".orion" / "orion.log")
    try:
        print("Orion log (Ctrl+C to stop)")
        _last_size = 0
        while True:
            try:
                with open(_log_path) as _f:
                    _f.seek(_last_size)
                    for _line in _f:
                        print(_line, end="", flush=True)
                    _last_size = _f.tell()
            except FileNotFoundError:
                _info("cli", message="log file not found, retrying")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()


# ============================================================
# Agent REPL
# ============================================================


def _run_agent(args: argparse.Namespace) -> None:
    global _last_request

    _info("orion", message="orion started")

    from uuid import uuid4

    resume_id = getattr(args, "resume", None)
    if resume_id:
        print(f"Resuming session: {resume_id}")
    else:
        resume_id = uuid4().hex[:12]

    # SQLite is the default persistence backend (replaces JSON files).
    store = SQLiteConversationStore(
        session_id=resume_id,
        source="terminal",
    )

    agent = create_deterministic_agent(
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
        conversation_store=store,
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
                print(f"    {status} {pkg.evidence_name}")
            continue

        if raw_input.lower() == "/intent":
            if _last_request is None:
                print("  No previous request.")
                continue
            print(
                f"  Intent: {_last_request.intent.name if _last_request.intent else 'N/A'}"
            )
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

        _old_sigint = _sig.signal(
            _sig.SIGINT,
            lambda signum, frame: (_sig.default_int_handler(signum, frame), None),
        )
        try:
            result = agent.run_with_steps(raw_input)
            _last_request = result.get("investigation")
            answer = result["response"]
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

    _info("orion", message="orion stopped")


# ============================================================
# Entry point
# ============================================================


def main() -> None:
    from src.shared.config_schema import ConfigValidationError, validate_all_configs

    try:
        validate_all_configs()
    except ConfigValidationError as exc:
        print(f"Configuration error:\n{exc}", file=sys.stderr)
        sys.exit(1)

    if os.environ.get("ORION_PACKAGED_WEB_URL", "").strip():
        web_help = (
            "  web                   Start packaged Web UI and follow Web logs\n"
            "    Ctrl+C                Stop API, UI, and reverse proxy\n"
            "  log                   Follow logs from every Compose service\n"
            "    Ctrl+C                Exit logs; keep Orion running\n"
        )
    else:
        web_help = (
            "  web                   Start local API + Vite Web UI\n"
            "    --port <port>         Port (default: 61888)\n"
            "    --server <name>       Model connection\n"
            "    --model <name>        Override model name\n"
            "  log                   Tail structured log output\n"
        )

    parser = argparse.ArgumentParser(
        description="Orion — Infrastructure Investigation Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  help                  Show this help message\n"
            "  session               Manage sessions\n"
            "    session list        List all saved sessions\n"
            "    session delete <id> Delete a specific session by ID\n"
            "    session clean       Delete ALL sessions\n"
            "  migrate              Migrate JSON sessions to SQLite\n"
            "  model                Configure and test model connections\n"
            "    model list          List configured models\n"
            "    model add           Add an OpenAI-compatible connection\n"
            "    model test <name>   Test a saved connection\n"
            "    model use <name>    Select a connection\n"
            "    model remove <name> Remove a connection\n"
            "  run                   Run terminal agent (default)\n"
            "    --server <name>       Model connection (default: active)\n"
            "    --model <name>        Override model name\n"
            "    --target-file <path>  Target config (default: targets.json)\n"
            "    --verbose             Debug output\n"
            "    --status              One-line per-iteration status\n"
            "  resume <id>           Resume session\n"
            "    (same options as run)\n"
            + web_help
            + "  add-target            Add a remote SSH target\n"
            "  remove-target         Remove a remote SSH target\n"
            "  list-targets          List all configured targets\n"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", help=argparse.SUPPRESS)

    subparsers.add_parser("help", help=argparse.SUPPRESS, add_help=False)

    session_parser = subparsers.add_parser("session", help=argparse.SUPPRESS)
    session_sub = session_parser.add_subparsers(
        dest="session_action", help=argparse.SUPPRESS
    )
    session_sub.add_parser("list", help=argparse.SUPPRESS)
    del_parser = session_sub.add_parser("delete", help=argparse.SUPPRESS)
    del_parser.add_argument("id", type=str, help=argparse.SUPPRESS)
    del_parser.add_argument("-y", "--yes", action="store_true", help=argparse.SUPPRESS)
    session_sub.add_parser("clean", help=argparse.SUPPRESS)

    # Migrate command: JSON → SQLite
    migrate_parser = subparsers.add_parser("migrate", help=argparse.SUPPRESS)
    migrate_parser.add_argument(
        "--json-dir",
        type=str,
        default=None,
        help="JSON sessions directory (default: ~/.orion/sessions/)",
    )

    model_parser = subparsers.add_parser(
        "model", help="Manage user-provided model connections"
    )
    model_sub = model_parser.add_subparsers(
        dest="model_action", metavar="ACTION", required=True
    )
    model_sub.add_parser("list", help="List saved model connections")

    model_add = model_sub.add_parser(
        "add", help="Save an OpenAI-compatible model connection"
    )
    model_add.add_argument("name", help="Unique connection name")
    model_add.add_argument(
        "--provider", default="openai", choices=["openai", "ollama", "vllm"]
    )
    model_add.add_argument("--base-url", required=True, help="Provider base URL")
    model_add.add_argument(
        "--model", dest="model_name", required=True, help="Provider model name"
    )
    model_add.add_argument("--api-key", default="", help="Provider API key")
    model_add.add_argument(
        "--api-key-stdin",
        action="store_true",
        help="Read the model API key from stdin instead of process arguments",
    )
    model_add.add_argument("--timeout", type=int, default=180)
    model_add.add_argument("--temperature", type=float, default=0.0)
    model_add.add_argument("--max-tokens", type=int, default=4096)
    model_add.add_argument("--no-activate", action="store_true")

    model_test = model_sub.add_parser("test", help="Test a saved connection")
    model_test.add_argument("name", help="Connection name")
    model_test.add_argument("--timeout", type=int, default=30)

    model_use = model_sub.add_parser("use", help="Select the active connection")
    model_use.add_argument("name", help="Connection name")
    model_remove = model_sub.add_parser("remove", help="Delete a connection")
    model_remove.add_argument("name", help="Connection name")
    migrate_parser.add_argument(
        "--sqlite-path",
        type=str,
        default=None,
        help="SQLite database path (default: ~/.orion/sessions.db)",
    )

    run_parser = subparsers.add_parser("run", help=argparse.SUPPRESS)
    run_parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Model connection name (default: active)",
    )
    run_parser.add_argument(
        "--model", type=str, default=None, help="Override model name"
    )
    run_parser.add_argument(
        "--target-file",
        type=str,
        default="targets.json",
        help="Target config file (default: targets.json)",
    )
    run_parser.add_argument(
        "--verbose", action="store_true", help="Show detailed debug output"
    )
    run_parser.add_argument(
        "--status", action="store_true", help="Show one-line per-iteration status"
    )

    resume_parser = subparsers.add_parser("resume", help=argparse.SUPPRESS)
    resume_parser.add_argument("id", type=str, help=argparse.SUPPRESS)
    resume_parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Model connection name (default: active)",
    )
    resume_parser.add_argument(
        "--model", type=str, default=None, help="Override model name"
    )
    resume_parser.add_argument(
        "--target-file",
        type=str,
        default="targets.json",
        help="Target config file (default: targets.json)",
    )

    web_parser = subparsers.add_parser("web", help=argparse.SUPPRESS)
    web_parser.add_argument(
        "--port", type=int, default=61888, help="Web UI port (default: 61888)"
    )
    web_parser.add_argument(
        "--server",
        type=str,
        default=None,
        help="Model connection name (default: active)",
    )
    web_parser.add_argument(
        "--model", type=str, default=None, help="Override model name"
    )
    web_parser.add_argument(
        "--target-file",
        type=str,
        default="targets.json",
        help="Target config file (default: targets.json)",
    )

    subparsers.add_parser("log", help=argparse.SUPPRESS)

    add_parser = subparsers.add_parser("add-target", help=argparse.SUPPRESS)
    add_parser.add_argument("spec", type=str, help=argparse.SUPPRESS)
    add_parser.add_argument(
        "--ssh-user", type=str, default="root", help=argparse.SUPPRESS
    )
    add_parser.add_argument(
        "--ssh-identity-file", type=str, default=None, help=argparse.SUPPRESS
    )
    add_parser.add_argument(
        "--strict-host-key-checking",
        action="store_true",
        default=True,
        help=argparse.SUPPRESS,
    )
    add_parser.add_argument(
        "--insecure-skip-host-key-checking",
        dest="strict_host_key_checking",
        action="store_false",
        help=argparse.SUPPRESS,
    )

    rem_parser = subparsers.add_parser("remove-target", help=argparse.SUPPRESS)
    rem_parser.add_argument("name", type=str, help=argparse.SUPPRESS)

    subparsers.add_parser("list-targets", help=argparse.SUPPRESS)

    import sys as _sys

    if len(_sys.argv) == 1:
        _sys.argv.append("run")
    args = parser.parse_args()

    if args.command == "help" or args.command is None:
        parser.print_help()
        return

    if args.command == "migrate":
        count = migrate_json_to_sqlite(
            json_dir=args.json_dir,
            sqlite_path=args.sqlite_path,
        )
        print(f"Migrated {count} sessions from JSON to SQLite.")
        return

    if args.command == "model":
        _manage_model(args)
        return

    if args.command == "session":
        if args.session_action == "delete":
            deleted = SQLiteConversationStore.delete_session(args.id)
            if not deleted:
                print(f"Session '{args.id}' not found.")
                return
            if not args.yes:
                ans = input(f"Delete session '{args.id}'? [y/N] ").strip().lower()
                if ans not in ("y", "yes"):
                    print("Cancelled.")
                    return
            print(f"Session '{args.id}' deleted.")
            return

        if args.session_action == "clean":
            DB_PATH = Path.home() / ".orion" / "sessions.db"
            import os as _os

            if _os.path.exists(DB_PATH):
                _os.remove(DB_PATH)
                print("All sessions deleted (SQLite database removed).")
            else:
                print("No sessions database found.")
            return

        _print_saved_sessions(_list_saved_sessions())
        return

    if args.command == "resume":
        args.resume = args.id
        _run_agent(args)
        return

    if args.command == "web":
        _run_web_command(args)
        return

    if args.command == "log":
        _run_log()
        return

    if args.command == "run":
        _run_agent(args)
        return

    if args.command == "add-target":
        _add_target(args)
    elif args.command == "remove-target":
        _remove_target(args)
    elif args.command == "list-targets":
        _list_targets(args)
    else:
        _run_agent(args)


if __name__ == "__main__":
    main()
