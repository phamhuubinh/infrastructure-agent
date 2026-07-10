from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agent.agent import Agent
from src.infrastructure.ollama.ollama_client import OllamaClient
from src.infrastructure.openai.openai_client import OpenAIClient
from src.model.ollama_model_adapter import OllamaModelAdapter
from src.tool.execution_backend import SSHExecutionBackend
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.shell_tool import ShellTool
from src.tool.target_registry import TargetRegistry
from src.tool.target_store import TargetStore
from src.tool.tool_registry import ToolRegistry
from src.tool.zabbix_tool import ZabbixTool


def _build_client(cfg: dict[str, object]) -> OllamaModelAdapter:
    provider = cfg.get("provider", "auto")
    base_url = cfg.get("base_url", "")
    model = cfg.get("model")
    api_key = cfg.get("api_key")

    if provider == "openai":
        raw = OpenAIClient(base_url=base_url, model=model, api_key=api_key)
    elif provider == "ollama":
        raw = OllamaClient(host=base_url, model=model)
    else:
        raise ValueError(f"Unknown provider: {provider!r}")

    return OllamaModelAdapter(raw)


def _load_server_config(name: str | None = None) -> dict[str, object]:
    config_path = Path("servers.json")
    if not config_path.exists():
        raise RuntimeError("servers.json not found.")
    data = json.loads(config_path.read_text())
    servers: dict[str, object] = data.get("servers", {})
    if name is None:
        name = data.get("active_server", "")
    cfg = servers.get(name)
    if cfg is None:
        available = ", ".join(sorted(servers))
        raise RuntimeError(
            f"Server {name!r} not found. Available servers: {available}"
        )
    return dict(cfg)


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
    from src.agent.agent import set_verbose, set_status

    if args.verbose:
        set_verbose(True)
    if args.status:
        set_status(True)
    store = TargetStore(path=args.target_file)
    registry = TargetRegistry(store=store)

    tool_registry = ToolRegistry()

    tool_registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    tool_registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(
            target_registry=registry,
        ),
    )

    client = _build_client(_load_server_config(name=args.server))

    registry.register_tool(
        name="zabbix",
        tool=ZabbixTool(
            url="http://192.168.10.222/zabbix",
            token="7456fa347e17ce81f8f9d7429c8d4b8c2161b9fe62596d629ad390fdfb7e4eb7",
        ),
    )

    agent = Agent(
        model=client,
        tool_registry=tool_registry,
        available_resources=registry.target_names()
        and KnowledgeTool(target_registry=registry).get_available_resources(),
    )

    print("Agent is ready.")
    print("Type 'exit' to quit.")

    while True:
        user_request = input("> ").strip()

        if user_request.lower() in {
            "exit",
            "quit",
        }:
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
        help="Server name from servers.json (default: active_server)"
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
