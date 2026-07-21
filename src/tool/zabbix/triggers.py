from __future__ import annotations

from .client import _ZabbixAPI
from .common import _count_by_severity, _severity_label


def _get_triggers(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": [
            "triggerid",
            "description",
            "expression",
            "priority",
            "status",
            "value",
            "lastchange",
            "comments",
            "url",
            "error",
        ],
        "selectHosts": ["hostid", "host"],
        "selectTags": ["tag", "value"],
        "selectDependencies": ["triggerid", "description"],
        "filter": {"value": 1},
        "sortfield": "priority",
        "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("trigger.get", params)
    if not isinstance(result, list):
        return {"triggers": [], "total_triggers": 0}
    triggers = []
    for trigger in result:
        if not isinstance(trigger, dict):
            continue
        dependencies = trigger.get("dependencies", [])
        tags = trigger.get("tags", [])
        triggers.append(
            {
                "triggerid": trigger.get("triggerid"),
                "description": trigger.get("description"),
                "expression": trigger.get("expression"),
                "priority": trigger.get("priority"),
                "severity": _severity_label(trigger.get("priority", "0")),
                "status": trigger.get("status"),
                "value": trigger.get("value"),
                "hosts": trigger.get("hosts"),
                "lastchange": trigger.get("lastchange"),
                "comments": trigger.get("comments", ""),
                "url": trigger.get("url", ""),
                "error": trigger.get("error", ""),
                "dependencies": [
                    {
                        "triggerid": dependency.get("triggerid"),
                        "description": dependency.get("description", ""),
                    }
                    for dependency in dependencies
                    if isinstance(dependency, dict)
                ]
                if isinstance(dependencies, list)
                else [],
                "tags": [
                    {"tag": tag.get("tag", ""), "value": tag.get("value", "")}
                    for tag in tags
                    if isinstance(tag, dict)
                ]
                if isinstance(tags, list)
                else [],
            }
        )
    return {
        "triggers": triggers,
        "total_triggers": len(triggers),
        "severity_summary": _count_by_severity(triggers),
    }


def _get_problems(zapi: _ZabbixAPI, hostid: str = "") -> dict[str, object]:
    params: dict[str, object] = {
        "output": ["eventid", "objectid", "name", "clock", "severity"],
        "sortfield": "eventid",
        "sortorder": "DESC",
    }
    if hostid:
        params["hostids"] = hostid
    result = zapi.call("problem.get", params)
    if not isinstance(result, list):
        return {"problems": [], "total_problems": 0}
    problems = [
        {
            "eventid": problem.get("eventid"),
            "name": problem.get("name"),
            "clock": problem.get("clock"),
            "severity": problem.get("severity"),
            "severity_label": _severity_label(problem.get("severity", "0")),
        }
        for problem in result
        if isinstance(problem, dict)
    ]
    return {
        "problems": problems,
        "total_problems": len(problems),
        "severity_summary": _count_by_severity(problems),
    }
