import time

from src.infrastructure.ollama.ollama_client import OllamaClient
from src.prompts.prompt_loader import load_prompt

client = OllamaClient()

system = load_prompt("shell_command.md")

user = "Print hello."

prompt = system + "\n\n" + user

start = time.perf_counter()

response = client.generate(prompt)

elapsed = time.perf_counter() - start

print(response)
print(elapsed)
