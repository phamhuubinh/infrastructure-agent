from __future__ import annotations

import re
import time as _time
from datetime import datetime, timezone


class TimeRangeResolver:
    """Resolve natural language time expressions into Unix timestamps.

    Examples:
        "1h" / "1 giờ" → (now - 3600, now)
        "today" / "hôm nay" → (start of today, now)
        "7d" / "7 ngày" → (now - 7 days, now)
        "yesterday" / "hôm qua" → (start of yesterday, end of yesterday)
    """

    # Fixed expressions → (start_fn, end_fn) where fn takes now_ts and returns ts.
    _FIXED: dict[str, tuple[str, str]] = {
        "1h": ("relative", "-3600"),
        "1 giờ": ("relative", "-3600"),
        "1 tiếng": ("relative", "-3600"),
        "6h": ("relative", "-21600"),
        "12h": ("relative", "-43200"),
        "24h": ("relative", "-86400"),
        "1d": ("relative", "-86400"),
        "1 ngày": ("relative", "-86400"),
        "today": ("day_start", "0"),
        "hôm nay": ("day_start", "0"),
        "yesterday": ("yesterday", "0"),
        "hôm qua": ("yesterday", "0"),
        "7d": ("relative", "-604800"),
        "7 ngày": ("relative", "-604800"),
        "this week": ("week_start", "0"),
        "tuần này": ("week_start", "0"),
        "last week": ("last_week", "0"),
        "tuần trước": ("last_week", "0"),
        "30d": ("relative", "-2592000"),
        "30 ngày": ("relative", "-2592000"),
    }

    # Pattern: number + unit
    _PATTERN: re.Pattern = re.compile(
        r"\b(\d+)\s*(?:giờ|tiếng|ngày|hours?|days?|h|d)\b", re.IGNORECASE
    )

    def resolve(self, raw_request: str) -> tuple[int, int] | None:
        """Resolve a time range from the user request.

        Args:
            raw_request: The raw user request string.

        Returns:
            A tuple of (start_unix_ts, end_unix_ts), or None if no
            time expression is detected.
        """
        lower = raw_request.lower()
        now_ts = int(_time.time())

        # 1. Check fixed expressions first.
        for phrase, (fn_type, arg) in self._FIXED.items():
            if phrase in lower:
                return self._compute(fn_type, arg, now_ts)

        # 2. Try numeric + unit patterns.
        m = self._PATTERN.search(lower)
        if m:
            num = int(m.group(1))
            unit_text = m.group(0).lower()

            # Determine unit in seconds.
            if any(u in unit_text for u in ("giờ", "tiếng", "h")):
                seconds = num * 3600
            elif any(u in unit_text for u in ("ngày", "d")):
                seconds = num * 86400
            else:
                return None

            return (now_ts - seconds, now_ts)

        return None

    def _compute(self, fn_type: str, arg: str, now_ts: int) -> tuple[int, int]:
        """Compute (start_ts, end_ts) from function type and arg."""
        if fn_type == "relative":
            offset = int(arg)  # negative seconds
            return (now_ts + offset, now_ts)

        if fn_type == "day_start":
            dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            return (int(start.timestamp()), now_ts)

        if fn_type == "yesterday":
            dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            yesterday = dt.replace(
                day=dt.day - 1, hour=0, minute=0, second=0, microsecond=0
            )
            yesterday_end = yesterday.replace(hour=23, minute=59, second=59)
            return (int(yesterday.timestamp()), int(yesterday_end.timestamp()))

        if fn_type == "week_start":
            dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            weekday = dt.weekday()  # Monday=0
            start = dt.replace(
                day=dt.day - weekday, hour=0, minute=0, second=0, microsecond=0
            )
            return (int(start.timestamp()), now_ts)

        if fn_type == "last_week":
            dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            weekday = dt.weekday()
            last_monday = dt.replace(
                day=dt.day - weekday - 7, hour=0, minute=0, second=0, microsecond=0
            )
            last_sunday = last_monday.replace(
                day=last_monday.day + 6, hour=23, minute=59, second=59
            )
            return (int(last_monday.timestamp()), int(last_sunday.timestamp()))

        return (now_ts, now_ts)
