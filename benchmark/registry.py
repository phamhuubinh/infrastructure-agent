from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_registry_path = Path(".benchmark_history.json")

# Metrics compared for regression detection.
# Each entry: (field_path, label, threshold)
_REGRESSION_METRICS: list[tuple[str, str, float]] = [
    ("scores.total", "total", 0.15),
    ("assessment_metrics.overall", "assessment_overall", 0.15),
    ("assessment_metrics.evidence_coverage", "evidence_coverage", 0.15),
    ("assessment_metrics.grounding", "grounding", 0.15),
    ("assessment_metrics.completeness", "completeness", 0.15),
]


def _get_nested(result: dict[str, Any], path: str) -> float:
    """Get a nested value from a result dict using dot notation.

    Example: _get_nested(r, "assessment_metrics.overall")
    """
    parts = path.split(".")
    current: Any = result
    for part in parts:
        if not isinstance(current, dict):
            return 0.0
        current = current.get(part, 0.0)
    return float(current) if isinstance(current, (int, float)) else 0.0


def load_history() -> dict[str, Any]:
    if not _registry_path.exists():
        return {}
    try:
        return json.loads(_registry_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def save_results(
    results: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    history = load_history()
    run_id = str(len(history) + 1)
    entry: dict[str, Any] = {
        "results": results,
        "overall": _compute_overall(results),
    }
    if metadata:
        entry["metadata"] = metadata
    history[run_id] = entry
    _registry_path.write_text(json.dumps(history, indent=2))
    return history


def detect_regressions(
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    history = load_history()
    if not history:
        return []

    previous_run = list(history.values())[-1]
    prev_results = previous_run["results"]
    prev_map = {r["benchmark"]: r for r in prev_results}
    new_map = {r["benchmark"]: r for r in new_results}

    regressions: list[dict[str, Any]] = []
    for bm_name, new_r in new_map.items():
        old_r = prev_map.get(bm_name)
        if old_r is None:
            continue

        for field_path, label, threshold in _REGRESSION_METRICS:
            old_val = _get_nested(old_r, field_path)
            new_val = _get_nested(new_r, field_path)

            # Only compare if the previous run had this metric.
            if old_val == 0.0 and field_path != "scores.total":
                continue

            if new_val < old_val - threshold:
                regressions.append({
                    "benchmark": bm_name,
                    "metric": label,
                    "previous": round(old_val, 4),
                    "new": round(new_val, 4),
                    "delta": round(new_val - old_val, 4),
                })

    return regressions


def _compute_overall(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    scores = [r["scores"]["total"] for r in results]
    return round(sum(scores) / len(scores), 2)
