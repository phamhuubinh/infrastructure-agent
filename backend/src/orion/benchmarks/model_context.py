"""Small deterministic context measurements for the direct-registry runtime."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from orion.access import LocalAccessAdapter
from orion.chat.runtime import ChatRuntime
from orion.contracts import (
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.knowledge.tools import (
    list_documents_definition,
    read_definition,
    search_definition,
    source_metadata_definition,
)
from orion.models.backend import ModelBackend, ModelSettings, ModelStreamEvent
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.paths import database_path
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.calculator import calculator_definition
from orion.tool_runtime.infrastructure import infrastructure_definitions
from orion.tool_runtime.internet import internet_fetch_definition, internet_search_definition
from orion.tool_runtime.registry import ToolRegistryBuilder

OFFLINE_BUDGETS = {
    "fresh_payload_bytes": 12_000,
    "full_registry_schema_bytes": 64_000,
    "ten_turn_payload_bytes": 24_000,
}


@dataclass(frozen=True)
class BenchmarkScenario:
    name: str
    prompt: str


_SCENARIOS = (
    BenchmarkScenario("fresh_hello", "hello"),
    BenchmarkScenario("direct_non_tool", "Explain TCP vs UDP"),
    BenchmarkScenario("direct_registry", "Read CPU, RAM, disk and load independently"),
    BenchmarkScenario("ten_turn_ordinary", "Continue the conversation"),
    BenchmarkScenario("single_read", "Read CPU once"),
    BenchmarkScenario("dependent_tools", "Read CPU, then use that count in a calculation"),
)


def benchmark_scenarios() -> tuple[BenchmarkScenario, ...]:
    return _SCENARIOS


def provider_payload(
    messages: tuple[ContextMessage, ...], tools: tuple[ToolDefinition, ...]
) -> dict[str, object]:
    payload: dict[str, object] = {"messages": OpenAICompatibleBackend._provider_messages(messages)}
    if tools:
        payload["tools"] = [definition.provider_schema() for definition in tools]
    return payload


def provider_payload_bytes(
    messages: tuple[ContextMessage, ...], tools: tuple[ToolDefinition, ...]
) -> int:
    return len(
        json.dumps(
            provider_payload(messages, tools), ensure_ascii=False, separators=(",", ":")
        ).encode()
    )


@dataclass(frozen=True)
class BenchmarkMeasurement:
    scenario: str
    payload_bytes: int | None
    catalog_bytes: int | None
    message_count: int | None
    main_calls: int
    summary_calls: int = 0
    visible_tools_by_call: tuple[tuple[str, ...], ...] = ()
    returned_tool_calls_by_call: tuple[tuple[str, ...], ...] = ()
    input_tokens_by_call: tuple[int | None, ...] = ()
    output_tokens_by_call: tuple[int | None, ...] = ()
    metrics: dict[str, int | bool | None] = field(default_factory=dict)
    budgets: dict[str, int] = field(default_factory=dict)
    warning_only: bool = False

    @property
    def status(self) -> str:
        return (
            "PASS"
            if all(
                self.metrics.get(key) is None or value <= self.budgets.get(key, value)
                for key, value in self.metrics.items()
                if isinstance(value, int)
            )
            else "FAIL"
        )


@dataclass(frozen=True)
class BenchmarkReport:
    mode: str
    measurements: tuple[BenchmarkMeasurement, ...]

    def require_passing(self) -> None:
        for measurement in self.measurements:
            if measurement.status != "PASS":
                raise AssertionError(f"{measurement.scenario} exceeded its measurement budget")

    def to_json(self) -> str:
        return json.dumps(
            {
                "mode": self.mode,
                "measurements": [
                    asdict(item) | {"status": item.status} for item in self.measurements
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )

    def to_text(self) -> str:
        return "\n".join(
            f"{item.scenario}: {item.status}; payload_bytes={item.payload_bytes}; "
            f"calls={item.main_calls}"
            for item in self.measurements
        )


def complete_tool_definitions() -> tuple[ToolDefinition, ...]:
    """The actual shipped schemas, including families without locally configured targets."""
    return tuple(
        sorted(
            (
                calculator_definition(),
                internet_search_definition(),
                internet_fetch_definition(),
                list_documents_definition(),
                read_definition(),
                search_definition(),
                source_metadata_definition(),
                *infrastructure_definitions(),
            ),
            key=lambda item: item.name,
        )
    )


def active_model_settings() -> ModelSettings:
    """Resolve the application's persisted profile without touching its data."""
    path = database_path()
    try:
        profile = SQLiteStore.read_active_model_config(path)
    except (OSError, sqlite3.Error) as error:
        raise RuntimeError(
            f"Cannot read Orion model profile at resolved database {path}"
        ) from error
    if profile is None:
        raise RuntimeError(f"No active Orion model profile in resolved database {path}")
    return ModelSettings.model_validate(
        {
            key: profile[key]
            for key in ("provider_type", "base_url", "model_id", "api_key", "reasoning_mode")
        }
    )


class _RecordingBackend(ModelBackend):
    def __init__(self, backend: ModelBackend) -> None:
        self.backend = backend
        self.inputs: list[tuple[tuple[ContextMessage, ...], tuple[ToolDefinition, ...]]] = []
        self.turns: list[ModelTurn] = []

    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.inputs.append((messages, tools))
        async for event in self.backend.stream(messages, tools, settings, cancellation):
            if isinstance(event, ModelTurnCompleted):
                self.turns.append(event.turn)
            yield event


class _OfflineBackend(ModelBackend):
    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = iter(turns)

    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        yield ModelTurnCompleted(turn=next(self.turns))


def _script(scenario: str) -> list[ModelTurn]:
    reads = tuple(
        ModelToolCall(
            call_id=section,
            tool_name="linux.system.inspect",
            arguments={"target_ref": "benchmark", "sections": [section]},
        )
        for section in ("cpu", "memory", "disk")
    ) + (
        ModelToolCall(
            call_id="load",
            tool_name="linux.file.read",
            arguments={"target_ref": "benchmark", "path": "/proc/loadavg"},
        ),
    )
    answer = ModelTurn(assistant=AssistantMessage(content="Observed fixture values."))
    if scenario == "direct_registry":
        return [ModelTurn(tool_calls=reads), answer]
    if scenario == "single_read":
        return [ModelTurn(tool_calls=reads[:1]), answer]
    if scenario == "dependent_tools":
        return [
            ModelTurn(tool_calls=reads[:1]),
            ModelTurn(
                tool_calls=(
                    ModelToolCall(
                        call_id="calc",
                        tool_name="calculator.evaluate",
                        arguments={"expression": "4 * 2"},
                    ),
                )
            ),
            answer,
        ]
    return [answer]


def _fixture_read(call: ToolCall) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.tool_name,
        status="success",
        data={"target_ref": "benchmark", "cpu_count": 4, "fixture": True},
    )


async def _run_benchmark(live: bool) -> BenchmarkReport:
    settings = (
        active_model_settings()
        if live
        else ModelSettings(
            provider_type="openai_compatible",
            base_url="http://offline.invalid/v1",
            model_id="scripted",
        )
    )
    measurements: list[BenchmarkMeasurement] = []
    with TemporaryDirectory(prefix="orion-context-benchmark-") as temporary:
        for scenario in _SCENARIOS:
            store = SQLiteStore(Path(temporary) / (scenario.name + ".db"))
            try:
                store.upsert_model_config(
                    settings.provider_type,
                    settings.base_url,
                    settings.model_id,
                    settings.api_key,
                    settings.reasoning_mode,
                )
                builder = ToolRegistryBuilder()
                for definition in complete_tool_definitions():
                    builder.register(definition, _fixture_read)
                backend = _RecordingBackend(
                    OpenAICompatibleBackend() if live else _OfflineBackend(_script(scenario.name))
                )
                runtime = ChatRuntime(
                    store,
                    backend,
                    builder.freeze(),
                    LocalAccessAdapter(),
                    blocked_tool_operation_kinds=frozenset({"mutation"}),
                )
                session = store.create_session()
                if scenario.name == "ten_turn_ordinary":
                    for index in range(10):
                        store.append_timeline(
                            session,
                            None,
                            "user_message",
                            {"content": f"Historical question {index}"},
                        )
                        store.append_timeline(
                            session,
                            None,
                            "assistant_message",
                            {
                                "content": f"Historical answer {index}",
                                "tool_calls": [],
                                "citation_source_ref_ids": [],
                            },
                        )
                await runtime.submit(
                    session,
                    scenario.prompt
                    + (
                        " (Use synthetic benchmark target; all results are fixtures.)"
                        if live
                        else ""
                    ),
                )
                sizes = [
                    provider_payload_bytes(messages, tools) for messages, tools in backend.inputs
                ]
                schema_bytes = max(
                    len(
                        json.dumps(
                            [tool.provider_schema() for tool in tools],
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode()
                    )
                    for _, tools in backend.inputs
                )
                measurements.append(
                    BenchmarkMeasurement(
                        scenario=scenario.name,
                        payload_bytes=max(sizes),
                        catalog_bytes=schema_bytes,
                        message_count=max(len(messages) for messages, _ in backend.inputs),
                        main_calls=len(backend.inputs),
                        visible_tools_by_call=tuple(
                            tuple(tool.name for tool in tools) for _, tools in backend.inputs
                        ),
                        returned_tool_calls_by_call=tuple(
                            tuple(call.tool_name for call in turn.tool_calls)
                            for turn in backend.turns
                        ),
                        metrics={
                            "full_registry_schema_bytes": schema_bytes,
                            "context_bytes": max(
                                provider_payload_bytes(messages, ())
                                for messages, _ in backend.inputs
                            ),
                        },
                        budgets={
                            "full_registry_schema_bytes": OFFLINE_BUDGETS[
                                "full_registry_schema_bytes"
                            ],
                            "context_bytes": OFFLINE_BUDGETS["fresh_payload_bytes"],
                        },
                        warning_only=live,
                    )
                )
            finally:
                store.close()
    report = BenchmarkReport("live" if live else "offline", tuple(measurements))
    if not live:
        report.require_passing()
    return report


async def run_offline_benchmark() -> BenchmarkReport:
    return await _run_benchmark(live=False)


async def run_live_benchmark() -> BenchmarkReport:
    """Real provider turns with deterministic fixture tools; never a deployed-system verdict."""
    return await _run_benchmark(live=True)
