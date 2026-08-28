from __future__ import annotations

import importlib.util
import json
import re
import sys
from io import BytesIO
from pathlib import Path

import pytest


@pytest.fixture
def qa_runner():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[2] / "scripts" / "qa" / "runner.py"
    specification = importlib.util.spec_from_file_location("orion_qa_runner", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_qa_case_loading_evaluation_and_report_generation(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    corpus = tmp_path / "cases.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "id": "tool",
                    "prompt": "calculate",
                    "category": "calculation",
                    "expected_tools": ["calculator.evaluate"],
                    "requires_citation": True,
                }
            ]
        ),
        encoding="utf-8",
    )
    case = qa_runner.load_cases(corpus)[0]
    status, reason, tools, sources = qa_runner.evaluate(
        case,
        [
            {"kind": "tool_call", "tool_name": "calculator.evaluate", "payload": {}},
            {
                "kind": "tool_result",
                "tool_name": "calculator.evaluate",
                "payload": {
                    "result": {
                        "status": "success",
                        "sources": [{"source_ref_id": "source-1"}],
                    }
                },
            },
            {
                "kind": "assistant_message",
                "payload": {
                    "content": "The result is cited.",
                    "citation_source_ref_ids": ["source-1"],
                },
            },
        ],
    )
    report = tmp_path / "report"
    qa_runner.write_reports(
        report,
        {"mode": "smoke", "api_key": "provider-secret"},
        [
            {
                "id": case.id,
                "category": case.category,
                "status": status,
                "reason": reason,
                "credential": "provider-secret",
                "citation_diagnostics": {
                    "visible_source_ref_ids": ["provider-secret-source"],
                },
            }
        ],
        secret_values=("provider-secret",),
    )

    assert (status, reason, dict(tools), sources) == ("PASS", None, {"calculator.evaluate": 1}, 1)
    assert json.loads((report / "summary.json").read_text(encoding="utf-8"))["passed"] == 1
    assert (report / "manifest.json").exists() and (report / "cases.jsonl").exists()
    assert "provider-secret" not in "".join(
        item.read_text(encoding="utf-8") for item in report.iterdir()
    )


def test_qa_rejects_malformed_cases_and_redacts_endpoint(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    corpus = tmp_path / "cases.json"
    corpus.write_text('[{"id":"one"}]', encoding="utf-8")

    with pytest.raises(ValueError):
        qa_runner.load_cases(corpus)
    assert qa_runner.sanitize_endpoint("https://user:secret@example.test:8443/v1?key=secret") == (
        "https://example.test:8443/v1"
    )


def test_qa_http_error_diagnostics_are_bounded_and_redacted(qa_runner) -> None:  # type: ignore[no-untyped-def]
    error = qa_runner.urllib.error.HTTPError(
        "http://127.0.0.1/test",
        502,
        "Bad Gateway",
        None,
        BytesIO(b'{"detail":"OpenAI-compatible model stream failed."}'),
    )
    diagnostics = qa_runner.http_error_diagnostics(error)

    assert diagnostics == {
        "http_status": 502,
        "http_reason": "Bad Gateway",
        "http_detail": "OpenAI-compatible model stream failed.",
    }

    non_json = qa_runner.urllib.error.HTTPError(
        "http://127.0.0.1/test",
        502,
        "Bad Gateway",
        None,
        BytesIO(b"untrusted arbitrary body must not be persisted"),
    )
    assert qa_runner.http_error_diagnostics(non_json) == {
        "http_status": 502,
        "http_reason": "Bad Gateway",
    }

    secret = "provider-secret"
    bounded = qa_runner.urllib.error.HTTPError(
        "http://127.0.0.1/test",
        502,
        f"{secret}-" + "r" * 600,
        None,
        BytesIO(json.dumps({"detail": f"{secret}-" + "d" * 600}).encode()),
    )
    raw = qa_runner.http_error_diagnostics(bounded)
    safe = qa_runner.redact_report(raw, (secret,))

    assert isinstance(safe, dict)
    assert len(str(raw["http_reason"])) == qa_runner.DIAGNOSTIC_TEXT_LIMIT
    assert len(str(raw["http_detail"])) == qa_runner.DIAGNOSTIC_TEXT_LIMIT
    assert len(str(safe["http_reason"])) <= qa_runner.DIAGNOSTIC_TEXT_LIMIT
    assert len(str(safe["http_detail"])) <= qa_runner.DIAGNOSTIC_TEXT_LIMIT
    assert secret not in json.dumps(safe)


def test_qa_case_selection_is_precise_and_unknown_ids_fail_cleanly(
    qa_runner, capsys, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    cases = [
        qa_runner.Case(id="first", prompt="one", category="test"),
        qa_runner.Case(id="second", prompt="two", category="test"),
    ]

    assert qa_runner.select_cases(cases, None) is cases
    assert qa_runner.select_cases(cases, "second") == [cases[1]]
    with pytest.raises(ValueError, match="QA case not found: absent"):
        qa_runner.select_cases(cases, "absent")

    assert qa_runner.run("smoke", fail_fast=False, case_id="absent") == 2
    assert "QA preflight failed: QA case not found: absent" in capsys.readouterr().err

    captured: dict[str, object] = {}
    monkeypatch.setattr(
        qa_runner,
        "active_model",
        lambda: {"base_url": "http://model.test/v1", "id": "test", "api_key": ""},
    )
    monkeypatch.setattr(qa_runner.subprocess, "Popen", lambda *args, **kwargs: object())
    monkeypatch.setattr(qa_runner, "_wait_for_health", lambda *args: None)
    monkeypatch.setattr(qa_runner, "_configured_capabilities", lambda: {})
    monkeypatch.setattr(qa_runner, "stop_qa_process", lambda process: None)
    monkeypatch.setattr(
        qa_runner.os,
        "popen",
        lambda command: type("Pipe", (), {"read": lambda self: "test-sha\n"})(),
    )
    monkeypatch.setattr(
        qa_runner,
        "_execute_case",
        lambda *args: ([{"kind": "assistant_message", "payload": {"content": "answer"}}], [[]]),
    )
    monkeypatch.setattr(qa_runner, "qa_report_directory", lambda run_id: tmp_path / run_id)

    def capture_reports(report, manifest, results, **kwargs):  # type: ignore[no-untyped-def]
        captured["manifest"] = manifest
        captured["results"] = results

    monkeypatch.setattr(qa_runner, "write_reports", capture_reports)

    assert qa_runner.run("smoke", fail_fast=False, case_id="vi-direct") == 0
    manifest = captured["manifest"]
    results = captured["results"]
    assert isinstance(manifest, dict) and manifest["selected_case_id"] == "vi-direct"
    assert isinstance(results, list)
    assert [result["id"] for result in results] == ["vi-direct"]


def test_qa_loads_expected_tool_errors(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    corpus = tmp_path / "cases.json"
    corpus.write_text(
        json.dumps(
            [
                {
                    "id": "unknown-target",
                    "prompt": "inspect",
                    "category": "linux",
                    "expected_tools": ["linux.system.inspect"],
                    "expected_tool_errors": {"linux.system.inspect": "unknown_target"},
                }
            ]
        ),
        encoding="utf-8",
    )

    case = qa_runner.load_cases(corpus)[0]

    assert case.expected_tool_errors == (("linux.system.inspect", "unknown_target"),)


def test_qa_loads_and_validates_expected_any_tools(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    corpus = tmp_path / "cases.json"
    valid = {
        "id": "document",
        "prompt": "read",
        "category": "knowledge",
        "expected_any_tools": ["knowledge.search", "knowledge.read"],
    }
    corpus.write_text(json.dumps([valid]), encoding="utf-8")

    assert qa_runner.load_cases(corpus)[0].expected_any_tools == (
        "knowledge.search",
        "knowledge.read",
    )

    for value in ([], ["knowledge.search", ""], [" "], "knowledge.search", None):
        invalid = {**valid, "expected_any_tools": value}
        corpus.write_text(json.dumps([invalid]), encoding="utf-8")
        with pytest.raises(ValueError, match="invalid alternative tool expectations"):
            qa_runner.load_cases(corpus)


def test_qa_unknown_target_case_uses_the_linux_target_schema(qa_runner) -> None:  # type: ignore[no-untyped-def]
    from orion.tool_runtime.infrastructure import infrastructure_definitions

    cases = qa_runner.load_cases(Path(__file__).parents[2] / "scripts/qa/cases/full.json")
    case = next(item for item in cases if item.id == "linux-unknown-target")
    target_match = re.search(r"target_ref ([a-z0-9._-]+)", case.prompt)
    assert target_match is not None
    target_schema = next(
        definition.input_schema["properties"]["target_ref"]
        for definition in infrastructure_definitions()
        if definition.name == "linux.system.inspect"
    )

    assert case.expected_tools == ("linux.system.inspect",)
    assert case.expected_tool_errors == (("linux.system.inspect", "unknown_target"),)
    assert re.fullmatch(str(target_schema["pattern"]), target_match.group(1))


def test_qa_evaluation_requires_final_canonical_citations(qa_runner) -> None:  # type: ignore[no-untyped-def]
    case = qa_runner.Case(id="citation", prompt="cite", category="test", requires_citation=True)
    source = {
        "kind": "tool_result",
        "payload": {"result": {"status": "success", "sources": [{"source_ref_id": "real"}]}},
    }
    assistant = {"kind": "assistant_message", "payload": {"content": "answer"}}

    assert qa_runner.evaluate(case, [source, assistant])[:2] == (
        "FAIL",
        "final assistant citation is absent",
    )
    invented = {
        "kind": "assistant_message",
        "payload": {"content": "answer", "citation_source_ref_ids": ["invented"]},
    }
    assert qa_runner.evaluate(case, [source, invented])[:2] == (
        "FAIL",
        "final assistant cites unavailable source",
    )
    cited = {
        "kind": "assistant_message",
        "payload": {"content": "answer", "citation_source_ref_ids": ["real"]},
    }
    assert qa_runner.evaluate(case, [source, cited])[:2] == ("PASS", None)


def test_qa_evaluation_accepts_alternative_tools_without_weakening_mandatory_tools(
    qa_runner,
) -> None:  # type: ignore[no-untyped-def]
    alternatives = qa_runner.Case(
        id="document",
        prompt="read",
        category="knowledge",
        expected_any_tools=("knowledge.search", "knowledge.read"),
    )
    mandatory_and_alternative = qa_runner.Case(
        id="combined",
        prompt="read and calculate",
        category="knowledge",
        expected_tools=("calculator.evaluate",),
        expected_any_tools=("knowledge.search", "knowledge.read"),
    )

    def timeline(*tool_names: str) -> list[dict[str, object]]:
        return [{"kind": "tool_call", "tool_name": name, "payload": {}} for name in tool_names]

    assert qa_runner.evaluate(alternatives, timeline("knowledge.search"))[:2] == ("PASS", None)
    assert qa_runner.evaluate(alternatives, timeline("knowledge.read"))[:2] == ("PASS", None)
    assert qa_runner.evaluate(alternatives, timeline("knowledge.list_documents"))[:2] == (
        "FAIL",
        "none of the acceptable tools were called: knowledge.search, knowledge.read",
    )
    assert qa_runner.evaluate(mandatory_and_alternative, timeline("knowledge.search"))[:2] == (
        "FAIL",
        "expected tool not called: calculator.evaluate",
    )
    assert qa_runner.evaluate(mandatory_and_alternative, timeline("calculator.evaluate"))[:2] == (
        "FAIL",
        "none of the acceptable tools were called: knowledge.search, knowledge.read",
    )
    assert qa_runner.evaluate(
        mandatory_and_alternative, timeline("calculator.evaluate", "knowledge.read")
    )[:2] == ("PASS", None)


def test_qa_citation_diagnostics_are_bounded_and_content_free(qa_runner) -> None:  # type: ignore[no-untyped-def]
    timeline = [
        {
            "kind": "tool_result",
            "payload": {
                "result": {
                    "status": "success",
                    "sources": [{"source_ref_id": f"source-{index}"} for index in range(10)],
                    "data": {"text": "tool content must not be reported"},
                }
            },
        },
        {
            "kind": "assistant_message",
            "payload": {
                "content": "model content must not be reported",
                "citation_source_ref_ids": [f"citation-{index}" for index in range(10)],
            },
        },
    ]

    diagnostics = qa_runner.citation_diagnostics(timeline)

    assert diagnostics == {
        "visible_source_count": 10,
        "visible_source_ref_ids": [
            "source-0",
            "source-1",
            "source-2",
            "source-3",
            "source-4",
            "source-5",
            "source-6",
            "source-7",
        ],
        "final_citation_count": 10,
        "final_citation_source_ref_ids": [
            "citation-0",
            "citation-1",
            "citation-2",
            "citation-3",
            "citation-4",
            "citation-5",
            "citation-6",
            "citation-7",
        ],
    }


def test_qa_evaluation_requires_the_expected_canonical_tool_error(qa_runner) -> None:  # type: ignore[no-untyped-def]
    case = qa_runner.Case(
        id="unknown-target",
        prompt="inspect",
        category="safety",
        expected_tools=("linux.system.inspect",),
        expected_tool_errors=(("linux.system.inspect", "unknown_target"),),
    )
    tool_call = {"kind": "tool_call", "tool_name": "linux.system.inspect", "payload": {}}
    wrong_error = {
        "kind": "tool_result",
        "tool_name": "linux.system.inspect",
        "payload": {"result": {"status": "error", "error": {"code": "timeout"}}},
    }
    expected_error = {
        "kind": "tool_result",
        "tool_name": "linux.system.inspect",
        "payload": {"result": {"status": "error", "error": {"code": "unknown_target"}}},
    }

    assert qa_runner.evaluate(case, [tool_call, wrong_error])[:2] == (
        "FAIL",
        "expected tool error absent: linux.system.inspect: unknown_target",
    )
    assert qa_runner.evaluate(case, [tool_call, expected_error])[:2] == ("PASS", None)


def test_qa_citation_parsing_is_nested_defensive_and_handles_multiple_sources(qa_runner) -> None:  # type: ignore[no-untyped-def]
    case = qa_runner.Case(id="citation", prompt="cite", category="test", requires_citation=True)
    malformed = {
        "kind": "tool_result",
        "payload": {"sources": [{"source_ref_id": "wrong-level"}], "result": "not-a-result"},
    }
    first = {
        "kind": "tool_result",
        "payload": {"result": {"status": "success", "sources": [{"source_ref_id": "one"}]}},
    }
    second = {
        "kind": "tool_result",
        "payload": {"result": {"status": "success", "sources": [{"source_ref_id": "two"}]}},
    }
    final = {
        "kind": "assistant_message",
        "payload": {"content": "answer", "citation_source_ref_ids": ["one", "two"]},
    }
    malformed_final = {
        "kind": "assistant_message",
        "payload": {"content": "answer", "citation_source_ref_ids": "one"},
    }

    assert qa_runner.evaluate(case, [malformed, final])[:2] == (
        "FAIL",
        "final assistant cites unavailable source",
    )
    assert qa_runner.evaluate(case, [first, second, final])[:2] == ("PASS", None)
    assert qa_runner.evaluate(case, [first, malformed_final])[:2] == (
        "FAIL",
        "final assistant citation is absent",
    )


def test_qa_missing_model_is_a_clear_preflight_result(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(qa_runner, "active_model", lambda: None)
    monkeypatch.setattr(
        qa_runner.subprocess, "Popen", lambda *args, **kwargs: pytest.fail("process")
    )
    monkeypatch.setattr(
        qa_runner.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("network")
    )

    assert qa_runner.run("smoke", fail_fast=True) == 2


def test_qa_import_and_make_targets_are_manual_only(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: pytest.fail("process"))
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: pytest.fail("network"))
    path = Path(__file__).parents[2] / "scripts" / "qa" / "runner.py"
    specification = importlib.util.spec_from_file_location("orion_qa_import_check", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    makefile = (Path(__file__).parents[2] / "Makefile").read_text(encoding="utf-8")
    ci = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert (
        "acceptance: openapi-check architecture-check operations-check test lint typecheck"
        in makefile
    )
    assert "qa-smoke:" in makefile and "qa-full:" in makefile
    assert "qa-smoke" not in ci and "qa-full" not in ci


def test_qa_process_environment_reports_and_cleanup_are_isolated(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    model = {"base_url": "https://user:secret@example.test/v1", "id": "model", "api_key": "secret"}
    environment = qa_runner.qa_environment(tmp_path, model)
    command = qa_runner.qa_process_command(61889)
    report = qa_runner.qa_report_directory("run-id")

    class Process:
        stopped = False
        killed = False

        def send_signal(self, value):  # type: ignore[no-untyped-def]
            assert value == qa_runner.signal.SIGTERM
            self.stopped = True

        def poll(self):  # type: ignore[no-untyped-def]
            return None

        def wait(self, timeout):  # type: ignore[no-untyped-def]
            assert timeout == 10

        def kill(self):  # type: ignore[no-untyped-def]
            self.killed = True

    process = Process()
    qa_runner.stop_qa_process(process)

    assert environment["ORION_DATABASE_PATH"] == str(tmp_path / "orion.db")
    assert environment["ORION_LOG_PATH"] == str(tmp_path / "orion.log")
    assert environment["ORION_MODEL_API_KEY"] == "secret"
    assert command[-2:] == ["--port", "61889"]
    assert "127.0.0.1" in command and "uvicorn" in command
    assert report == qa_runner.ROOT / "artifacts" / "qa" / "run-id"
    assert process.stopped and not process.killed


def test_qa_redacts_secret_values_and_capability_skip_is_conditional(
    qa_runner, tmp_path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    report = tmp_path / "report"
    qa_runner.write_reports(
        report,
        {"mode": "smoke", "detail": "provider-secret appeared"},
        [{"id": "safety", "category": "safety", "status": "PASS", "reason": "provider-secret"}],
        secret_values=("provider-secret",),
    )
    assert "provider-secret" not in "".join(
        item.read_text(encoding="utf-8") for item in report.iterdir()
    )

    case = qa_runner.Case(id="linux", prompt="read", category="linux", capability="linux")
    assert (
        qa_runner._optional_skip_reason(case, {"linux": ()})
        == "optional capability not configured: linux"
    )
    assert qa_runner._optional_skip_reason(case, {"linux": ("safe",)}) is None
    mutation = qa_runner.Case(
        id="edit",
        prompt="edit",
        category="linux",
        capability="linux",
        mutation=True,
        fixture_env="FIXTURE",
    )
    assert qa_runner._optional_skip_reason(mutation, {"linux": ("safe",)}) is not None
    monkeypatch.setenv("ORION_QA_ALLOW_MUTATION", "1")
    monkeypatch.setenv("ORION_QA_LINUX_TARGET_REF", "safe")
    monkeypatch.setenv("FIXTURE", "/tmp/orion-qa-safe/file.txt")
    assert qa_runner._optional_skip_reason(mutation, {"linux": ("safe",)}) is None
