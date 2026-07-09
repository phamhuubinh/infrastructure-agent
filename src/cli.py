from __future__ import annotations

import argparse
import sys

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


def _add_target(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.store)
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
    store = TargetStore(path=args.store)
    registry = TargetRegistry(store=store)
    try:
        registry.remove(args.name)
        print(f"Target '{args.name}' removed.")
    except KeyError:
        print(f"Target '{args.name}' not found.")
        sys.exit(1)


def _list_targets(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.store)
    registry = TargetRegistry(store=store)
    names = registry.target_names()
    if not names:
        print("No targets configured.")
        return
    for name in names:
        print(name)


def _run_agent(args: argparse.Namespace) -> None:
    store = TargetStore(path=args.store)
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

    if args.provider == "openai":
        client = OpenAIClient(
            base_url=args.openai_base_url,
            model=args.openai_model,
            api_key=args.openai_api_key,
        )
    else:
        client = OllamaClient()

    agent = Agent(
        model=OllamaModelAdapter(client),
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
    parser.add_argument("--store", type=str, default="targets.json",
                        help="Target store file path")
    parser.add_argument("--provider", type=str, default="ollama",
                        choices=["ollama", "openai"],
                        help="Model provider")
    parser.add_argument("--openai-base-url", type=str, default="http://localhost:8000",
                        help="OpenAI-compatible API base URL")
    parser.add_argument("--openai-model", type=str, default="default",
                        help="OpenAI model name")
    parser.add_argument("--openai-api-key", type=str, default=None,
                        help="OpenAI API key (optional)")
    subparsers = parser.add_subparsers(dest="command")

    add_parser = subparsers.add_parser("add-target", help="Add a remote target")
    add_parser.add_argument("spec", type=str,
                            help="Target spec in format name@host or name@host:port")
    add_parser.add_argument("--ssh-user", type=str, default="root", help="SSH user")
    add_parser.add_argument("--ssh-identity-file", type=str, default=None,
                            help="SSH identity file path")

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
