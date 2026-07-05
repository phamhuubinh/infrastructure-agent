from __future__ import annotations

from src.agent.agent import Agent
from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.ollama_model_adapter import OllamaModelAdapter
from src.tool.knowledge_tool import KnowledgeTool
from src.tool.shell_tool import ShellTool
from src.tool.tool_registry import ToolRegistry


def main() -> None:
    tool_registry = ToolRegistry()

    tool_registry.register(
        tool_id="shell",
        tool=ShellTool(),
    )

    tool_registry.register(
        tool_id="knowledge",
        tool=KnowledgeTool(),
    )

    agent = Agent(
        model=OllamaModelAdapter(
            OllamaClient(),
        ),
        tool_registry=tool_registry,
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


if __name__ == "__main__":
    main()
