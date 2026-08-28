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
RUNNER_VERSION = "2"
SCENARIOS = {
    "ordinary_chat",
    "continuity",
    "session_document",
    "project_shared_document",
    "tool_error_recovery",
    "project_isolation",
    "prompt_injection_document",
    "safety_response",
}


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    category: str
    expected_tools: tuple[str, ...] = ()
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
        expected_tool_errors = item.get("expected_tool_errors", {})
        forbidden = item.get("forbidden_tools", [])
        if (
            not isinstance(tools, list)
            or not isinstance(forbidden, list)
            or not all(isinstance(value, str) for value in [*tools, *forbidden])
        ):
            raise ValueError(f"QA case {item['id']} has invalid tool expectations.")
        if (
            not isinstance(expected_tool_errors, dict)
            or not all(
                isinstance(tool_name, str)
                and tool_name
                and isinstance(error_code, str)
                and error_code
                for tool_name, error_code in expected_tool_errors.items()
            )
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
            for key in ("first_prompt", "expected_marker", "document_content", "forbidden_marker", "fixture_env")
        }
        if any(value is not None and not isinstance(value, str) for value in optional_strings.values()):
            raise ValueError(f"QA case {item['id']} has invalid scenario data.")
        cases.append(
            Case(
                id=item["id"],
                prompt=item["prompt"],
                category=item["category"],
                expected_tools=tuple(tools),
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
            )
        )
    return cases


def sanitize_endpoint(value: str) -> str:
    parts = urlsplit(value)
    host = parts.hostname or ""
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, "", ""))


def evaluate(
    case: Case, timeline: list[dict[str, Any]]
) -> tuple[str, str | None, Counter[str], int]:
    tools = Counter(
        str(item.get("tool_name")) for item in timeline if item.get("kind") == "tool_call"
    )
    source_ids = _source_ids(timeline)
    sources = len(source_ids)
    missing = [tool for tool in case.expected_tools if not tools[tool]]
    forbidden = [tool for tool in case.forbidden_tools if tools[tool]]
    if missing:
        return "FAIL", f"expected tool not called: {', '.join(missing)}", tools, sources
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


def _json_request(
    base_url: str, method: str, path: str, body: dict[str, object] | None = None
) -> object:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{base_url}{path}", data=data, method=method, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310 - fixed loopback URL.
        return json.loads(response.read())


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


def qa_environment(temporary: Path, model: dict[str, str]) -> dict[str, str]:
    """Build the explicit QA process environment without mutating the source database."""
    environment = os.environ.copy()
    environment.update(
        {
            "ORION_DATABASE_PATH": str(temporary / "orion.db"),
            "ORION_MODEL_BASE_URL": model["base_url"],
            "ORION_MODEL_ID": model["id"],
            "ORION_MODEL_API_KEY": model["api_key"],
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
        "orion.api.app:create_app",
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
                if any(marker in str(key).lower() for marker in ("key", "token", "secret", "credential"))
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
    data = {
        "total": len(safe_results),
        "passed": summary["PASS"],
        "failed": summary["FAIL"],
        "skipped": summary["SKIP"],
        "manual_review": summary["MANUAL_REVIEW"],
        "categories": categories,
        "first_failures": [item for item in safe_results if item["status"] == "FAIL"][:5],
    }
    report_directory.mkdir(parents=True, exist_ok=True)
    (report_directory / "manifest.json").write_text(
        json.dumps(safe_manifest, indent=2), encoding="utf-8"
    )
    (report_directory / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in safe_results), encoding="utf-8"
    )
    (report_directory / "summary.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    (report_directory / "summary.md").write_text(
        f"# Orion QA {manifest['mode']}\n\nTotal: {data['total']} · PASS: {data['passed']} · FAIL: {data['failed']} · SKIP: {data['skipped']}\n",
        encoding="utf-8",
    )


class ScenarioFailure(RuntimeError):
    pass


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


def _optional_skip_reason(
    case: Case, configured: dict[str, tuple[str, ...]]
) -> str | None:
    if case.capability is None:
        return None
    targets = configured.get(case.capability, ())
    if not targets:
        return f"optional capability not configured: {case.capability}"
    fixture = os.getenv(case.fixture_env or "") if case.fixture_env else None
    target_ref = os.getenv("ORION_QA_LINUX_TARGET_REF")
    if case.capability == "linux" and case.fixture_env and (
        not fixture
        or not fixture.startswith("/tmp/orion-qa-")
        or not target_ref
        or target_ref not in targets
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
    response = _json_request(
        base_url, "POST", f"/api/sessions/{session_id}/messages", {"content": content}
    )
    if not isinstance(response, dict) or not isinstance(response.get("assistant_content"), str):
        raise ScenarioFailure("message endpoint did not return an assistant response")


def _timeline(base_url: str, session_id: str) -> list[dict[str, Any]]:
    timeline = _json_request(base_url, "GET", f"/api/sessions/{session_id}/timeline")
    if not isinstance(timeline, list) or not all(isinstance(item, dict) for item in timeline):
        raise ScenarioFailure("timeline endpoint did not return canonical timeline items")
    return timeline


def _require_final(
    timeline: list[dict[str, Any]], *, expected: str | None = None, forbidden: str | None = None,
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


def _attach_and_wait(
    base_url: str, path: str, content: str
) -> dict[str, object]:
    attachment = _json_request(
        base_url,
        "POST",
        path,
        {"name": "orion-qa-sentinel.txt", "content": content, "media_type": "text/plain"},
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


def _execute_case(base_url: str, case: Case, secret: str) -> tuple[list[dict[str, Any]], list[list[dict[str, Any]]]]:
    """Exercise only public HTTP APIs; return the final and all checked timelines."""
    prompt = _case_prompt(case, case.prompt)
    if case.scenario == "ordinary_chat" or case.scenario == "safety_response":
        session = _create_session(base_url)
        _send(base_url, str(session["session_id"]), prompt)
        timeline = _timeline(base_url, str(session["session_id"]))
        _require_final(timeline, expected=case.expected_marker, secret=secret if case.scenario == "safety_response" else None)
        return timeline, [timeline]
    if case.scenario == "continuity":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        _send(base_url, session_id, _case_prompt(case, case.first_prompt or "Remember QA_SENTINEL."))
        _send(base_url, session_id, prompt)
        timeline = _timeline(base_url, session_id)
        _require_final(timeline, expected=case.expected_marker)
        return timeline, [timeline]
    if case.scenario == "session_document" or case.scenario == "prompt_injection_document":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        document = _attach_and_wait(
            base_url, f"/api/sessions/{session_id}/attachments", case.document_content or ""
        )
        _send(base_url, session_id, prompt)
        timeline = _timeline(base_url, session_id)
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
            base_url, f"/api/projects/{project_id}/documents", case.document_content or ""
        )
        timelines: list[list[dict[str, Any]]] = []
        for _ in range(2):
            session = _create_session(base_url, project_id)
            if session.get("project_id") != project_id:
                raise ScenarioFailure("project conversation is not project scoped")
            session_id = str(session["session_id"])
            _send(base_url, session_id, prompt)
            timeline = _timeline(base_url, session_id)
            _require_final(timeline, expected=case.expected_marker)
            if str(document["document_id"]) not in _document_source_ids(timeline):
                raise ScenarioFailure("project document was not visible to both conversations")
            timelines.append(timeline)
        return timelines[-1], timelines
    if case.scenario == "tool_error_recovery":
        session = _create_session(base_url)
        session_id = str(session["session_id"])
        _send(base_url, session_id, _case_prompt(case, case.first_prompt or case.prompt))
        failed = _timeline(base_url, session_id)
        if not any(
            item.get("kind") == "tool_result"
            and isinstance(item.get("payload"), dict)
            and isinstance(item["payload"].get("result"), dict)
            and item["payload"]["result"].get("status") == "error"
            for item in failed
        ) or _source_ids(failed):
            raise ScenarioFailure("controlled tool failure did not remain source-free")
        _send(base_url, session_id, prompt)
        timeline = _timeline(base_url, session_id)
        _require_final(timeline, expected=case.expected_marker)
        return timeline, [timeline]
    if case.scenario == "project_isolation":
        projects: list[tuple[str, dict[str, object]]] = []
        for marker in (case.expected_marker or "QA_A", case.forbidden_marker or "QA_B"):
            project = _json_request(base_url, "POST", "/api/projects", {"name": f"QA {marker}"})
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
        timeline = _timeline(base_url, session_id)
        _require_final(timeline, expected=case.expected_marker, forbidden=case.forbidden_marker)
        sources = _document_source_ids(timeline)
        if str(projects[0][1]["document_id"]) not in sources or str(projects[1][1]["document_id"]) in sources:
            raise ScenarioFailure("Project document scope was not isolated")
        return timeline, [timeline]
    raise ScenarioFailure("unsupported QA scenario")


def run(mode: str, fail_fast: bool) -> int:
    cases = load_cases(ROOT / "scripts" / "qa" / "cases" / f"{mode}.json")
    model = active_model()
    if model is None:
        print(
            "QA preflight failed: no active model profile or ORION_QA_MODEL_BASE_URL/ID override.",
            file=sys.stderr,
        )
        return 2
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    reports = qa_report_directory(run_id)
    with tempfile.TemporaryDirectory(prefix="orion-qa-") as temporary:
        environment = qa_environment(Path(temporary), model)
        port = _available_port()
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            qa_process_command(port),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        results: list[dict[str, object]] = []
        started = datetime.now(UTC)
        try:
            _wait_for_health(base_url, process)
            configured = _configured_capabilities()
            for case in cases:
                skip_reason = _optional_skip_reason(case, configured)
                if skip_reason:
                    results.append(
                        {
                            "id": case.id,
                            "category": case.category,
                            "status": "SKIP",
                            "reason": skip_reason,
                        }
                    )
                    continue
                try:
                    timeline, checked_timelines = _execute_case(base_url, case, model["api_key"])
                    status, reason, tools, sources = evaluate(case, timeline)
                    for checked in checked_timelines:
                        checked_status, checked_reason, _, _ = evaluate(case, checked)
                        if checked_status == "FAIL":
                            status, reason = checked_status, checked_reason
                            break
                    results.append(
                        {
                            "id": case.id,
                            "category": case.category,
                            "status": status,
                            "reason": reason,
                            "tools": dict(tools),
                            "sources": sources,
                        }
                    )
                except (
                    AssertionError,
                    ScenarioFailure,
                    urllib.error.URLError,
                    urllib.error.HTTPError,
                    json.JSONDecodeError,
                ) as error:
                    results.append(
                        {
                            "id": case.id,
                            "category": case.category,
                            "status": "FAIL",
                            "reason": "HTTP/runtime failure",
                            "detail": type(error).__name__,
                        }
                    )
                if fail_fast and results[-1]["status"] == "FAIL":
                    break
        finally:
            stop_qa_process(process)
        manifest = {
            "git_sha": os.popen("git rev-parse HEAD").read().strip(),
            "dirty": bool(os.popen("git status --porcelain").read().strip()),
            "runner_version": RUNNER_VERSION,
            "mode": mode,
            "started_at": started.isoformat(),
            "ended_at": datetime.now(UTC).isoformat(),
            "qa_api_base_url": base_url,
            "model_id": model["id"],
            "model_endpoint": sanitize_endpoint(model["base_url"]),
            "optional_capabilities": ["linux", "grafana", "zabbix"],
        }
        write_reports(reports, manifest, results, secret_values=(model["api_key"],))
    print(f"QA report: {reports}")
    return 1 if any(result["status"] == "FAIL" for result in results) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--fail-fast", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.mode, arguments.fail_fast))
