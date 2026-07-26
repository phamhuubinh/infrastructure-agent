from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from src.agent.runtime_factory import create_deterministic_agent
from src.backend.app import run_web
from src.backend.sqlite_store import (
    SQLiteConversationStore,
    migrate_json_to_sqlite,
)
from src.shared.logger import info as _info
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore

_last_request = None


# ============================================================
# Target management
# ============================================================


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
    store = TargetStore(path=args.target_file)
    registry = TargetRegistry(store=store)
    names = registry.target_names()
    if not names:
        print("No targets configured.")
        return
    for name in names:
        print(name)


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
            "  run                   Run terminal agent (default)\n"
            "    --server <name>       Model server (default: sv1)\n"
            "    --model <name>        Override model name\n"
            "    --target-file <path>  Target config (default: targets.json)\n"
            "    --verbose             Debug output\n"
            "    --status              One-line per-iteration status\n"
            "  resume <id>           Resume session\n"
            "    (same options as run)\n"
            "  web                   Start web UI\n"
            "    --port <port>         Port (default: 61888)\n"
            "    --server <name>       Model server\n"
            "    --model <name>        Override model name\n"
            "  log                   Tail structured log output\n"
            "  add-target            Add a remote SSH target\n"
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
    migrate_parser.add_argument(
        "--sqlite-path",
        type=str,
        default=None,
        help="SQLite database path (default: ~/.orion/sessions.db)",
    )

    run_parser = subparsers.add_parser("run", help=argparse.SUPPRESS)
    run_parser.add_argument(
        "--server", type=str, default="sv1", help="Model server name (default: sv1)"
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
        "--server", type=str, default="sv1", help="Model server name (default: sv1)"
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
        "--server", type=str, default="sv1", help="Model server name (default: sv1)"
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
        default=False,
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

        sessions = SQLiteConversationStore.list_sessions()
        if not sessions:
            print("No sessions found.")
            return
        print(f"{'ID':<24} {'Source':<10} {'Turns':<6} {'Updated':<20} Preview")
        print("-" * 100)
        for s in sessions:
            preview = s["preview"][:50]
            print(
                f"{s['id']:<24} {s['source']:<10} {s['turns']:<6} {s['updated'][:19]:<20} {preview}"
            )
        return

    if args.command == "resume":
        args.resume = args.id
        _run_agent(args)
        return

    if args.command == "web":
        run_web(
            port=args.port,
            target_store_path=args.target_file,
            server_name=args.server,
            model=args.model,
        )
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
