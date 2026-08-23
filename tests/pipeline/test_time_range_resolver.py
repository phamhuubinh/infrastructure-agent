from __future__ import annotations

from datetime import datetime, timezone

from src.pipeline.time_range_resolver import (
    TemporalRequirement,
    TimeRange,
    TimeRangeResolver,
)


NOW = datetime(
    2026,
    8,
    23,
    12,
    0,
    tzinfo=timezone.utc,
)


def test_resolve_one_hour() -> None:
    result = TimeRangeResolver().resolve(
        "last 1h",
        now=NOW,
    )

    assert result is not None
    assert result.end - result.start == 3600
    assert result.requirement is (
        TemporalRequirement.HISTORICAL
    )


def test_future_duration_is_forecast() -> None:
    result = TimeRangeResolver().resolve(
        "next 7 days",
        now=NOW,
    )

    assert result is not None
    assert result.start == int(
        NOW.timestamp()
    )
    assert result.requirement is (
        TemporalRequirement.FORECAST
    )


def test_comparison_has_explicit_windows() -> None:
    result = TimeRangeResolver().resolve(
        "compare yesterday vs today",
        now=NOW,
    )

    assert result is not None
    assert result.requirement is (
        TemporalRequirement.COMPARISON
    )
    assert len(result.windows) == 2


def test_time_range_round_trip() -> None:
    result = TimeRangeResolver().resolve(
        "last 7 days",
        now=NOW,
    )

    assert result is not None
    assert (
        TimeRange.from_dict(
            result.to_dict()
        )
        == result
    )
