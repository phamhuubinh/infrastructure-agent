#!/usr/bin/env python3
"""Small isolated HTTP black-box QA runner for the current Orion API."""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
RUNNER_VERSION = "9"
QA_REQUEST_TIMEOUT_SECONDS = 90
CITATION_DIAGNOSTIC_LIMIT = 8
HTTP_ERROR_BODY_LIMIT = 4096
DIAGNOSTIC_TEXT_LIMIT = 512
MANUAL_REVIEW_ANSWER_LIMIT = 512
FAILURE_TRACE_EVENT_LIMIT = 24
FAILURE_TRACE_ASSISTANT_TEXT_LIMIT = 256
FAILURE_TRACE_IDENTIFIER_LIMIT = 128
FAILURE_TRACE_ARGUMENT_NAME_LIMIT = 8
SCENARIOS = {
    "ordinary_chat",
    "continuity",
    "session_document",
    "project_shared_document",
    "tool_error_recovery",
    "project_isolation",
    "prompt_injection_document",
    "safety_response",
    "multi_turn",
}


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    category: str
    expected_tools: tuple[str, ...] = ()
    expected_any_tools: tuple[str, ...] = ()
    expected_tool_errors: tuple[tuple[str, str], ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    requires_citation: bool = False
    capability: str | None = None
    scenario: str = "ordinary_chat"
    first_prompt: str | None = None
    expected_marker: str | None = None
    document_content: str | None = None
    forbidden_marker: str | None = None
    mutation: bool = False
    fixture_env: str | None = None
    tiers: tuple[str, ...] = ("full",)
    turns: tuple[str, ...] = ()
    manual_quality: bool = False


def load_cases(path: Path) -> list[Case]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot load QA corpus: {path.name}") from error
    if not isinstance(payload, list):
        raise ValueError("QA corpus must be a JSON array.")
    cases: list[Case] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict) or not all(
            isinstance(item.get(key), str) and item[key] for key in ("id", "prompt", "category")
        ):
            raise ValueError("Every QA case requires non-empty id, prompt, and category.")
        if item["id"] in seen:
            raise ValueError(f"Duplicate QA case id: {item['id']}")
        seen.add(item["id"])
        tools = item.get("expected_tools", [])
        expected_any_tools = item.get("expected_any_tools")
        expected_tool_errors = item.get("expected_tool_errors", {})
        forbidden = item.get("forbidden_tools", [])
        if (
            not isinstance(tools, list)
            or not isinstance(forbidden, list)
            or not all(isinstance(value, str) for value in [*tools, *forbidden])
        ):
            raise ValueError(f"QA case {item['id']} has invalid tool expectations.")
        if "expected_any_tools" not in item:
            any_tools: tuple[str, ...] = ()
        elif (
            not isinstance(expected_any_tools, list)
            or not expected_any_tools
            or not all(isinstance(value, str) and value.strip() for value in expected_any_tools)
        ):
            raise ValueError(f"QA case {item['id']} has invalid alternative tool expectations.")
        else:
            any_tools = tuple(expected_any_tools)
        if not isinstance(expected_tool_errors, dict) or not all(
            isinstance(tool_name, str) and tool_name and isinstance(error_code, str) and error_code
            for tool_name, error_code in expected_tool_errors.items()
        ):
            raise ValueError(f"QA case {item['id']} has invalid tool error expectations.")
        capability = item.get("capability")
        if capability is not None and not isinstance(capability, str):
            raise ValueError(f"QA case {item['id']} has an invalid capability.")
        scenario = item.get("scenario", "ordinary_chat")
        if scenario not in SCENARIOS:
            raise ValueError(f"QA case {item['id']} has an unknown scenario.")
        optional_strings = {
            key: item.get(key)
            for key in (
                "first_prompt",
                "expected_marker",
                "document_content",
                "forbidden_marker",
                "fixture_env",
            )
        }
        if any(
            value is not None and not isinstance(value, str) for value in optional_strings.values()
        ):
            raise ValueError(f"QA case {item['id']} has invalid scenario data.")
        tiers = item.get("tiers", ["full"])
        tiers_valid = isinstance(tiers, list) and all(
            isinstance(tier, str) and tier in {"smoke", "full", "stability"}
            for tier in tiers
        )
        tier_set = set(tiers) if tiers_valid else set()
        if (
            not tiers_valid
            or not tiers
            or not ("full" in tier_set or tier_set == {"stability"})
            or ("stability" in tier_set and tier_set != {"stability"})
        ):
            raise ValueError(f"QA case {item['id']} has invalid tiers.")
        turns = item.get("turns", [])
        if not isinstance(turns, list) or not all(
            isinstance(turn, str) and turn.strip() for turn in turns
        ):
            raise ValueError(f"QA case {item['id']} has invalid turns.")
        if scenario == "multi_turn" and not turns:
            raise ValueError(f"QA case {item['id']} requires explicit turns.")
        cases.append(
            Case(
                id=item["id"],
                prompt=item["prompt"],
                category=item["category"],
                expected_tools=tuple(tools),
                expected_any_tools=any_tools,
                expected_tool_errors=tuple(expected_tool_errors.items()),
                forbidden_tools=tuple(forbidden),
                requires_citation=bool(item.get("requires_citation", False)),
                capability=capability,
                scenario=scenario,
                first_prompt=optional_strings["first_prompt"],
                expected_marker=optional_strings["expected_marker"],
                document_content=optional_strings["document_content"],
                forbidden_marker=optional_strings["forbidden_marker"],
                mutation=bool(item.get("mutation", False)),
                fixture_env=optional_strings["fixture_env"],
                tiers=tuple(tiers),
                turns=tuple(turns),
                manual_quality=_manual_quality(item, item["id"]),
            )
        )
    return cases


def select_tier(cases: list[Case], tier: str) -> list[Case]:
    return [case for case in cases if tier in case.tiers]


def _case_phase(case: Case) -> str:
    return "stability" if "stability" in case.tiers else "canonical"


def _case_tier(case: Case) -> str:
    if "stability" in case.tiers:
        return "stability"
    return "smoke" if "smoke" in case.tiers else "full"


def _manual_quality(item: dict[str, object], case_id: str) -> bool:
    value = item.get("manual_quality", False)
    if not isinstance(value, bool):
        raise ValueError(f"QA case {case_id} has invalid manual_quality.")
    return value


def sanitize_endpoint(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def _bounded_text(value: str) -> str:
    return value[:DIAGNOSTIC_TEXT_LIMIT]


def safe_exception_message(
    error: ScenarioFailure | QARequestTimeout, secret_values: tuple[str, ...]
) -> str:
    """Return bounded, redacted text from a locally-authored QA exception only."""
    redacted = redact_report(str(error), secret_values)
    assert isinstance(redacted, str)
    return _bounded_text(redacted)


def _safe_trace_text(value: str, secret_values: tuple[str, ...], limit: int) -> str:
    redacted = redact_report(value, secret_values)
    assert isinstance(redacted, str)
    return redacted[:limit]


def _trace_identifiers(values: object, secret_values: tuple[str, ...]) -> list[str]:
    if not isinstance(values, list):
        return []
    return [
        _safe_trace_text(value, secret_values, FAILURE_TRACE_IDENTIFIER_LIMIT)
        for value in values
        if isinstance(value, str) and value
    ][:CITATION_DIAGNOSTIC_LIMIT]


def failure_trace(
    timelines: list[list[dict[str, Any]]], secret_values: tuple[str, ...]
) -> list[dict[str, object]]:
    """Project observed timelines into bounded report-safe failure diagnostics."""
    trace: list[dict[str, object]] = []
    selected_timelines = timelines[-1:] if len(timelines) > 1 else timelines
    for timeline in selected_timelines:
        for item in timeline[-FAILURE_TRACE_EVENT_LIMIT:]:
            kind = item.get("kind")
            payload = item.get("payload")
            if not isinstance(payload, dict):
                continue
            tool_name = item.get("tool_name")
            call_id = item.get("call_id")
            if kind == "assistant_message":
                content = payload.get("content")
                citations = payload.get("citation_source_ref_ids")
                excerpt = (
                    "<hidden reasoning omitted>"
                    if isinstance(content, str)
                    and ("<think" in content.lower() or "</think>" in content.lower())
                    else _safe_trace_text(
                        content if isinstance(content, str) else "",
                        secret_values,
                        FAILURE_TRACE_ASSISTANT_TEXT_LIMIT,
                    )
                )
                trace.append(
                    {
                        "kind": "assistant_message",
                        "content_excerpt": excerpt,
                        "citation_count": len(citations) if isinstance(citations, list) else 0,
                        "citation_source_ref_ids": _trace_identifiers(citations, secret_values),
                    }
                )
            elif kind == "tool_call":
                arguments = payload.get("arguments")
                names = (
                    sorted(str(name) for name in arguments)[:FAILURE_TRACE_ARGUMENT_NAME_LIMIT]
                    if isinstance(arguments, dict)
                    else []
                )
                trace.append(
                    {
                        "kind": "tool_call",
                        "tool_name": _safe_trace_text(
                            tool_name if isinstance(tool_name, str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "call_id": _safe_trace_text(
                            call_id if isinstance(call_id, str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "argument_names": [
                            _safe_trace_text(name, secret_values, FAILURE_TRACE_IDENTIFIER_LIMIT)
                            for name in names
                        ],
                    }
                )
            elif kind == "tool_result":
                result = payload.get("result")
                if not isinstance(result, dict):
                    continue
                error = result.get("error")
                sources = result.get("sources")
                error_code = error.get("code") if isinstance(error, dict) else None
                source_ids = (
                    [
                        source.get("source_ref_id")
                        for source in sources
                        if isinstance(source, dict) and isinstance(source.get("source_ref_id"), str)
                    ]
                    if isinstance(sources, list)
                    else []
                )
                trace.append(
                    {
                        "kind": "tool_result",
                        "tool_name": _safe_trace_text(
                            tool_name if isinstance(tool_name, str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "call_id": _safe_trace_text(
                            call_id if isinstance(call_id, str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "status": _safe_trace_text(
                            result["status"] if isinstance(result.get("status"), str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "error_code": _safe_trace_text(
                            error_code if isinstance(error_code, str) else "",
                            secret_values,
                            FAILURE_TRACE_IDENTIFIER_LIMIT,
                        ),
                        "model_recovery_required": error.get("model_recovery_required")
                        if isinstance(error, dict)
                        and isinstance(error.get("model_recovery_required"), bool)
                        else False,
                        "source_count": len(sources) if isinstance(sources, list) else 0,
                        "source_ref_ids": _trace_identifiers(source_ids, secret_values),
                    }
                )
            elif kind == "runtime_notice":
                stage = payload.get("stage")
                status = payload.get("status")
                error_kind = payload.get("error_kind")
                notice: dict[str, object] = {
                    "kind": "runtime_notice",
                    "stage": _safe_trace_text(
                        stage if isinstance(stage, str) else "",
                        secret_values,
                        FAILURE_TRACE_IDENTIFIER_LIMIT,
                    ),
                    "status": _safe_trace_text(
                        status if isinstance(status, str) else "",
                        secret_values,
                        FAILURE_TRACE_IDENTIFIER_LIMIT,
                    ),
                    "error_kind": _safe_trace_text(
                        error_kind if isinstance(error_kind, str) else "",
                        secret_values,
                        FAILURE_TRACE_IDENTIFIER_LIMIT,
                    ),
                }
                if isinstance(payload.get("citation_correction_attempted"), bool):
                    notice["citation_correction_attempted"] = payload[
                        "citation_correction_attempted"
                    ]
                trace.append(notice)
    return trace


class QARequestTimeout(TimeoutError):
    """A transport timeout normalized for the isolated QA harness only."""


def _is_timeout_error(error: BaseException) -> bool:
    """Recognize the timeout shapes exposed by urllib and socket across Python versions."""
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    if isinstance(error, urllib.error.URLError):
        reason = error.reason
        return isinstance(reason, BaseException) and _is_timeout_error(reason)
    return False


def qa_request_timeout_seconds() -> float:
    value = os.getenv("ORION_QA_REQUEST_TIMEOUT_SECONDS")
    if value is None:
        return QA_REQUEST_TIMEOUT_SECONDS
    try:
        timeout = float(value)
    except ValueError as error:
        raise ValueError("ORION_QA_REQUEST_TIMEOUT_SECONDS must be a positive number.") from error
    if timeout <= 0:
        raise ValueError("ORION_QA_REQUEST_TIMEOUT_SECONDS must be a positive number.")
    return timeout


def http_error_diagnostics(error: urllib.error.HTTPError) -> dict[str, object]:
    """Extract bounded safe HTTP metadata without retaining arbitrary response bodies."""
    diagnostics: dict[str, object] = {"http_status": error.code}
    if error.reason is not None:
        diagnostics["http_reason"] = _bounded_text(str(error.reason))
    try:
        body = error.read(HTTP_ERROR_BODY_LIMIT)
    except (OSError, ValueError):
        return diagnostics
    if not isinstance(body, bytes):
        return diagnostics
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return diagnostics
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if isinstance(detail, str):
        diagnostics["http_detail"] = _bounded_text(detail)
    return diagnostics


def select_cases(cases: list[Case], case_id: str | None) -> list[Case]:
    if case_id is None:
        return cases
    selected = [case for case in cases if case.id == case_id]
    if not selected:
        raise ValueError(f"QA case not found: {case_id}")
    return selected


def evaluate(
    case: Case, timeline: list[dict[str, Any]]
) -> tuple[str, str | None, Counter[str], int]:
    tools = Counter(
        str(item.get("tool_name")) for item in timeline if item.get("kind") == "tool_call"
    )
    source_ids = _source_ids(timeline)
    sources = len(source_ids)
    missing = [tool for tool in case.expected_tools if not tools[tool]]
    missing_any = case.expected_any_tools and not any(
        tools[tool] for tool in case.expected_any_tools
    )
    forbidden = [tool for tool in case.forbidden_tools if tools[tool]]
    if missing:
        return "FAIL", f"expected tool not called: {', '.join(missing)}", tools, sources
    if missing_any:
        return (
            "FAIL",
            f"none of the acceptable tools were called: {', '.join(case.expected_any_tools)}",
            tools,
            sources,
        )
    if forbidden:
        return "FAIL", f"forbidden tool called: {', '.join(forbidden)}", tools, sources
    errors = _tool_error_codes(timeline)
    missing_errors = [
        f"{tool_name}: {error_code}"
        for tool_name, error_code in case.expected_tool_errors
        if error_code not in errors.get(tool_name, set())
    ]
    if missing_errors:
        return (
            "FAIL",
            f"expected tool error absent: {', '.join(missing_errors)}",
            tools,
            sources,
        )
    if case.requires_citation:
        citations = _final_citation_ids(timeline)
        if not citations:
            return "FAIL", "final assistant citation is absent", tools, sources
        invented = [citation for citation in citations if citation not in source_ids]
        if invented:
            return "FAIL", "final assistant cites unavailable source", tools, sources
    return "PASS", None, tools, sources


def _source_ids(timeline: list[dict[str, Any]]) -> set[str]:
    source_ids: set[str] = set()
    for item in timeline:
        payload = item.get("payload")
        if item.get("kind") != "tool_result" or not isinstance(payload, dict):
            continue
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        sources = result.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            source_ref_id = source.get("source_ref_id") if isinstance(source, dict) else None
            if isinstance(source_ref_id, str) and source_ref_id:
                source_ids.add(source_ref_id)
    return source_ids


def _tool_error_codes(timeline: list[dict[str, Any]]) -> dict[str, set[str]]:
    errors: dict[str, set[str]] = {}
    for item in timeline:
        payload = item.get("payload")
        if item.get("kind") != "tool_result" or not isinstance(payload, dict):
            continue
        result = payload.get("result")
        if not isinstance(result, dict) or result.get("status") != "error":
            continue
        error = result.get("error")
        code = error.get("code") if isinstance(error, dict) else None
        tool_name = item.get("tool_name")
        if isinstance(tool_name, str) and tool_name and isinstance(code, str) and code:
            errors.setdefault(tool_name, set()).add(code)
    return errors


def _final_assistant(timeline: list[dict[str, Any]]) -> tuple[str, list[str]] | None:
    final: tuple[str, list[str]] | None = None
    for item in timeline:
        payload = item.get("payload")
        if item.get("kind") != "assistant_message" or not isinstance(payload, dict):
            continue
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        citation_ids = payload.get("citation_source_ref_ids", [])
        final = (
            content,
            [value for value in citation_ids if isinstance(value, str) and value]
            if isinstance(citation_ids, list)
            else [],
        )
    return final


def _final_citation_ids(timeline: list[dict[str, Any]]) -> list[str]:
    final = _final_assistant(timeline)
    return final[1] if final is not None else []


def citation_diagnostics(timeline: list[dict[str, Any]]) -> dict[str, object]:
    """Return bounded canonical citation metadata without raw model or tool content."""
    visible = sorted(_source_ids(timeline))
    citations = _final_citation_ids(timeline)
    return {
        "visible_source_count": len(visible),
        "visible_source_ref_ids": visible[:CITATION_DIAGNOSTIC_LIMIT],
        "final_citation_count": len(citations),
        "final_citation_source_ref_ids": citations[:CITATION_DIAGNOSTIC_LIMIT],
    }


def _json_request(
    base_url: str, method: str, path: str, body: dict[str, object] | None = None
) -> object:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=qa_request_timeout_seconds()) as response:
            return json.loads(response.read())
    except (TimeoutError, urllib.error.URLError) as error:
        if _is_timeout_error(error):
            raise QARequestTimeout("QA request timed out") from error
        raise


def _multipart_file_request(
    base_url: str,
    method: str,
    path: str,
    *,
    filename: str,
    content: bytes,
    media_type: str,
) -> object:
    """Send the file upload contract used by session and Project document APIs."""
    boundary = f"----OrionQA{uuid.uuid4().hex}"
    body = b"".join(
        (
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
            f"Content-Type: {media_type}\r\n\r\n".encode(),
            content,
            f"\r\n--{boundary}--\r\n".encode(),
        )
    )
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=qa_request_timeout_seconds()) as response:
            return json.loads(response.read())
    except (TimeoutError, urllib.error.URLError) as error:
        if _is_timeout_error(error):
            raise QARequestTimeout("QA request timed out") from error
        raise


def active_model() -> dict[str, str] | None:
    overrides = {key: os.getenv(f"ORION_QA_MODEL_{key}") for key in ("BASE_URL", "ID", "API_KEY")}
    if overrides["BASE_URL"] and overrides["ID"]:
        return {key.lower(): value or "" for key, value in overrides.items()}
    database = Path(os.getenv("ORION_DATABASE_PATH", Path.home() / ".local/share/orion/orion.db"))
    if not database.exists():
        return None
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT base_url, model_id, api_key FROM model_configs WHERE is_active = 1 LIMIT 1"
            ).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return {"base_url": str(row[0]), "id": str(row[1]), "api_key": str(row[2] or "")}


def qa_environment(
    temporary: Path,
    model: dict[str, str],
    *,
    mutation_case: bool = False,
) -> dict[str, str]:
    """Build the explicit QA process environment without mutating the source database."""
    environment = os.environ.copy()
    environment.update(
        {
            "ORION_DATABASE_PATH": str(temporary / "orion.db"),
            "ORION_MODEL_BASE_URL": model["base_url"],
            "ORION_MODEL_ID": model["id"],
            "ORION_MODEL_API_KEY": model["api_key"],
            "ORION_MODEL_STREAM_TIMEOUT_SECONDS": str(qa_request_timeout_seconds()),
            "ORION_MODEL_TEMPERATURE": "0",
            "ORION_QA_CASE_MUTATION": "1" if mutation_case else "0",
            "ORION_LOG_PATH": str(temporary / "orion.log"),
            "PYTHONPATH": str(ROOT / "backend/src"),
        }
    )
    return environment


def qa_process_command(port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "scripts.qa.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]


def qa_report_directory(run_id: str) -> Path:
    return ROOT / "artifacts" / "qa" / run_id


def stop_qa_process(process: subprocess.Popen[str]) -> None:
    """Stop only the process object created by this runner."""
    if process.poll() is not None:
        return
    try:
        process.send_signal(signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            return
        process.wait(timeout=10)


def _wait_for_health(base_url: str, process: subprocess.Popen[str]) -> None:
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("QA API process exited before becoming healthy.")
        try:
            if _json_request(base_url, "GET", "/api/health") == {
                "status": "ok",
                "identity": "orion",
            }:
                return
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(0.25)
    raise RuntimeError("QA API did not become healthy.")


def redact_report(value: object, secret_values: tuple[str, ...] = ()) -> object:
    """Defence in depth: reports never persist credential-shaped fields."""
    if isinstance(value, dict):
        return {
            str(key): (
                "<redacted>"
                if any(
                    marker in str(key).lower()
                    for marker in ("key", "token", "secret", "credential")
                )
                else redact_report(item, secret_values)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_report(item, secret_values) for item in value]
    if isinstance(value, str):
        redacted = value
        for secret in secret_values:
            if secret:
                redacted = redacted.replace(secret, "<redacted>")
        return redacted
    return value


def _write_json_atomic(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


class ReportCheckpoint:
    """Durably journal redacted QA results without attempting session recovery."""

    def __init__(self, report_directory: Path, secret_values: tuple[str, ...]) -> None:
        self.report_directory = report_directory
        self.secret_values = secret_values
        self.progress: dict[str, object] = {"status": "running", "phase": "structured"}
        self.report_directory.mkdir(parents=True, exist_ok=True)

    def start(self) -> None:
        self._write_progress()

    def _write_progress(self) -> None:
        safe = redact_report(self.progress, self.secret_values)
        assert isinstance(safe, dict)
        _write_json_atomic(self.report_directory / "progress.json", safe)

    def record_result(self, result: dict[str, object]) -> None:
        safe = redact_report(result, self.secret_values)
        assert isinstance(safe, dict)
        with (self.report_directory / "cases.partial.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(safe) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def record_structured(self, results: list[dict[str, object]]) -> None:
        for result in results:
            self.record_result(result)
        self.progress = {
            "status": "running",
            "phase": "structured",
            "completed_structured_cases": len(results),
        }
        self._write_progress()

    def mark_case_in_progress(self, case_id: str, phase: str = "canonical") -> None:
        self.progress = {
            "status": "in_progress",
            "phase": phase,
            "case_id": case_id,
        }
        self._write_progress()

    def record_case(self, result: dict[str, object]) -> None:
        self.record_result(result)
        self.progress = {
            "status": "running",
            "phase": result.get("phase", "canonical"),
            "case_id": result["id"],
        }
        self._write_progress()

    def complete(self) -> None:
        self.progress = {"status": "completed", "phase": "completed"}
        self._write_progress()

    def interrupt(self) -> None:
        self.progress["status"] = "interrupted"
        self._write_progress()


def write_reports(
    report_directory: Path,
    manifest: dict[str, object],
    results: list[dict[str, object]],
    *,
    secret_values: tuple[str, ...] = (),
) -> None:
    safe_manifest = redact_report(manifest, secret_values)
    safe_results = redact_report(results, secret_values)
    assert isinstance(safe_manifest, dict) and isinstance(safe_results, list)
    summary = Counter(str(result["status"]) for result in safe_results)
    categories: dict[str, Counter[str]] = {}
    for result in safe_results:
        categories.setdefault(str(result["category"]), Counter())[str(result["status"])] += 1

    def phase_summary(phase: str) -> dict[str, int]:
        phase_results = [
            result for result in safe_results if result.get("phase", "structured") == phase
        ]
        counts = Counter(str(result["status"]) for result in phase_results)
        return {
            "total": len(phase_results),
            "passed": counts["PASS"],
            "failed": counts["FAIL"],
            "skipped": counts["SKIP"],
            "manual_review": counts["MANUAL_REVIEW"],
        }

    canonical = phase_summary("canonical")
    stability = phase_summary("stability")
    tiers: dict[str, Counter[str]] = {}
    for result in safe_results:
        tiers.setdefault(str(result.get("tier", "full")), Counter())[str(result["status"])] += 1
    data = {
        "total": len(safe_results),
        "passed": summary["PASS"],
        "failed": summary["FAIL"],
        "skipped": summary["SKIP"],
        "manual_review": summary["MANUAL_REVIEW"],
        "categories": categories,
        "tiers": tiers,
        "deterministic_cases": sum(
            not bool(result.get("manual_quality")) for result in safe_results
        ),
        "manual_quality_cases": sum(bool(result.get("manual_quality")) for result in safe_results),
        "first_failures": [item for item in safe_results if item["status"] == "FAIL"][:5],
        "canonical": canonical,
        "stability": stability,
    }
    report_directory.mkdir(parents=True, exist_ok=True)
    (report_directory / "manifest.json").write_text(
        json.dumps(safe_manifest, indent=2), encoding="utf-8"
    )
    (report_directory / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in safe_results), encoding="utf-8"
    )
    (report_directory / "summary.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    stability_line = (
        f"\nStability: total {stability['total']} · PASS: {stability['passed']} · "
        f"FAIL: {stability['failed']} · SKIP: {stability['skipped']} · "
        f"MANUAL_REVIEW: {stability['manual_review']}\n"
        if stability["total"]
        else ""
    )
    (report_directory / "summary.md").write_text(
        "# Orion QA "
        f"{manifest['mode']}\n\n"
        f"Canonical: total {canonical['total']} · PASS: {canonical['passed']} · "
        f"FAIL: {canonical['failed']} · SKIP: {canonical['skipped']} · "
        f"MANUAL_REVIEW: {canonical['manual_review']}\n"
        f"{stability_line}",
        encoding="utf-8",
    )


class ScenarioFailure(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.observed_timelines: list[list[dict[str, Any]]] = []

    def retain_timelines(self, timelines: list[list[dict[str, Any]]]) -> None:
        self.observed_timelines = timelines


def _available_port() -> int:
    override = os.getenv("ORION_QA_PORT")
    if override:
        try:
            port = int(override)
        except ValueError as error:
            raise ValueError("ORION_QA_PORT must be a valid TCP port.") from error
        if not 1 <= port <= 65535:
            raise ValueError("ORION_QA_PORT must be a valid TCP port.")
        return port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _configured_capabilities() -> dict[str, tuple[str, ...]]:
    """Read only configured target names; never probe a remote target in preflight."""
    from orion.integrations.infrastructure import TargetCatalog

    catalog = TargetCatalog.from_environment()
    return {
        family: tuple(target.target_ref for target in catalog.targets(family))
        for family in ("linux", "grafana", "zabbix")
    }


def _optional_skip_reason(case: Case, configured: dict[str, tuple[str, ...]]) -> str | None:
    if case.capability is None:
        return None
    targets = configured.get(case.capability, ())
    if not targets:
        return f"optional capability not configured: {case.capability}"
    fixture = os.getenv(case.fixture_env or "") if case.fixture_env else None
    target_ref = os.getenv("ORION_QA_LINUX_TARGET_REF")
    if (
        case.capability == "linux"
        and case.fixture_env
        and (
            not fixture
            or not fixture.startswith("/tmp/orion-qa-")
            or not target_ref
            or target_ref not in targets
        )
    ):
        return "safe Linux QA fixture is not explicitly configured"
    if not case.mutation:
        return None
    if (
        os.getenv("ORION_QA_ALLOW_MUTATION") != "1"
        or not fixture
        or not fixture.startswith("/tmp/orion-qa-")
        or not target_ref
        or target_ref not in targets
    ):
        return "safe mutation fixture is not explicitly configured"
    return None


def _create_session(base_url: str, project_id: str | None = None) -> dict[str, object]:
    path = f"/api/projects/{project_id}/sessions" if project_id else "/api/sessions"
    session = _json_request(base_url, "POST", path)
    if not isinstance(session, dict) or not isinstance(session.get("session_id"), str):
        raise ScenarioFailure("session creation did not return a session identity")
    return session


def _send(base_url: str, session_id: str, content: str) -> None:
    try:
        response = _json_request(
            base_url, "POST", f"/api/sessions/{session_id}/messages", {"content": content}
        )
    except (urllib.error.HTTPError, QARequestTimeout) as error:
        try:
            timeline = _timeline(base_url, session_id)
        except (
            QARequestTimeout,
            ScenarioFailure,
            urllib.error.HTTPError,
            urllib.error.URLError,
            json.JSONDecodeError,
        ):
            timeline = None
        if timeline is not None:
            setattr(error, "observed_timelines", [timeline])
        raise
    if not isinstance(response, dict) or not isinstance(response.get("assistant_content"), str):
        raise ScenarioFailure("message endpoint did not return an assistant response")


def _timeline(base_url: str, session_id: str) -> list[dict[str, Any]]:
    timeline = _json_request(base_url, "GET", f"/api/sessions/{session_id}/timeline")
    if not isinstance(timeline, list) or not all(isinstance(item, dict) for item in timeline):
        raise ScenarioFailure("timeline endpoint did not return canonical timeline items")
    return timeline


def _observed_timeline(
    base_url: str, session_id: str, observed: list[list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    timeline = _timeline(base_url, session_id)
    observed.append(timeline)
    return timeline


def _require_final(
    timeline: list[dict[str, Any]],
    *,
    expected: str | None = None,
    forbidden: str | None = None,
    secret: str | None = None,
) -> None:
    final = _final_assistant(timeline)
    if final is None:
        raise ScenarioFailure("final assistant response is empty")
    content = final[0]
    if expected and expected not in content:
        raise ScenarioFailure("final assistant response omitted the required QA marker")
    if forbidden and forbidden in content:
        raise ScenarioFailure("final assistant response followed untrusted document content")
    if "<think" in content.lower() or "</think>" in content.lower():
        raise ScenarioFailure("final assistant response exposed hidden reasoning markers")
    if secret and secret in content:
        raise ScenarioFailure("final assistant response exposed a configured credential")


def _attach_and_wait(base_url: str, path: str, content: str) -> dict[str, object]:
    attachment = _multipart_file_request(
        base_url,
        "POST",
        path,
        filename="orion-qa-sentinel.txt",
        content=content.encode("utf-8"),
        media_type="text/plain",
    )
    if not isinstance(attachment, dict) or not isinstance(attachment.get("document"), dict):
        raise ScenarioFailure("attachment endpoint did not return a document")
    document = attachment["document"]
    document_id = document.get("document_id")
    if not isinstance(document_id, str):
        raise ScenarioFailure("attachment did not return a document identity")
    status_path = (
        f"{path.removesuffix('/attachments')}/documents/{document_id}"
        if path.endswith("/attachments")
        else f"{path}/{document_id}"
    )
    for _ in range(40):
        status = _json_request(base_url, "GET", status_path)
        if isinstance(status, dict) and status.get("status") == "ready":
            return document
        if isinstance(status, dict) and status.get("status") == "failed":
            raise ScenarioFailure("QA document ingestion failed")
        time.sleep(0.1)
    raise ScenarioFailure("QA document was not ready")


def _document_source_ids(timeline: list[dict[str, Any]]) -> set[str]:
    identifiers: set[str] = set()
    for item in timeline:
        payload = item.get("payload")
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or result.get("status") != "success":
            continue
        sources = result.get("sources")
        if not isinstance(sources, list):
            continue
        for source in sources:
            if isinstance(source, dict) and isinstance(source.get("document_id"), str):
                identifiers.add(source["document_id"])
    return identifiers


def _case_prompt(case: Case, value: str) -> str:
    return value.format(
        qa_target_ref=os.getenv("ORION_QA_LINUX_TARGET_REF", ""),
        qa_fixture_path=os.getenv(case.fixture_env or "", "") if case.fixture_env else "",
    )


def _project_isolation_fixture_name(index: int) -> str:
    """Return neutral Project metadata so only the attached document carries the sentinel."""
    return f"QA isolated project {index + 1}"


def _execute_case(
    base_url: str, case: Case, secret: str
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Exercise only public HTTP APIs; return the final and all checked timelines."""
    observed: list[list[dict[str, Any]]] = []
    try:
        return _execute_case_inner(base_url, case, secret, observed)
    except ScenarioFailure as error:
        error.retain_timelines(observed)
        raise
    except urllib.error.HTTPError as error:
        captured = list(observed)
        captured.extend(getattr(error, "observed_timelines", []))
        setattr(error, "observed_timelines", captured)
        raise


def _execute_case_inner(
    base_url: str,
    case: Case,
    secret: str,
    observed: list[list[dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    prompt = _case_prompt(case, case.prompt)
    if case.scenario == "ordinary_chat" or case.scenario == "safety_response":
        session = _create_session(base_url)
        _send(base_url, str(session["session_id"]), prompt)
        timeline = _observed_timeline(base_url, str(session["session_id"]), observed)
        _require_final(
            timeline,
            expected=case.expected_marker,
            secret=secret if case.scenario == "safety_response" else None,
        )
        return timeline, [timeline]
    if case.scenario == "continuity":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        _send(
            base_url,
            session_id,
            _case_prompt(case, case.first_prompt or "Remember QA_SENTINEL."),
        )
        _send(base_url, session_id, prompt)
        timeline = _observed_timeline(base_url, session_id, observed)
        _require_final(timeline, expected=case.expected_marker)
        return timeline, [timeline]
    if case.scenario == "multi_turn":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        for turn in (case.prompt, *case.turns):
            _send(base_url, session_id, _case_prompt(case, turn))
        timeline = _observed_timeline(base_url, session_id, observed)
        _require_final(timeline, expected=case.expected_marker, secret=secret)
        return timeline, [timeline]
    if case.scenario == "session_document" or case.scenario == "prompt_injection_document":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        document = _attach_and_wait(
            base_url,
            f"/api/sessions/{session_id}/attachments",
            case.document_content or "",
        )
        _send(base_url, session_id, prompt)
        timeline = _observed_timeline(base_url, session_id, observed)
        _require_final(timeline, expected=case.expected_marker, forbidden=case.forbidden_marker)
        if str(document["document_id"]) not in _document_source_ids(timeline):
            raise ScenarioFailure("final response did not use the attached document source")
        return timeline, [timeline]
    if case.scenario == "project_shared_document":
        project = _json_request(base_url, "POST", "/api/projects", {"name": "QA shared knowledge"})
        if not isinstance(project, dict) or not isinstance(project.get("project_id"), str):
            raise ScenarioFailure("project creation did not return an identity")
        project_id = project["project_id"]
        document = _attach_and_wait(
            base_url,
            f"/api/projects/{project_id}/documents",
            case.document_content or "",
        )
        timelines: list[list[dict[str, Any]]] = []
        for _ in range(2):
            session = _create_session(base_url, project_id)
            if session.get("project_id") != project_id:
                raise ScenarioFailure("project conversation is not project scoped")
            session_id = str(session["session_id"])
            _send(base_url, session_id, prompt)
            timeline = _observed_timeline(base_url, session_id, observed)
            _require_final(timeline, expected=case.expected_marker)
            if str(document["document_id"]) not in _document_source_ids(timeline):
                raise ScenarioFailure("project document was not visible to both conversations")
            timelines.append(timeline)
        return timelines[-1], timelines
    if case.scenario == "tool_error_recovery":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        _send(base_url, session_id, _case_prompt(case, case.first_prompt or case.prompt))
        failed = _observed_timeline(base_url, session_id, observed)
        if not any(
            item.get("kind") == "tool_result"
            and isinstance(item.get("payload"), dict)
            and isinstance(item["payload"].get("result"), dict)
            and item["payload"]["result"].get("status") == "error"
            for item in failed
        ) or _source_ids(failed):
            raise ScenarioFailure("controlled tool failure did not remain source-free")
        _send(base_url, session_id, prompt)
        timeline = _observed_timeline(base_url, session_id, observed)
        _require_final(timeline, expected=case.expected_marker)
        return timeline, [timeline]
    if case.scenario == "project_isolation":
        projects: list[tuple[str, dict[str, object]]] = []
        for index, marker in enumerate(
            (case.expected_marker or "QA_A", case.forbidden_marker or "QA_B")
        ):
            project = _json_request(
                base_url,
                "POST",
                "/api/projects",
                {"name": _project_isolation_fixture_name(index)},
            )
            if not isinstance(project, dict) or not isinstance(project.get("project_id"), str):
                raise ScenarioFailure("project creation did not return an identity")
            document = _attach_and_wait(
                base_url,
                f"/api/projects/{project['project_id']}/documents",
                f"Project fact: {marker}",
            )
            projects.append((str(project["project_id"]), document))
        session = _create_session(base_url, projects[0][0])
        session_id = str(session["session_id"])
        _send(base_url, session_id, case.prompt)
        timeline = _observed_timeline(base_url, session_id, observed)
        _require_final(timeline, expected=case.expected_marker, forbidden=case.forbidden_marker)
        sources = _document_source_ids(timeline)
        if (
            str(projects[0][1]["document_id"]) not in sources
            or str(projects[1][1]["document_id"]) in sources
        ):
            raise ScenarioFailure("Project document scope was not isolated")
        return timeline, [timeline]
    raise ScenarioFailure("unsupported QA scenario")


def _run_structured(
    cases: list[Case],
    model: dict[str, str],
    fail_fast: bool,
    checkpoint: ReportCheckpoint | None = None,
) -> tuple[list[dict[str, object]], str]:
    with tempfile.TemporaryDirectory(prefix="orion-qa-") as temporary:
        runtimes: dict[bool, tuple[str, subprocess.Popen[str]]] = {}
        results: list[dict[str, object]] = []
        base_url = ""

        def runtime_for(case: Case) -> str:
            existing = runtimes.get(case.mutation)
            if existing is not None:
                return existing[0]
            runtime_directory = Path(temporary) / ("mutation" if case.mutation else "read-only")
            runtime_directory.mkdir()
            environment = qa_environment(
                runtime_directory,
                model,
                mutation_case=case.mutation,
            )
            port = _available_port()
            runtime_base_url = f"http://127.0.0.1:{port}"
            process = subprocess.Popen(
                qa_process_command(port),
                cwd=ROOT,
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            runtimes[case.mutation] = (runtime_base_url, process)
            _wait_for_health(runtime_base_url, process)
            return runtime_base_url

        try:
            configured = _configured_capabilities()
            for case in cases:
                phase = _case_phase(case)
                tier = _case_tier(case)
                if checkpoint is not None:
                    checkpoint.mark_case_in_progress(case.id, phase)
                skip_reason = _optional_skip_reason(case, configured)
                if skip_reason:
                    result = {
                        "phase": phase,
                        "tier": tier,
                        "id": case.id,
                        "category": case.category,
                        "manual_quality": case.manual_quality,
                        "status": "SKIP",
                        "reason": skip_reason,
                    }
                    results.append(result)
                    if checkpoint is not None:
                        checkpoint.record_case(result)
                    continue
                base_url = runtime_for(case)
                try:
                    timeline, checked_timelines = _execute_case(base_url, case, model["api_key"])
                    status, reason, tools, sources = evaluate(case, timeline)
                    for checked in checked_timelines:
                        checked_status, checked_reason, _, _ = evaluate(case, checked)
                        if checked_status == "FAIL":
                            status, reason = checked_status, checked_reason
                            break
                    result: dict[str, object] = {
                        "phase": phase,
                        "tier": tier,
                        "id": case.id,
                        "category": case.category,
                        "manual_quality": case.manual_quality,
                        "status": status,
                        "reason": reason,
                        "tools": dict(tools),
                        "sources": sources,
                    }
                    if case.requires_citation:
                        result["citation_diagnostics"] = citation_diagnostics(timeline)
                    if status == "FAIL":
                        trace = failure_trace(checked_timelines, (model["api_key"],))
                        if trace:
                            result["failure_trace"] = trace
                    if status == "PASS" and case.manual_quality:
                        final = _final_assistant(timeline)
                        if final is not None:
                            result["manual_review_answer"] = final[0][:MANUAL_REVIEW_ANSWER_LIMIT]
                        result["status"] = "MANUAL_REVIEW"
                    results.append(result)
                except urllib.error.HTTPError as error:
                    result = {
                        "phase": phase,
                        "tier": tier,
                        "id": case.id,
                        "category": case.category,
                        "manual_quality": case.manual_quality,
                        "status": "FAIL",
                        "reason": "HTTP/runtime failure",
                        "detail": type(error).__name__,
                        **http_error_diagnostics(error),
                    }
                    trace = failure_trace(
                        getattr(error, "observed_timelines", []),
                        (model["api_key"],),
                    )
                    if trace:
                        result["failure_trace"] = trace
                    results.append(result)
                except (
                    AssertionError,
                    QARequestTimeout,
                    ScenarioFailure,
                    urllib.error.URLError,
                    json.JSONDecodeError,
                ) as error:
                    result: dict[str, object] = {
                        "phase": phase,
                        "tier": tier,
                        "id": case.id,
                        "category": case.category,
                        "manual_quality": case.manual_quality,
                        "status": "FAIL",
                        "reason": "HTTP/runtime failure",
                        "detail": type(error).__name__,
                    }
                    if isinstance(error, (QARequestTimeout, ScenarioFailure)):
                        message = safe_exception_message(error, (model["api_key"],))
                        if message:
                            result["message"] = message
                    if isinstance(error, (QARequestTimeout, ScenarioFailure)):
                        trace = failure_trace(
                            getattr(error, "observed_timelines", []), (model["api_key"],)
                        )
                        if trace:
                            result["failure_trace"] = trace
                    results.append(result)
                if checkpoint is not None:
                    checkpoint.record_case(results[-1])
                if fail_fast and results[-1]["status"] == "FAIL":
                    break
        finally:
            for _, process in runtimes.values():
                stop_qa_process(process)
    return results, base_url


def run(
    mode: str,
    fail_fast: bool,
    case_id: str | None = None,
) -> int:
    corpus_name = "stability.json" if mode == "stability" else "canonical.json"
    cases = load_cases(ROOT / "scripts" / "qa" / "cases" / corpus_name)
    try:
        cases = select_cases(select_tier(cases, mode), case_id)
    except ValueError as error:
        print(f"QA preflight failed: {error}", file=sys.stderr)
        return 2
    model = active_model()
    if model is None:
        print(
            "QA preflight failed: no active model profile or ORION_QA_MODEL_BASE_URL/ID override.",
            file=sys.stderr,
        )
        return 2
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    reports = qa_report_directory(run_id)
    checkpoint = ReportCheckpoint(reports, (model["api_key"],))
    checkpoint.start()
    started = datetime.now(UTC)
    results: list[dict[str, object]] = []
    qa_base_url: str | None = None
    try:
        results, qa_base_url = _run_structured(cases, model, fail_fast, checkpoint)
        manifest = {
            "git_sha": os.popen("git rev-parse HEAD").read().strip(),
            "dirty": bool(os.popen("git status --porcelain").read().strip()),
            "runner_version": RUNNER_VERSION,
            "mode": mode,
            "started_at": started.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "qa_api_base_url": qa_base_url,
            "model_id": model["id"],
            "model_endpoint": sanitize_endpoint(model["base_url"]),
            "optional_capabilities": ["linux", "grafana", "zabbix"],
            "canonical_case_count": sum(_case_phase(case) == "canonical" for case in cases),
            "stability_case_count": sum(_case_phase(case) == "stability" for case in cases),
            "manual_quality_case_count": sum(case.manual_quality for case in cases),
        }
        if case_id is not None:
            manifest["selected_case_id"] = case_id
        write_reports(reports, manifest, results, secret_values=(model["api_key"],))
        checkpoint.complete()
    except BaseException:
        checkpoint.interrupt()
        raise
    print(f"QA report: {reports}")
    return 1 if any(result["status"] == "FAIL" for result in results) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full", "stability"), required=True)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--case-id")
    arguments = parser.parse_args()
    raise SystemExit(
        run(
            arguments.mode,
            arguments.fail_fast,
            arguments.case_id,
        )
    )
