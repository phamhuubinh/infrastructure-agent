from __future__ import annotations

from src.agent.agent import Agent
from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.ollama_model_adapter import OllamaModelAdapter


def main() -> None:
    agent = Agent(
        OllamaModelAdapter(
            OllamaClient(),
        )
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
