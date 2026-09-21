"""QA-only bounded stream metadata; never persist raw chunks, arguments or reasoning."""

from __future__ import annotations

import json
import time
from collections import Counter
from unittest.mock import patch

import httpx

from orion.models.providers.openai_compatible import OpenAICompatibleBackend


class DiagnosticProvider(OpenAICompatibleBackend):
    """Transparent observer for the sequential, opt-in semantic QA harness only."""

    def __init__(self):
        super().__init__()
        self.diagnostics = []
        self._record = {}

    async def stream(self, messages, tools, settings, cancellation):
        record = {
            "roles": [message.role for message in messages],
            "http_status": None,
            "finish_reasons": [],
            "sse_done": False,
            "sse_eof": False,
            "tool_argument_json": [],
            "adapter_error_category": None,
            "exception_types": [],
            "stage": "transport",
        }
        self._record = record
        self._pending_calls = {}
        events = Counter()
        started = time.monotonic()
        client_factory = httpx.AsyncClient

        async def response_hook(response):
            record["http_status"] = response.status_code

        def client(**kwargs):
            return client_factory(**kwargs, event_hooks={"response": [response_hook]})

        try:
            # Adapter has no transport injection hook. Scope the QA-only patch to this
            # sequential attempt, restore even on failure; never alter HTTP payloads.
            with patch("orion.models.providers.openai_compatible.httpx.AsyncClient", client):
                async for event in super().stream(messages, tools, settings, cancellation):
                    events[type(event).__name__] += 1
                    yield event
        except BaseException as error:
            kind = getattr(error, "kind", None)
            record["adapter_error_category"] = getattr(kind, "value", type(error).__name__)
            for _ in range(4):
                if error is None:
                    break
                record["exception_types"].append(type(error).__name__)
                error = error.__cause__
            raise
        finally:
            for call in list(self._pending_calls.values())[:32]:
                try:
                    parsed = json.loads(call.arguments or "{}")
                    state = "valid_object" if isinstance(parsed, dict) else "non_object"
                except (ValueError, TypeError):
                    state = "incomplete_or_malformed"
                record["tool_argument_json"].append(state)
            self._pending_calls = {}
            record["elapsed_ms"] = round((time.monotonic() - started) * 1000)
            record["normalized_event_counts"] = dict(events)
            record["sse_ended_normally"] = record["sse_done"] or (
                record["sse_eof"] and bool(record["finish_reasons"])
            )
            if len(self.diagnostics) < 32:
                self.diagnostics.append(record)

    async def _next_line_or_cancel(self, lines, cancellation):
        line = await super()._next_line_or_cancel(lines, cancellation)
        if line is None:
            self._record["sse_eof"] = True
        elif line.startswith("data:") and line[5:].strip() == "[DONE]":
            self._record["sse_done"] = True
        return line

    def _parse_chunk(self, raw_chunk):
        self._record["stage"] = "parse_chunk"
        chunk = super()._parse_chunk(raw_chunk)
        choices = chunk.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            reason = choices[0].get("finish_reason")
            if reason is not None and len(self._record["finish_reasons"]) < 8:
                self._record["finish_reasons"].append(
                    reason
                    if reason in ("stop", "tool_calls", "length", "content_filter")
                    else "other"
                )
        self._record["stage"] = "normalize_chunk"
        return chunk

    def _normalize_chunk(self, chunk, content_parts, calls):
        self._pending_calls = calls
        yield from super()._normalize_chunk(chunk, content_parts, calls)

    def _build_turn(self, content_parts, calls):
        self._record["stage"] = "build_turn"
        return super()._build_turn(content_parts, calls)
