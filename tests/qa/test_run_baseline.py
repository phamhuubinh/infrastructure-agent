"""Tests for canonical scripts/qa/run_baseline.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
import yaml


PROJECT_ROOT = Path(
    __file__
).resolve().parents[2]

RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "qa"
    / "run_baseline.py"
)


def _load_module():
    spec = (
        importlib.util.spec_from_file_location(
            "run_baseline",
            RUNNER_PATH,
        )
    )

    module = (
        importlib.util.module_from_spec(
            spec
        )
    )

    assert spec.loader is not None

    sys.modules[
        "run_baseline"
    ] = module

    spec.loader.exec_module(
        module
    )

    return module


rb = _load_module()


def _expected(
    **overrides,
) -> dict:
    result = {
        "terminals": ["final"],
        "required_capability_sets": [],
        "required_capability_prefixes": [],
        "forbidden_capability_prefixes": [],
        "required_references": [],
        "forbidden_references": [],
        "min_successful_observations": 0,
        "max_actions": 0,
        "approval_required": False,
        "failure": None,
        "response_required": True,
    }

    result.update(overrides)

    return result


def _result(
    *,
    terminal="final",
    steps=None,
    action_attempts=0,
    tool_calls=0,
    approval_required=False,
    failure=None,
    response="answer",
):
    return {
        "response": response,
        "steps": steps or [],
        "investigation": None,
        "trace_id": "trace",
        "execution_trace": {
            "runtime_metrics": {
                "canonical_runtime": {
                    "terminal": terminal,
                    "model_calls": 2,
                    "discovery_calls": 1,
                    "action_attempts": (
                        action_attempts
                    ),
                    "observation_count": len(
                        steps or []
                    ),
                    "failure": failure,
                    "approval_required": (
                        approval_required
                    ),
                    "budget": {
                        "max_actions": 6,
                        "actions_used": (
                            tool_calls
                        ),
                        "max_cost": 6,
                        "cost_used": (
                            tool_calls
                        ),
                    },
                }
            }
        },
    }


def _success_step(
    capability,
    *,
    target=None,
    source=None,
):
    return {
        "type": "evidence",
        "action_id": 1,
        "capability_id": capability,
        "status": "success",
        "target_id": target,
        "source_id": source,
    }


def test_extract_actual_reads_public_canonical_trace():
    actual = rb.extract_actual(
        _result(
            steps=[
                _success_step(
                    "host.get_cpu",
                    target="monitor",
                )
            ],
            action_attempts=1,
            tool_calls=1,
        )
    )

    assert actual[
        "terminal"
    ] == "final"
    assert actual[
        "capabilities"
    ] == [
        "host.get_cpu"
    ]
    assert actual[
        "references"
    ] == [
        "monitor"
    ]
    assert actual[
        "successful_observations"
    ] == 1
    assert actual[
        "runtime_metrics"
    ]["tool_calls"] == 1


def test_required_capability_set_accepts_one_exact_alternative():
    actual = rb.extract_actual(
        _result(
            steps=[
                _success_step(
                    "host.get_cpu_usage"
                )
            ],
            action_attempts=1,
            tool_calls=1,
        )
    )

    scored = rb.score_case(
        _expected(
            required_capability_sets=[
                [
                    "host.get_cpu",
                    "host.get_cpu_usage",
                ]
            ],
            min_successful_observations=1,
            max_actions=2,
        ),
        actual,
    )

    assert scored[
        "contract_pass"
    ] is True


def test_forbidden_capability_prefix_is_strict():
    actual = rb.extract_actual(
        _result(
            steps=[
                _success_step(
                    "host.get_cpu"
                )
            ],
            action_attempts=1,
            tool_calls=1,
        )
    )

    scored = rb.score_case(
        _expected(
            forbidden_capability_prefixes=[
                "host."
            ],
            max_actions=2,
        ),
        actual,
    )

    assert scored[
        "contract_pass"
    ] is False
    assert scored[
        "field_status"
    ][
        "forbidden_capability_prefixes"
    ] == "mismatch"


def test_exact_reference_matching_is_case_sensitive():
    actual = rb.extract_actual(
        _result(
            steps=[
                _success_step(
                    "host.get_cpu",
                    target="Monitor",
                )
            ],
            action_attempts=1,
            tool_calls=1,
        )
    )

    scored = rb.score_case(
        _expected(
            required_references=[
                "monitor"
            ],
            max_actions=2,
        ),
        actual,
    )

    assert scored[
        "field_status"
    ][
        "required_references"
    ] == "mismatch"


def test_action_budget_is_scored():
    actual = rb.extract_actual(
        _result(
            action_attempts=3,
        )
    )

    scored = rb.score_case(
        _expected(
            max_actions=2
        ),
        actual,
    )

    assert scored[
        "field_status"
    ]["max_actions"] == (
        "mismatch"
    )


def test_runner_exception_never_passes_normal_contract():
    result = (
        rb._runner_exception_result(
            RuntimeError("boom")
        )
    )

    actual = rb.extract_actual(
        result
    )

    scored = rb.score_case(
        _expected(),
        actual,
    )

    assert actual[
        "terminal"
    ] == "runner_exception"
    assert scored[
        "contract_pass"
    ] is False


def test_case_context_store_does_not_accumulate_turns():
    store = rb._CaseContextStore(
        [
            {
                "role": "user",
                "content": "context",
            }
        ]
    )

    store.add_turn(
        "new",
        "answer",
    )

    assert store.history == [
        {
            "role": "user",
            "content": "context",
        }
    ]


def test_load_canonical_file_skips_harness_cases(
    tmp_path,
):
    golden = tmp_path / "golden.yaml"

    document = {
        "schema_version": 2,
        "groups": {
            "A": "General",
        },
        "cases": [
            {
                "id": "a",
                "group": "A",
                "source": "fixture",
                "tags": ["vi"],
                "question": "q",
                "expected": (
                    _expected()
                ),
                "harness_error": False,
                "note": "fixture",
            },
            {
                "id": "b",
                "group": "A",
                "source": "fixture",
                "tags": ["vi"],
                "question": "q",
                "expected": (
                    _expected()
                ),
                "harness_error": True,
                "note": "fixture",
            },
        ],
    }

    golden.write_text(
        yaml.safe_dump(document),
        encoding="utf-8",
    )

    cases = rb.load_golden_cases(
        golden
    )

    assert [
        case["id"]
        for case in cases
    ] == ["a"]


def test_no_model_fails_before_agent_creation(
    tmp_path,
    monkeypatch,
):
    golden = tmp_path / "golden.yaml"

    golden.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "groups": {
                    "A": "General",
                },
                "cases": [
                    {
                        "id": "a",
                        "group": "A",
                        "source": "fixture",
                        "tags": ["vi"],
                        "question": "q",
                        "expected": (
                            _expected()
                        ),
                        "harness_error": False,
                        "note": "fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

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

    with pytest.raises(
        rb.BaselinePreflightError,
        match="No model",
    ):
        rb.run_baseline(
            golden,
            None,
            "targets.json",
            agent_factory=(
                lambda **kwargs:
                calls.append(kwargs)
            ),
        )

    assert calls == []


def test_smoke_is_not_meaningful_baseline(
    tmp_path,
    monkeypatch,
):
    golden = tmp_path / "golden.yaml"

    case = {
        "id": "a",
        "group": "A",
        "source": "fixture",
        "tags": ["vi"],
        "question": "q",
        "expected": _expected(
            terminals=[
                "setup_required"
            ]
        ),
        "harness_error": False,
        "note": "fixture",
    }

    # setup_required is intentionally not
    # valid golden terminal. For the smoke
    # fake, use a normal expectation and
    # observe that the headline is suppressed.
    case["expected"] = _expected()

    golden.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "groups": {
                    "A": "General",
                },
                "cases": [case],
            }
        ),
        encoding="utf-8",
    )

    class FakeAgent:
        conversation_store = None

        def run_with_steps(
            self,
            question,
        ):
            return _result()

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
        agent_factory=(
            lambda **_kwargs:
            FakeAgent()
        ),
    )

    assert report[
        "metadata"
    ][
        "meaningful_baseline"
    ] is False
    assert report[
        "summary"
    ][
        "canonical_contract_rate"
    ] is None


def test_unhealthy_model_aborts_before_cases(
    tmp_path,
    monkeypatch,
):
    golden = tmp_path / "golden.yaml"

    golden.write_text(
        yaml.safe_dump(
            {
                "schema_version": 2,
                "groups": {
                    "A": "General",
                },
                "cases": [
                    {
                        "id": "a",
                        "group": "A",
                        "source": "fixture",
                        "tags": ["vi"],
                        "question": "q",
                        "expected": (
                            _expected()
                        ),
                        "harness_error": False,
                        "note": "fixture",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    class FakeAgent:
        def health_check(
            self,
            timeout,
        ):
            return False

        def run_with_steps(
            self,
            question,
        ):
            raise AssertionError(
                "must not run cases"
            )

    monkeypatch.setattr(
        rb,
        "_resolve_model_context",
        lambda _server: {
            "configured": True,
            "server_name": "sv1",
            "model": "model",
            "provider": "openai",
        },
    )

    with pytest.raises(
        rb.BaselinePreflightError,
        match="health check",
    ):
        rb.run_baseline(
            golden,
            "sv1",
            "targets.json",
            agent_factory=(
                lambda **_kwargs:
                FakeAgent()
            ),
        )


def test_summary_reports_strict_canonical_rate():
    actual_ok = rb.extract_actual(
        _result()
    )

    actual_bad = rb.extract_actual(
        _result(
            terminal="refuse"
        )
    )

    expected = _expected()

    reports = [
        {
            "id": "a",
            "group": "A",
            "tags": ["vi"],
            "elapsed_ms": 10.0,
            "response_empty": False,
            "response_character_count": 20,
            **rb.score_case(
                expected,
                actual_ok,
            ),
        },
        {
            "id": "b",
            "group": "A",
            "tags": ["vi"],
            "elapsed_ms": 20.0,
            "response_empty": False,
            "response_character_count": 20,
            **rb.score_case(
                expected,
                actual_bad,
            ),
        },
    ]

    report = rb._summarize(
        [],
        reports,
        Path("golden.yaml"),
        None,
    )

    assert report[
        "summary"
    ][
        "strict_canonical_contract_rate"
    ] == 0.5

    assert report[
        "summary"
    ][
        "canonical_contract_rate"
    ] == 0.5


def test_render_markdown_uses_canonical_language():
    actual = rb.extract_actual(
        _result()
    )

    scored = rb.score_case(
        _expected(),
        actual,
    )

    report = rb._summarize(
        [],
        [
            {
                "id": "a",
                "group": "A",
                "tags": ["vi"],
                "elapsed_ms": 10.0,
                "response_empty": False,
                "response_character_count": 20,
                **scored,
            }
        ],
        Path("golden.yaml"),
        None,
    )

    markdown = rb.render_markdown(
        report
    )

    assert (
        "canonical_contract_rate"
        in markdown
    )
    assert (
        "investigation_rate"
        not in markdown
    )
    assert (
        "intent"
        not in markdown.lower()
    )
