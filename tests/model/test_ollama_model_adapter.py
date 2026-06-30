from __future__ import annotations

import time

from src.infrastructure.ollama.ollama_client import OllamaClient
from src.model.ollama_model_adapter import OllamaModelAdapter
from src.shared.execution.execution_plan import ExecutionPlan


def test_generate_execution_plan() -> None:
    adapter = OllamaModelAdapter(
        OllamaClient(),
    )

    start = time.perf_counter()

    plan = adapter.generate_execution_plan(
        "Print hello.",
    )

    elapsed = time.perf_counter() - start

    print(f"\nElapsed: {elapsed:.2f}s")
    print(f"Command: {plan.steps[0].payload}")

    assert isinstance(plan, ExecutionPlan)

    assert len(plan.steps) == 1

    assert plan.steps[0].step_type == "cli"

    assert isinstance(
        plan.steps[0].payload,
        str,
    )

    assert (
        len(
            plan.steps[0].payload,
        )
        > 0
    )
