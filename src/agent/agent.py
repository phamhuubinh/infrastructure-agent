from __future__ import annotations

import time as _time
from typing import TYPE_CHECKING

from src.model.model_adapter import ModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.evidence_extractor import extract_known_facts
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.shared.reasoning.reasoning_state import ReasoningState
from src.tool.tool_registry import ToolRegistry

if TYPE_CHECKING:
    from src.pipeline.execution_engine import ExecutionEngine


_VERBOSE = False
_STATUS = False


def set_verbose(v: bool) -> None:
    global _VERBOSE
    _VERBOSE = v


def set_status(v: bool) -> None:
    global _STATUS
    _STATUS = v


def _log(msg: str = "") -> None:
    if _VERBOSE or _STATUS:
        print(msg)


class Agent:
    """
    Coordinates the reasoning loop between the Model and Tools.
    Uses ReasoningState to manage observations and known facts per request.
    """

    def __init__(
        self,
        model: ModelAdapter,
        tool_registry: ToolRegistry,
        available_resources: dict[str, list[str]] | None = None,
        max_iterations: int = 15,
        capability_metadata: dict[str, list[dict[str, object]]] | None = None,
        execution_engine: ExecutionEngine | None = None,
    ) -> None:
        self._model = model
        self._tool_registry = tool_registry
        self._available_resources = available_resources
        self._max_iterations = max_iterations
        self._capability_metadata = capability_metadata or {}
        self._execution_engine = execution_engine

    def run(
        self,
        user_request: str,
    ) -> str:
        state = ReasoningState()

        for iteration in range(self._max_iterations):
            iter_t0 = _time.perf_counter()

            if _VERBOSE:
                print(f"\n{'='*60}")
                print(f"Iteration {iteration}")
                print(f"{'='*60}")

            known_facts = extract_known_facts(state.observations)

            t_reason = _time.perf_counter()
            try:
                decision = self._model.reason(
                    user_request=user_request,
                    observations=state.observations,
                    available_resources=self._available_resources,
                    known_facts=known_facts,
                    capability_metadata=self._capability_metadata,
                )
            except Exception as exc:
                if _VERBOSE:
                    print(f"[{_time.perf_counter() - t_reason:.3f}s] reason FAILED: {exc}")
                raise

            if isinstance(decision, FinalResponse):
                if _STATUS:
                    print(f"[{iteration}] Final")
                elif _VERBOSE:
                    print(f"[{_time.perf_counter() - iter_t0:.3f}s] iteration total -> FinalResponse")
                return decision.content

            if not isinstance(decision, Action):
                raise TypeError(
                    f"Unsupported reasoning result: {type(decision).__name__}"
                )

            action_desc = f"{decision.tool}({decision.arguments})"
            if _STATUS:
                print(f"[{iteration}] {decision.tool}", end="")

            # ---- Deduplication: skip if identical call already succeeded ----
            if state.was_executed(decision):
                if _VERBOSE:
                    print(f"[{_time.perf_counter() - iter_t0:.3f}s] SKIP (already executed): {action_desc}")
                if _STATUS:
                    print(f" -> SKIP (duplicate)")
                continue

            t_tool = _time.perf_counter()
            try:
                tool = self._tool_registry.get(decision.tool)
                result = tool.execute(decision.arguments)
            except Exception as exc:
                if _VERBOSE:
                    print(f"[{_time.perf_counter() - t_tool:.3f}s] tool FAILED: {exc}")
                state.add_observation(
                    Observation(
                        data=None,
                        success=False,
                        error=str(exc),
                        tool=decision.tool,
                        arguments=decision.arguments,
                    ),
                )
                if _STATUS:
                    elapsed = _time.perf_counter() - iter_t0
                    print(f" -> ERROR ({elapsed:.1f}s)")
                continue

            tool_time = _time.perf_counter() - t_tool

            result_label = ""
            if result.success and result.data:
                if isinstance(result.data, dict):
                    keys = list(result.data.keys())[:3]
                    result_label = ", ".join(keys)
                elif isinstance(result.data, list):
                    result_label = f"{len(result.data)} items"
                else:
                    result_label = str(result.data)[:60]

            if _STATUS:
                if result.success:
                    elapsed = _time.perf_counter() - iter_t0
                    print(f" -> {result_label} ({elapsed:.1f}s)")
                else:
                    elapsed = _time.perf_counter() - iter_t0
                    print(f" -> FAILED ({elapsed:.1f}s)")

            if _VERBOSE:
                print(f"[{tool_time:.3f}s] tool.execute")
                result_str = str(result.data) if result.data else ""
                print(f"ToolResult: success={result.success} data_chars={len(result_str):,}")

            state.add_observation(
                Observation(
                    data=result.data,
                    success=result.success,
                    error=result.error,
                    tool=decision.tool,
                    arguments=decision.arguments,
                ),
            )

        return f"Max iterations ({self._max_iterations}) reached without FinalResponse."
