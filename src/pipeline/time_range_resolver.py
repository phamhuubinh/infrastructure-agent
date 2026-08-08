from __future__ import annotations

import re
import time as _time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TemporalRequirement(Enum):
    """Evidence shape required by a temporal request."""

    SNAPSHOT = auto()
    HISTORICAL = auto()
    COMPARISON = auto()
    FORECAST = auto()


@dataclass(frozen=True, slots=True)
class TimeWindow:
    start: int
    end: int
    label: str = ""

    def to_dict(self) -> dict[str, object]:
        return {"start": self.start, "end": self.end, "label": self.label}


@dataclass(frozen=True, slots=True, eq=False)
class TimeRange:
    """Canonical, timezone-aware temporal request.

    Iteration intentionally yields ``(start, end)`` to keep existing Grafana
    link builders and callers compatible with the former tuple contract.
    """

    start: int
    end: int
    granularity: str
    timezone: str
    source_phrase: str
    requirement: TemporalRequirement = TemporalRequirement.HISTORICAL
    windows: tuple[TimeWindow, ...] = ()

    def __iter__(self):
        yield self.start
        yield self.end

    def as_tuple(self) -> tuple[int, int]:
        return self.start, self.end

    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return self.legacy_value == other
        if not isinstance(other, TimeRange):
            return False
        return self.to_dict() == other.to_dict()

    def __hash__(self) -> int:
        return hash(
            (
                self.start,
                self.end,
                self.granularity,
                self.timezone,
                self.source_phrase,
                self.requirement,
                self.windows,
            )
        )

    @property
    def legacy_value(self) -> str:
        aliases = {
            "1 giờ": "1h",
            "1 tiếng": "1h",
            "7 ngày": "7d",
            "30 ngày": "30d",
            "1 ngày": "1d",
            "6 tháng": "6months",
            "yesterday": "yesterday",
            "today": "today",
            "last_week": "last_week",
            "this_week": "7d",
        }
        return aliases.get(self.source_phrase, self.source_phrase.replace(" ", ""))

    def to_dict(self) -> dict[str, object]:
        return {
            "start": self.start,
            "end": self.end,
            "granularity": self.granularity,
            "timezone": self.timezone,
            "source_phrase": self.source_phrase,
            "requirement": self.requirement.name,
            "windows": [window.to_dict() for window in self.windows],
        }

    @classmethod
    def from_dict(cls, value: object) -> TimeRange | None:
        if not isinstance(value, dict):
            return None
        try:
            windows = tuple(
                TimeWindow(
                    start=int(item["start"]),
                    end=int(item["end"]),
                    label=str(item.get("label", "")),
                )
                for item in value.get("windows", [])
                if isinstance(item, dict)
            )
            raw_requirement = value.get("requirement", "HISTORICAL")
            requirement = TemporalRequirement[str(raw_requirement)]
            return cls(
                start=int(value["start"]),
                end=int(value["end"]),
                granularity=str(value.get("granularity", "auto")),
                timezone=str(value.get("timezone", "UTC")),
                source_phrase=str(value.get("source_phrase", "")),
                requirement=requirement,
                windows=windows,
            )
        except (KeyError, TypeError, ValueError):
            return None


class TimeRangeResolver:
    """Resolve relative/historical/forecast phrases deterministically."""

    _DURATION = re.compile(
        r"\b(\d+)\s*(giờ|tiếng|ngày|tuần|tháng|hours?|days?|weeks?|months?|h|d|w)\b",
        re.IGNORECASE,
    )
    _FUTURE_MARKERS = (
        "tới",
        "sắp tới",
        "tiếp theo",
        "trong tương lai",
        "next",
        "ahead",
        "future",
        "forecast",
        "predict",
        "dự báo",
        "dự đoán",
    )
    _COMPARISON_MARKERS = ("so sánh", "compare", " versus ", " vs ", "khác biệt")

    def resolve(
        self,
        raw_request: str,
        *,
        now: int | float | datetime | None = None,
        timezone_name: str = "UTC",
    ) -> TimeRange | None:
        lower = raw_request.casefold()
        tz = self._timezone(timezone_name)
        now_dt = self._now(now, tz)
        now_ts = int(now_dt.timestamp())

        is_comparison = any(marker in lower for marker in self._COMPARISON_MARKERS)
        explicit_windows = self._named_windows(lower, now_dt)
        if is_comparison and len(explicit_windows) >= 2:
            windows = tuple(explicit_windows)
            return TimeRange(
                start=min(window.start for window in windows),
                end=max(window.end for window in windows),
                granularity="day",
                timezone=timezone_name,
                source_phrase=self._comparison_source(lower),
                requirement=TemporalRequirement.COMPARISON,
                windows=windows,
            )

        if explicit_windows:
            window = explicit_windows[0]
            requirement = (
                TemporalRequirement.COMPARISON
                if is_comparison
                else TemporalRequirement.HISTORICAL
            )
            return TimeRange(
                start=window.start,
                end=window.end,
                granularity="day",
                timezone=timezone_name,
                source_phrase=window.label,
                requirement=requirement,
                windows=(window,),
            )

        match = self._DURATION.search(lower)
        if match:
            count = int(match.group(1))
            unit = match.group(2).casefold()
            seconds, granularity = self._duration(count, unit)
            if seconds is None:
                return None
            source = match.group(0)
            is_future = any(marker in lower for marker in self._FUTURE_MARKERS)
            requirement = (
                TemporalRequirement.FORECAST
                if is_future
                else TemporalRequirement.COMPARISON
                if is_comparison
                else TemporalRequirement.HISTORICAL
            )
            start, end = (
                (now_ts, now_ts + seconds)
                if is_future
                else (now_ts - seconds, now_ts)
            )
            return TimeRange(
                start=start,
                end=end,
                granularity=granularity,
                timezone=timezone_name,
                source_phrase=source,
                requirement=requirement,
                windows=(TimeWindow(start, end, source),),
            )

        fixed = self._fixed_relative(lower, now_dt)
        if fixed is not None:
            return TimeRange(
                start=fixed.start,
                end=fixed.end,
                granularity="hour",
                timezone=timezone_name,
                source_phrase=fixed.label,
                requirement=(
                    TemporalRequirement.COMPARISON
                    if is_comparison
                    else TemporalRequirement.HISTORICAL
                ),
                windows=(fixed,),
            )
        future_named = self._future_named_window(lower, now_dt)
        if future_named is not None:
            return TimeRange(
                start=future_named.start,
                end=future_named.end,
                granularity="day",
                timezone=timezone_name,
                source_phrase=future_named.label,
                requirement=TemporalRequirement.FORECAST,
                windows=(future_named,),
            )
        return None

    @staticmethod
    def _timezone(name: str):
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return timezone.utc

    @staticmethod
    def _now(value: int | float | datetime | None, tz) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=tz)
            return value.astimezone(tz)
        timestamp = _time.time() if value is None else float(value)
        return datetime.fromtimestamp(timestamp, tz=tz)

    def _named_windows(self, text: str, now: datetime) -> list[TimeWindow]:
        windows: list[TimeWindow] = []
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        if "hôm qua" in text or "yesterday" in text:
            start = today - timedelta(days=1)
            windows.append(
                TimeWindow(int(start.timestamp()), int(today.timestamp()) - 1, "yesterday")
            )
        if "hôm nay" in text or "today" in text:
            windows.append(TimeWindow(int(today.timestamp()), int(now.timestamp()), "today"))
        if "tuần trước" in text or "last week" in text:
            monday = today - timedelta(days=today.weekday())
            start = monday - timedelta(days=7)
            windows.append(
                TimeWindow(int(start.timestamp()), int(monday.timestamp()) - 1, "last_week")
            )
        if "tuần này" in text or "this week" in text:
            monday = today - timedelta(days=today.weekday())
            windows.append(
                TimeWindow(int(monday.timestamp()), int(now.timestamp()), "this_week")
            )
        return windows

    @staticmethod
    def _fixed_relative(text: str, now: datetime) -> TimeWindow | None:
        durations = (
            (("24h", "24 giờ"), 86400, "24h"),
            (("12h",), 43200, "12h"),
            (("6h",), 21600, "6h"),
            (("1h", "1 giờ", "1 tiếng"), 3600, "1h"),
            (("30d", "30 ngày"), 2592000, "30d"),
            (("7d", "7 ngày"), 604800, "7d"),
            (("1d", "1 ngày"), 86400, "1d"),
        )
        now_ts = int(now.timestamp())
        for phrases, seconds, label in durations:
            if any(phrase in text for phrase in phrases):
                return TimeWindow(now_ts - seconds, now_ts, label)
        return None

    @staticmethod
    def _future_named_window(text: str, now: datetime) -> TimeWindow | None:
        if not any(
            phrase in text
            for phrase in ("next month", "tháng tới", "tháng tiếp theo", "next quarter", "quý tới", "quý tiếp theo")
        ):
            return None

        if any(phrase in text for phrase in ("next quarter", "quý tới", "quý tiếp theo")):
            current_quarter_start_month = ((now.month - 1) // 3) * 3 + 1
            next_quarter_start_month = current_quarter_start_month + 3
            year = now.year + (1 if next_quarter_start_month > 12 else 0)
            month = ((next_quarter_start_month - 1) % 12) + 1
            start = now.replace(
                year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
            )
            end_month = month + 3
            end_year = year + (1 if end_month > 12 else 0)
            end_month = ((end_month - 1) % 12) + 1
            end = start.replace(year=end_year, month=end_month)
            return TimeWindow(int(start.timestamp()), int(end.timestamp()) - 1, "next_quarter")

        year = now.year + (1 if now.month == 12 else 0)
        month = 1 if now.month == 12 else now.month + 1
        start = now.replace(
            year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
        )
        end_year = year + (1 if month == 12 else 0)
        end_month = 1 if month == 12 else month + 1
        end = start.replace(year=end_year, month=end_month)
        return TimeWindow(int(start.timestamp()), int(end.timestamp()) - 1, "next_month")

    @staticmethod
    def _duration(count: int, unit: str) -> tuple[int | None, str]:
        if unit in {"giờ", "tiếng", "hour", "hours", "h"}:
            return count * 3600, "minute" if count <= 24 else "hour"
        if unit in {"ngày", "day", "days", "d"}:
            return count * 86400, "hour" if count <= 7 else "day"
        if unit in {"tuần", "week", "weeks", "w"}:
            return count * 7 * 86400, "day"
        if unit in {"tháng", "month", "months"}:
            return count * 30 * 86400, "week"
        return None, "auto"

    @staticmethod
    def _comparison_source(text: str) -> str:
        labels = [
            label
            for label in ("yesterday", "today", "last week", "this week")
            if label in text
        ]
        if "hôm qua" in text:
            labels.append("hôm qua")
        if "hôm nay" in text:
            labels.append("hôm nay")
        return " vs ".join(dict.fromkeys(labels)) or "comparison"
