from __future__ import annotations

import json
from typing import Any

from src.pipeline.assessment_request import AssessmentRequest


def _normalize_evidence(data: Any) -> Any:
    """Normalize evidence data to reduce prompt size.

    Preserves key summaries while trimming verbose/multi-line raw output.
    """
    if isinstance(data, dict):
        normalized: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, list):
                # Truncate long lists to first 10 + a summary count
                if len(value) > 10:
                    normalized[key] = value[:10] + [f"... ({len(value)} total)"]
                else:
                    normalized[key] = value
            elif isinstance(value, str) and len(value) > 500:
                normalized[key] = value[:500] + "..."
            elif isinstance(value, dict):
                normalized[key] = _normalize_evidence(value)
            else:
                normalized[key] = value
        return normalized
    elif isinstance(data, list):
        if len(data) > 10:
            return data[:10] + [f"... ({len(data)} total)"]
        return data
    elif isinstance(data, str) and len(data) > 500:
        return data[:500] + "..."
    return data


def _summarize_evidence(pkg_data: Any, evidence_name: str) -> str:
    """Build a compact text summary for common evidence types.

    Returns None if no summarization rule applies (falls back to JSON).
    """
    if not isinstance(pkg_data, dict):
        return ""

    # CPU summarization
    if evidence_name in ("CPU", "CPU Runtime", "CPU Usage"):
        parts = []
        for key in ("cpu_percent", "usage_percent", "cpu_usage_percent",
                     "idle_percent", "load_1", "load_5", "load_15",
                     "model", "cores", "threads", "count"):
            if key in pkg_data:
                parts.append(f"{key}={pkg_data[key]}")
        if parts:
            return f"CPU: {', '.join(parts)}"

    # Memory summarization
    if evidence_name in ("Memory", "Memory Usage", "Memory Information"):
        parts = []
        for key in ("total_gb", "used_gb", "available_gb", "usage_percent",
                     "total", "used", "available", "usage", "used_pct"):
            if key in pkg_data:
                parts.append(f"{key}={pkg_data[key]}")
        if parts:
            return f"Memory: {', '.join(parts)}"

    # Storage / Filesystem summarization
    if evidence_name in ("Storage", "Filesystem", "Disk Usage", "Filesystems"):
        lines = []
        mounts = pkg_data.get("mounts") or pkg_data.get("filesystems") or pkg_data.get("partitions") or []
        if isinstance(mounts, list):
            for m in mounts[:10]:
                if isinstance(m, dict):
                    mp = m.get("mount") or m.get("mountpoint") or m.get("name") or "?"
                    size = m.get("size_gb") or m.get("total_gb") or ""
                    used = m.get("used_gb") or m.get("used_pct") or ""
                    lines.append(f"{mp}: {used}{'%' if used and not 'GB' in str(used) else ''}")
            if len(mounts) > 10:
                lines.append(f"... ({len(mounts)} total)")
        if lines:
            return "Filesystems:\n  " + "\n  ".join(lines)
        return ""

    # Services summarization
    if evidence_name in ("Services", "Service Status"):
        lines = []
        svcs = pkg_data.get("services") or pkg_data.get("service_list") or []
        failed = pkg_data.get("failed") or pkg_data.get("failed_services")
        total = pkg_data.get("total") or pkg_data.get("service_count") or len(svcs)
        lines.append(f"Total: {total}")
        if failed:
            f_list = failed if isinstance(failed, list) else []
            if f_list:
                lines.append(f"Failed: {len(f_list)} - {', '.join(f_list[:5])}")
                if len(f_list) > 5:
                    lines.append(f"  ... and {len(f_list) - 5} more")
        if isinstance(svcs, list):
            for s in svcs[:10]:
                if isinstance(s, dict):
                    name = s.get("name") or s.get("unit") or "?"
                    state = s.get("state") or s.get("active") or s.get("status") or "?"
                    lines.append(f"  {name}: {state}")
            if len(svcs) > 10:
                lines.append(f"  ... ({len(svcs)} services total)")
        if lines:
            return "Services:\n" + "\n".join(lines)
        return ""

    # Network summarization
    if evidence_name == "Network":
        lines = []
        interfaces = pkg_data.get("interfaces") or pkg_data.get("interface_list") or []
        if isinstance(interfaces, list):
            for iface in interfaces[:10]:
                if isinstance(iface, dict):
                    name = iface.get("name") or iface.get("interface") or "?"
                    ip = iface.get("ip") or iface.get("ip_address") or iface.get("addr") or ""
                    state = iface.get("state") or iface.get("operstate") or iface.get("status") or ""
                    lines.append(f"  {name}: {ip} ({state})")
            if len(interfaces) > 10:
                lines.append(f"  ... ({len(interfaces)} total)")
        if lines:
            return "Network:\n" + "\n".join(lines)
        return ""

    return ""


CPU_PROMPT = """You are performing a CPU assessment only.

Scope: You MUST NOT assess Memory, Disk, Network, GPU, Docker, or Services. Only discuss CPU evidence and CPU-related processes.

Structure:
1. Summary (1-2 sentences)
2. CPU Hardware (model, cores, threads)
3. CPU Runtime (usage%, idle%, user%, system%, iowait%, load averages)
4. Top CPU Consumers (if processes provided)
5. Conclusion (only if evidence shows a problem; otherwise state no action needed)

Rules:
- Base every statement ONLY on evidence provided.
- Do NOT mention Risks or Recommendations unless there is a clear problem.
- Do NOT suggest baselines, historical data, or missing metrics.
- CRITICAL: Respond in plain Markdown text. NEVER wrap your response in JSON, a code block, or triple backticks. Output raw Markdown only.
- A linkdown docker0 interface is normal if Docker is not in use. Label it "Inactive", not "Degraded"."""


MEMORY_PROMPT = """You are performing a Memory assessment only.

Scope: You MUST NOT assess CPU, Disk, Network, GPU, Docker, or Services. Only discuss Memory and Swap evidence.

Structure:
1. Summary (1-2 sentences)
2. Memory Utilization (total, used, available, usage%)
3. Swap (if available)
4. Top Memory Consumers (if processes provided)
5. Conclusion (only if evidence shows a problem)

Rules:
- Base every statement ONLY on evidence provided.
- Do NOT mention Risks or Recommendations unless there is a clear problem.
- CRITICAL: Respond in plain Markdown text. NEVER wrap your response in JSON, a code block, or triple backticks. Output raw Markdown only.
- A linkdown docker0 interface is normal if Docker is not in use. Label it "Inactive", not "Degraded"."""


DISK_PROMPT = """You are performing a Disk assessment only.

Scope: You MUST NOT assess CPU, Memory, Network, GPU, Docker, or Services. Only discuss filesystems, mounts, capacity, and disk health.

Structure:
1. Summary (1-2 sentences)
2. Filesystem Usage (per mount: size, used, available, usage%)
3. Mount Points
4. Disk Health (only if evidence like SMART available)
5. Conclusion (only if evidence shows a problem)

Rules:
- Base every statement ONLY on evidence provided.
- Do NOT mention Risks or Recommendations unless there is a clear problem.
- CRITICAL: Respond in plain Markdown text. NEVER wrap your response in JSON, a code block, or triple backticks. Output raw Markdown only.
- A linkdown docker0 interface is normal if Docker is not in use. Label it "Inactive", not "Degraded"."""


NETWORK_SINGLE_PROMPT = """You are performing a Network assessment only.

Scope: You MUST NOT assess CPU, Memory, Disk, GPU, Docker, or Services. Only discuss network interfaces, routing, and connectivity.

Structure:
1. Summary (1-2 sentences)
2. Interfaces (name, IP, status)
3. Routing
4. Connectivity
5. Conclusion

Rules:
- Base every statement ONLY on evidence provided.
- CRITICAL: Respond in plain Markdown text. NEVER wrap your response in JSON or a code block.
- A linkdown docker0 interface is normal if Docker is not in use. Label it "Inactive", not "Degraded".
- Only flag a risk if evidence shows expected functionality is broken."""


PROCESS_PROMPT = """You are performing a Process assessment only.

Scope: You MUST NOT assess CPU, Memory usage trends, Disk, or Network. Only discuss running processes, top consumers, and process health.

Structure:
1. Summary (1-2 sentences)
2. Running Processes (total count, zombie count)
3. Top CPU Consumers
4. Top Memory Consumers
5. Process Health
6. Conclusion

Rules:
- Base every statement ONLY on evidence provided."""


COMPACT_PROMPT = """You are an infrastructure assessment engine. Interpret collected evidence and produce an operational assessment.

All evidence has been collected by the deterministic pipeline — you receive completed evidence only.

Structure your response with these sections:
1. Summary
2. Assessment per subsystem
3. Risks
4. Unknowns
5. Recommendations

Rules:
- Base every statement on evidence.
- If evidence is missing, say so. Never assume healthy without evidence.
- Be concise. Prefer structured output."""


MINIMAL_PROMPT = """You are an infrastructure assessment engine. Interpret the evidence below and produce a structured operational assessment.

Response sections: Summary, Assessment, Risks, Unknowns, Recommendations.

Be concise. Base everything on evidence."""


STRUCTURED_PROMPT = """You are an infrastructure assessment engine. Produce a structured assessment from the collected evidence.

Respond in exactly this JSON format:
{
  "summary": "...",
  "assessments": {"subsystem": {"status": "OK|WARNING|CRITICAL|UNKNOWN", "evidence": "..."}},
  "risks": [{"risk": "...", "severity": "low|medium|high", "evidence": "..."}],
  "unknowns": ["..."],
  "recommendations": ["..."]
}"""


PROMPT_VERSIONS = {
    "compact": COMPACT_PROMPT,
    "minimal": MINIMAL_PROMPT,
    "structured": STRUCTURED_PROMPT,
}

_INTENT_PROMPTS = {}

def _init_intent_prompts():
    from src.pipeline.intent_resolver import Intent
    _INTENT_PROMPTS.update({
        Intent.CPU_ASSESSMENT: CPU_PROMPT,
        Intent.MEMORY_ASSESSMENT: MEMORY_PROMPT,
        Intent.DISK_ASSESSMENT: DISK_PROMPT,
        Intent.NETWORK_ASSESSMENT_SINGLE: NETWORK_SINGLE_PROMPT,
        Intent.PROCESS_ASSESSMENT: PROCESS_PROMPT,
    })


# Default prompt version used by the system.
_ACTIVE_PROMPT = COMPACT_PROMPT


def set_prompt_version(version: str) -> None:
    global _ACTIVE_PROMPT
    if version not in PROMPT_VERSIONS:
        raise ValueError(
            f"Unknown prompt version '{version}'. "
            f"Available: {', '.join(PROMPT_VERSIONS)}"
        )
    _ACTIVE_PROMPT = PROMPT_VERSIONS[version]


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
    if not _INTENT_PROMPTS:
        _init_intent_prompts()

    intent_name = assessment_request.intent
    instruction = _INTENT_PROMPTS.get(intent_name, _ACTIVE_PROMPT)

    lines: list[str] = [
        instruction,
        "",
        f"User request: {assessment_request.raw_request}",
        f"Investigation intent: {intent_name}",
        f"Evidence complete: {assessment_request.evidence_complete}",
    ]
    if assessment_request.missing_evidence:
        lines.append(f"Missing evidence: {', '.join(assessment_request.missing_evidence)}")

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
            json_str = json.dumps(normalized, indent=2)
            if len(json_str) > 3000:
                json_str = json_str[:3000] + "\n  ... (truncated)"
            lines.append(json_str)

        lines.append("")

    lines.append("--- End of evidence ---")
    lines.append("")
    lines.append("Now produce your assessment in plain Markdown text.")
    lines.append("CRITICAL: Start your response with the first line of the assessment directly. Do NOT wrap in JSON, code blocks, or backticks.")

    return "\n".join(lines)
