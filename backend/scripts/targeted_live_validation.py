"""Small opt-in live validation using Orion's persisted profile and real runtime.

Uses isolated request storage, denies all mutations, and never runs the historical corpus.
Tool results are kept in temporary storage only; the report contains bounded numeric
evidence/telemetry and terminal answers, not credentials or raw full tool payloads.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from orion.benchmarks.model_context import active_model_settings
from orion.bootstrap import build_application
from orion.chat.diagnostics import BoundedModelInputDiagnostics
from orion.chat.runtime import ChatRuntime, RequestCancelled, RequestFailed
from orion.contracts import (
    ContextMessage,
    ModelToolCall,
    ModelTurn,
    ModelTurnCompleted,
    ToolDefinition,
    ToolResult,
)
from orion.models.backend import ModelBackend, ModelSettings, ModelStreamEvent
from orion.models.providers.openai_compatible import OpenAICompatibleBackend
from orion.paths import database_path
from orion.security import redact_public


class ObservedProvider(ModelBackend):
    def __init__(self, *, inject_unknown: bool = False) -> None:
        self.provider = OpenAICompatibleBackend()
        self.attempts = 0
        self.completed = 0
        self.inject_unknown = inject_unknown

    async def stream(
        self,
        messages: tuple[ContextMessage, ...],
        tools: tuple[ToolDefinition, ...],
        settings: ModelSettings,
        cancellation: asyncio.Event,
    ) -> AsyncIterator[ModelStreamEvent]:
        self.attempts += 1
        inject = self.inject_unknown and self.attempts == 1
        async for event in self.provider.stream(messages, tools, settings, cancellation):
            if isinstance(event, ModelTurnCompleted):
                self.completed += 1
                if inject:
                    event = ModelTurnCompleted(
                        turn=ModelTurn(
                            tool_calls=(
                                ModelToolCall(
                                    call_id="injected-unknown",
                                    tool_name="qa.nonexistent_read",
                                    arguments={},
                                ),
                            )
                        ),
                        usage=event.usage,
                    )
            if not inject or isinstance(event, ModelTurnCompleted):
                yield event


def _numeric_evidence(value: object, prefix: str = "", remaining: int = 32) -> dict[str, object]:
    """Retain only bounded measurement numbers, never arbitrary file text or credentials."""
    output: dict[str, object] = {}
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or any(
                word in key.lower() for word in ("secret", "token", "password", "key")
            ):
                continue
            path = f"{prefix}.{key}" if prefix else key
            if type(item) in (int, float, bool):
                output[path] = item
            elif isinstance(item, Mapping):
                output.update(_numeric_evidence(item, path, remaining - len(output)))
            if len(output) >= remaining:
                break
    return dict(list(output.items())[: max(0, remaining)])


async def validate(output: Path) -> list[dict[str, Any]]:
    settings = active_model_settings()
    results: list[dict[str, Any]] = []
    with TemporaryDirectory(prefix="orion-targeted-live-") as temporary:
        app = build_application(
            database_path=Path(temporary) / "requests.db",
            blocked_tool_operation_kinds=frozenset({"mutation"}),
        )
        try:
            profile_id = app.store.upsert_model_config(
                settings.provider_type,
                settings.base_url,
                settings.model_id,
                settings.api_key,
                settings.reasoning_mode,
            )
            # Explicitly activate the persisted profile if environment seeding created another row.
            app.store.activate_model_config(profile_id)
            targets = app.runtime._infrastructure_targets
            linux = next((target for family, target, _ in targets if family == "linux"), None)
            target = linux or "no-configured-linux-target"
            cases = [
                ("direct", "Giải thích sự khác nhau giữa TCP và UDP"),
                (
                    "linux_read",
                    f"Đọc thông tin CPU hiện tại trên máy {target}. "
                    "Chỉ cần CPU, không đánh giá sức khỏe.",
                ),
                (
                    "independent_reads",
                    f"Trên máy {target}, đọc CPU, RAM, disk và load hiện tại. "
                    "Các đầu vào độc lập đã biết: có thể gọi các read cùng lượt. "
                    "Chỉ báo số đo và giới hạn, không suy ra sức khỏe.",
                ),
                ("tool_roundtrip", "Dùng công cụ tính 12345 * 6789."),
                (
                    "stale_refresh",
                    f"Đọc lại CPU và RAM hiện tại trên {target}; "
                    "không dùng số đo hoặc kết luận cũ làm trạng thái hiện tại.",
                ),
                (
                    "service_not_found",
                    f"Kiểm tra trạng thái service orion-qa-absent-7df12 trên {target}. "
                    "Chỉ kết luận từ lookup; không suy ra package đã cài hay chưa.",
                ),
                ("unknown_recovery", "Dùng công cụ tính 17 * 19 và trả kết quả."),
                (
                    "ssh_commented",
                    "Đọc tệp ssh-commented-fixture.txt đính kèm. "
                    "Dòng PermitRootLogin trong tệp có đang active không? "
                    "Có đủ bằng chứng để kết luận giá trị hiệu lực của hệ thống không?",
                ),
            ]
            for name, prompt in cases:
                session = app.store.create_session()
                if name == "ssh_commented":
                    app.knowledge.attach(
                        session,
                        "ssh-commented-fixture.txt",
                        b"#PermitRootLogin prohibit-password\n",
                    )
                if name == "stale_refresh":
                    app.store.append_timeline(
                        session,
                        None,
                        "user_message",
                        {"content": "Historical synthetic observation, not current."},
                    )
                    old_call = ModelToolCall(
                        call_id="historical",
                        tool_name="linux.system.inspect",
                        arguments={"target_ref": target, "sections": ["cpu", "memory"]},
                    )
                    app.store.append_timeline(
                        session,
                        None,
                        "assistant_message",
                        {
                            "content": "",
                            "tool_calls": [old_call.model_dump()],
                            "citation_source_ref_ids": [],
                        },
                    )
                    old = ToolResult(
                        call_id=old_call.call_id,
                        tool_name=old_call.tool_name,
                        status="success",
                        data={"target_ref": target, "cpu_count": 999, "memory_free_bytes": 1},
                    )
                    app.store.append_timeline(
                        session,
                        None,
                        "tool_result",
                        {"result": old.model_dump(mode="json")},
                        call_id=old.call_id,
                        tool_name=old.tool_name,
                    )
                    app.store.append_timeline(
                        session,
                        None,
                        "assistant_message",
                        {
                            "content": "Earlier assistant claimed: 999 CPUs, 1 byte free RAM; "
                            "everything healthy.",
                            "tool_calls": [],
                            "citation_source_ref_ids": [],
                        },
                    )
                provider = ObservedProvider(inject_unknown=name == "unknown_recovery")
                sink = BoundedModelInputDiagnostics()
                runtime = ChatRuntime(
                    app.store,
                    provider,
                    app.registry,
                    app.access,
                    targets,
                    diagnostic_sink=sink,
                    blocked_tool_operation_kinds=frozenset({"mutation"}),
                )
                timeline_start = len(app.store.timeline(session))
                request_id = runtime.begin(session, prompt)
                started = time.monotonic()
                error_kind = None
                answer = ""
                try:
                    outcome = await runtime.run(session, request_id)
                    status, answer = outcome.status, outcome.assistant_content
                except (RequestFailed, RequestCancelled) as error:
                    status, error_kind = "failed", type(error).__name__
                wall_ms = round((time.monotonic() - started) * 1000)
                timeline = app.store.timeline(session)[timeline_start:]
                records = sink.records(request_id)["records"]
                inputs = [record["model_input"] for record in records if "model_input" in record]
                calls = [item.tool_name for item in timeline if item.kind == "tool_call"]
                tool_results = [item for item in timeline if item.kind == "tool_result"]
                result = {
                    "case": name,
                    "prompt": prompt,
                    "wall_time_ms": wall_ms,
                    "model_attempt_count": provider.attempts,
                    "model_completed_count": provider.completed,
                    "tool_calls": calls,
                    "terminal_status": status,
                    "terminal_answer": redact_public(answer),
                    "error_kind": error_kind,
                    "tool_schema_bytes": [item.get("tool_schema_bytes") for item in inputs],
                    "context_bytes": [item.get("context_bytes") for item in inputs],
                    "provider_request_proxy_bytes": [
                        item.get("request_proxy_bytes") for item in inputs
                    ],
                    "current_evidence_bytes": [
                        item.get("current_evidence_bytes") for item in inputs
                    ],
                    "tool_elapsed_ms_total": sum(
                        item.payload.get("elapsed_ms", 0) for item in tool_results
                    ),
                    "tool_results": [
                        {
                            "tool_name": item.tool_name,
                            "call_id": item.call_id,
                            "elapsed_ms": item.payload.get("elapsed_ms"),
                            "status": item.payload["result"]["status"],
                            "error_code": (item.payload["result"].get("error") or {}).get("code"),
                            "numeric_evidence": _numeric_evidence(
                                item.payload["result"].get("data")
                            ),
                        }
                        for item in tool_results
                    ],
                    "model_phases": [
                        {
                            key: value
                            for key, value in record.items()
                            if key not in {"model_input", "canonical_result"}
                        }
                        for record in records
                        if record.get("phase") == "model"
                    ],
                    "summary_model_calls": 0,
                    "grounding_concern": "Requires manual answer/evidence review; "
                    "completion is not semantic correctness.",
                    "fault_injected": name == "unknown_recovery",
                    "fixture_evidence": name in {"ssh_commented", "stale_refresh"},
                    "linux_target_configured": linux is not None,
                }
                results.append(result)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(
                    json.dumps(
                        {
                            "resolved_database": str(database_path()),
                            "model_id": settings.model_id,
                            "base_url": settings.base_url,
                            "cases": results,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                print(
                    json.dumps(
                        {
                            key: result[key]
                            for key in (
                                "case",
                                "wall_time_ms",
                                "model_attempt_count",
                                "model_completed_count",
                                "terminal_status",
                                "tool_calls",
                            )
                        }
                    ),
                    flush=True,
                )
        finally:
            app.store.close()
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(validate(parser.parse_args().output))
