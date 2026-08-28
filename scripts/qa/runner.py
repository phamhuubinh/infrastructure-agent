#!/usr/bin/env python3
"""Small isolated HTTP black-box QA runner for the current Orion API."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
RUNNER_VERSION = "1"


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    category: str
    expected_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    requires_citation: bool = False
    capability: str | None = None


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
        forbidden = item.get("forbidden_tools", [])
        if (
            not isinstance(tools, list)
            or not isinstance(forbidden, list)
            or not all(isinstance(value, str) for value in [*tools, *forbidden])
        ):
            raise ValueError(f"QA case {item['id']} has invalid tool expectations.")
        capability = item.get("capability")
        if capability is not None and not isinstance(capability, str):
            raise ValueError(f"QA case {item['id']} has an invalid capability.")
        cases.append(
            Case(
                id=item["id"],
                prompt=item["prompt"],
                category=item["category"],
                expected_tools=tuple(tools),
                forbidden_tools=tuple(forbidden),
                requires_citation=bool(item.get("requires_citation", False)),
                capability=capability,
            )
        )
    return cases


def sanitize_endpoint(value: str) -> str:
    parts = urlsplit(value)
    return urlunsplit((parts.scheme, parts.hostname or "", parts.path, "", ""))


def evaluate(
    case: Case, timeline: list[dict[str, Any]]
) -> tuple[str, str | None, Counter[str], int]:
    tools = Counter(
        str(item.get("tool_name")) for item in timeline if item.get("kind") == "tool_call"
    )
    sources = sum(
        len(item.get("payload", {}).get("sources", []))
        for item in timeline
        if item.get("kind") == "tool_result" and isinstance(item.get("payload"), dict)
    )
    missing = [tool for tool in case.expected_tools if not tools[tool]]
    forbidden = [tool for tool in case.forbidden_tools if tools[tool]]
    if missing:
        return "FAIL", f"expected tool not called: {', '.join(missing)}", tools, sources
    if forbidden:
        return "FAIL", f"forbidden tool called: {', '.join(forbidden)}", tools, sources
    if case.requires_citation and sources == 0:
        return "FAIL", "required source/citation is absent", tools, sources
    return "PASS", None, tools, sources


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
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


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


def redact_report(value: object) -> object:
    """Defence in depth: reports never persist credential-shaped fields."""
    if isinstance(value, dict):
        return {
            str(key): (
                "<redacted>"
                if any(marker in str(key).lower() for marker in ("key", "token", "secret", "credential"))
                else redact_report(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_report(item) for item in value]
    return value


def write_reports(
    report_directory: Path, manifest: dict[str, object], results: list[dict[str, object]]
) -> None:
    safe_manifest = redact_report(manifest)
    safe_results = redact_report(results)
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
        port = 61889
        base_url = f"http://127.0.0.1:{port}"
        process = subprocess.Popen(
            qa_process_command(port),
            cwd=ROOT,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        results: list[dict[str, object]] = []
        started = datetime.now(UTC)
        try:
            _wait_for_health(base_url, process)
            for case in cases:
                if case.capability:
                    results.append(
                        {
                            **asdict(case),
                            "status": "SKIP",
                            "reason": f"optional capability not configured: {case.capability}",
                        }
                    )
                    continue
                try:
                    session = _json_request(base_url, "POST", "/api/sessions")
                    assert isinstance(session, dict)
                    _json_request(
                        base_url,
                        "POST",
                        f"/api/sessions/{session['session_id']}/messages",
                        {"content": case.prompt},
                    )
                    timeline = _json_request(
                        base_url, "GET", f"/api/sessions/{session['session_id']}/timeline"
                    )
                    assert isinstance(timeline, list)
                    status, reason, tools, sources = evaluate(case, timeline)
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
        write_reports(reports, manifest, results)
    print(f"QA report: {reports}")
    return 1 if any(result["status"] == "FAIL" for result in results) else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("smoke", "full"), required=True)
    parser.add_argument("--fail-fast", action="store_true")
    arguments = parser.parse_args()
    raise SystemExit(run(arguments.mode, arguments.fail_fast))
