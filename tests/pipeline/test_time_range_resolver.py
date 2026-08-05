from __future__ import annotations

import time

import pytest

from src.pipeline.evidence_planner import EvidencePlanner
from src.pipeline.intent_resolver import IntentResolver
from src.pipeline.normalizer import Normalizer
from src.pipeline.time_range_resolver import TemporalRequirement, TimeRangeResolver


def test_resolve_1h() -> None:
    tr = TimeRangeResolver()
    now = int(time.time())
    result = tr.resolve("CPU 1h trước")
    assert result is not None
    start, end = result
    assert end == pytest.approx(now, abs=5)
    assert start == pytest.approx(now - 3600, abs=5)


def test_resolve_1_giờ() -> None:
    tr = TimeRangeResolver()
    now = int(time.time())
    result = tr.resolve("memory 1 giờ qua")
    assert result is not None
    start, end = result
    assert start == pytest.approx(now - 3600, abs=5)


def test_resolve_today() -> None:
    tr = TimeRangeResolver()
    result = tr.resolve("hôm nay")
    assert result is not None
    start, end = result
    assert start < end


def test_resolve_7d() -> None:
    tr = TimeRangeResolver()
    now = int(time.time())
    result = tr.resolve("disk 7 ngày")
    assert result is not None
    start, end = result
    assert start == pytest.approx(now - 604800, abs=5)


def test_resolve_yesterday() -> None:
    tr = TimeRangeResolver()
    result = tr.resolve("yesterday metrics")
    assert result is not None
    start, end = result
    assert start < end  # start of yesterday
    assert end < time.time()  # end of yesterday < now


def test_resolve_numeric_pattern() -> None:
    tr = TimeRangeResolver()
    now = int(time.time())
    result = tr.resolve("CPU 3 giờ")
    assert result is not None
    start, end = result
    assert start == pytest.approx(now - 10800, abs=5)


def test_resolve_no_match() -> None:
    tr = TimeRangeResolver()
    result = tr.resolve("cho tôi xem CPU")
    assert result is None


def test_resolve_30d() -> None:
    tr = TimeRangeResolver()
    now = int(time.time())
    result = tr.resolve("30 ngày data")
    assert result is not None
    start, end = result
    assert start == pytest.approx(now - 2592000, abs=10)


def test_relative_range_is_timezone_aware_and_deterministic() -> None:
    result = TimeRangeResolver().resolve(
        "CPU hôm qua", now=2_000_000_000, timezone_name="Asia/Ho_Chi_Minh"
    )
    assert result is not None
    assert result.timezone == "Asia/Ho_Chi_Minh"
    assert result.source_phrase == "yesterday"
    assert result.end - result.start == 86399


def test_comparison_has_two_explicit_windows() -> None:
    result = TimeRangeResolver().resolve(
        "so sánh CPU hôm qua và hôm nay", now=2_000_000_000
    )
    assert result is not None
    assert result.requirement is TemporalRequirement.COMPARISON
    assert len(result.windows) == 2


def test_future_range_is_not_a_historical_snapshot() -> None:
    result = TimeRangeResolver().resolve(
        "dự báo dung lượng 6 tháng tới", now=2_000_000_000
    )
    assert result is not None
    assert result.requirement is TemporalRequirement.FORECAST
    assert result.start == 2_000_000_000
    assert result.end > result.start


def test_historical_query_creates_series_requirements() -> None:
    frame = Normalizer().normalize("CPU hôm qua")
    request = IntentResolver().resolve(frame)

    EvidencePlanner().plan(request)

    assert frame.timeframe is not None
    assert request.required_evidence
    assert all(item.requires_time_series for item in request.required_evidence)
