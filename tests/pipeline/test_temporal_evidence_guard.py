from __future__ import annotations

from dataclasses import replace

from src.pipeline.answer_type import AnswerType
from src.pipeline.deterministic_responder import DeterministicResponder
from src.pipeline.evidence_completeness import EvidenceCompleteness
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.investigation_request import InvestigationRequest
from src.pipeline.temporal_evidence_guard import TemporalEvidenceGuard


def _request(answer_type: AnswerType, data: dict) -> InvestigationRequest:
    requirement = EvidenceRequirement("CPU")
    requirement = replace(
        requirement,
        requires_time_series=True,
        minimum_windows=2 if answer_type is AnswerType.COMPARISON else 1,
        minimum_points=6 if answer_type is AnswerType.FORECAST else 2,
        requires_growth_model=answer_type is AnswerType.FORECAST,
    )
    return InvestigationRequest(
        raw_request="compare CPU yesterday vs today",
        answer_type=answer_type,
        required_evidence=[requirement],
        evidence=[EvidencePackage("CPU Information", "CPU", data=data)],
    )


def test_snapshot_cannot_support_comparison() -> None:
    request = _request(AnswerType.COMPARISON, {"usage_percent": 42})

    EvidenceCompleteness().check(request)
    response = DeterministicResponder().try_response(request)

    assert request.evidence_complete is False
    assert "compatible windows" in " ".join(request.temporal_evidence_failures)
    assert response is not None
    assert "không suy ra xu hướng từ một snapshot" in response


def test_two_compatible_windows_support_comparison_contract() -> None:
    request = _request(
        AnswerType.COMPARISON,
        {
            "series": [
                {"start": 1, "points": [[1, 40], [2, 45]]},
                {"start": 3, "points": [[3, 42], [4, 41]]},
            ],
            "windows": [{"start": 1, "end": 2}, {"start": 3, "end": 4}],
        },
    )

    assert TemporalEvidenceGuard().evaluate(request).sufficient is True


def test_incompatible_window_sizes_do_not_support_comparison() -> None:
    request = _request(
        AnswerType.COMPARISON,
        {
            "points": [[1, 40], [2, 45]],
            "windows": [{"start": 1, "end": 2}, {"start": 3, "end": 30}],
        },
    )

    assert TemporalEvidenceGuard().evaluate(request).sufficient is False


def test_forecast_requires_long_series_and_defined_growth_model() -> None:
    without_model = _request(
        AnswerType.FORECAST,
        {"points": [[index, index * 2] for index in range(6)]},
    )
    with_model = _request(
        AnswerType.FORECAST,
        {
            "points": [[index, index * 2] for index in range(6)],
            "growth_model": {"type": "linear", "version": "1"},
        },
    )

    assert TemporalEvidenceGuard().evaluate(without_model).sufficient is False
    assert TemporalEvidenceGuard().evaluate(with_model).sufficient is True
