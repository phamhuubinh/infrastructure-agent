from __future__ import annotations

from .provider import GrafanaProvider


def get_annotations(api: GrafanaProvider, limit: int = 50) -> dict[str, object]:
    result = api.get(f"/api/annotations?limit={limit}")
    if not isinstance(result, list):
        return {"annotations": [], "total": 0}
    annotations = [
        {
            "id": item.get("id"),
            "text": item.get("text", ""),
            "dashboard_uid": item.get("dashboardUID", ""),
            "panel_id": item.get("panelId"),
            "created": item.get("created"),
            "updated": item.get("updated"),
        }
        for item in result
        if isinstance(item, dict)
    ]
    return {"annotations": annotations, "total": len(annotations)}
