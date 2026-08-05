"""Conservative guard against temporal claims from snapshot evidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.pipeline.answer_type import AnswerType

if TYPE_CHECKING:
    from src.pipeline.investigation_request import InvestigationRequest


@dataclass(frozen=True, slots=True)
class TemporalEvidenceResult:
    sufficient: bool
    failures: tuple[str, ...] = ()


class TemporalEvidenceGuard:
    """Verify series/window/model richness before comparison or forecast."""

    def evaluate(self, request: InvestigationRequest) -> TemporalEvidenceResult:
        answer_type = request.answer_type
        temporal_requirements = [
            item
            for item in request.required_evidence
            if item.requires_time_series
            or answer_type in {AnswerType.COMPARISON, AnswerType.FORECAST}
        ]
        if not temporal_requirements:
            return TemporalEvidenceResult(True)

        packages_by_name = {
            package.evidence_name: package
            for package in request.evidence
            if package.valid_for_requirements and isinstance(package.data, dict)
        }
        failures: list[str] = []
        for requirement in temporal_requirements:
            package = packages_by_name.get(requirement.name)
            if package is None:
                failures.append(f"{requirement.name}: time-series evidence missing")
                continue
            data = package.data
            points = self._point_count(data)
            windows = self._window_count(data)
            if points < max(2, requirement.minimum_points):
                failures.append(
                    f"{requirement.name}: needs at least "
                    f"{max(2, requirement.minimum_points)} time-series points"
                )
            if requirement.minimum_windows > 1 and windows < requirement.minimum_windows:
                failures.append(
                    f"{requirement.name}: needs at least "
                    f"{requirement.minimum_windows} compatible windows"
                )
            if requirement.requires_growth_model and not self._has_growth_model(data):
                failures.append(f"{requirement.name}: defined growth model missing")
        return TemporalEvidenceResult(not failures, tuple(dict.fromkeys(failures)))

    @classmethod
    def _point_count(cls, data: dict[str, object]) -> int:
        counts: list[int] = []
        for key in ("series", "datapoints", "points", "values", "history"):
            value = data.get(key)
            if isinstance(value, list):
                if value and all(isinstance(item, dict) for item in value):
                    nested = [
                        cls._point_count(item)
                        for item in value
                        if isinstance(item, dict)
                    ]
                    counts.append(max([len(value), *nested]))
                else:
                    counts.append(len(value))
            elif isinstance(value, dict):
                counts.append(cls._point_count(value))
        return max(counts, default=0)

    @staticmethod
    def _window_count(data: dict[str, object]) -> int:
        windows = data.get("windows")
        if isinstance(windows, list):
            parsed: list[tuple[float, str | None]] = []
            for item in windows:
                if not isinstance(item, dict):
                    return 0
                start = item.get("start")
                end = item.get("end")
                if not isinstance(start, (int, float)) or not isinstance(
                    end, (int, float)
                ):
                    return 0
                duration = float(end) - float(start)
                if duration <= 0:
                    return 0
                granularity = item.get("granularity")
                parsed.append(
                    (duration, str(granularity) if granularity is not None else None)
                )
            granularities = {item[1] for item in parsed if item[1] is not None}
            if len(granularities) > 1:
                return 0
            durations = [item[0] for item in parsed]
            if durations and max(durations) / min(durations) > 1.25:
                return 0
            return len(parsed)
        return 0

    @staticmethod
    def _has_growth_model(data: dict[str, object]) -> bool:
        model = data.get("growth_model") or data.get("forecast_model")
        return isinstance(model, (str, dict)) and bool(model)

    @staticmethod
    def refusal(failures: tuple[str, ...]) -> str:
        details = "; ".join(failures[:4])
        return (
            "Không đủ bằng chứng chuỗi thời gian để so sánh hoặc dự báo. "
            "Orion không suy ra xu hướng từ một snapshot."
            + (f" Thiếu: {details}." if details else "")
        )
