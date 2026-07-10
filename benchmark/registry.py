from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_registry_path = Path(".benchmark_history.json")


def load_history() -> dict[str, Any]:
    if not _registry_path.exists():
        return {}
    try:
        return json.loads(_registry_path.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def save_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    history = load_history()
    run_id = str(len(history) + 1)
    history[run_id] = {
        "results": results,
        "overall": _compute_overall(results),
    }
    _registry_path.write_text(json.dumps(history, indent=2))
    return history


def detect_regressions(
    new_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    history = load_history()
    if not history:
        return []

    # Compare with the most recent previous run
    previous_run = list(history.values())[-1]
    prev_results = previous_run["results"]
    prev_map = {r["benchmark"]: r for r in prev_results}
    new_map = {r["benchmark"]: r for r in new_results}

    regressions: list[dict[str, Any]] = []
    for bm_name, new_r in new_map.items():
        old_r = prev_map.get(bm_name)
        if old_r is None:
            continue
        old_total = old_r["scores"]["total"]
        new_total = new_r["scores"]["total"]
        if new_total < old_total - 0.15:
            regressions.append({
                "benchmark": bm_name,
                "previous_total": round(old_total, 2),
                "new_total": round(new_total, 2),
                "delta": round(new_total - old_total, 2),
            })

    return regressions


def _compute_overall(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    scores = [r["scores"]["total"] for r in results]
    return round(sum(scores) / len(scores), 2)
