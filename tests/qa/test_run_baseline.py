"""Tests for scripts/qa/run_baseline.py (DR1-005)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNNER_PATH = PROJECT_ROOT / "scripts" / "qa" / "run_baseline.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_baseline", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["run_baseline"] = module
    spec.loader.exec_module(module)
    return module


rb = _load_module()


def _enum(name: str):
    return SimpleNamespace(name=name)


def _fake_investigation(
    *,
    concept="cpu",
    action="inspect",
    intent_name="CPU_ASSESSMENT",
    target="monitor",
    answer_type_name="FACT",
    evidence_complete=True,
    has_evidence=True,
    required_evidence_names=("CPU",),
    params=None,
):
    semantic = SimpleNamespace(concept=concept, action=action)
    extracted = SimpleNamespace(to_dict=lambda: params or {})
    required_evidence = [SimpleNamespace(name=name) for name in required_evidence_names]
    return SimpleNamespace(
        semantic_request=semantic,
        intent=_enum(intent_name) if intent_name else None,
        target=target,
        extracted_params=extracted,
        answer_type=_enum(answer_type_name) if answer_type_name else None,
        evidence_complete=evidence_complete,
        evidence=["dummy"] if has_evidence else [],
        required_evidence=required_evidence,
    )


def _actual_result() -> dict:
    return {
        "investigation": _fake_investigation(),
        "execution_trace": {
            "answer_strategy": "DETERMINISTIC_FACT",
            "llm_usage_reason": "NONE",
            "total_duration_ms": 42.0,
            "failure_stage": None,
            "runtime_metrics": None,
        },
    }


def _chat_result() -> dict:
    """Matches the REAL shape from deterministic_agent.py: when
    `_should_pipeline()` is False, `execution_trace` is `None` entirely, not
    just missing individual fields."""
    return {
        "investigation": None,
        "execution_trace": None,
    }


def _target_shortcircuit_result() -> dict:
    """Matches the REAL shape from deterministic_agent.py's UnknownTargetError
    handler: llm_usage_reason=NONE IS set explicitly; answer_strategy is not."""
    return {
        "investigation": None,
        "execution_trace": {
            "failure_stage": "target",
            "failure_reason": "unknown target",
            "answer_strategy": None,
            "llm_usage_reason": "NONE",
            "total_duration_ms": 5.0,
        },
    }


def _pipeline_shortcircuit_result() -> dict:
    """Matches the REAL shape from deterministic_agent.py's generic Exception
    handler: both answer_strategy=CHAT and llm_usage_reason=ROUTING_FALLBACK
    ARE set explicitly."""
    return {
        "investigation": None,
        "execution_trace": {
            "failure_stage": "pipeline",
            "failure_reason": "boom",
            "answer_strategy": "CHAT",
            "llm_usage_reason": "ROUTING_FALLBACK",
            "total_duration_ms": 7.0,
        },
    }


def _expected() -> dict:
    return {
        "concepts": ["cpu"],
        "operation": "inspect",
        "intent": "CPU_ASSESSMENT",
        "target": "monitor",
        "params": {},
        "answer_type": "FACT",
        "routing_status": "resolved",
        "evidence_status": "sufficient",
        "answer_strategy": "DETERMINISTIC_FACT",
        "llm_usage_reason": "NONE",
        "required_evidence": ["CPU"],
    }


class TestLoadGoldenCases:
    def test_skips_harness_error_cases(self, tmp_path):
        data = {
            "cases": [
                {
                    "id": "a",
                    "harness_error": False,
                    "question": "q1",
                    "expected": {},
                    "group": "A",
                },
                {
                    "id": "b",
                    "harness_error": True,
                    "question": "q2",
                    "expected": {},
                    "group": "A",
                },
                {"id": "c", "question": "q3", "expected": {}, "group": "A"},
            ]
        }
        path = tmp_path / "golden.yaml"
        path.write_text(yaml.safe_dump(data), encoding="utf-8")

        cases = rb.load_golden_cases(path)

        assert [case["id"] for case in cases] == ["a", "c"]

    def test_rejects_non_list_cases(self, tmp_path):
        path = tmp_path / "golden.yaml"
        path.write_text("cases: wrong\n", encoding="utf-8")

        with pytest.raises(ValueError, match="must be a list"):
            rb.load_golden_cases(path)


class TestExtractActual:
    def test_extracts_investigation_fields(self):
        actual = rb.extract_actual(_actual_result())

        assert actual["concepts"] == ["cpu"]
        assert actual["operation"] == "inspect"
        assert actual["intent"] == "CPU_ASSESSMENT"
        assert actual["target"] == "monitor"
        assert actual["answer_type"] == "FACT"
        assert actual["answer_strategy"] == "DETERMINISTIC_FACT"
        assert actual["llm_usage_reason"] == "NONE"
        assert actual["required_evidence"] == ["CPU"]
        assert actual["routing_status"] == "resolved"
        assert actual["evidence_status"] == "sufficient"
        assert actual["_context"] == "investigated"

    def test_real_chat_shape_execution_trace_is_none(self):
        """Real shape from deterministic_agent.py: when routing decides chat
        without ever entering the pipeline, `execution_trace` is `None`
        entirely (not a dict with missing keys). Must not crash."""
        actual = rb.extract_actual(_chat_result())

        assert actual["concepts"] == []
        assert actual["answer_strategy"] is None
        assert actual["llm_usage_reason"] is None
        assert actual["_context"] == "chat"

    def test_chat_path_has_no_investigation(self):
        result = {
            "investigation": None,
            "execution_trace": {
                "answer_strategy": "CHAT",
                "llm_usage_reason": "NONE",
                "total_duration_ms": 10.0,
                "failure_stage": None,
                "runtime_metrics": None,
            },
        }

        actual = rb.extract_actual(result)

        assert actual["concepts"] == []
        assert actual["intent"] is None
        assert actual["target"] is None
        assert actual["routing_status"] == "chat"
        assert actual["evidence_status"] == "not_applicable"

    def test_unknown_target_routing_status(self):
        result = {
            "investigation": None,
            "execution_trace": {
                "answer_strategy": None,
                "llm_usage_reason": "NONE",
                "total_duration_ms": 5.0,
                "failure_stage": "target",
                "runtime_metrics": None,
            },
        }

        assert rb.extract_actual(result)["routing_status"] == "unsupported"

    def test_partial_evidence_status(self):
        investigation = _fake_investigation(
            evidence_complete=False, has_evidence=True
        )
        result = {
            "investigation": investigation,
            "execution_trace": {
                "answer_strategy": "LLM_ASSESSMENT",
                "llm_usage_reason": "INSUFFICIENT_EVIDENCE",
                "total_duration_ms": 100.0,
                "failure_stage": None,
                "runtime_metrics": None,
            },
        }

        assert rb.extract_actual(result)["evidence_status"] == "partial"

    def test_missing_to_dict_params_defaults_empty(self):
        investigation = _fake_investigation()
        investigation.extracted_params = SimpleNamespace()
        result = _actual_result()
        result["investigation"] = investigation

        assert rb.extract_actual(result)["params"] == {}


class TestInvestigationContext:
    def test_investigated_when_investigation_present(self):
        assert (
            rb.investigation_context(_fake_investigation(), {"failure_stage": None})
            == "investigated"
        )

    def test_chat_when_investigation_none_and_no_failure_stage(self):
        assert rb.investigation_context(None, {}) == "chat"

    def test_target_shortcircuit(self):
        assert (
            rb.investigation_context(None, {"failure_stage": "target"})
            == "target_shortcircuit"
        )

    def test_pipeline_shortcircuit(self):
        assert (
            rb.investigation_context(None, {"failure_stage": "pipeline"})
            == "pipeline_shortcircuit"
        )

    def test_runner_exception_takes_priority(self):
        assert (
            rb.investigation_context(
                _fake_investigation(), {"failure_stage": "runner_exception"}
            )
            == "runner_exception"
        )


class TestScoreCase:
    def test_all_fields_match(self):
        actual = dict(_expected())
        actual["_context"] = "investigated"

        scored = rb.score_case(_expected(), actual)

        assert scored["core_pass"] is True
        assert all(status == "match" for status in scored["field_status"].values())

    def test_target_mismatch_fails_core(self):
        """A genuine mismatch (both values observable, e.g. the DR1-306
        fallback-to-localhost bug) must still be reported as "mismatch",
        never softened by the tri-state refinement."""
        actual = dict(_expected())
        actual["target"] = "localhost"
        actual["_context"] = "investigated"

        scored = rb.score_case(_expected(), actual)

        assert scored["core_pass"] is False
        assert scored["field_status"]["target"] == "mismatch"

    def test_concepts_order_independent(self):
        expected = {"concepts": ["cpu", "memory"]}
        actual = {"concepts": ["memory", "cpu"], "_context": "investigated"}
        for field in rb._CORE_FIELDS:
            expected.setdefault(field, None)
            actual.setdefault(field, None)
        expected["params"] = {}
        actual["params"] = {}
        expected["required_evidence"] = []
        actual["required_evidence"] = []

        assert rb.score_case(expected, actual)["field_status"]["concepts"] == "match"

    def test_required_evidence_order_independent(self):
        expected = {"required_evidence": ["CPU", "Process"]}
        actual = {
            "required_evidence": ["Process", "CPU"],
            "_context": "investigated",
        }
        for field in rb._CORE_FIELDS:
            expected.setdefault(field, None)
            actual.setdefault(field, None)
        expected["params"] = {}
        actual["params"] = {}
        expected["concepts"] = []
        actual["concepts"] = []

        assert (
            rb.score_case(expected, actual)["field_status"]["required_evidence"]
            == "match"
        )

    def test_chat_path_missing_strategy_is_not_observable(self):
        """Requirement: chat path with missing answer_strategy/
        llm_usage_reason must be not_observable, never compared/fabricated,
        while routing_status=chat is treated as confirmed (scored normally)."""
        actual = rb.extract_actual(_chat_result())
        expected = {
            "concepts": [],
            "operation": None,
            "intent": None,
            "target": None,
            "params": {},
            "answer_type": None,
            "routing_status": "chat",
            "evidence_status": "not_applicable",
            "answer_strategy": "CHAT",
            "llm_usage_reason": "NONE",
            "required_evidence": [],
        }

        scored = rb.score_case(expected, actual)

        assert scored["context"] == "chat"
        assert scored["field_status"]["answer_strategy"] == "not_observable"
        assert scored["field_status"]["llm_usage_reason"] == "not_observable"
        assert scored["field_status"]["routing_status"] == "match"
        assert scored["core_pass"] is False

    def test_unknown_target_shortcircuit_marks_upstream_fields_not_observable(self):
        """Requirement: unknown-target short-circuit must not count
        concept/operation/intent as mismatches — the pipeline computed them
        before discarding `investigation`, so they are not_observable. target
        stays a normal comparison (None is the real, meaningful value)."""
        actual = rb.extract_actual(_target_shortcircuit_result())
        expected = {
            "concepts": ["cpu"],
            "operation": "inspect",
            "intent": "CPU_ASSESSMENT",
            "target": None,
            "params": {},
            "answer_type": None,
            "routing_status": "unsupported",
            "evidence_status": "not_applicable",
            "answer_strategy": None,
            "llm_usage_reason": "NONE",
            "required_evidence": [],
        }

        scored = rb.score_case(expected, actual)

        assert scored["context"] == "target_shortcircuit"
        assert scored["field_status"]["concepts"] == "not_observable"
        assert scored["field_status"]["operation"] == "not_observable"
        assert scored["field_status"]["intent"] == "not_observable"
        assert scored["field_status"]["answer_type"] == "not_observable"
        assert scored["field_status"]["target"] == "match"
        assert scored["field_status"]["llm_usage_reason"] == "match"
        assert scored["field_status"]["answer_strategy"] == "not_observable"

    def test_pipeline_shortcircuit_marks_target_not_observable_too(self):
        """Unlike target_shortcircuit, a bare pipeline exception gives no
        structural guarantee about `target` either — it must also be
        not_observable, not silently treated as a confirmed None."""
        actual = rb.extract_actual(_pipeline_shortcircuit_result())
        expected = dict(_expected())
        expected["routing_status"] = "fallback"
        expected["evidence_status"] = "not_applicable"
        expected["answer_strategy"] = "CHAT"
        expected["llm_usage_reason"] = "ROUTING_FALLBACK"

        scored = rb.score_case(expected, actual)

        assert scored["context"] == "pipeline_shortcircuit"
        assert scored["field_status"]["target"] == "not_observable"
        assert scored["field_status"]["answer_strategy"] == "match"
        assert scored["field_status"]["llm_usage_reason"] == "match"

    def test_runner_exception_marks_everything_not_observable(self):
        actual = rb.extract_actual(
            {
                "investigation": None,
                "execution_trace": {
                    "failure_stage": "runner_exception",
                    "failure_reason": "boom",
                    "answer_strategy": None,
                    "llm_usage_reason": None,
                    "total_duration_ms": None,
                },
            }
        )

        scored = rb.score_case(_expected(), actual)

        for field in rb._CORE_FIELDS:
            assert scored["field_status"][field] == "not_observable", field
        assert scored["core_pass"] is False


class TestConfigHash:
    def test_returns_unknown_when_no_config_files(self, tmp_path):
        assert rb._config_hash(tmp_path) == "unknown"

    def test_returns_stable_hash_when_config_present(self, tmp_path):
        (tmp_path / "targets.json").write_text("{}", encoding="utf-8")

        first = rb._config_hash(tmp_path)
        second = rb._config_hash(tmp_path)

        assert first == second
        assert first != "unknown"


class TestRunBaselinePreflight:
    def test_no_model_fails_before_agent_creation(self, tmp_path, monkeypatch):
        golden = tmp_path / "golden.yaml"
        golden.write_text("cases: []\n", encoding="utf-8")
        calls = []

        monkeypatch.setattr(
            rb,
            "_resolve_model_context",
            lambda _server: {
                "configured": False,
                "server_name": "",
                "model": "",
                "provider": "",
            },
        )

        with pytest.raises(rb.BaselinePreflightError, match="No model"):
            rb.run_baseline(
                golden,
                None,
                "targets.json",
                agent_factory=lambda **kwargs: calls.append(kwargs),
            )

        assert calls == []

    def test_smoke_uses_one_agent_for_all_cases(self, tmp_path, monkeypatch):
        golden = tmp_path / "golden.yaml"
        cases = [
            {
                "id": "a",
                "group": "A",
                "question": "q1",
                "expected": _expected(),
            },
            {
                "id": "b",
                "group": "A",
                "question": "q2",
                "expected": _expected(),
            },
        ]
        golden.write_text(yaml.safe_dump({"cases": cases}), encoding="utf-8")
        factory_calls = []

        class FakeAgent:
            def __init__(self):
                self.questions = []

            def run_with_steps(self, question):
                self.questions.append(question)
                return _actual_result()

        agent = FakeAgent()

        def factory(**kwargs):
            factory_calls.append(kwargs)
            return agent

        monkeypatch.setattr(
            rb,
            "_resolve_model_context",
            lambda _server: {
                "configured": False,
                "server_name": "",
                "model": "",
                "provider": "",
            },
        )

        report = rb.run_baseline(
            golden,
            None,
            "targets.json",
            smoke=True,
            agent_factory=factory,
        )

        assert len(factory_calls) == 1
        assert agent.questions == ["q1", "q2"]
        assert report["metadata"]["meaningful_baseline"] is False
        assert report["summary"]["correct_investigation_rate"] is None
        assert report["summary"]["observed_core_pass_rate"] == 1.0

    def test_unhealthy_model_aborts_before_cases(self, tmp_path, monkeypatch):
        golden = tmp_path / "golden.yaml"
        golden.write_text(
            yaml.safe_dump(
                {
                    "cases": [
                        {
                            "id": "a",
                            "group": "A",
                            "question": "q1",
                            "expected": _expected(),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )

        class FakeAgent:
            def health_check(self, timeout):
                return False

            def run_with_steps(self, question):
                raise AssertionError("cases must not run after failed health check")

        monkeypatch.setattr(
            rb,
            "_resolve_model_context",
            lambda _server: {
                "configured": True,
                "server_name": "sv1",
                "model": "model-1",
                "provider": "openai",
            },
        )

        with pytest.raises(rb.BaselinePreflightError, match="health check"):
            rb.run_baseline(
                golden,
                "sv1",
                "targets.json",
                agent_factory=lambda **_kwargs: FakeAgent(),
            )


class TestSummarizeAndMarkdown:
    def _case_reports(self):
        return [
            {
                "id": "a",
                "group": "A",
                "core_pass": True,
                "context": "investigated",
                "field_status": {field: "match" for field in rb._ALL_SCORED_FIELDS},
                "actual": {
                    "answer_strategy": "DETERMINISTIC_FACT",
                    "llm_usage_reason": "NONE",
                    "total_duration_ms": 50.0,
                },
            },
            {
                "id": "b",
                "group": "A",
                "core_pass": False,
                "context": "investigated",
                "field_status": {
                    field: "mismatch" for field in rb._ALL_SCORED_FIELDS
                },
                "actual": {
                    "answer_strategy": "LLM_ASSESSMENT",
                    "llm_usage_reason": "ROUTING_FALLBACK",
                    "total_duration_ms": 150.0,
                },
            },
        ]

    def test_summarize_computes_meaningful_rate(self):
        cases = [
            {"id": "a", "group": "A", "expected": {}},
            {"id": "b", "group": "A", "expected": {}},
        ]

        report = rb._summarize(
            cases, self._case_reports(), Path("golden.yaml"), None
        )

        assert report["summary"]["cases_total"] == 2
        assert report["summary"]["correct_investigation_rate"] == 0.5
        assert report["summary"]["observed_core_pass_rate"] == 0.5
        assert report["summary"]["strict_correct_investigation_rate"] == 0.5
        # One case all "match", one all "mismatch" -> 50% observable accuracy,
        # and every core-field instance was observable -> full completeness.
        assert report["summary"]["observable_core_accuracy"] == 0.5
        assert report["summary"]["trace_completeness_rate"] == 1.0
        assert report["metadata"]["not_authoritative_fields"] == list(
            rb._APPROXIMATE_FIELDS
        )

    def test_not_observable_excluded_from_observable_accuracy_and_completeness(self):
        """Requirement: not_observable must not be counted as a mismatch in
        aggregate metrics — it should be excluded from observable_core_accuracy's
        denominator and reflected in trace_completeness_rate, while
        strict_correct_investigation_rate still fails the case (no free pass)."""
        case_reports = [
            {
                "id": "a",
                "group": "A",
                "core_pass": False,
                "context": "chat",
                "field_status": {
                    **{field: "match" for field in rb._CORE_FIELDS},
                    "answer_strategy": "not_observable",
                    "llm_usage_reason": "not_observable",
                    "routing_status": "match",
                    "evidence_status": "match",
                    "params": "match",
                    "required_evidence": "match",
                },
                "actual": {
                    "answer_strategy": None,
                    "llm_usage_reason": None,
                    "total_duration_ms": None,
                },
            }
        ]
        cases = [{"id": "a", "group": "A", "expected": {}}]

        report = rb._summarize(cases, case_reports, Path("golden.yaml"), None)
        summary = report["summary"]

        # 7 core fields, 2 are not_observable -> 5 observable, all "match".
        assert summary["observable_core_accuracy"] == 1.0
        assert summary["trace_completeness_rate"] == round(5 / 7, 4)
        # Strict rate still fails: not_observable is not a free pass for the
        # overall core_pass bar, even though every observable field matched.
        assert summary["strict_correct_investigation_rate"] == 0.0

    def test_smoke_summary_suppresses_baseline_headline(self):
        cases = [
            {"id": "a", "group": "A", "expected": {}},
            {"id": "b", "group": "A", "expected": {}},
        ]
        context = {
            "run_mode": "smoke",
            "baseline_status": "smoke_only",
            "meaningful_baseline": False,
            "model_configured": False,
            "model_health_ok": None,
            "resolved_server": "",
            "resolved_model": "",
            "resolved_provider": "",
        }

        report = rb._summarize(
            cases,
            self._case_reports(),
            Path("golden.yaml"),
            None,
            run_context=context,
        )
        markdown = rb.render_markdown(report)

        assert report["summary"]["correct_investigation_rate"] is None
        assert report["summary"]["observed_core_pass_rate"] == 0.5
        assert "not a meaningful baseline" in markdown
        assert "correct_investigation_rate (strict) =" not in markdown

    def test_render_markdown_contains_headline_diagnostics_and_groups(self):
        report = {
            "metadata": {
                "git_commit": "abc123",
                "config_hash": "deadbeef",
                "model": "mock",
                "provider": "",
                "captured_at": "now",
                "golden_dataset_path": "golden.yaml",
                "golden_dataset_cases_total": 1,
                "run_mode": "baseline",
                "baseline_status": "completed",
                "meaningful_baseline": True,
                "not_authoritative_reason": "heuristic until DR1-308/505 land.",
            },
            "summary": {
                "correct_investigation_rate": 1.0,
                "observed_core_pass_rate": 1.0,
                "strict_correct_investigation_rate": 1.0,
                "observable_core_accuracy": 1.0,
                "trace_completeness_rate": 1.0,
                "stage_accuracy": {
                    field: {
                        "match": 1,
                        "mismatch": 0,
                        "not_observable": 0,
                        "observable_accuracy": 1.0,
                    }
                    for field in rb._ALL_SCORED_FIELDS
                },
                "deterministic_answer_coverage": 1.0,
                "expected_assessment_rate": 0.0,
                "routing_fallback_rate": 0.0,
                "insufficient_evidence_rate": 0.0,
                "by_group": {
                    "A": {
                        "total": 1,
                        "core_pass": 1,
                        "observed_core_pass_rate": 1.0,
                        "strict_correct_investigation_rate": 1.0,
                        "correct_investigation_rate": 1.0,
                    }
                },
                "latency_ms": {"median": 50.0, "p95": 50.0},
            },
            "diagnostics": {
                "behavioral_mismatches": [],
                "trace_observability_gaps": [
                    {
                        "id": "x-1",
                        "group": "A",
                        "context": "chat",
                        "fields": ["answer_strategy", "llm_usage_reason"],
                    }
                ],
                "approximate_fields": list(rb._APPROXIMATE_FIELDS),
            },
            "cases": [],
        }

        markdown = rb.render_markdown(report)

        assert "correct_investigation_rate (strict) = 100.00%" in markdown
        assert "| A | 1 | 100.00% (correct investigation) |" in markdown
        assert "## Behavioral mismatches" in markdown
        assert "## Trace observability gaps" in markdown
        assert "`x-1` (A, context=chat)" in markdown
        assert "## Approximate fields (not authoritative)" in markdown


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
