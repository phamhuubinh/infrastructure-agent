from __future__ import annotations

from .client import _ZabbixAPI
from .common import _count_by_severity, _severity_label


def _event_output() -> list[str]:
    return [
        "eventid",
        "source",
        "object",
        "objectid",
        "clock",
        "value",
        "name",
        "severity",
    ]


def _format_event(event: dict[str, object]) -> dict[str, object]:
    return {
        "eventid": event.get("eventid"),
        "name": event.get("name"),
        "clock": event.get("clock"),
        "severity": event.get("severity"),
        "value": event.get("value"),
        "severity_label": _severity_label(event.get("severity", "0")),
    }


def _get_events(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": _event_output(),
        "sortfield": "eventid",
        "sortorder": "DESC",
        "limit": 50,
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("event.get", params)
    if not isinstance(result, list):
        return {"events": [], "total_events": 0}
    events = [_format_event(event) for event in result if isinstance(event, dict)]
    return {"events": events, "total_events": len(events)}


def _get_problem_timeline(zapi: _ZabbixAPI, limit: int = 50) -> dict[str, object]:
    result = zapi.call(
        "problem.get",
        {
            "output": [
                "eventid",
                "objectid",
                "name",
                "clock",
                "severity",
                "acknowledged",
            ],
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": limit,
        },
    )
    if not isinstance(result, list):
        return {"problems": [], "total": 0}
    problems = [
        {
            "eventid": problem.get("eventid"),
            "name": problem.get("name"),
            "clock": problem.get("clock"),
            "severity": problem.get("severity"),
            "severity_label": _severity_label(problem.get("severity", "0")),
            "acknowledged": problem.get("acknowledged", "0"),
        }
        for problem in result
        if isinstance(problem, dict)
    ]
    return {"problems": problems, "total": len(problems)}


def _get_maintenance_status(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "maintenance.get",
        {
            "output": [
                "maintenanceid",
                "name",
                "active_since",
                "active_till",
                "description",
            ],
            "selectHosts": ["hostid", "host"],
        },
    )
    if not isinstance(result, list):
        return {"maintenances": []}
    return {
        "maintenances": [
            maintenance for maintenance in result if isinstance(maintenance, dict)
        ],
        "total_maintenances": len(result),
    }


def _get_event_summary(zapi: _ZabbixAPI, limit: int = 100) -> dict[str, object]:
    result = zapi.call(
        "event.get",
        {
            "output": _event_output(),
            "sortfield": "eventid",
            "sortorder": "DESC",
            "limit": limit,
        },
    )
    if not isinstance(result, list):
        return {"events": [], "total": 0}
    events = [_format_event(event) for event in result if isinstance(event, dict)]
    return {
        "events": events,
        "total": len(events),
        "severity_summary": _count_by_severity(events),
    }


def _get_users(zapi: _ZabbixAPI) -> dict[str, object]:
    result = zapi.call(
        "user.get", {"output": ["userid", "alias", "name", "surname", "roleid"]}
    )
    return (
        {"users": [user for user in result if isinstance(user, dict)]}
        if isinstance(result, list)
        else {"users": []}
    )
