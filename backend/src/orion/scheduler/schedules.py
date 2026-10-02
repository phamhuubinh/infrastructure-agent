"""Bounded calendar evaluation of five-field cron in IANA timezones.

Nonexistent wall minutes are skipped. Both folds of an ambiguous minute are
occurrences, with distinct UTC identities. Search walks calendar days, never
replays missed minute intervals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})")
_MONTHS = dict(
    zip("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), range(1, 13), strict=True)
)
_DAYS = dict(zip("SUN MON TUE WED THU FRI SAT".split(), range(7), strict=True))


def utc_text(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Timestamp must have a timezone.")
    return moment.astimezone(UTC).isoformat()


def parse_instant(text: str) -> datetime:
    if not _RFC3339.fullmatch(text):
        raise ValueError("run_at must be a timezone-aware RFC3339 timestamp.")
    if text[-1:].upper() != "Z" and (int(text[-5:-3]) > 23 or int(text[-2:]) > 59):
        raise ValueError("run_at has an invalid UTC offset.")
    try:
        return datetime.fromisoformat(text.upper()).astimezone(UTC)
    except ValueError:
        raise ValueError("run_at must be a valid RFC3339 timestamp.") from None


def _field(text: str, low: int, high: int, names: dict[str, int]) -> frozenset[int]:
    for name, value in names.items():
        text = text.replace(name, str(value))
    values: set[int] = set()
    for part in text.split(","):
        pieces = part.split("/")
        if len(pieces) > 2 or not pieces[0]:
            raise ValueError("Invalid cron field.")
        step = int(pieces[1]) if len(pieces) == 2 and pieces[1].isdigit() else 1
        if len(pieces) == 2 and (not pieces[1].isdigit() or step < 1):
            raise ValueError("Invalid cron step.")
        base = pieces[0]
        if base == "*":
            start, end = low, high
        elif re.fullmatch(r"\d+-\d+", base):
            start, end = map(int, base.split("-"))
        elif base.isdigit():
            start = int(base)
            end = high if len(pieces) == 2 else start
        else:
            raise ValueError("Invalid cron field.")
        if not low <= start <= end <= high:
            raise ValueError("Cron field is out of range.")
        values.update(range(start, end + 1, step))
    return frozenset(values)


@dataclass(frozen=True)
class CronSchedule:
    text: str
    timezone: str
    zone: ZoneInfo
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    day_wild: bool
    weekday_wild: bool

    @classmethod
    def parse(cls, text: str, timezone: str) -> CronSchedule:
        fields = text.upper().split()
        if len(fields) != 5 or len(text) > 256:
            raise ValueError("Cron must contain exactly five fields (minute precision).")
        try:
            zone = ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be an installed IANA timezone name.") from None
        minute, hour, day, month, weekday = fields
        return cls(
            " ".join(fields),
            timezone,
            zone,
            _field(minute, 0, 59, {}),
            _field(hour, 0, 23, {}),
            _field(day, 1, 31, {}),
            _field(month, 1, 12, _MONTHS),
            frozenset(value % 7 for value in _field(weekday, 0, 7, _DAYS)),
            day.startswith("*"),
            weekday.startswith("*"),
        )

    def next_after(self, moment: datetime) -> datetime:
        return self._search(moment, forward=True)

    def latest_at(self, moment: datetime) -> datetime:
        return self._search(moment, forward=False)

    def _search(self, moment: datetime, *, forward: bool) -> datetime:
        moment = moment.astimezone(UTC)
        # Inspect the adjacent local day as well, for date-line offset transitions.
        date = moment.astimezone(self.zone).date() + timedelta(days=-1 if forward else 1)
        times = [(hour, minute) for hour in sorted(self.hours) for minute in sorted(self.minutes)]
        for _ in range(366 * 8 + 3):
            dom = date.day in self.days
            dow = (date.weekday() + 1) % 7 in self.weekdays
            day_matches = (dom and dow) if self.day_wild or self.weekday_wild else (dom or dow)
            if date.month in self.months and day_matches:
                occurrences: set[datetime] = set()
                for hour, minute in times:
                    wall = datetime(date.year, date.month, date.day, hour, minute)
                    for fold in (0, 1):
                        instant = wall.replace(tzinfo=self.zone, fold=fold).astimezone(UTC)
                        if instant.astimezone(self.zone).replace(tzinfo=None) != wall:
                            continue
                        if (instant > moment) if forward else (instant <= moment):
                            occurrences.add(instant)
                if occurrences:
                    return min(occurrences) if forward else max(occurrences)
            date += timedelta(days=1 if forward else -1)
        raise ValueError("Cron has no occurrence within eight calendar years.")
