from __future__ import annotations

import json

from src.shared.discovery.observation import Observation

CONTEXT_BUDGET = 5000

RULES = [
    'Use "knowledge" instead of general knowledge for questions about this machine.',
    "Only use resource names listed in available_resources.",
    "Each entry in actions_taken is an Action already executed this "
    "session and its result -- do not repeat one.",
    "A failed entry's error lists valid resources; retry with one of those.",
    "A successful entry with empty data is itself a final answer (e.g. not installed), not a reason to retry.",
    "You can only perform actions whose names appear in available_resources. "
    "If the user requests an action that is not listed (e.g. format, delete, reboot), "
    'you cannot perform it. Return "final" stating the action is not supported.',
    "Do NOT claim an action was performed unless you called it and received a successful ToolResult.",
    "Answer each question before returning final. Call capabilities for each question one at a time.",
    "BEFORE calling another capability, evaluate: "
    "will this information materially change the final conclusion? "
    "If YES, collect evidence. If NO, return FinalResponse.",
    "Do not stop investigating simply because some evidence has been collected. "
    "Continue collecting evidence until one of: (a) sufficient evidence exists to answer with reasonable confidence; "
    "(b) no additional relevant capabilities are available; (c) more evidence would not materially improve the answer. "
    "For broad requests (e.g. check the server, inspect the machine, review configuration, system health, "
    "operational assessment), investigate all major subsystems relevant to the target. "
    "Before FinalResponse: have I investigated every major aspect? "
    "Is additional evidence available that could change my conclusion? "
    "Am I stopping because I have enough evidence, or because I already have some evidence? "
    "Unknowns should represent information that cannot currently be determined, "
    "not information that could have been collected using existing capabilities.",
    "When presenting your final assessment, structure it into four clear sections: "
    "Evidence: what was directly observed (scoped to its source). "
    "Assessment: what the evidence implies operationally. "
    "Unknowns: what cannot yet be concluded. "
    "Recommendations: suggested next steps (only if supported by evidence).",
    "Never treat absence of evidence as evidence of absence. "
    "If no evidence exists for a claim, say 'There is no evidence of X in the available Y data', "
    "not 'X does not exist'.",
    "Evidence is scoped to its source. "
    "Evidence from one source (Linux, Zabbix, Grafana, etc.) must never be used to invalidate "
    "or deny entities in another source unless explicit evidence establishes a relationship between them.",
    "Never make stronger claims than the evidence supports. "
    "If evidence is insufficient, state exactly what additional evidence would be required.",
    "Select the correct source based on the user's intent: "
    "use the zabbix source for monitoring questions (host problems, interface down, WAN status, alerts, triggers); "
    "use the grafana source for visualization questions (dashboards, panels, datasources, folders, annotations); "
    "Priority: collect evidence directly related to the user's intent before general system info. "
    "Example: 'check monitor' -> monitoring services (Grafana, Zabbix) first; "
    "'check SSH' -> SSH config, ports, firewall, auth first; "
    "'check storage' -> disk, filesystem, storage first. "
    "General OS info must not take priority over evidence that directly answers the question.",
    "Before selecting any capability, first identify the investigation target. "
    "If the user explicitly names a known source or target (e.g. monitor, prod, staging, zabbix, grafana), "
    "investigate that source first. "
    "Otherwise determine which source best matches the user's intent. "
    "Only use localhost when no other source is applicable. "
    "Never assume localhost simply because the request concerns configuration, services, monitoring, "
    "health, logs, diagnostics, or operating systems — always determine the target first. "
    "If multiple sources are relevant, collect evidence from all before answering. "
    "Never force an investigation sequence. The model remains responsible for reasoning.",
]

TERMINATION_RULES = """
=== TERMINATION PROTOCOL ===

A FinalResponse asserts that the current evidence is sufficient to answer the user's request.

You MUST return type "action" when:
- Additional evidence is required and an available capability can obtain it.
- You state that more information, evidence, or tool results are needed.

You MUST return type "final" ONLY when:
- All required evidence has been collected and the user's request has been answered.
- No available capability exists to obtain missing evidence.

CONSISTENCY RULE:
Never state that additional evidence is required and then return "final".
These are logically contradictory. If more evidence is needed, return "action".
If "final" is returned, you are asserting that sufficient evidence already exists.

COMPLETION CHECK (perform before every FinalResponse):
1. Have I answered the user's request?
2. Is any required evidence still missing?
3. Can any available capability obtain that evidence?
If required evidence is still obtainable, return "action". Otherwise, return "final".
"""

HEALTH_ASSESSMENT_FORMAT = (
    "Health assessment format:\n"
    "1. Collect evidence for each relevant subsystem "
    "(CPU: get_cpu/get_cpu_usage, Memory: get_memory/get_swap, Disk: get_disk, "
    "Filesystem: get_filesystem, Network: get_network, Services: get_services, "
    "System: get_system/get_uptime/get_time, Docker: get_docker, "
    "Zabbix: get_hosts/get_problems/get_triggers).\n"
    "2. Final report sections: Evidence (raw data), Assessment (OK/INFO/WARNING/HIGH/CRITICAL per subsystem, "
    "must reference evidence), Risk (overall, justified), "
    "Missing Evidence (list uninspected subsystems, never assume healthy), "
    "Summary (evidence-based only).\n"
    "3. Do NOT return final until evidence collected for all relevant subsystems."
)

CAPABILITY_DESCRIPTIONS: dict[str, str] = {
    "get_system": "Purpose: OS identity. Use when: checking target identity, OS version, kernel. "
                 "Do NOT use when: checking CPU, memory, disk, or services. "
                 "Output: hostname, OS name/version, kernel version. Follow-up: get_memory, get_disk, get_cpu.",
    "get_network": "Purpose: Network configuration. Use when: IP address, routes, interface questions. "
                   "Do NOT use when: checking DNS, services, or disk. "
                   "Output: interfaces with IPs, routes. Follow-up: get_dns.",
    "get_services": "Purpose: Systemd service status. Use when: checking if a service is running. "
                    "Do NOT use when: checking CPU, memory, or disk. "
                    "Output: service list with running/exited/failed counts. Follow-up: get_service.",
    "get_service": "Purpose: Check a specific service. Use when: checking a named service. "
                   "Do NOT use when: listing all services (use get_services). "
                   "Output: name, active, enabled. Requires: name parameter.",
    "get_docker": "Purpose: Docker engine presence. Use when: container-related questions. "
                  "Do NOT use when: non-Docker service checks. "
                  "Output: installed (bool), version. Follow-up: get_services.",
    "get_memory": "Purpose: RAM usage. Use when: memory capacity or usage questions. "
                  "Do NOT use when: disk, CPU, or swap questions. "
                  "Output: total_kb, free_kb, available_kb, usage_percent. Follow-up: get_swap.",
    "get_swap": "Purpose: Swap usage. Use when: swap or memory pressure questions. "
                "Do NOT use when: RAM-only questions. "
                "Output: total_kb, used_kb, free_kb. Follow-up: get_memory.",
    "get_disk": "Purpose: Disk usage. Use when: disk space, storage questions. "
                "Do NOT use when: CPU, memory, or filesystem type questions. "
                "Output: per-mount size/used/available. Follow-up: get_filesystem.",
    "get_filesystem": "Purpose: Mounted filesystems. Use when: mount point or filesystem type questions. "
                      "Do NOT use when: disk usage questions (use get_disk). "
                      "Output: mount list with device, mountpoint, fstype. Follow-up: get_disk.",
    "get_dns": "Purpose: DNS resolver config. Use when: DNS or nameserver questions. "
               "Do NOT use when: network interface or IP questions. "
               "Output: nameserver IPs. Follow-up: get_network.",
    "get_process": "Purpose: Running processes. Use when: process or resource usage questions. "
                   "Do NOT use when: service status (use get_services). "
                   "Output: pid, command, cpu%, mem%. Follow-up: get_memory, get_cpu_usage.",
    "get_user": "Purpose: Local user accounts. Use when: user or account questions. "
                "Do NOT use when: system or process questions. "
                "Output: username, UID, home, shell. Follow-up: get_process.",
    "get_package": "Purpose: Installed packages. Use when: software version or package questions. "
                   "Do NOT use when: service status or process questions. "
                   "Output: package list and count. Follow-up: get_services.",
    "get_ssh": "Purpose: SSH server config. Use when: SSH port, auth settings, or service status. "
               "Do NOT use when: non-SSH service checks. "
               "Output: port, permit_root_login, active status. Follow-up: get_services.",
    "get_hardware": "Purpose: Hardware identity. Use when: vendor, model, serial number questions. "
                    "Do NOT use when: OS or software questions. "
                    "Output: manufacturer, product, serial. Follow-up: get_system.",
    "get_uptime": "Purpose: System uptime. Use when: how long the system has been running. "
                  "Do NOT use when: CPU or memory questions. "
                  "Output: uptime_seconds, uptime_hours, uptime_days. Follow-up: get_boot_time.",
    "get_boot_time": "Purpose: System boot time. Use when: last restart or boot time questions. "
                     "Do NOT use when: uptime duration questions (use get_uptime). "
                     "Output: boot_time string. Follow-up: get_uptime.",
    "get_cpu_usage": "Purpose: Current CPU usage. Use when: CPU load or utilization questions. "
                     "Do NOT use when: CPU model or core count questions (use get_cpu). "
                     "Output: user/system/idle/iowait percentages (structured). Follow-up: get_memory, get_process.",
    "get_listening_ports": "Purpose: Open TCP listening ports. Use when: checking what services are exposed. "
                          "Do NOT use when: checking service status (use get_services). "
                          "Output: port list with addresses. Follow-up: get_services.",
    "get_hosts": "Purpose: Zabbix host inventory. Use first when checking Zabbix. "
                 "Do NOT use when: checking problems, triggers, or items. "
                 "Output: host list with hostid, name, status, groups, IP. Follow-up: get_problems, get_triggers.",
    "get_host": "Purpose: Zabbix host details by name or ID. Use when searching for a specific host. "
                "Do NOT use when: listing all hosts (use get_hosts). "
                "Output: host details. Follow-up: get_items.",
    "search_hosts": "Purpose: Search Zabbix hosts by name pattern. Use when the exact hostname is unknown. "
                    "Do NOT use when: the hostname is already known. "
                    "Output: matching hosts. Follow-up: get_host, get_items.",
    "get_host_groups": "Purpose: Zabbix host groups. Use for group/classification questions. "
                       "Do NOT use when: host or problem questions. "
                       "Output: group list. Follow-up: get_hosts.",
    "get_templates": "Purpose: Zabbix templates. Use for template/configuration questions. "
                     "Do NOT use when: host or problem questions. "
                     "Output: template list. Follow-up: get_hosts.",
    "get_items": "Purpose: Zabbix items for a host. Use after getting hostid from get_hosts. "
                 "Do NOT use without a hostid. "
                 "Output: item list with lastvalue and units. Follow-up: get_triggers.",
    "get_triggers": "Purpose: Active Zabbix triggers in problem state. Use for alert/incident questions. "
                    "Do NOT use when: listing hosts (use get_hosts). "
                    "Output: trigger list with priority and hosts. Follow-up: get_problems.",
    "get_events": "Purpose: Recent Zabbix events. Use for event history questions. "
                  "Do NOT use when: current problems (use get_problems). "
                  "Output: event list with clock and severity. Follow-up: get_problems.",
    "get_problems": "Purpose: Active Zabbix problems. Use for current issue questions. "
                    "Do NOT use when: host inventory questions (use get_hosts). "
                    "Output: problem list with severity. Follow-up: get_triggers.",
    "get_users": "Purpose: Zabbix user accounts. Use for user/access questions. "
                 "Do NOT use when: host or problem questions. "
                 "Output: user list. Follow-up: get_hosts.",
    "get_api_version": "Purpose: Zabbix API version. Use for compatibility questions. "
                       "Do NOT use when: monitoring or host questions. "
                       "Output: version string. Follow-up: get_hosts.",
    "health": "Purpose: Grafana health status. Use first when checking Grafana connectivity. "
              "Do NOT use when: checking dashboards or datasources. "
              "Output: health status response. Follow-up: version.",
    "version": "Purpose: Grafana version. Use for version/compatibility questions. "
               "Do NOT use when: monitoring or dashboard questions. "
               "Output: version string. Follow-up: dashboards.",
    "dashboards": "Purpose: List all Grafana dashboards. Use for dashboard inventory questions. "
                  "Do NOT use when: searching for specific dashboards (use dashboard_search). "
                  "Output: dashboard list with title, uid, folder, tags. Follow-up: dashboard_search.",
    "dashboard_search": "Purpose: Search Grafana dashboards by query. Use when looking for specific dashboards. "
                        "Do NOT use when: listing all dashboards (use dashboards). "
                        "Output: matching dashboards. Follow-up: dashboards.",
    "dashboard_summary": "Purpose: Aggregated Grafana dashboard overview. Use for high-level dashboard inventory. "
                          "Do NOT use when: detailed dashboard info (use dashboards or dashboard_search). "
                          "Output: total count, tag list, unique tag count. Follow-up: dashboards.",
    "dashboard_details": "Purpose: Full dashboard definition with panels, queries, metrics, field config, transformations, and observed signals. "
                          "Use when: panel details, query languages (PromQL, SQL), metrics, thresholds, units, or panel structure questions. "
                          "Do NOT use when: listing all dashboards (use dashboards). "
                          "Requires: uid parameter. "
                          "Output: title, version, time range, variables, panels with queries/metrics/field_config/transformations, "
                          "panel_type_summary, datasource_domain_summary, observed_signals, infrastructure_domains. "
                          "Follow-up: dashboards.",
    "folders": "Purpose: List Grafana folders. Use for folder/classification questions. "
               "Do NOT use when: dashboard or datasource questions. "
               "Output: folder list. Follow-up: dashboards.",
    "datasources": "Purpose: List Grafana datasources. Use for datasource/connection questions. "
                   "Do NOT use when: dashboard or alert questions. "
                   "Output: datasource list with name, type, url. Follow-up: dashboards.",
    "alert_rules": "Purpose: Grafana alert rule definitions. Use for rule configuration questions. "
                   "Do NOT use when: current alert states. "
                   "Output: alert rule list. Follow-up: dashboards.",
    "annotations": "Purpose: Grafana annotations. Use for annotation/event timeline questions. "
                   "Do NOT use when: dashboard or alert questions. "
                   "Output: annotation list with text and timestamps. Follow-up: dashboards.",
}

RESPONSE_EXAMPLES = [
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "localhost",
            "resource": "get_system",
        },
    },
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "zabbix",
            "resource": "get_hosts",
        },
    },
    {
        "type": "action",
        "tool": "knowledge",
        "arguments": {
            "source": "grafana",
            "resource": "dashboards",
        },
    },
    {
        "type": "final",
        "content": "...",
    },
]


def _observation_to_dict(
    observation: Observation,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": observation.tool,
        "arguments": observation.arguments,
        "success": observation.success,
    }

    if observation.success:
        entry["data"] = observation.data
    else:
        entry["error"] = observation.error

    return entry


def _observation_size(
    observation: Observation,
) -> int:
    raw = str({"tool": observation.tool, "arguments": observation.arguments, "success": observation.success, "data": observation.data, "error": observation.error})
    return len(raw)


def _summarize_observation(
    observation: Observation,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "tool": observation.tool,
        "arguments": observation.arguments,
        "success": observation.success,
    }
    if observation.success:
        if isinstance(observation.data, dict):
            entry["summary"] = {k: v for k, v in observation.data.items()
                                if not isinstance(v, (list, dict)) or len(str(v)) < 200}
        elif isinstance(observation.data, list):
            entry["summary"] = f"[{len(observation.data)} items]"
        else:
            entry["data"] = observation.data
    else:
        entry["error"] = observation.error
    return entry


def _compress_observations(
    observations: tuple[Observation, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    actions_taken: list[dict[str, object]] = []
    errors: list[dict[str, object]] = []
    compressed: list[tuple[int, Observation]] = []

    for i, obs in enumerate(observations):
        if not obs.success:
            entry = _observation_to_dict(obs)
            actions_taken.append(entry)
            errors.append(entry)
        else:
            compressed.append((i, obs))

    total_size = sum(len(json.dumps(e)) for e in actions_taken)

    for position, (idx, obs) in enumerate(compressed):
        full = _observation_to_dict(obs)
        full_size = len(json.dumps(full))
        if total_size + full_size <= CONTEXT_BUDGET:
            actions_taken.insert(len(actions_taken) - len(errors) if errors else len(actions_taken), full)
            total_size += full_size
        else:
            summary = _summarize_observation(obs)
            actions_taken.insert(len(actions_taken) - len(errors) if errors else len(actions_taken), summary)
            total_size += len(json.dumps(summary))

    return actions_taken, errors


def _summarize_known_facts(
    known_facts: dict[str, object],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in known_facts.items():
        data = value.get("result") if isinstance(value, dict) else value
        if isinstance(data, dict):
            flat = {}
            for k, v in data.items():
                if not isinstance(v, (list, dict)):
                    flat[k] = v
                elif isinstance(v, list) and len(v) < 10:
                    flat[k] = f"[{len(v)} items]"
            if flat:
                result[key] = flat
            else:
                result[key] = type(data).__name__
        elif isinstance(data, list):
            result[key] = f"[{len(data)} items]"
        else:
            result[key] = data
    return result


def build_prompt(
    user_request: str,
    observations: tuple[Observation, ...],
    available_resources: dict[str, list[str]] | None = None,
    known_facts: dict[str, object] | None = None,
    capability_metadata: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    if available_resources is None:
        from src.tool.knowledge_tool import KnowledgeTool

        available_resources = KnowledgeTool().get_available_resources()

    actions_taken, errors = _compress_observations(observations)

    payload: dict[str, object] = {
        "role": "reasoning model for an execution agent",
        "output_format": (
            "respond with exactly one of the objects in response_examples "
            "below, unwrapped -- no markdown, no explanation, no extra key "
            "wrapping it"
        ),
        "response_examples": RESPONSE_EXAMPLES,
        "rules": RULES,
        "termination_rules": TERMINATION_RULES,
        "health_assessment_format": HEALTH_ASSESSMENT_FORMAT,
        "capability_descriptions": CAPABILITY_DESCRIPTIONS,
        "available_resources": available_resources,
        "user_request": user_request,
        "actions_taken": actions_taken,
    }

    if errors:
        payload["errors"] = errors

    if known_facts:
        payload["known_facts"] = _summarize_known_facts(known_facts)

    if capability_metadata:
        payload["capability_metadata"] = capability_metadata

    return json.dumps(payload)
