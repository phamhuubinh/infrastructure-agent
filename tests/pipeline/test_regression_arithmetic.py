"""Regression matrix for deterministic natural-language arithmetic (#45).

Every case asserts the semantic operands/operation and the final numeric
result — never source-code strings or model prose.
"""

from __future__ import annotations

from decimal import Decimal

from src.pipeline.basic_calculator import (
    CalculatorDurationUnit,
    CalculatorOperation,
    CalculatorRateUnit,
    CalculatorRequest,
    calculate,
    calculate_request,
    calculate_supplied_text,
)


def test_average_cpu_with_count_noun_ignores_machine_count() -> None:
    result = calculate_supplied_text(
        "CPU trung bình của 3 máy là 20%, 40%, 60%"
    )

    assert result.recognized
    assert result.result.value == Decimal("40")


def test_average_english_count_noun_ignores_machine_count() -> None:
    result = calculate_supplied_text("average CPU of 3 machines: 20, 40, 60")

    assert result.result.value == Decimal("40")


def test_structured_worker_task_rate_uses_explicit_operands() -> None:
    request = CalculatorRequest(
        operation=CalculatorOperation.WORKER_TASK_RATE,
        total_tasks=Decimal("800"),
        workers=Decimal("8"),
        duration=Decimal("10"),
        duration_unit=CalculatorDurationUnit.MINUTES,
    )

    result = calculate_request(request)

    assert result.ok
    assert result.operation is CalculatorOperation.WORKER_TASK_RATE
    assert result.value == Decimal("10")
    assert result.unit == "tasks/worker/minute"


def test_structured_rate_conversion_req_per_minute_to_second() -> None:
    request = CalculatorRequest(
        operation=CalculatorOperation.RATE_CONVERT,
        rate_value=Decimal("120"),
        rate_unit=CalculatorRateUnit.PER_MINUTE,
        target_rate_unit=CalculatorRateUnit.PER_SECOND,
    )

    result = calculate_request(request)

    assert result.ok
    assert result.operation is CalculatorOperation.RATE_CONVERT
    assert result.value == Decimal("2")


def test_structured_percent_of_large_base() -> None:
    request = CalculatorRequest(
        operation=CalculatorOperation.PERCENT_OF,
        base_value=Decimal("2000000"),
        percent=Decimal("15"),
    )

    result = calculate_request(request)

    assert result.ok
    assert result.operation is CalculatorOperation.PERCENT_OF
    assert result.value == Decimal("300000")


def test_supplied_gb_remaining_uses_only_total_and_used() -> None:
    result = calculate_supplied_text("64 GB tổng, 18 GB đã dùng")

    assert result.recognized
    assert result.result.value == Decimal("46")
    assert result.unit == "GB"


def test_structured_sequential_latency_addition() -> None:
    request = CalculatorRequest(
        operation=CalculatorOperation.ADD,
        left=Decimal("200"),
        right=Decimal("300"),
        unit="ms",
    )

    result = calculate_request(request)

    assert result.ok
    assert result.operation is CalculatorOperation.ADD
    assert result.value == Decimal("500")
    assert result.unit == "ms"


def test_supplied_availability_downtime_over_thirty_days() -> None:
    result = calculate_supplied_text("99.9% availability over 30 days")

    assert result.recognized
    assert result.result.value == Decimal("43.2")
    assert result.unit == "minutes"


def test_percentage_growth_via_safe_expression() -> None:
    result = calculate("(120 - 100) / 100 * 100")

    assert result.ok
    assert result.value == Decimal("20")


def test_simple_sort_cases_via_min_max() -> None:
    maximum = calculate("max(30, 10, 20)")
    minimum = calculate("min(30, 10, 20)")

    assert maximum.ok and maximum.value == Decimal("30")
    assert minimum.ok and minimum.value == Decimal("10")


def test_agent_computes_structured_average_without_a_model_call() -> None:
    from src.agent.deterministic_agent import DeterministicAgent
    from src.model.semantic_planner_adapter import SemanticPlannerAdapter
    from tests.fixtures.fake_environment import fake_environment
    from tests.fixtures.fake_models import (
        RecordingEngine,
        ScriptedAssessmentModel,
        ScriptedPlannerProvider,
        direct_answer_plan,
        plan_response,
    )

    plan = direct_answer_plan(
        concept="average cpu",
        calculation=CalculatorRequest(
            operation=CalculatorOperation.AVERAGE,
            values=(Decimal("20"), Decimal("40"), Decimal("60")),
        ),
    )
    env = fake_environment(localhost=True)
    engine = RecordingEngine(env)
    model = ScriptedAssessmentModel(draft="ignored")
    agent = DeterministicAgent(
        engine,  # type: ignore[arg-type]
        model,
        semantic_planner=SemanticPlannerAdapter(
            [ScriptedPlannerProvider([plan_response(plan)])]
        ),
    )

    result = agent.run_with_steps("CPU trung bình của 3 máy là 20%, 40%, 60%")

    semantic = result["execution_trace"]["runtime_metrics"]["semantic_loop"]
    assert result["response"] == "Kết quả: 40."
    assert semantic["calculator_calls"] == 1
    assert engine.execute_calls == 0
    assert [call.kind for call in model.calls] == []
