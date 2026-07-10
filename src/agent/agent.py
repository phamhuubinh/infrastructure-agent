from __future__ import annotations

import time as _time

from src.model.model_adapter import ModelAdapter
from src.shared.discovery.observation import Observation
from src.shared.reasoning.action import Action
from src.shared.reasoning.final_response import FinalResponse
from src.tool.tool_registry import ToolRegistry


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
    """

    def __init__(
        self,
        model: ModelAdapter,
        tool_registry: ToolRegistry,
        available_resources: dict[str, list[str]] | None = None,
        max_iterations: int = 15,
    ) -> None:
        self._model = model
        self._tool_registry = tool_registry
        self._available_resources = available_resources
        self._max_iterations = max_iterations
        self._known_facts: dict[str, object] = {}

    def run(
        self,
        user_request: str,
    ) -> str:
        observations: tuple[Observation, ...] = ()

        for iteration in range(self._max_iterations):
            iter_t0 = _time.perf_counter()

            if _VERBOSE:
                print(f"\n{'='*60}")
                print(f"Iteration {iteration}")
                print(f"{'='*60}")

            t_reason = _time.perf_counter()
            try:
                decision = self._model.reason(
                    user_request=user_request,
                    observations=observations,
                    available_resources=self._available_resources,
                    known_facts=self._known_facts,
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

            t_tool = _time.perf_counter()
            try:
                tool = self._tool_registry.get(decision.tool)
                result = tool.execute(decision.arguments)
            except Exception as exc:
                if _VERBOSE:
                    print(f"[{_time.perf_counter() - t_tool:.3f}s] tool FAILED: {exc}")
                observations += (
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

            observations += (
                Observation(
                    data=result.data,
                    success=result.success,
                    error=result.error,
                    tool=decision.tool,
                    arguments=decision.arguments,
                ),
            )

            # Update known facts (summarized)
            if result.success and result.data:
                action_key = (
                    f"{decision.tool}:"
                    f"{decision.arguments.get('source', '')}:"
                    f"{decision.arguments.get('resource', '')}"
                )
                raw = result.data
                if isinstance(raw, dict):
                    flat = {}
                    for k, v in raw.items():
                        if not isinstance(v, (list, dict)):
                            flat[k] = v
                        elif isinstance(v, list):
                            flat[f"{k}_count"] = len(v)
                    self._known_facts[action_key] = flat
                else:
                    self._known_facts[action_key] = str(raw)[:200]

        return f"Max iterations ({self._max_iterations}) reached without FinalResponse."
