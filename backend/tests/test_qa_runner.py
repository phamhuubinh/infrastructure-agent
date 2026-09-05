from __future__ import annotations

import importlib.util
import json
import re
import socket
import sys
import urllib.error
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

    cases = qa_runner.load_cases(Path(__file__).parents[2] / "scripts/qa/cases/canonical.json")
    case = next(item for item in cases if item.id == "linux-unknown-target")
    target_match = re.search(r"target_ref ([a-z0-9._-]+)", case.prompt)
    assert target_match is not None
    target_schema = next(
        definition.input_schema["properties"]["target_ref"]
        for definition in infrastructure_definitions()
        if definition.name == "linux.system.inspect"
    )

    assert case.expected_tools == ()
    assert case.expected_tool_errors == ()
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


def test_qa_safe_target_metadata_boundaries_allow_no_tool_answers(qa_runner) -> None:  # type: ignore[no-untyped-def]
    corpus = {case.id: case for case in cases(qa_runner)}

    assert corpus["linux-unknown-target"].expected_tools == ()
    assert corpus["linux-unknown-target"].expected_tool_errors == ()
    assert corpus["multi-target-comparison"].expected_tools == ()
    assert qa_runner.evaluate(corpus["linux-unknown-target"], [])[:2] == ("PASS", None)
    assert qa_runner.evaluate(corpus["multi-target-comparison"], [])[:2] == ("PASS", None)


def test_qa_local_address_requires_the_safe_fetch_rejection(qa_runner) -> None:  # type: ignore[no-untyped-def]
    case = next(item for item in cases(qa_runner) if item.id == "local-address-probe")
    fetch = {"kind": "tool_call", "tool_name": "internet.fetch", "payload": {}}
    rejected = {
        "kind": "tool_result",
        "tool_name": "internet.fetch",
        "payload": {"result": {"status": "error", "error": {"code": "unsafe_url"}}},
    }

    assert case.forbidden_tools == ()
    assert case.expected_tools == ("internet.fetch",)
    assert case.expected_tool_errors == (("internet.fetch", "unsafe_url"),)
    assert qa_runner.evaluate(case, [fetch, rejected])[:2] == ("PASS", None)


def test_qa_ssrf_metadata_requires_the_safe_fetch_rejection(qa_runner) -> None:  # type: ignore[no-untyped-def]
    case = next(item for item in cases(qa_runner) if item.id == "ssrf-metadata-probe")
    fetch = {"kind": "tool_call", "tool_name": "internet.fetch", "payload": {}}
    rejected = {
        "kind": "tool_result",
        "tool_name": "internet.fetch",
        "payload": {"result": {"status": "error", "error": {"code": "unsafe_url"}}},
    }

    assert case.manual_quality is False
    assert case.forbidden_tools == ()
    assert case.expected_tools == ("internet.fetch",)
    assert case.expected_tool_errors == (("internet.fetch", "unsafe_url"),)
    assert qa_runner.evaluate(case, [fetch, rejected])[:2] == ("PASS", None)


def test_qa_safety_explanations_accept_direct_non_mutating_answers(qa_runner) -> None:  # type: ignore[no-untyped-def]
    corpus = {case.id: case for case in cases(qa_runner)}
    direct_answer = [{"kind": "assistant_message", "payload": {"content": "Safe explanation."}}]

    assert corpus["system-prompt-probe"].expected_tools == ()
    assert corpus["system-prompt-probe"].requires_citation is False
    assert qa_runner.evaluate(corpus["system-prompt-probe"], direct_answer)[:2] == ("PASS", None)
    assert corpus["dangerous-firewall-boundary"].manual_quality is True
    assert qa_runner.evaluate(corpus["dangerous-firewall-boundary"], direct_answer)[:2] == (
        "PASS",
        None,
    )


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
    mutation_environment = qa_runner.qa_environment(tmp_path, model, mutation_case=True)
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
    assert environment["ORION_QA_CASE_MUTATION"] == "0"
    assert mutation_environment["ORION_QA_CASE_MUTATION"] == "1"
    assert command[-2:] == ["--port", "61889"]
    assert "127.0.0.1" in command and "uvicorn" in command
    assert "scripts.qa.app:create_app" in command
    assert report == qa_runner.ROOT / "artifacts" / "qa" / "run-id"
    assert process.stopped and not process.killed


def test_qa_app_enables_mutations_only_with_case_and_operator_opt_in(monkeypatch) -> None:
    path = Path(__file__).parents[2] / "scripts" / "qa" / "app.py"
    specification = importlib.util.spec_from_file_location("orion_qa_app", path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    blocked: list[frozenset[str]] = []
    application = object()

    def build_application(*, blocked_tool_operation_kinds):  # type: ignore[no-untyped-def]
        blocked.append(blocked_tool_operation_kinds)
        return application

    monkeypatch.setattr(module, "build_application", build_application)
    monkeypatch.setattr(module, "create_http_app", lambda *, application: application)
    monkeypatch.delenv("ORION_QA_CASE_MUTATION", raising=False)
    monkeypatch.delenv("ORION_QA_ALLOW_MUTATION", raising=False)

    assert module.create_app() is application
    monkeypatch.setenv("ORION_QA_CASE_MUTATION", "1")
    assert module.create_app() is application
    monkeypatch.setenv("ORION_QA_ALLOW_MUTATION", "1")
    assert module.create_app() is application

    assert blocked == [frozenset({"mutation"}), frozenset({"mutation"}), frozenset()]


def test_qa_routes_read_only_and_mutation_cases_to_separate_guarded_processes(
    qa_runner, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    environments: list[dict[str, str]] = []
    executed: list[tuple[str, str]] = []

    def popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        environments.append(kwargs["env"])
        return Process()

    def execute(base_url, case, secret):  # type: ignore[no-untyped-def]
        executed.append((base_url, case.id))
        timeline = [{"kind": "assistant_message", "payload": {"content": "done"}}]
        return timeline, [timeline]

    ports = iter((61001, 61002))
    monkeypatch.setattr(qa_runner.subprocess, "Popen", popen)
    monkeypatch.setattr(qa_runner, "_available_port", lambda: next(ports))
    monkeypatch.setattr(qa_runner, "_wait_for_health", lambda *args: None)
    monkeypatch.setattr(qa_runner, "_configured_capabilities", lambda: {})
    monkeypatch.setattr(qa_runner, "_execute_case", execute)

    results, _ = qa_runner._run_structured(
        [
            qa_runner.Case(id="read", prompt="inspect", category="qa"),
            qa_runner.Case(id="write", prompt="change", category="qa", mutation=True),
        ],
        {"base_url": "http://model", "id": "model", "api_key": "secret"},
        False,
    )

    assert [result["status"] for result in results] == ["PASS", "PASS"]
    assert [environment["ORION_QA_CASE_MUTATION"] for environment in environments] == [
        "0",
        "1",
    ]
    assert executed == [
        ("http://127.0.0.1:61001", "read"),
        ("http://127.0.0.1:61002", "write"),
    ]


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


def cases(qa_runner):  # type: ignore[no-untyped-def]
    return qa_runner.load_cases(qa_runner.ROOT / "scripts/qa/cases/canonical.json")


def stability_cases(qa_runner):  # type: ignore[no-untyped-def]
    return qa_runner.load_cases(qa_runner.ROOT / "scripts/qa/cases/stability.json")


def test_canonical_source_selection_and_metadata(qa_runner) -> None:  # type: ignore[no-untyped-def]
    corpus = cases(qa_runner)
    smoke = qa_runner.select_tier(corpus, "smoke")
    full = qa_runner.select_tier(corpus, "full")
    assert len(corpus) == 88 and 84 <= len(corpus) <= 92
    assert 0 < len(smoke) < len(full) == len(corpus)
    assert {case.id for case in smoke} < {case.id for case in full}
    assert len({case.id for case in corpus}) == 88
    assert all(case.category and case.scenario and case.tiers for case in corpus)
    assert not (qa_runner.ROOT / "scripts/qa/cases/full.json").exists()
    assert not (qa_runner.ROOT / "scripts/qa/cases/smoke.json").exists()
    assert (qa_runner.ROOT / "scripts/qa/cases/stability.json").is_file()
    assert not list((qa_runner.ROOT / "scripts/qa/cases/historical").glob("*.txt"))


def test_invariants_multiturn_and_capability_boundaries_are_explicit(qa_runner) -> None:  # type: ignore[no-untyped-def]
    corpus = {case.id: case for case in cases(qa_runner)}
    required = {
        "vi-direct",
        "en-direct",
        "identity",
        "writing",
        "continuity",
        "continuity-vietnamese",
        "calculation",
        "calculation-percent-vietnamese",
        "internet-search-citation",
        "url-fetch-citation",
        "session-document",
        "project-shared-document",
        "tool-error-recovery",
        "project-isolation",
        "prompt-injection-document",
        "secret-hidden-reasoning-safety",
        "linux-system-inspection",
        "linux-unknown-target",
        "linux-read",
        "linux-document-read",
        "linux-document-edit",
        "linux-docx-edit",
        "linux-xlsx-edit",
        "grafana-read",
        "zabbix-read",
    }
    multiturn = {
        "continuity",
        "continuity-vietnamese",
        "correction-not-cpu-ram",
        "referent-follow-up-ram",
        "operator-action-follow-up",
        "operational-workflow-follow-up",
    }
    assert required <= corpus.keys()
    assert all(corpus[item].scenario == "multi_turn" and corpus[item].turns for item in multiturn)
    assert corpus["linux-unknown-target"].expected_tool_errors == ()
    assert corpus["multi-target-comparison"].expected_tools == ()
    assert corpus["local-address-probe"].expected_tool_errors == (("internet.fetch", "unsafe_url"),)
    assert corpus["unsupported-container-boundary"].manual_quality
    assert (
        corpus["grafana-read"].capability == "grafana"
        and corpus["zabbix-read"].capability == "zabbix"
    )
    operator_follow_up = corpus["operator-action-follow-up"]
    assert "linux.service.status" in operator_follow_up.turns[0]
    assert "Do not restart" in operator_follow_up.turns[0]
    assert set(operator_follow_up.forbidden_tools) == {
        "linux.service.restart",
        "linux.package.status",
        "linux.package.install",
        "linux.file.edit",
    }


def test_broad_synthesis_cases_bound_read_only_evidence_collection(qa_runner) -> None:  # type: ignore[no-untyped-def]
    from orion.tool_runtime.infrastructure import infrastructure_definitions

    corpus = {case.id: case for case in cases(qa_runner)}
    infrastructure_tools = {definition.name for definition in infrastructure_definitions()}
    enterprise = corpus["enterprise-readiness"]
    weekly = corpus["weekly-synthesis"]

    assert enterprise.capability == "linux"
    assert enterprise.expected_tools == ("linux.system.inspect",)
    assert "{qa_target_ref}" in enterprise.prompt
    assert "stop calling tools" in enterprise.prompt
    assert set(enterprise.forbidden_tools) == infrastructure_tools - {"linux.system.inspect"}

    weekly_tools = {"linux.system.inspect", "grafana.alert.list", "zabbix.event.list"}
    assert set(weekly.expected_any_tools) == weekly_tools
    assert "{qa_target_ref}" in weekly.prompt
    assert "at most one successful observation per family" in weekly.prompt
    assert "without retrying it" in weekly.prompt
    assert set(weekly.forbidden_tools) == infrastructure_tools - weekly_tools
    assert not enterprise.mutation and not weekly.mutation


def test_original_broad_prompts_remain_in_read_only_stability_suite(qa_runner) -> None:  # type: ignore[no-untyped-def]
    from orion.tool_runtime.infrastructure import infrastructure_definitions

    stability = {case.id: case for case in stability_cases(qa_runner)}
    assert set(stability) == {"enterprise-readiness", "weekly-synthesis"}
    assert stability["enterprise-readiness"].prompt == (
        "Give a bounded enterprise-readiness assessment based only on evidence you can obtain, "
        "and label assumptions."
    )
    assert stability["weekly-synthesis"].prompt == (
        "Prepare a weekly infrastructure synthesis only from available Linux, Grafana, or "
        "Zabbix evidence; identify gaps."
    )
    mutating_tools = {
        definition.name
        for definition in infrastructure_definitions()
        if definition.operation_kind == "mutation"
    }
    assert mutating_tools
    assert all(case.tiers == ("stability",) for case in stability.values())
    assert all(not case.mutation for case in stability.values())
    assert all(set(case.forbidden_tools) == mutating_tools for case in stability.values())


def test_parser_validates_tiers_and_turns(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps([{"id": "bad", "category": "x", "prompt": "x", "tiers": ["nightly"]}])
    )
    with pytest.raises(ValueError, match="invalid tiers"):
        qa_runner.load_cases(path)
    path.write_text(
        json.dumps([{"id": "stable", "category": "x", "prompt": "x", "tiers": ["stability"]}])
    )
    assert qa_runner.load_cases(path)[0].tiers == ("stability",)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "mixed",
                    "category": "x",
                    "prompt": "x",
                    "tiers": ["full", "stability"],
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="invalid tiers"):
        qa_runner.load_cases(path)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "category": "x",
                    "prompt": "x",
                    "tiers": ["full"],
                    "scenario": "multi_turn",
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="requires explicit turns"):
        qa_runner.load_cases(path)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "bad",
                    "category": "x",
                    "prompt": "x",
                    "tiers": ["full"],
                    "manual_quality": "yes",
                }
            ]
        )
    )
    with pytest.raises(ValueError, match="invalid manual_quality"):
        qa_runner.load_cases(path)


def test_multiturn_reuses_one_session_but_cases_are_isolated(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    sessions: list[str] = []
    sent: list[tuple[str, str]] = []

    def create(_):  # type: ignore[no-untyped-def]
        session = f"s{len(sessions) + 1}"
        sessions.append(session)
        return {"session_id": session}

    monkeypatch.setattr(qa_runner, "_create_session", create)
    monkeypatch.setattr(qa_runner, "_send", lambda _, sid, prompt: sent.append((sid, prompt)))
    monkeypatch.setattr(
        qa_runner,
        "_timeline",
        lambda *_: [
            {"kind": "assistant_message", "payload": {"content": "ORION_QA_CONTINUITY_7391"}}
        ],
    )
    corpus = {case.id: case for case in cases(qa_runner)}
    qa_runner._execute_case("http://qa", corpus["continuity"], "secret")
    qa_runner._execute_case("http://qa", corpus["vi-direct"], "secret")
    qa_runner._execute_case("http://qa", corpus["en-direct"], "secret")
    assert [sid for sid, _ in sent] == ["s1", "s1", "s2", "s3"]
    assert [prompt for _, prompt in sent[:2]] == [
        corpus["continuity"].prompt,
        corpus["continuity"].turns[0],
    ]


class Process:
    def poll(self):
        return None

    def send_signal(self, value):
        return None

    def wait(self, timeout):
        return None


def _runner_mocks(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(qa_runner.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(qa_runner, "_wait_for_health", lambda *args: None)
    monkeypatch.setattr(qa_runner, "_configured_capabilities", lambda: {})


def test_manual_quality_and_timeout_are_contained_and_journaled(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    manual = qa_runner.Case(id="manual", prompt="one", category="quality", manual_quality=True)
    timed = qa_runner.Case(id="timed", prompt="two", category="quality")
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, ("provider-secret",))
    checkpoint.start()
    calls: list[str] = []

    def execute(_, case, __):  # type: ignore[no-untyped-def]
        calls.append(case.id)
        if case.id == "timed":
            raise qa_runner.QARequestTimeout()
        return (
            [{"kind": "assistant_message", "payload": {"content": "provider-secret " + "x" * 600}}],
            [[]],
        )

    monkeypatch.setattr(qa_runner, "_execute_case", execute)
    results, _ = qa_runner._run_structured(
        [manual, timed],
        {"base_url": "http://model", "id": "model", "api_key": "provider-secret"},
        False,
        checkpoint,
    )
    assert calls == ["manual", "timed"]
    assert [item["status"] for item in results] == ["MANUAL_REVIEW", "FAIL"]
    assert len(str(results[0]["manual_review_answer"])) == qa_runner.MANUAL_REVIEW_ANSWER_LIMIT
    persisted = (tmp_path / "cases.partial.jsonl").read_text()
    assert "provider-secret" not in persisted and "tool_result" not in persisted
    assert [json.loads(line)["id"] for line in persisted.splitlines()] == ["manual", "timed"]


def test_project_isolation_fixture_names_do_not_contain_document_markers(qa_runner) -> None:  # type: ignore[no-untyped-def]
    expected = "ORION_QA_PROJECT_A_7711"
    forbidden = "ORION_QA_PROJECT_B_8822"

    names = [qa_runner._project_isolation_fixture_name(index) for index in range(2)]

    assert names == ["QA isolated project 1", "QA isolated project 2"]
    assert all(marker not in name for marker in (expected, forbidden) for name in names)


def test_safe_exception_diagnostics_are_bounded_redacted_and_checkpointed(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    secret = "provider-secret"
    cases = [
        qa_runner.Case(id="marker", prompt="one", category="qa"),
        qa_runner.Case(id="secret", prompt="two", category="qa"),
        qa_runner.Case(id="long", prompt="three", category="qa"),
        qa_runner.Case(id="timeout", prompt="four", category="qa"),
    ]
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, (secret,))
    checkpoint.start()

    def execute(_, case, __):  # type: ignore[no-untyped-def]
        if case.id == "marker":
            raise qa_runner.ScenarioFailure(
                "final assistant response omitted the required QA marker"
            )
        if case.id == "secret":
            raise qa_runner.ScenarioFailure(f"configured API key is {secret}")
        if case.id == "long":
            raise qa_runner.ScenarioFailure("x" * (qa_runner.DIAGNOSTIC_TEXT_LIMIT + 1))
        raise qa_runner.QARequestTimeout(f"QA request timed out for {secret}")

    monkeypatch.setattr(qa_runner, "_execute_case", execute)
    results, _ = qa_runner._run_structured(
        cases,
        {"base_url": "http://model", "id": "model", "api_key": secret},
        False,
        checkpoint,
    )
    qa_runner.write_reports(tmp_path, {"mode": "full"}, results, secret_values=(secret,))

    assert [item["detail"] for item in results] == [
        "ScenarioFailure",
        "ScenarioFailure",
        "ScenarioFailure",
        "QARequestTimeout",
    ]
    assert [item["reason"] for item in results] == ["HTTP/runtime failure"] * 4
    assert results[0]["message"] == "final assistant response omitted the required QA marker"
    assert results[1]["message"] == "configured API key is <redacted>"
    assert results[2]["message"] == "x" * qa_runner.DIAGNOSTIC_TEXT_LIMIT
    assert results[3]["message"] == "QA request timed out for <redacted>"
    partial = (tmp_path / "cases.partial.jsonl").read_text(encoding="utf-8")
    final = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert partial == final
    assert secret not in partial and "tool_result" not in partial
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["failed"] == 4


def test_scenario_failure_trace_is_safe_bounded_and_checkpointed(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    secret = "provider-secret"
    timeline = [
        *[
            {
                "kind": "tool_call",
                "tool_name": "fake.prefix",
                "call_id": f"prefix-{index}",
                "payload": {"arguments": {"value": index}},
            }
            for index in range(4)
        ],
        {
            "kind": "tool_call",
            "tool_name": "orion.tools.expand",
            "call_id": "expand",
            "payload": {
                "arguments": {
                    "tool_names": ["knowledge.read"],
                    "document_id": "raw-argument-value",
                }
            },
        },
        {
            "kind": "tool_result",
            "tool_name": "orion.tools.expand",
            "call_id": "expand",
            "payload": {
                "result": {
                    "status": "success",
                    "data": {"raw": f"raw-tool-result-data-{secret}"},
                    "sources": [{"source_ref_id": f"source-{secret}"}],
                }
            },
        },
        {
            "kind": "assistant_message",
            "payload": {
                "content": f"I need a document id. {secret} " + "x" * 300,
                "citation_source_ref_ids": [f"source-{secret}"],
            },
        },
        {
            "kind": "assistant_message",
            "payload": {"content": "<think>hidden reasoning</think>"},
        },
        *[
            {
                "kind": "tool_call",
                "tool_name": "fake.tool",
                "call_id": f"extra-{index}",
                "payload": {"arguments": {"value": f"raw-{index}"}},
            }
            for index in range(qa_runner.FAILURE_TRACE_EVENT_LIMIT - 4)
        ],
    ]
    case = qa_runner.Case(
        id="trace", prompt="one", category="qa", expected_marker="REQUIRED_MARKER"
    )
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, (secret,))
    checkpoint.start()
    monkeypatch.setattr(qa_runner, "_create_session", lambda _: {"session_id": "session"})
    monkeypatch.setattr(qa_runner, "_send", lambda *args: None)
    monkeypatch.setattr(qa_runner, "_timeline", lambda *args: timeline)

    results, _ = qa_runner._run_structured(
        [case],
        {"base_url": "http://model", "id": "model", "api_key": secret},
        False,
        checkpoint,
    )
    qa_runner.write_reports(tmp_path, {"mode": "full"}, results, secret_values=(secret,))

    assert results[0]["message"] == "final assistant response omitted the required QA marker"
    trace = results[0]["failure_trace"]
    assert isinstance(trace, list) and len(trace) == qa_runner.FAILURE_TRACE_EVENT_LIMIT
    assert trace[0] == {
        "kind": "tool_call",
        "tool_name": "orion.tools.expand",
        "call_id": "expand",
        "argument_names": ["document_id", "tool_names"],
    }
    assert trace[1] == {
        "kind": "tool_result",
        "tool_name": "orion.tools.expand",
        "call_id": "expand",
        "status": "success",
        "error_code": "",
        "model_recovery_required": False,
        "source_count": 1,
        "source_ref_ids": ["source-<redacted>"],
    }
    assert trace[2]["kind"] == "assistant_message"
    assert str(trace[2]["content_excerpt"]).startswith("I need a document id. <redacted>")
    assert len(str(trace[2]["content_excerpt"])) == qa_runner.FAILURE_TRACE_ASSISTANT_TEXT_LIMIT
    assert trace[2]["citation_count"] == 1
    assert trace[2]["citation_source_ref_ids"] == ["source-<redacted>"]
    assert trace[3]["content_excerpt"] == "<hidden reasoning omitted>"
    partial = (tmp_path / "cases.partial.jsonl").read_text(encoding="utf-8")
    final = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert partial == final
    assert all(
        value not in partial
        for value in (secret, "raw-tool-result-data", "raw-argument-value", "<think>")
    )
    assert json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))["failed"] == 1


def test_http_error_after_message_send_persists_failure_trace(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    timeline = [
        {
            "kind": "tool_call",
            "tool_name": "knowledge.read",
            "call_id": "read",
            "payload": {"arguments": {"document_id": "raw-document-id"}},
        },
        {
            "kind": "tool_result",
            "tool_name": "knowledge.read",
            "call_id": "read",
            "payload": {
                "result": {
                    "status": "success",
                    "sources": [{"source_ref_id": "source-1"}],
                }
            },
        },
    ]

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        if method == "POST" and path == "/api/sessions":
            return {"session_id": "session"}
        if method == "POST" and path == "/api/sessions/session/messages":
            raise urllib.error.HTTPError(
                "http://qa/api/sessions/session/messages",
                502,
                "Bad Gateway",
                None,
                BytesIO(b'{"detail":"Assistant cited an unavailable source."}'),
            )
        if method == "GET" and path == "/api/sessions/session/timeline":
            return timeline
        pytest.fail(f"unexpected request: {method} {path}")

    monkeypatch.setattr(qa_runner, "_json_request", request)
    case = qa_runner.Case(id="http-trace", prompt="read", category="qa")

    results, _ = qa_runner._run_structured(
        [case],
        {"base_url": "http://model", "id": "model", "api_key": "secret"},
        False,
    )

    assert results[0]["status"] == "FAIL"
    assert results[0]["http_status"] == 502
    assert results[0]["http_detail"] == "Assistant cited an unavailable source."
    trace = results[0]["failure_trace"]
    assert trace[0]["argument_names"] == ["document_id"]
    assert trace[1]["source_ref_ids"] == ["source-1"]
    assert "raw-document-id" not in json.dumps(results[0])


def test_timeout_after_message_send_persists_failure_trace(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    timeline = [
        {
            "kind": "tool_result",
            "tool_name": "linux.system.inspect",
            "call_id": "inspect",
            "payload": {
                "result": {
                    "status": "error",
                    "error": {"code": "timeout", "model_recovery_required": False},
                    "sources": [],
                }
            },
        }
    ]

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        if method == "POST" and path == "/api/sessions":
            return {"session_id": "session"}
        if method == "POST" and path == "/api/sessions/session/messages":
            raise qa_runner.QARequestTimeout()
        if method == "GET" and path == "/api/sessions/session/timeline":
            return timeline
        pytest.fail(f"unexpected request: {method} {path}")

    monkeypatch.setattr(qa_runner, "_json_request", request)
    case = qa_runner.Case(id="timeout-trace", prompt="inspect", category="qa")

    results, _ = qa_runner._run_structured(
        [case],
        {"base_url": "http://model", "id": "model", "api_key": "secret"},
        False,
    )

    assert results[0]["detail"] == "QARequestTimeout"
    assert results[0]["failure_trace"] == [
        {
            "kind": "tool_result",
            "tool_name": "linux.system.inspect",
            "call_id": "inspect",
            "status": "error",
            "error_code": "timeout",
            "model_recovery_required": False,
            "source_count": 0,
            "source_ref_ids": [],
        }
    ]


def test_citation_http_error_persists_redacted_validation_notice(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    secret = "provider-secret"
    timeline = [
        {"kind": "user_message", "payload": {"content": f"request {secret}"}},
        {
            "kind": "runtime_notice",
            "payload": {
                "stage": "citation_validation",
                "status": "failed",
                "error_kind": "unavailable_source",
                "citation_correction_attempted": True,
                "unreported_source_ref_id": secret,
            },
        },
    ]

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        if method == "POST" and path == "/api/sessions":
            return {"session_id": "session"}
        if method == "POST" and path == "/api/sessions/session/messages":
            raise urllib.error.HTTPError(
                "http://qa/api/sessions/session/messages",
                502,
                "Bad Gateway",
                None,
                BytesIO(b'{"detail":"Assistant cited an unavailable source."}'),
            )
        if method == "GET" and path == "/api/sessions/session/timeline":
            return timeline
        pytest.fail(f"unexpected request: {method} {path}")

    monkeypatch.setattr(qa_runner, "_json_request", request)
    case = next(item for item in cases(qa_runner) if item.id == "system-prompt-probe")
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, (secret,))
    checkpoint.start()

    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": secret}, False, checkpoint
    )
    qa_runner.write_reports(tmp_path, {"mode": "full"}, results, secret_values=(secret,))

    assert results[0]["http_detail"] == "Assistant cited an unavailable source."
    assert results[0]["failure_trace"] == [
        {
            "kind": "runtime_notice",
            "stage": "citation_validation",
            "status": "failed",
            "error_kind": "unavailable_source",
            "citation_correction_attempted": True,
        }
    ]
    cases_json = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert "citation_validation" in cases_json
    assert secret not in cases_json


@pytest.mark.parametrize(
    "case_id",
    ("ssrf-metadata-probe", "overnight-health", "follow-up-after-action"),
)
def test_model_timeout_http_error_persists_redacted_runtime_notice(
    qa_runner, monkeypatch, tmp_path, case_id
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    secret = "provider-secret"
    timeline = [
        {"kind": "user_message", "payload": {"content": f"request {secret}"}},
        {
            "kind": "runtime_notice",
            "payload": {
                "stage": "model",
                "status": "failed",
                "error_kind": "timeout",
                "unreported_detail": secret,
            },
        },
    ]

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        if method == "POST" and path == "/api/sessions":
            return {"session_id": "session"}
        if method == "POST" and path == "/api/sessions/session/messages":
            raise urllib.error.HTTPError(
                "http://qa/api/sessions/session/messages",
                502,
                "Bad Gateway",
                None,
                BytesIO(b'{"detail":"OpenAI-compatible model stream timed out."}'),
            )
        if method == "GET" and path == "/api/sessions/session/timeline":
            return timeline
        pytest.fail(f"unexpected request: {method} {path}")

    monkeypatch.setattr(qa_runner, "_json_request", request)
    case = next(item for item in cases(qa_runner) if item.id == case_id)
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, (secret,))
    checkpoint.start()

    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": secret}, False, checkpoint
    )
    qa_runner.write_reports(tmp_path, {"mode": "full"}, results, secret_values=(secret,))

    assert results[0]["http_detail"] == "OpenAI-compatible model stream timed out."
    assert results[0]["failure_trace"] == [
        {"kind": "runtime_notice", "stage": "model", "status": "failed", "error_kind": "timeout"}
    ]
    cases_json = (tmp_path / "cases.jsonl").read_text(encoding="utf-8")
    assert "runtime_notice" in cases_json
    assert secret not in cases_json


def test_failure_trace_prioritizes_latest_observed_timeline(qa_runner) -> None:  # type: ignore[no-untyped-def]
    earlier = [
        {
            "kind": "assistant_message",
            "payload": {"content": f"earlier-{index}"},
        }
        for index in range(qa_runner.FAILURE_TRACE_EVENT_LIMIT)
    ]
    latest = [
        {
            "kind": "assistant_message",
            "payload": {"content": "latest-failing-conversation"},
        }
    ]

    trace = qa_runner.failure_trace([earlier, latest], ())

    assert [item["content_excerpt"] for item in trace] == ["latest-failing-conversation"]


def test_failure_trace_preserves_implicit_exposure_recovery_code(qa_runner) -> None:  # type: ignore[no-untyped-def]
    trace = qa_runner.failure_trace(
        [
            [
                {
                    "kind": "tool_result",
                    "tool_name": "fake.alpha",
                    "call_id": "hidden",
                    "payload": {
                        "result": {
                            "status": "error",
                            "error": {
                                "code": "exposed_for_retry",
                                "model_recovery_required": True,
                            },
                            "sources": [],
                        },
                    },
                }
            ]
        ],
        (),
    )

    assert trace == [
        {
            "kind": "tool_result",
            "tool_name": "fake.alpha",
            "call_id": "hidden",
            "status": "error",
            "error_code": "exposed_for_retry",
            "model_recovery_required": True,
            "source_count": 0,
            "source_ref_ids": [],
        }
    ]


def test_successful_cases_do_not_gain_failure_trace(qa_runner, monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    case = qa_runner.Case(id="success", prompt="one", category="qa")
    timeline = [{"kind": "assistant_message", "payload": {"content": "Done."}}]
    monkeypatch.setattr(qa_runner, "_execute_case", lambda *args: (timeline, [timeline]))

    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": "secret"}, False
    )

    assert results[0]["status"] == "PASS"
    assert "failure_trace" not in results[0]


def test_stability_cases_keep_separate_runtime_phase(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    case = qa_runner.Case(
        id="stability",
        prompt="one",
        category="qa",
        tiers=("stability",),
    )
    timeline = [{"kind": "assistant_message", "payload": {"content": "Done."}}]
    monkeypatch.setattr(qa_runner, "_execute_case", lambda *args: (timeline, [timeline]))

    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": "secret"}, False
    )

    assert results[0]["phase"] == "stability"
    assert results[0]["tier"] == "stability"
    assert results[0]["stability_diagnostic"]["events"][0] == {
        "kind": "assistant_message",
        "content": "Done.",
        "content_truncated": False,
        "content_characters": 5,
        "hidden_reasoning_omitted": False,
        "has_tool_calls": False,
        "terminal_response": False,
    }


@pytest.mark.parametrize("timed_out", [False, True])
def test_synthesis_transcript_is_checkpointed_on_success_and_timeout(
    qa_runner, monkeypatch, tmp_path, timed_out
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    secret = "configured-secret"
    case = qa_runner.Case(
        id="weekly-synthesis", prompt="original", category="workflow", manual_quality=True
    )
    timeline = [
        {
            "kind": "tool_result",
            "tool_name": "zabbix.event.list",
            "call_id": "events",
            "payload": {
                "result": {
                    "status": "success",
                    "data": {"clock": "1776067292", "password": "never-persist"},
                    "sources": [
                        {"source_ref_id": "old-event", "retrieved_at": "2026-09-05T00:00:00Z"}
                    ],
                }
            },
        },
        {
            "kind": "assistant_message",
            "payload": {"content": secret + " answer " * 100, "metrics": {"response_time_ms": 123}},
        },
    ]

    def execute(*args):  # type: ignore[no-untyped-def]
        if timed_out:
            error = qa_runner.QARequestTimeout("timed out")
            error.observed_timelines = [timeline]
            raise error
        return timeline, [timeline]

    monkeypatch.setattr(qa_runner, "_execute_case", execute)
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, (secret,))
    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": secret}, False, checkpoint
    )
    persisted = (tmp_path / "cases.partial.jsonl").read_text()
    assert secret not in persisted and "never-persist" not in persisted
    result = json.loads(persisted)
    assert result["status"] == ("FAIL" if timed_out else "MANUAL_REVIEW")
    events = result["stability_diagnostic"]["events"]
    assert events[0]["data"]["clock"] == "1776067292"
    assert events[0]["sources"][0]["source_ref_id"] == "old-event"
    assert events[1]["content"].endswith(" answer " * 100)
    assert events[1]["content_truncated"] is False
    assert events[1]["terminal_response"] is True
    if not timed_out:
        assert results[0]["manual_review_answer_truncated"] is True


def test_diagnostic_marks_text_event_bounds_and_omitted_reasoning(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(qa_runner, "STABILITY_DIAGNOSTIC_EVENT_LIMIT", 2)
    monkeypatch.setattr(qa_runner, "STABILITY_DIAGNOSTIC_TEXT_LIMIT", 8)
    diagnostic = qa_runner.stability_diagnostic_transcript(
        [
            [
                {"kind": "assistant_message", "payload": {"content": "long-answer"}},
                {
                    "kind": "assistant_message",
                    "payload": {"content": "<think>hidden</think>answer"},
                },
                {"kind": "assistant_message", "payload": {"content": "not captured"}},
            ]
        ],
        (),
    )
    assert diagnostic["events_truncated"] is True
    assert diagnostic["timeline_events"] == 3
    assert diagnostic["events"][0]["content_truncated"] is True
    assert diagnostic["events"][0]["content_characters"] == 11
    assert diagnostic["events"][1]["hidden_reasoning_omitted"] is True
    assert "hidden</think>" not in json.dumps(diagnostic)


def test_stability_diagnostic_keeps_full_redacted_evidence_and_marks_bounds(
    qa_runner, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ORION_QA_DIAGNOSTIC_SECRET", "environment-secret")
    long_answer = "provider-secret " + "x" * 600
    oversized = "y" * (qa_runner.STABILITY_DIAGNOSTIC_VALUE_LIMIT + 1)
    diagnostic = qa_runner.stability_diagnostic_transcript(
        [
            [
                {
                    "kind": "assistant_message",
                    "payload": {"content": long_answer},
                },
                {
                    "kind": "tool_result",
                    "tool_name": "zabbix.event.list",
                    "call_id": "call-1",
                    "payload": {
                        "result": {
                            "status": "success",
                            "data": {
                                "events": [
                                    {
                                        "clock": "1776067292",
                                        "note": "environment-secret",
                                    }
                                ]
                            },
                            "sources": [{"source_ref_id": "source-1"}],
                            "error": None,
                        }
                    },
                },
                {
                    "kind": "tool_result",
                    "tool_name": "test.large",
                    "call_id": "call-2",
                    "payload": {
                        "result": {
                            "status": "success",
                            "data": {"value": oversized},
                            "sources": [],
                            "error": None,
                        }
                    },
                },
            ]
        ],
        ("provider-secret",),
    )

    assert diagnostic is not None
    answer = diagnostic["events"][0]
    assert answer["content"] == "<redacted> " + "x" * 600
    assert answer["content_truncated"] is False
    evidence = diagnostic["events"][1]
    assert evidence["data"]["events"][0] == {
        "clock": "1776067292",
        "note": "[REDACTED]",
    }
    assert evidence["sources"] == [{"source_ref_id": "source-1"}]
    assert evidence["data_truncated"] is False
    assert diagnostic["events"][2]["data_truncated"] is True
    persisted = json.dumps(diagnostic)
    assert "provider-secret" not in persisted
    assert "environment-secret" not in persisted


@pytest.mark.parametrize(
    "error",
    (
        AssertionError("untrusted assertion text"),
        urllib.error.URLError("untrusted URL error text"),
        json.JSONDecodeError("untrusted JSON error text", "document", 0),
    ),
)
def test_existing_untrusted_exception_categories_keep_prior_report_shape(
    qa_runner, monkeypatch, tmp_path, error
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    case = qa_runner.Case(id="failure", prompt="one", category="qa")
    monkeypatch.setattr(
        qa_runner,
        "_execute_case",
        lambda *_: (_ for _ in ()).throw(error),
    )

    results, _ = qa_runner._run_structured(
        [case], {"base_url": "http://model", "id": "model", "api_key": "secret"}, False
    )

    assert results == [
        {
            "phase": "canonical",
            "tier": "full",
            "id": "failure",
            "category": "qa",
            "manual_quality": False,
            "status": "FAIL",
            "reason": "HTTP/runtime failure",
            "detail": type(error).__name__,
        }
    ]


def test_mapping_accounts_for_386_rows_and_references_canonical_ids(qa_runner) -> None:  # type: ignore[no-untyped-def]
    mapping = (qa_runner.ROOT / "docs/qa/HISTORICAL_CORPUS_MIGRATION.md").read_text()
    expected = {
        "historical-default.txt": 193,
        "cauhoi_kiemtra_v2.txt": 66,
        "cauhoi_phanb.txt": 28,
        "cauhoi_v4_adversarial.txt": 61,
        "cauhoi_v5_workflow.txt": 38,
    }
    approved = {
        "retained",
        "rewritten",
        "merged_duplicate",
        "converted_multi_turn",
        "manual_quality",
        "removed_obsolete",
        "removed_low_value",
    }
    seen: set[tuple[str, int]] = set()
    counts = {name: 0 for name in expected}
    ids = {case.id for case in cases(qa_runner)}
    for line in mapping.splitlines():
        if not line.startswith("| ") or ".txt |" not in line:
            continue
        source, index, excerpt, disposition, targets, reason = [
            part.strip() for part in line.strip("|").split("|")
        ]
        pair = (source, int(index))
        assert pair not in seen and excerpt and len(excerpt) <= 128 and reason
        assert disposition in approved
        seen.add(pair)
        counts[source] += 1
        if targets != "—":
            assert set(targets.split(",")) <= ids
    assert len(seen) == 386 and counts == expected


def test_reports_and_ci_policy(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    qa_runner.write_reports(
        tmp_path,
        {"mode": "full"},
        [
            {
                "phase": "canonical",
                "tier": "full",
                "id": "manual",
                "category": "quality",
                "manual_quality": True,
                "status": "MANUAL_REVIEW",
                "reason": None,
            }
        ],
    )
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["canonical"]["manual_review"] == 1 and summary["manual_quality_cases"] == 1
    assert summary["stability"]["total"] == 0
    ci = (qa_runner.ROOT / ".github/workflows/ci.yml").read_text()
    assert "qa-smoke" not in ci and "qa-full" not in ci


def test_stability_results_are_reported_separately(qa_runner, tmp_path) -> None:  # type: ignore[no-untyped-def]
    qa_runner.write_reports(
        tmp_path,
        {"mode": "stability"},
        [
            {
                "phase": "stability",
                "tier": "stability",
                "id": "enterprise-readiness",
                "category": "workflow",
                "manual_quality": True,
                "status": "FAIL",
                "reason": "HTTP/runtime failure",
            }
        ],
    )
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["canonical"]["total"] == 0
    assert summary["stability"]["failed"] == 1
    assert "Stability: total 1" in (tmp_path / "summary.md").read_text()


@pytest.mark.parametrize(
    "error",
    (
        TimeoutError(),
        socket.timeout(),  # noqa: UP041 - exercise the socket alias.
        urllib.error.URLError(TimeoutError()),
    ),
)
def test_107_timeout_normalization_remains(qa_runner, monkeypatch, error) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        qa_runner.urllib.request,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(error),
    )
    with pytest.raises(qa_runner.QARequestTimeout):
        qa_runner._json_request("http://qa", "GET", "/api/health")


def test_qa_multipart_upload_includes_file_name_bytes_and_content_type(
    qa_runner, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *args):  # type: ignore[no-untyped-def]
            return None

        def read(self) -> bytes:
            return b'{"status":"ready"}'

    def urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(qa_runner.urllib.request, "urlopen", urlopen)

    assert qa_runner._multipart_file_request(
        "http://qa",
        "POST",
        "/api/sessions/session/attachments",
        filename="sentinel.txt",
        content=b"document bytes\x00",
        media_type="text/plain",
    ) == {"status": "ready"}

    request = captured["request"]
    assert request.full_url == "http://qa/api/sessions/session/attachments"
    content_type = request.get_header("Content-type")
    assert isinstance(content_type, str)
    boundary = content_type.removeprefix("multipart/form-data; boundary=")
    assert boundary and boundary != content_type
    assert request.data == b"".join(
        (
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="file"; filename="sentinel.txt"\r\n',
            b"Content-Type: text/plain\r\n\r\n",
            b"document bytes\x00",
            f"\r\n--{boundary}--\r\n".encode(),
        )
    )


def test_qa_attachments_use_the_same_multipart_contract_for_sessions_and_projects(
    qa_runner, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    uploads: list[tuple[str, str, str, str, bytes, str]] = []
    statuses: list[str] = []

    def upload(base_url, method, path, *, filename, content, media_type):  # type: ignore[no-untyped-def]
        uploads.append((base_url, method, path, filename, content, media_type))
        document_id = "session-document" if "/sessions/" in path else "project-document"
        return {"document": {"document_id": document_id}}

    def request(_, method, path, body=None):  # type: ignore[no-untyped-def]
        assert method == "GET" and body is None
        statuses.append(path)
        return {"status": "ready"}

    monkeypatch.setattr(qa_runner, "_multipart_file_request", upload)
    monkeypatch.setattr(qa_runner, "_json_request", request)

    session_document = qa_runner._attach_and_wait(
        "http://qa", "/api/sessions/session/attachments", "session fact"
    )
    project_document = qa_runner._attach_and_wait(
        "http://qa", "/api/projects/project/documents", "project fact"
    )

    assert session_document == {"document_id": "session-document"}
    assert project_document == {"document_id": "project-document"}
    assert uploads == [
        (
            "http://qa",
            "POST",
            "/api/sessions/session/attachments",
            "orion-qa-sentinel.txt",
            b"session fact",
            "text/plain",
        ),
        (
            "http://qa",
            "POST",
            "/api/projects/project/documents",
            "orion-qa-sentinel.txt",
            b"project fact",
            "text/plain",
        ),
    ]
    assert statuses == [
        "/api/sessions/session/documents/session-document",
        "/api/projects/project/documents/project-document",
    ]


def test_107_timeout_override_and_health_wait_are_contained(qa_runner, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    captured: list[float] = []

    class WaitingProcess:
        def poll(self):  # type: ignore[no-untyped-def]
            return None

    def urlopen(request, timeout):  # type: ignore[no-untyped-def]
        captured.append(timeout)
        raise TimeoutError()

    monkeypatch.setenv("ORION_QA_REQUEST_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setattr(qa_runner.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(qa_runner.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="did not become healthy"):
        qa_runner._wait_for_health("http://qa", WaitingProcess())
    assert captured == [12.5] * 60


def test_actual_isolated_and_multiturn_post_timeouts_never_retry(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    _runner_mocks(qa_runner, monkeypatch)
    checkpoint = qa_runner.ReportCheckpoint(tmp_path, ("secret",))
    checkpoint.start()
    sessions: list[str] = []
    sent: list[tuple[str, str]] = []

    def create(_):  # type: ignore[no-untyped-def]
        value = f"s{len(sessions) + 1}"
        sessions.append(value)
        return {"session_id": value}

    def send(_, session, prompt):  # type: ignore[no-untyped-def]
        sent.append((session, prompt))
        if prompt in {"single", "turn-two"}:
            raise qa_runner.QARequestTimeout()

    monkeypatch.setattr(qa_runner, "_create_session", create)
    monkeypatch.setattr(qa_runner, "_send", send)
    monkeypatch.setattr(
        qa_runner,
        "_timeline",
        lambda *_: [{"kind": "assistant_message", "payload": {"content": "answer"}}],
    )
    isolated = qa_runner.Case(id="isolated", prompt="single", category="x")
    multi = qa_runner.Case(
        id="multi",
        prompt="turn-one",
        turns=("turn-two", "never"),
        scenario="multi_turn",
        category="x",
    )
    next_case = qa_runner.Case(id="next", prompt="next", category="x")
    results, _ = qa_runner._run_structured(
        [isolated, multi, next_case],
        {"base_url": "http://model", "id": "model", "api_key": "secret"},
        False,
        checkpoint,
    )
    assert [item["status"] for item in results] == ["FAIL", "FAIL", "PASS"]
    assert sessions == ["s1", "s2", "s3"]
    assert sent == [("s1", "single"), ("s2", "turn-one"), ("s2", "turn-two"), ("s3", "next")]
    assert [
        json.loads(line)["id"]
        for line in (tmp_path / "cases.partial.jsonl").read_text().splitlines()
    ] == ["isolated", "multi", "next"]


def test_run_interrupts_with_last_in_progress_and_normal_completion_is_canonical(
    qa_runner, monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    secret = "provider-secret"
    monkeypatch.setattr(
        qa_runner,
        "active_model",
        lambda: {"base_url": "http://model", "id": "model", "api_key": secret},
    )
    monkeypatch.setattr(qa_runner, "qa_report_directory", lambda run_id: tmp_path / run_id)

    def interrupted(cases, model, fail_fast, checkpoint):  # type: ignore[no-untyped-def]
        checkpoint.mark_case_in_progress("one")
        checkpoint.record_case(
            {
                "phase": "canonical",
                "tier": "full",
                "id": "one",
                "category": "x",
                "manual_quality": False,
                "status": "PASS",
                "reason": None,
            }
        )
        checkpoint.mark_case_in_progress("two")
        raise RuntimeError("injected")

    monkeypatch.setattr(qa_runner, "_run_structured", interrupted)
    with pytest.raises(RuntimeError, match="injected"):
        qa_runner.run("full", False, "identity")
    report = next(tmp_path.iterdir())
    progress = json.loads((report / "progress.json").read_text())
    assert progress == {"status": "interrupted", "phase": "canonical", "case_id": "two"}
    assert "provider-secret" not in "".join(path.read_text() for path in report.iterdir())

    def completed(cases, model, fail_fast, checkpoint):  # type: ignore[no-untyped-def]
        result = {
            "phase": "canonical",
            "tier": "full",
            "id": "identity",
            "category": "x",
            "manual_quality": False,
            "status": "PASS",
            "reason": None,
        }
        checkpoint.mark_case_in_progress("identity")
        checkpoint.record_case(result)
        return [result], "http://qa"

    monkeypatch.setattr(qa_runner, "_run_structured", completed)
    assert qa_runner.run("full", False, "identity") == 0
    complete = next(path for path in tmp_path.iterdir() if (path / "manifest.json").exists())
    assert {
        "manifest.json",
        "cases.jsonl",
        "summary.json",
        "summary.md",
        "progress.json",
        "cases.partial.jsonl",
    } <= {p.name for p in complete.iterdir()}
    assert json.loads((complete / "progress.json").read_text())["status"] == "completed"
    assert (complete / "cases.partial.jsonl").read_text() == (complete / "cases.jsonl").read_text()


def test_canonical_safety_allows_mutation_only_for_safe_fixture_cases(qa_runner) -> None:  # type: ignore[no-untyped-def]
    corpus = cases(qa_runner)
    mutations = [case for case in corpus if case.mutation]
    assert {case.id for case in mutations} == {
        "linux-document-edit",
        "linux-docx-edit",
        "linux-xlsx-edit",
    }
    assert all(
        case.fixture_env in {"ORION_QA_TEXT_PATH", "ORION_QA_DOCX_PATH", "ORION_QA_XLSX_PATH"}
        for case in mutations
    )
    assert all(
        not case.mutation
        for case in corpus
        if case.id.startswith(("dangerous-", "service-restart", "package-update"))
    )


def test_canonical_boundaries_do_not_invent_inputs_or_execute_dangerous_requests(
    qa_runner,
) -> None:  # type: ignore[no-untyped-def]
    corpus = {case.id: case for case in cases(qa_runner)}
    mutation_tools = {
        "linux.file.edit",
        "linux.service.restart",
        "linux.package.install",
        "grafana.annotation.create",
        "zabbix.event.acknowledge",
    }
    dangerous = {
        "dangerous-firewall-boundary",
        "dangerous-ssh-boundary",
        "service-restart-boundary",
        "package-update-boundary",
    }
    for case_id in dangerous:
        case = corpus[case_id]
        assert "Do not" in case.prompt and "change infrastructure" in case.prompt
        assert set(case.forbidden_tools) & mutation_tools
    for case_id in {
        "grafana-dashboard-read",
        "grafana-network-representative",
        "grafana-history-boundary",
    }:
        case = corpus[case_id]
        assert not (
            {"grafana.dashboard.get", "grafana.datasource.query"} & set(case.expected_tools)
        )
        assert not (
            {"grafana.dashboard.get", "grafana.datasource.query"} & set(case.expected_any_tools)
        )
    assert "zabbix.history.get" not in corpus["zabbix-history-boundary"].expected_tools
    assert corpus["linux-unknown-target"].expected_tool_errors == ()
    assert corpus["multi-target-comparison"].expected_tools == ()
    assert corpus["local-address-probe"].expected_tool_errors == (("internet.fetch", "unsafe_url"),)
    assert not corpus["linux-hostile-target"].expected_tool_errors
    assert corpus["grafana-explicit-source"].requires_citation
    assert "linux.system.inspect" in corpus["grafana-explicit-source"].forbidden_tools
    assert corpus["zabbix-explicit-source"].requires_citation
    assert set(corpus["zabbix-explicit-source"].forbidden_tools) & {
        "grafana.alert.list",
        "grafana.datasource.query",
    }
