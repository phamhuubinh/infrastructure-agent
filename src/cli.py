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


def _run_agent(args: argparse.Namespace) -> None:
    agent = create_deterministic_agent(
        target_store_path=args.target_file,
        server_name=args.server,
        model=args.model,
    )

    print("Deterministic pipeline is ready.")
    print("Type 'exit' to quit.")

    while True:
        user_request = input("> ").strip()
        if user_request.lower() in {"exit", "quit"}:
            break
        if not user_request:
            continue
        answer = agent.run(user_request)
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
        "--server", type=str, default=None,
        help="Model server name from servers.json (default: active_server)"
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
