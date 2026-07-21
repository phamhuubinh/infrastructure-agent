from __future__ import annotations

from .provider import GrafanaProvider


def alert_rules(api: GrafanaProvider) -> dict[str, object]:
    result = api.get("/api/v1/provisioning/alert-rules")
    if not isinstance(result, list):
        return {"alert_rules": [], "total": 0}
    rules = [
        {
            "uid": rule.get("uid", ""),
            "title": rule.get("title", ""),
            "folder": rule.get("folderUID", ""),
            "interval": rule.get("intervalSeconds"),
            "for": rule.get("for"),
        }
        for rule in result
        if isinstance(rule, dict)
    ]
    return {"alert_rules": rules, "total": len(rules)}
