from __future__ import annotations

import time

import pytest

from src.pipeline.time_range_resolver import TimeRangeResolver


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
