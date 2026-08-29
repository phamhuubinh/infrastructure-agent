"""Reusable model-context benchmark fixtures and measurements.

The provider projection deliberately reuses ``OpenAICompatibleBackend._message_payload``.
That helper is the adapter's canonical message serialization, and centralizing this small
internal dependency here avoids maintaining a second hand-written provider prompt shape.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory

from orion.bootstrap import OrionApplication, build_application
from orion.chat.context_builder import CONVERSATION_STATE_MAX_BYTES, ContextBuilder
from orion.contracts import (
    AssistantMessage,
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ModelUsage,
    ToolCall,
    ToolDefinition,
    ToolResult,
)
from orion.integrations import TargetCatalog
from orion.models.backend import ModelBackend, ModelSettings, ModelStreamEvent
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.persistence.sqlite import SQLiteStore
from orion.tool_runtime.calculator import calculate, calculator_definition
from orion.tool_runtime.infrastructure import infrastructure_definitions
from orion.tool_runtime.registry import EXPAND_TOOL_NAME, ToolRegistration


@dataclass(frozen=True)
class BenchmarkScenario:
    """One stable, canonical Orion conversation shape."""

    name: str
    prompt: str


SCENARIOS = (
    BenchmarkScenario("fresh_hello", "hello"),
    BenchmarkScenario(
        "direct_non_tool", "Explain what a local-first application is in one sentence."
    ),
    BenchmarkScenario(
        "project_fresh", "Summarize the active project's operating constraints in one sentence."
    ),
    BenchmarkScenario("calculator_progressive", "What is 2 + 3?"),
    BenchmarkScenario("ambiguous_infrastructure_initial", "check CPU server monitor"),
    BenchmarkScenario("ten_turn_ordinary", "What is the current ordinary-conversation topic?"),
    BenchmarkScenario("checkpoint_trigger", "Continue the technical plan directly."),
    BenchmarkScenario("long_steady_state", "What decision remains active?"),
)

OFFLINE_BUDGETS: dict[str, int] = {
    "fresh_payload_bytes": 2_000,
    "one_expanded_payload_bytes": 2_400,
    "three_expanded_payload_bytes": 3_300,
    "ten_turn_payload_bytes": 6_000,
    "long_steady_payload_bytes": 7_500,
    "summary_payload_bytes": 6_000,
    "summary_state_bytes": CONVERSATION_STATE_MAX_BYTES,
}

OFFLINE_REFERENCES: dict[str, int] = {
    "fresh_payload_bytes": 1_680,
    "one_expanded_payload_bytes": 1_948,
    "three_expanded_payload_bytes": 2_777,
    "ten_turn_payload_bytes": 4_992,
    "long_steady_payload_bytes": 6_107,
    "summary_payload_bytes": 4_741,
    "summary_state_bytes": CONVERSATION_STATE_MAX_BYTES,
}

OFFLINE_REFERENCE_BY_SCENARIO_METRIC: dict[tuple[str, str], int] = {
    ("fresh_hello", "payload_bytes"): OFFLINE_REFERENCES["fresh_payload_bytes"],
    ("progressive_exposure_projections", "fresh_payload_bytes"): OFFLINE_REFERENCES[
        "fresh_payload_bytes"
    ],
    ("progressive_exposure_projections", "one_expanded_payload_bytes"): OFFLINE_REFERENCES[
        "one_expanded_payload_bytes"
    ],
    ("progressive_exposure_projections", "three_expanded_payload_bytes"): OFFLINE_REFERENCES[
        "three_expanded_payload_bytes"
    ],
    ("ten_turn_ordinary", "payload_bytes"): OFFLINE_REFERENCES["ten_turn_payload_bytes"],
    ("checkpoint_trigger", "summary_payload_bytes"): OFFLINE_REFERENCES["summary_payload_bytes"],
    ("checkpoint_trigger", "summary_state_bytes"): OFFLINE_REFERENCES["summary_state_bytes"],
    ("long_steady_state", "payload_bytes"): OFFLINE_REFERENCES["long_steady_payload_bytes"],
}

LIVE_WARNING_BUDGETS: dict[str, int] = {
    "fresh_hello_input_tokens": 650,
    "direct_non_tool_input_tokens": 650,
    "ambiguous_infrastructure_initial_input_tokens": 650,
    "project_fresh_input_tokens": 800,
    "calculator_progressive_cumulative_input_tokens": 3_500,
    "calculator_progressive_model_calls": 5,
    "ten_turn_ordinary_input_tokens": 1_400,
    "checkpoint_trigger_summary_input_tokens": 850,
    "checkpoint_trigger_main_input_tokens": 1_700,
    "checkpoint_trigger_cumulative_input_tokens": 2_600,
    "long_steady_state_input_tokens": 1_500,
}


def provider_payload(
    messages: tuple[ContextMessage, ...], tools: tuple[ToolDefinition, ...]
) -> dict[str, object]:
    """Return the adapter-equivalent, deterministic request projection for measurement."""
    payload: dict[str, object] = {
        "messages": [OpenAICompatibleBackend._message_payload(message) for message in messages]
    }
    if tools:
        payload["tools"] = [definition.provider_schema() for definition in tools]
    return payload


def provider_payload_bytes(
    messages: tuple[ContextMessage, ...], tools: tuple[ToolDefinition, ...]
) -> int:
    """Measure a compact UTF-8 JSON representation of Orion's provider projection."""
    return len(
        json.dumps(
            provider_payload(messages, tools),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


@dataclass
class RecordedCall:
    messages: tuple[ContextMessage, ...]
    tools: tuple[ToolDefinition, ...]
    usage: ModelUsage | None = None
    returned_tool_calls: tuple[str, ...] = ()

    @property
    def payload_bytes(self) -> int:
        return provider_payload_bytes(self.messages, self.tools)

    @property
    def visible_tools(self) -> tuple[str, ...]:
        return tuple(definition.name for definition in self.tools)


class RecordingBackend(ModelBackend):
    """Script deterministic turns or observe a real backend through the same model boundary."""

    def __init__(
        self,
        scripted_turns: Sequence[tuple[ModelTurn, ModelUsage | None]] = (),
        delegate: ModelBackend | None = None,
        permitted_live_tools: frozenset[str] | None = None,
    ) -> None:
        self._scripted_turns = list(scripted_turns)
        self._delegate = delegate
        self._permitted_live_tools = permitted_live_tools
        self.calls: list[RecordedCall] = []

    def add_scripted(self, *turns: tuple[ModelTurn, ModelUsage | None]) -> None:
        self._scripted_turns.extend(turns)

    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        recorded = RecordedCall(messages=messages, tools=tools)
        self.calls.append(recorded)
        if self._delegate is None:
            if not self._scripted_turns:
                raise RuntimeError("Benchmark scripted backend ran out of turns.")
            turn, usage = self._scripted_turns.pop(0)
            recorded.usage = usage
            recorded.returned_tool_calls = tuple(call.tool_name for call in turn.tool_calls)
            yield ModelTurnCompleted(turn=turn, usage=usage)
            return

        async for event in self._delegate.stream(messages, tools, settings, cancellation):
            if isinstance(event, ModelTurnCompleted):
                recorded.usage = event.usage
                recorded.returned_tool_calls = tuple(
                    call.tool_name for call in event.turn.tool_calls
                )
                if self._permitted_live_tools is not None and any(
                    name not in self._permitted_live_tools for name in recorded.returned_tool_calls
                ):
                    # The model's actual call names remain recorded for the diagnostic report.
                    # The replacement terminal turn prevents an owner diagnostic from executing
                    # infrastructure, internet, or knowledge operations unexpectedly.
                    yield ModelTurnCompleted(
                        turn=ModelTurn(
                            assistant=AssistantMessage(
                                content=(
                                    "Live diagnostic stopped before an unapproved tool execution."
                                )
                            )
                        ),
                        usage=event.usage,
                    )
                    continue
            yield event


@dataclass(frozen=True)
class BenchmarkMeasurement:
    scenario: str
    payload_bytes: int | None
    catalog_bytes: int | None
    message_count: int | None
    main_calls: int
    summary_calls: int
    visible_tools_by_call: tuple[tuple[str, ...], ...]
    returned_tool_calls_by_call: tuple[tuple[str, ...], ...]
    input_tokens_by_call: tuple[int | None, ...]
    output_tokens_by_call: tuple[int | None, ...]
    elapsed_ms: int | None = None
    metrics: dict[str, int | bool | None] = field(default_factory=dict)
    budgets: dict[str, int] = field(default_factory=dict)
    warning_only: bool = False

    @property
    def model_calls(self) -> int:
        return self.main_calls + self.summary_calls

    @property
    def input_tokens(self) -> int | None:
        if not self.input_tokens_by_call or any(
            value is None for value in self.input_tokens_by_call
        ):
            return None
        return sum(value for value in self.input_tokens_by_call if value is not None)

    @property
    def output_tokens(self) -> int | None:
        if not self.output_tokens_by_call or any(
            value is None for value in self.output_tokens_by_call
        ):
            return None
        return sum(value for value in self.output_tokens_by_call if value is not None)

    def measured_values(self) -> dict[str, int | None]:
        values: dict[str, int | None] = {
            "payload_bytes": self.payload_bytes,
            "catalog_bytes": self.catalog_bytes,
            "message_count": self.message_count,
            "main_calls": self.main_calls,
            "summary_calls": self.summary_calls,
            "model_calls": self.model_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }
        for key, value in self.metrics.items():
            if isinstance(value, bool):
                values[key] = int(value)
            elif value is None or isinstance(value, int):
                values[key] = value
        return values

    @property
    def status(self) -> str:
        for metric, budget in self.budgets.items():
            value = self.measured_values().get(metric)
            if value is not None and value > budget:
                return "WARN" if self.warning_only else "FAIL"
        return "PASS"

    def as_dict(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "payload_bytes": self.payload_bytes,
            "catalog_bytes": self.catalog_bytes,
            "message_count": self.message_count,
            "main_calls": self.main_calls,
            "summary_calls": self.summary_calls,
            "model_calls": self.model_calls,
            "visible_tools_by_call": [list(tools) for tools in self.visible_tools_by_call],
            "returned_tool_calls_by_call": [
                list(tool_calls) for tool_calls in self.returned_tool_calls_by_call
            ],
            "input_tokens_by_call": list(self.input_tokens_by_call),
            "output_tokens_by_call": list(self.output_tokens_by_call),
            "cumulative_input_tokens": self.input_tokens,
            "cumulative_output_tokens": self.output_tokens,
            "elapsed_ms": self.elapsed_ms,
            "metrics": self.metrics,
            "budgets": self.budgets,
            "status": self.status,
        }


@dataclass(frozen=True)
class BenchmarkReport:
    mode: str
    measurements: tuple[BenchmarkMeasurement, ...]

    def as_dict(self) -> dict[str, object]:
        return {"mode": self.mode, "measurements": [item.as_dict() for item in self.measurements]}

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def to_text(self) -> str:
        rows = ["scenario                          calls input_tokens payload_bytes status"]
        for item in self.measurements:
            tokens = "-" if item.input_tokens is None else str(item.input_tokens)
            payload = "-" if item.payload_bytes is None else str(item.payload_bytes)
            rows.append(
                f"{item.scenario:<33} {item.model_calls:>5} {tokens:>12} "
                f"{payload:>13} {item.status}"
            )
        return "\n".join(rows)

    def require_passing(self) -> None:
        for item in self.measurements:
            if item.status != "FAIL":
                continue
            values = item.measured_values()
            for metric, budget in item.budgets.items():
                value = values.get(metric)
                if value is not None and value > budget:
                    reference = OFFLINE_REFERENCE_BY_SCENARIO_METRIC.get(
                        (item.scenario, metric), "not recorded"
                    )
                    raise AssertionError(
                        f"{item.scenario} {metric} grew to {value}; budget: {budget}; "
                        f"previous reference: {reference}"
                    )


def _settings(store: SQLiteStore) -> ModelSettings:
    config = store.active_model_config()
    if config is None:
        raise RuntimeError("Benchmark requires an active model configuration.")
    return ModelSettings.model_validate(
        {
            "provider_type": config["provider_type"],
            "base_url": config["base_url"],
            "model_id": config["model_id"],
            "api_key": config["api_key"],
        }
    )


def _application(path: Path, backend: ModelBackend, live: bool) -> OrionApplication:
    # The target catalog is intentionally empty in both modes: its model-facing identities
    # are local machine configuration, not a benchmark variable, and live diagnostics must
    # never execute infrastructure operations.
    app = build_application(
        database_path=path,
        backend=backend,
        infrastructure_catalog=TargetCatalog(),
        tool_registrations=_fixture_tool_registrations(),
    )
    if not live:
        app.store.upsert_model_config(
            "openai_compatible", "http://model.test/v1", "benchmark", None
        )
    return app


def _fixture_tool_registrations() -> tuple[ToolRegistration, ...]:
    """Use the complete configured-tool schema view without live target transports."""

    def disabled_infrastructure(call: ToolCall) -> ToolResult:
        return ToolResult.failure(
            call.call_id,
            call.tool_name,
            "benchmark_safety",
            "Infrastructure execution is disabled in the model-context benchmark.",
        )

    return (
        ToolRegistration(calculator_definition(), calculate),
        *(
            ToolRegistration(definition, disabled_infrastructure)
            for definition in infrastructure_definitions()
        ),
    )


def _project_session(store: SQLiteStore) -> str:
    project = store.create_project(
        "Incident response modernization",
        description="Keep investigations local-first and preserve evidence boundaries.",
        instructions="Prefer concise, evidence-based technical plans.",
        metadata={"environment": "staging", "owner": "platform"},
    )
    return store.create_session(project_id=str(project["project_id"]))


def _append_completed_turn(store: SQLiteStore, session_id: str, index: int, padding: int) -> None:
    store.append_timeline(
        session_id,
        None,
        "user_message",
        {"content": f"Topic {index}: " + "context " * padding},
    )
    store.append_timeline(
        session_id,
        None,
        "assistant_message",
        {
            "content": f"Decision {index}: " + "detail " * padding,
            "citation_source_ref_ids": [],
            "tool_calls": [],
        },
    )


def _measurement(
    scenario: str,
    calls: Sequence[RecordedCall],
    *,
    summary_calls: int = 0,
    catalog_bytes: int | None = None,
    metrics: dict[str, int | bool | None] | None = None,
    budgets: dict[str, int] | None = None,
    warning_only: bool = False,
    elapsed_ms: int | None = None,
) -> BenchmarkMeasurement:
    return BenchmarkMeasurement(
        scenario=scenario,
        payload_bytes=max((call.payload_bytes for call in calls), default=None),
        catalog_bytes=catalog_bytes,
        message_count=max((len(call.messages) for call in calls), default=None),
        main_calls=len(calls) - summary_calls,
        summary_calls=summary_calls,
        visible_tools_by_call=tuple(call.visible_tools for call in calls),
        returned_tool_calls_by_call=tuple(call.returned_tool_calls for call in calls),
        input_tokens_by_call=tuple(
            call.usage.input_tokens if call.usage is not None else None for call in calls
        ),
        output_tokens_by_call=tuple(
            call.usage.output_tokens if call.usage is not None else None for call in calls
        ),
        elapsed_ms=elapsed_ms,
        metrics=metrics or {},
        budgets=budgets or {},
        warning_only=warning_only,
    )


async def _initial_model_call(
    app: OrionApplication, backend: RecordingBackend, session_id: str
) -> RecordedCall:
    exposure = app.registry.new_tool_exposure()
    context = ContextBuilder(app.store).build_with_metadata(session_id)
    before = len(backend.calls)
    async for _ in backend.stream(
        context.messages,
        exposure.model_tools,
        _settings(app.store),
        asyncio.Event(),
    ):
        pass
    return backend.calls[before]


async def _run_benchmark(live: bool) -> BenchmarkReport:
    if live:
        missing = [
            name for name in ("ORION_MODEL_BASE_URL", "ORION_MODEL_ID") if not os.getenv(name)
        ]
        if missing:
            raise RuntimeError("Live benchmark requires " + ", ".join(missing) + ".")
        backend = RecordingBackend(
            delegate=OpenAICompatibleBackend(),
            permitted_live_tools=frozenset({EXPAND_TOOL_NAME, "calculator.evaluate"}),
        )
    else:
        backend = RecordingBackend()

    with TemporaryDirectory(prefix="orion-model-context-benchmark-") as directory:
        app = _application(Path(directory) / "orion.db", backend, live)
        try:
            measurements: list[BenchmarkMeasurement] = []

            # Fresh/direct/Project use the normal runtime offline. The live diagnostic sends one
            # canonical initial turn only, so an unexpected tool call can never be executed.
            fresh_session = app.store.create_session()
            if not live:
                backend.add_scripted(
                    (ModelTurn(assistant=AssistantMessage(content="Hello.")), None)
                )
                start = len(backend.calls)
                await app.runtime.submit(fresh_session, SCENARIOS[0].prompt)
                fresh_calls = backend.calls[start:]
            else:
                app.store.append_timeline(
                    fresh_session, None, "user_message", {"content": SCENARIOS[0].prompt}
                )
                started = time.perf_counter()
                fresh_calls = [await _initial_model_call(app, backend, fresh_session)]
                fresh_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "fresh_hello",
                    fresh_calls,
                    catalog_bytes=0,
                    budgets=(
                        {"payload_bytes": OFFLINE_BUDGETS["fresh_payload_bytes"]}
                        if not live
                        else {"input_tokens": LIVE_WARNING_BUDGETS["fresh_hello_input_tokens"]}
                    ),
                    warning_only=live,
                    elapsed_ms=fresh_elapsed if live else None,
                )
            )

            direct_session = app.store.create_session()
            if not live:
                backend.add_scripted(
                    (ModelTurn(assistant=AssistantMessage(content="It keeps data local.")), None)
                )
                start = len(backend.calls)
                await app.runtime.submit(direct_session, SCENARIOS[1].prompt)
                direct_calls = backend.calls[start:]
            else:
                app.store.append_timeline(
                    direct_session, None, "user_message", {"content": SCENARIOS[1].prompt}
                )
                started = time.perf_counter()
                direct_calls = [await _initial_model_call(app, backend, direct_session)]
                direct_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "direct_non_tool",
                    direct_calls,
                    budgets=(
                        {"main_calls": 1}
                        if not live
                        else {"input_tokens": LIVE_WARNING_BUDGETS["direct_non_tool_input_tokens"]}
                    ),
                    warning_only=live,
                    elapsed_ms=direct_elapsed if live else None,
                )
            )

            project_session = _project_session(app.store)
            if not live:
                backend.add_scripted(
                    (ModelTurn(assistant=AssistantMessage(content="Use local evidence.")), None)
                )
                start = len(backend.calls)
                await app.runtime.submit(project_session, SCENARIOS[2].prompt)
                project_calls = backend.calls[start:]
            else:
                app.store.append_timeline(
                    project_session, None, "user_message", {"content": SCENARIOS[2].prompt}
                )
                started = time.perf_counter()
                project_calls = [await _initial_model_call(app, backend, project_session)]
                project_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "project_fresh",
                    project_calls,
                    metrics={
                        "uses_project_context": any(
                            "Active Project" in message.content
                            for message in project_calls[0].messages
                        )
                    },
                    budgets=(
                        {}
                        if not live
                        else {"input_tokens": LIVE_WARNING_BUDGETS["project_fresh_input_tokens"]}
                    ),
                    warning_only=live,
                    elapsed_ms=project_elapsed if live else None,
                )
            )

            exposure_session = app.store.create_session()
            app.store.append_timeline(
                exposure_session, None, "user_message", {"content": SCENARIOS[0].prompt}
            )
            exposure = app.registry.new_tool_exposure()
            exposure_messages = ContextBuilder(app.store).build(exposure_session)
            initial_bytes = provider_payload_bytes(exposure_messages, exposure.model_tools)
            exposure.expand(
                ModelToolCall(
                    call_id="one",
                    tool_name=EXPAND_TOOL_NAME,
                    arguments={"tool_names": ["calculator.evaluate"]},
                )
            )
            one_bytes = provider_payload_bytes(exposure_messages, exposure.model_tools)
            exposure.expand(
                ModelToolCall(
                    call_id="three",
                    tool_name=EXPAND_TOOL_NAME,
                    arguments={"tool_names": ["internet.search", "zabbix.event.list"]},
                )
            )
            three_bytes = provider_payload_bytes(exposure_messages, exposure.model_tools)
            measurements.append(
                BenchmarkMeasurement(
                    scenario="progressive_exposure_projections",
                    payload_bytes=three_bytes,
                    catalog_bytes=0,
                    message_count=len(exposure_messages),
                    main_calls=0,
                    summary_calls=0,
                    visible_tools_by_call=(
                        (EXPAND_TOOL_NAME,),
                        (EXPAND_TOOL_NAME, "calculator.evaluate"),
                        tuple(definition.name for definition in exposure.model_tools),
                    ),
                    returned_tool_calls_by_call=(),
                    input_tokens_by_call=(),
                    output_tokens_by_call=(),
                    metrics={
                        "fresh_payload_bytes": initial_bytes,
                        "one_expanded_payload_bytes": one_bytes,
                        "three_expanded_payload_bytes": three_bytes,
                        "expansion_schema_bytes": len(
                            json.dumps(
                                exposure.model_tools[0].provider_schema(),
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ),
                    },
                    budgets=(
                        {
                            "fresh_payload_bytes": OFFLINE_BUDGETS["fresh_payload_bytes"],
                            "one_expanded_payload_bytes": OFFLINE_BUDGETS[
                                "one_expanded_payload_bytes"
                            ],
                            "three_expanded_payload_bytes": OFFLINE_BUDGETS[
                                "three_expanded_payload_bytes"
                            ],
                        }
                        if not live
                        else {}
                    ),
                    warning_only=live,
                )
            )

            calculator_session = app.store.create_session()
            if not live:
                backend.add_scripted(
                    (
                        ModelTurn(
                            tool_calls=(
                                ModelToolCall(
                                    call_id="expand-calculator",
                                    tool_name=EXPAND_TOOL_NAME,
                                    arguments={"tool_names": ["calculator.evaluate"]},
                                ),
                            )
                        ),
                        None,
                    ),
                    (
                        ModelTurn(
                            tool_calls=(
                                ModelToolCall(
                                    call_id="calculator-1",
                                    tool_name="calculator.evaluate",
                                    arguments={"expression": "2 + 3"},
                                ),
                            )
                        ),
                        None,
                    ),
                    (ModelTurn(assistant=AssistantMessage(content="The result is 5.")), None),
                    (ModelTurn(assistant=AssistantMessage(content="Fresh answer.")), None),
                )
            start = len(backend.calls)
            started = time.perf_counter()
            await app.runtime.submit(calculator_session, SCENARIOS[3].prompt)
            calculator_calls = backend.calls[start:]
            calculator_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "calculator_progressive",
                    calculator_calls,
                    budgets=(
                        {"main_calls": 3}
                        if not live
                        else {
                            "input_tokens": LIVE_WARNING_BUDGETS[
                                "calculator_progressive_cumulative_input_tokens"
                            ],
                            "model_calls": LIVE_WARNING_BUDGETS[
                                "calculator_progressive_model_calls"
                            ],
                        }
                    ),
                    warning_only=live,
                    elapsed_ms=calculator_elapsed if live else None,
                )
            )

            if not live:
                start = len(backend.calls)
                await app.runtime.submit(
                    calculator_session, "Answer directly after the calculation."
                )
                reset_calls = backend.calls[start:]
                measurements.append(
                    _measurement(
                        "progressive_exposure_reset",
                        reset_calls,
                        metrics={
                            "reset_is_expand_only": reset_calls[0].visible_tools
                            == (EXPAND_TOOL_NAME,)
                        },
                        budgets={"main_calls": 1},
                    )
                )

            ambiguous_session = app.store.create_session()
            app.store.append_timeline(
                ambiguous_session, None, "user_message", {"content": SCENARIOS[4].prompt}
            )
            if not live:
                ambiguous_call = RecordedCall(
                    messages=ContextBuilder(app.store).build(ambiguous_session),
                    tools=app.registry.new_tool_exposure().model_tools,
                )
                ambiguous_elapsed = None
            else:
                started = time.perf_counter()
                ambiguous_call = await _initial_model_call(app, backend, ambiguous_session)
                ambiguous_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "ambiguous_infrastructure_initial",
                    [ambiguous_call],
                    metrics={"infrastructure_operations_executed": 0},
                    budgets=(
                        {}
                        if not live
                        else {
                            "input_tokens": LIVE_WARNING_BUDGETS[
                                "ambiguous_infrastructure_initial_input_tokens"
                            ]
                        }
                    ),
                    warning_only=live,
                    elapsed_ms=ambiguous_elapsed,
                )
            )

            ordinary_session = app.store.create_session()
            for index in range(9):
                _append_completed_turn(app.store, ordinary_session, index, padding=16)
            if not live:
                backend.add_scripted(
                    (ModelTurn(assistant=AssistantMessage(content="Topic nine.")), None)
                )
                start = len(backend.calls)
                await app.runtime.submit(ordinary_session, SCENARIOS[5].prompt)
                ordinary_calls = backend.calls[start:]
                ordinary_elapsed = None
            else:
                app.store.append_timeline(
                    ordinary_session, None, "user_message", {"content": SCENARIOS[5].prompt}
                )
                started = time.perf_counter()
                ordinary_calls = [await _initial_model_call(app, backend, ordinary_session)]
                ordinary_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "ten_turn_ordinary",
                    ordinary_calls,
                    budgets=(
                        {
                            "payload_bytes": OFFLINE_BUDGETS["ten_turn_payload_bytes"],
                            "main_calls": 1,
                        }
                        if not live
                        else {
                            "input_tokens": LIVE_WARNING_BUDGETS["ten_turn_ordinary_input_tokens"]
                        }
                    ),
                    warning_only=live,
                    elapsed_ms=ordinary_elapsed,
                )
            )

            checkpoint_session = app.store.create_session()
            for index in range(16):
                _append_completed_turn(app.store, checkpoint_session, index, padding=42)
            if not live:
                backend.add_scripted(
                    (
                        ModelTurn(
                            assistant=AssistantMessage(content="Keep the active decision concise.")
                        ),
                        None,
                    ),
                    (
                        ModelTurn(assistant=AssistantMessage(content="The plan remains active.")),
                        None,
                    ),
                    (
                        ModelTurn(
                            assistant=AssistantMessage(content="The decision remains active.")
                        ),
                        None,
                    ),
                )
            start = len(backend.calls)
            started = time.perf_counter()
            await app.runtime.submit(checkpoint_session, SCENARIOS[6].prompt)
            checkpoint_calls = backend.calls[start:]
            checkpoint_elapsed = round((time.perf_counter() - started) * 1000)
            checkpoint = app.store.conversation_state_checkpoint(checkpoint_session)
            summary_call = checkpoint_calls[0]
            measurements.append(
                _measurement(
                    "checkpoint_trigger",
                    checkpoint_calls,
                    summary_calls=1,
                    metrics={
                        "summary_payload_bytes": summary_call.payload_bytes,
                        "summary_state_bytes": len(checkpoint.state.encode("utf-8"))
                        if checkpoint is not None
                        else None,
                        "summary_omits_tools": "tools"
                        not in provider_payload(summary_call.messages, summary_call.tools),
                    },
                    budgets=(
                        {
                            "summary_payload_bytes": OFFLINE_BUDGETS["summary_payload_bytes"],
                            "summary_state_bytes": OFFLINE_BUDGETS["summary_state_bytes"],
                            "main_calls": 1,
                            "summary_calls": 1,
                        }
                        if not live
                        else {
                            "input_tokens": LIVE_WARNING_BUDGETS[
                                "checkpoint_trigger_cumulative_input_tokens"
                            ],
                        }
                    ),
                    warning_only=live,
                    elapsed_ms=checkpoint_elapsed if live else None,
                )
            )
            if live and len(checkpoint_calls) >= 2:
                checkpoint_measurement = measurements[-1]
                checkpoint_metrics = dict(checkpoint_measurement.metrics)
                checkpoint_metrics["summary_input_tokens"] = (
                    checkpoint_calls[0].usage.input_tokens if checkpoint_calls[0].usage else None
                )
                checkpoint_metrics["main_input_tokens"] = (
                    checkpoint_calls[1].usage.input_tokens if checkpoint_calls[1].usage else None
                )
                measurements[-1] = BenchmarkMeasurement(
                    **{
                        **checkpoint_measurement.__dict__,
                        "metrics": checkpoint_metrics,
                        "budgets": {
                            **checkpoint_measurement.budgets,
                            "summary_input_tokens": LIVE_WARNING_BUDGETS[
                                "checkpoint_trigger_summary_input_tokens"
                            ],
                            "main_input_tokens": LIVE_WARNING_BUDGETS[
                                "checkpoint_trigger_main_input_tokens"
                            ],
                        },
                    }
                )

            start = len(backend.calls)
            started = time.perf_counter()
            await app.runtime.submit(checkpoint_session, SCENARIOS[7].prompt)
            steady_calls = backend.calls[start:]
            steady_elapsed = round((time.perf_counter() - started) * 1000)
            measurements.append(
                _measurement(
                    "long_steady_state",
                    steady_calls,
                    budgets=(
                        {
                            "payload_bytes": OFFLINE_BUDGETS["long_steady_payload_bytes"],
                            "main_calls": 1,
                        }
                        if not live
                        else {
                            "input_tokens": LIVE_WARNING_BUDGETS["long_steady_state_input_tokens"]
                        }
                    ),
                    warning_only=live,
                    elapsed_ms=steady_elapsed if live else None,
                )
            )

            empty_payload = provider_payload((ContextMessage(role="user", content="summary"),), ())
            measurements.append(
                BenchmarkMeasurement(
                    scenario="empty_tools_provider_representation",
                    payload_bytes=len(
                        json.dumps(empty_payload, sort_keys=True, separators=(",", ":")).encode(
                            "utf-8"
                        )
                    ),
                    catalog_bytes=0,
                    message_count=1,
                    main_calls=0,
                    summary_calls=0,
                    visible_tools_by_call=((),),
                    returned_tool_calls_by_call=(),
                    input_tokens_by_call=(),
                    output_tokens_by_call=(),
                    metrics={"tools_key_omitted": "tools" not in empty_payload},
                )
            )
            report = BenchmarkReport("live" if live else "offline", tuple(measurements))
            if not live:
                report.require_passing()
            return report
        finally:
            app.store.close()


async def run_offline_benchmark() -> BenchmarkReport:
    """Run the required network-free regression suite with deterministic model turns."""
    return await _run_benchmark(live=False)


async def run_live_benchmark() -> BenchmarkReport:
    """Run the owner-only configured-provider diagnostic; its thresholds only warn."""
    return await _run_benchmark(live=True)


def benchmark_scenarios() -> tuple[BenchmarkScenario, ...]:
    """Expose the shared stable scenario definitions to scripts and tests."""
    return SCENARIOS
