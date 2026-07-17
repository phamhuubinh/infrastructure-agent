from __future__ import annotations

import json
from typing import Any

from src.pipeline.assessment_request import AssessmentRequest


def _normalize_evidence(data: Any) -> Any:
    if isinstance(data, dict):
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, list):
                if len(value) > 5:
                    normalized[key] = value[:5] + [f"...+{len(value) - 5}"]
                else:
                    normalized[key] = value
            elif isinstance(value, str) and len(value) > 300:
                normalized[key] = value[:300] + "..."
            elif isinstance(value, dict):
                normalized[key] = _normalize_evidence(value)
            else:
                normalized[key] = value
        return normalized
    elif isinstance(data, list):
        if len(data) > 5:
            return data[:5] + [f"...+{len(data) - 5}"]
        return data
    elif isinstance(data, str) and len(data) > 300:
        return data[:300] + "..."
    return data


def _summarize_evidence(pkg_data: Any, evidence_name: str) -> str:
    if not isinstance(pkg_data, dict):
        return ""

    if evidence_name in ("CPU", "CPU Runtime", "CPU Usage", "CPU Information"):
        parts = []
        for k in (
            "model",
            "cores",
            "usage_percent",
            "user",
            "system",
            "idle",
            "iowait",
            "load_1min",
            "load_5min",
            "load_15min",
        ):
            v = pkg_data.get(k)
            if v is not None:
                parts.append(f"{k}={v}")
        if parts:
            return "CPU: " + ", ".join(parts)
        usage = pkg_data.get("usage", {})
        if isinstance(usage, dict):
            for k in ("user", "system", "idle", "iowait"):
                v = usage.get(k)
                if v is not None and not isinstance(v, str):
                    parts.append(f"{k}={v}%")
        load = pkg_data.get("load", {})
        if isinstance(load, dict):
            parts.append(
                f"load={load.get('1min', '?')}/{load.get('5min', '?')}/{load.get('15min', '?')}"
            )
        model = pkg_data.get("model", "")
        cores = pkg_data.get("cores", 0)
        if model or cores:
            parts.insert(0, f"{cores}c {model.split()[0] if model else '?'}")
        return "CPU: " + ", ".join(parts) if parts else ""

    if evidence_name in ("Memory", "Memory Usage", "Memory Information"):
        parts = []
        for k in ("total_kb", "used_kb", "available_kb", "usage_percent"):
            v = pkg_data.get(k)
            if v is not None:
                parts.append(f"{k}={v}")
        if parts:
            return "Memory: " + ", ".join(parts)
        # fallback: try other key names
        for k in ("total", "used", "available", "usage", "used_pct"):
            v = pkg_data.get(k)
            if v is not None:
                parts.append(f"{k}={v}")
        return "Memory: " + ", ".join(parts) if parts else ""

    if evidence_name in ("Storage", "Filesystem", "Disk Usage", "Filesystems"):
        mounts = (
            pkg_data.get("mounts")
            or pkg_data.get("disks")
            or pkg_data.get("filesystems")
            or []
        )
        if not isinstance(mounts, list):
            return ""
        lines = []
        for m in mounts[:8]:
            if isinstance(m, dict):
                mp = m.get("mountpoint") or m.get("target") or m.get("name") or "?"
                used = m.get("use_percent") or m.get("used_pct") or ""
                size = m.get("size_bytes") or m.get("total") or 0
                if isinstance(size, (int, float)) and size > 0:
                    size_gb = round(size / (1024**3), 1)
                    lines.append(f"{mp} {used} ({size_gb}GB)")
                else:
                    lines.append(f"{mp} {used}")
        if len(mounts) > 8:
            lines.append(f"...+{len(mounts) - 8}")
        return "Disks:\n" + "\n".join(lines) if lines else ""

    if evidence_name in ("Services", "Service Status"):
        total = pkg_data.get("total", 0)
        failed_list = pkg_data.get("failed_services") or []
        running = pkg_data.get("running", 0)
        parts = [f"total={total}", f"running={running}"]
        if failed_list:
            parts.append(
                f"failed={len(failed_list)}:{','.join(str(s)[:15] for s in failed_list[:3])}"
            )
        return "Services: " + ", ".join(parts)

    if evidence_name == "Network":
        ifaces = pkg_data.get("interfaces") or []
        if not isinstance(ifaces, list):
            return ""
        parts = []
        for iface in ifaces[:6]:
            if isinstance(iface, dict):
                name = iface.get("name", "?")
                addr = iface.get("address", iface.get("addr", iface.get("ip", "")))
                parts.append(f"{name}={addr}")
        if len(ifaces) > 6:
            parts.append(f"...+{len(ifaces) - 6}")
        routes = pkg_data.get("routes", [])
        if routes:
            parts.append(f"routes={len(routes)}")
        return "Net: " + ", ".join(parts)

    return ""


_OUTPUT_RULE = "Respond in plain Markdown. NEVER wrap in JSON or code blocks."


CPU_PROMPT = f"""Assess CPU. Scope: CPU only (no memory/disk/network).

Structure: Summary, Hardware (model/cores), Runtime (usage/idle/iowait/load), Top Consumers, Conclusion.

Rules: Base on evidence. No baselines. {_OUTPUT_RULE}"""


MEMORY_PROMPT = f"""Assess Memory. Scope: memory + swap only.

Structure: Summary, Utilization (total/used/available/%), Swap, Top Consumers, Conclusion.

Rules: Base on evidence. {_OUTPUT_RULE}"""


DISK_PROMPT = f"""Assess Disk. Scope: filesystems, mounts, capacity, disk health only.

Structure: Summary, Filesystem Usage, Mount Points, Disk Health, Conclusion.

Rules: Base on evidence. {_OUTPUT_RULE}"""


NETWORK_SINGLE_PROMPT = f"""Assess Network. Scope: interfaces, routing, connectivity only.

Structure: Summary, Interfaces, Routing, Connectivity, Conclusion.

Rules: Base on evidence. {_OUTPUT_RULE}"""


PROCESS_PROMPT = """Assess Processes. Scope: running processes, top consumers, process health only.

Structure: Summary, Running (total/zombie), Top CPU, Top Memory, Health, Conclusion.

Rules: Base on evidence."""


COMPACT_PROMPT = f"""You are an infrastructure assessment engine. Assess collected evidence.

Structure: Summary, Assessment per subsystem, Risks, Unknowns, Recommendations.

Rules: Base on evidence. Say if evidence missing. Be concise. {_OUTPUT_RULE}"""


MINIMAL_PROMPT = f"""Assess infrastructure evidence.

Sections: Summary, Assessment, Risks, Unknowns, Recommendations.

Be concise. Base on evidence. {_OUTPUT_RULE}"""


PROMPT_VERSIONS = {
    "compact": COMPACT_PROMPT,
    "minimal": MINIMAL_PROMPT,
}

_INTENT_PROMPTS = {}


def _init_intent_prompts():
    from src.pipeline.intent_resolver import Intent

    _INTENT_PROMPTS.update(
        {
            Intent.CPU_ASSESSMENT: CPU_PROMPT,
            Intent.MEMORY_ASSESSMENT: MEMORY_PROMPT,
            Intent.DISK_ASSESSMENT: DISK_PROMPT,
            Intent.NETWORK_ASSESSMENT_SINGLE: NETWORK_SINGLE_PROMPT,
            Intent.PROCESS_ASSESSMENT: PROCESS_PROMPT,
        }
    )


# Default prompt version used by the system.
_ACTIVE_PROMPT = COMPACT_PROMPT


def set_prompt_version(version: str) -> None:
    global _ACTIVE_PROMPT
    if version not in PROMPT_VERSIONS:
        msg = (
            f"Unknown prompt version '{version}'. "
            f"Available: {', '.join(PROMPT_VERSIONS)}"
        )
        raise ValueError(msg)
    _ACTIVE_PROMPT = PROMPT_VERSIONS[version]


def _resolve_intent_prompt(intent_str: str) -> str:
    """Resolve intent prompt from a string intent name.

    Converts the string to an Intent enum for lookup; falls back
    to the default compact prompt when no specific prompt exists.
    """
    if not _INTENT_PROMPTS:
        _init_intent_prompts()

    try:
        from src.pipeline.intent_resolver import Intent

        intent_enum = Intent[intent_str]
        return _INTENT_PROMPTS.get(intent_enum, _ACTIVE_PROMPT)
    except (KeyError, ValueError):
        return _ACTIVE_PROMPT


def build_assessment_prompt(
    assessment_request: AssessmentRequest,
) -> str:
    """Build a single-pass assessment prompt from completed evidence.

    The model receives evidence only — it does not need to decide
    what to investigate or what tools to call.

    Args:
        assessment_request: The immutable assessment input.

    Returns:
        A prompt string for the model.
    """
    instruction = _resolve_intent_prompt(assessment_request.intent)

    lines: list[str] = [
        instruction,
        "",
        f"User request: {assessment_request.raw_request}",
        f"Investigation intent: {assessment_request.intent}",
        f"Evidence complete: {assessment_request.evidence_complete}",
    ]
    if assessment_request.missing_evidence:
        lines.append(
            f"Missing evidence: {', '.join(assessment_request.missing_evidence)}"
        )

    lines.append("")
    lines.append("--- Evidence ---")
    for pkg in assessment_request.evidence:
        if not pkg.success:
            continue
        lines.append(f"=== {pkg.capability_name} ({pkg.evidence_name}) ===")

        # Try compact text summary first.
        summary = _summarize_evidence(pkg.data, pkg.evidence_name)
        if summary:
            lines.append(summary)
        else:
            # Normalize + serialize as JSON (with truncation).
            normalized = _normalize_evidence(pkg.data)
            json_str = json.dumps(normalized, indent=1)
            if len(json_str) > 2000:
                json_str = json_str[:2000] + "\n ..."
            lines.append(json_str)

        lines.append("")

    lines.append("--- End ---")
    lines.append("")
    lines.append("Assess in Markdown. No JSON/code blocks.")

    return "\n".join(lines)
