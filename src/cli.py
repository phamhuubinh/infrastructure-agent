from __future__ import annotations

import argparse
import sys

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


def _run_agent(args: argparse.Namespace) -> None:
    agent = create_deterministic_agent(
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
    )

    print("Infrastructure Investigation Agent")
    print("=" * 36)
    print("Gõ /help để xem hướng dẫn, /exit để thoát.")
    print()

    while True:
        try:
            print("> ", end="", flush=True)
            lines: list[str] = []
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.rstrip("\n")
                if not line and lines:
                    break
                if not line and not lines:
                    continue
                lines.append(line)

            raw_input = "\n".join(lines).strip()
        except (KeyboardInterrupt, EOFError):
            print()
            break

        if not raw_input:
            continue

        # --- Built-in commands ---
        if raw_input.lower() in {"/exit", "/quit", "exit", "quit"}:
            break

        if raw_input.lower() == "/help":
            print()
            print("  /exit       Thoát")
            print("  /help       Xem hướng dẫn này")
            print("  /model      Xem model đang dùng")
            print("  /evidence   Xem danh sách evidence sau câu hỏi trước")
            print("  /intent     Xem intent sau câu hỏi trước")
            print("  /target     Xem target sau câu hỏi trước")
            print()
            print("  Gõ câu hỏi để hỏi (Enter: xuống dòng, Ctrl+D: gửi)")
            print()
            continue

        if raw_input.lower() == "/model":
            print(f"  Model: {args.server or 'mock'}")
            if args.model:
                print(f"  Override: {args.model}")
            continue

        if raw_input.lower() == "/evidence":
            if _last_request is None:
                print("  Chưa có câu hỏi nào được xử lý.")
                continue
            print(f"  Evidence collected: {len(_last_request.evidence)} items")
            print(f"  Complete: {_last_request.evidence_complete}")
            for pkg in _last_request.evidence:
                status = "✓" if pkg.success else "✗"
                print(f"    {status} {pkg.capability_name}")
            continue

        if raw_input.lower() == "/intent":
            if _last_request is None:
                print("  Chưa có câu hỏi nào được xử lý.")
                continue
            print(f"  Intent: {_last_request.intent.name if _last_request.intent else 'N/A'}")
            continue

        if raw_input.lower() == "/target":
            if _last_request is None:
                print("  Chưa có câu hỏi nào được xử lý.")
                continue
            print(f"  Target: {_last_request.target or 'N/A'}")
            continue

        if raw_input.startswith("/"):
            print(f"  Lệnh không hợp lệ: {raw_input}. Gõ /help để xem các lệnh.")
            continue

        # --- Normal question ---
        _last_request = agent.execute_pipeline_only(raw_input)
        answer = agent.run(raw_input)
        print()
        print(answer)
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Infrastructure Agent")
    parser.add_argument(
        "--store", type=str, default="targets.json",
        help="Execution target store file path (deprecated, use --target-file)"
    )
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
    else:
        _run_agent(args)


if __name__ == "__main__":
    main()
