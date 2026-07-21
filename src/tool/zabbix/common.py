from __future__ import annotations

SEVERITY_LABELS = {
    "0": "ok",
    "1": "info",
    "2": "warning",
    "3": "average",
    "4": "high",
    "5": "disaster",
}


def _severity_label(priority: object) -> str:
    return SEVERITY_LABELS.get(str(priority), "unknown")


def _count_by_severity(
    items: list[dict[str, object]], key: str = "severity"
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        label = _severity_label(item.get(key, "0"))
        counts[label] = counts.get(label, 0) + 1
    return counts
