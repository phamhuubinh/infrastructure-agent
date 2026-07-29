from __future__ import annotations

import json
import re
from typing import Any

from src.model.protocol.prompt_loader import PromptLoader
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.intent_resolver import Intent

# Vietnamese characters with diacritics (Unicode range)
_VIETNAMESE_PATTERN = re.compile(
    r"[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ" r"ùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Detect if text contains Vietnamese characters. Returns 'vi' or 'en'."""
    if _VIETNAMESE_PATTERN.search(text):
        return "vi"
    return "en"


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
        mount_list = (
            pkg_data.get("disks")
            or pkg_data.get("mounts")
            or pkg_data.get("filesystems")
            or []
        )
        if not isinstance(mount_list, list):
            return ""
        lines = []
        for m in mount_list[:8]:
            if isinstance(m, dict):
                mp = (
                    m.get("target")
                    or m.get("mountpoint")
                    or m.get("mount")
                    or m.get("name")
                    or "?"
                )
                used = (
                    m.get("use_percent")
                    or m.get("used_pct")
                    or m.get("usage_percent")
                    or ""
                )
                size = m.get("size_bytes") or m.get("total") or 0
                if isinstance(size, (int, float)) and size > 0:
                    size_gb = round(size / (1024**3), 1)
                    lines.append(f"{mp} {used} ({size_gb}GB)")
                else:
                    lines.append(f"{mp} {used}")
        if len(mount_list) > 8:
            lines.append(f"...+{len(mount_list) - 8}")
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


def _get_loader() -> PromptLoader:
    """Get or create a PromptLoader instance."""
    return PromptLoader()


# Map Intent enum to template filename.
_INTENT_TEMPLATES: dict[Intent, str] = {
    Intent.CPU_ASSESSMENT: "assess_cpu.j2",
    Intent.MEMORY_ASSESSMENT: "assess_memory.j2",
    Intent.DISK_ASSESSMENT: "assess_disk.j2",
    Intent.NETWORK_ASSESSMENT_SINGLE: "assess_network.j2",
    Intent.PROCESS_ASSESSMENT: "assess_process.j2",
    Intent.SERVICE_ASSESSMENT: "assess_service.j2",
    Intent.TROUBLESHOOTING: "assess_troubleshoot.j2",
    Intent.APPLICATION_DISCOVERY: "assess_application.j2",
    Intent.MONITORING_ASSESSMENT: "assess_monitoring.j2",
    Intent.PERFORMANCE_ASSESSMENT: "assess_performance.j2",
    Intent.SECURITY_ASSESSMENT: "assess_security.j2",
}

# Map version name to template filename.
_VERSION_TEMPLATES: dict[str, str] = {
    "compact": "assess_compact.j2",
    "minimal": "assess_minimal.j2",
}

# Backward-compatible PROMPT_VERSIONS dict for the benchmark module.
# Maps version names to their rendered prompt strings.
PROMPT_VERSIONS: dict[str, str] = {
    version: _get_loader().render_raw(template)
    for version, template in _VERSION_TEMPLATES.items()
}

# Default prompt version used by the system.
_ACTIVE_VERSION: str = "compact"


def set_prompt_version(version: str) -> None:
    global _ACTIVE_VERSION
    if version not in _VERSION_TEMPLATES:
        msg = (
            f"Unknown prompt version '{version}'. "
            f"Available: {', '.join(_VERSION_TEMPLATES)}"
        )
        raise ValueError(msg)
    _ACTIVE_VERSION = version


def _resolve_intent_prompt(intent_str: str) -> str:
    """Resolve intent prompt from a string intent name.

    Converts the string to an Intent enum for lookup; falls back
    to the active version template when no specific prompt exists.
    """
    try:
        intent_enum = Intent[intent_str]
        template_name = _INTENT_TEMPLATES.get(intent_enum)
        if template_name is not None:
            loader = _get_loader()
            return loader.render_raw(template_name)
    except (KeyError, ValueError):
        pass

    # Fall back to the active version template.
    loader = _get_loader()
    return loader.render_raw(_VERSION_TEMPLATES[_ACTIVE_VERSION])


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

    lang = _detect_language(assessment_request.raw_request)
    if lang == "vi":
        instruction += (
            "\n\nQUAN TRỌNG: Bạn PHẢI trả lời TOÀN BỘ bằng tiếng Việt. "
            "Không được trả lời bằng bất kỳ ngôn ngữ nào khác (tiếng Anh, tiếng Trung, v.v.). "
            "Tất cả văn bản, giải thích, đánh giá, và khuyến nghị đều phải bằng tiếng Việt."
        )

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

    if lang == "vi":
        lines.append(
            "Trả lời bằng tiếng Việt. Đánh giá bằng Markdown. Không JSON/code blocks."
        )
    else:
        lines.append("Assess in Markdown. No JSON/code blocks.")

    return "\n".join(lines)
