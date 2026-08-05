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
            "logical_cores",
            "usage_percent",
            "user_percent",
            "system_percent",
            "idle_percent",
            "iowait_percent",
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
            for k in (
                "usage_percent",
                "user_percent",
                "system_percent",
                "idle_percent",
                "iowait_percent",
            ):
                v = usage.get(k)
                if v is not None and not isinstance(v, str):
                    parts.append(f"{k}={v}")
        load = pkg_data.get("load", {})
        if isinstance(load, dict) and any(
            key in load for key in ("load_1min", "load_5min", "load_15min")
        ):
            parts.append(
                f"load={load.get('load_1min', '?')}/"
                f"{load.get('load_5min', '?')}/{load.get('load_15min', '?')}"
            )
        model = pkg_data.get("model")
        cores = pkg_data.get("logical_cores")
        if model is not None or cores is not None:
            core_text = f"{cores}c" if cores is not None else "?c"
            model_text = str(model).split()[0] if model else "?"
            parts.insert(0, f"{core_text} {model_text}")
        return "CPU: " + ", ".join(parts) if parts else ""

    if evidence_name in ("Memory", "Memory Usage", "Memory Information"):
        parts = []
        for k in ("total_bytes", "used_bytes", "available_bytes", "usage_percent"):
            v = pkg_data.get(k)
            if v is not None:
                parts.append(f"{k}={v}")
        return "Memory: " + ", ".join(parts) if parts else ""

    if evidence_name in ("Storage", "Filesystem", "Disk Usage", "Filesystems"):
        mount_list = pkg_data.get("filesystems")
        if not isinstance(mount_list, list):
            return ""
        lines = []
        for m in mount_list[:8]:
            if isinstance(m, dict):
                mp = m.get("mountpoint") or "?"
                used = m.get("usage_percent", "")
                size = m.get("size_bytes")
                if isinstance(size, (int, float)) and size > 0:
                    size_gb = round(size / (1024**3), 1)
                    lines.append(f"{mp} {used} ({size_gb}GB)")
                else:
                    lines.append(f"{mp} {used}")
        if len(mount_list) > 8:
            lines.append(f"...+{len(mount_list) - 8}")
        return "Disks:\n" + "\n".join(lines) if lines else ""

    if evidence_name in ("Services", "Service Status"):
        parts = []
        total = pkg_data.get("total")
        running = pkg_data.get("running")
        failed_list = pkg_data.get("failed_services")
        if total is not None:
            parts.append(f"total={total}")
        if running is not None:
            parts.append(f"running={running}")
        if isinstance(failed_list, list) and failed_list:
            parts.append(
                f"failed={len(failed_list)}:{','.join(str(s)[:15] for s in failed_list[:3])}"
            )
        return "Services: " + ", ".join(parts) if parts else ""

    if evidence_name == "Network":
        ifaces = pkg_data.get("interfaces")
        if ifaces is not None and not isinstance(ifaces, list):
            return ""
        parts = []
        if isinstance(ifaces, list):
            for iface in ifaces[:6]:
                if isinstance(iface, dict):
                    name = iface.get("name", "?")
                    addr = iface.get(
                        "address", iface.get("addr", iface.get("ip", ""))
                    )
                    parts.append(f"{name}={addr}")
            if len(ifaces) > 6:
                parts.append(f"...+{len(ifaces) - 6}")
        routes = pkg_data.get("routes")
        if isinstance(routes, list) and routes:
            parts.append(f"routes={len(routes)}")
        return "Net: " + ", ".join(parts) if parts else ""

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
        (
            "Safety boundary: Orion is read-only. No mutation was executed. "
            "Never claim that a file, process, service, package, or system state "
            "was changed; recommendations are proposals only."
        ),
    ]
    if assessment_request.missing_evidence:
        lines.append(
            f"Missing evidence: {', '.join(assessment_request.missing_evidence)}"
        )

    canonical_by_id = {
        fact.id: fact
        for fact in (
            *assessment_request.facts,
            *(
                fact
                for package in assessment_request.evidence
                for fact in package.facts
            ),
        )
        if fact.usable
    }
    if canonical_by_id:
        lines.append("")
        lines.append("--- Canonical facts ---")
        fact_json = json.dumps(
            [
                canonical_by_id[fact_id].to_dict()
                for fact_id in sorted(canonical_by_id)[:20]
            ],
            indent=1,
            ensure_ascii=False,
        )
        if len(fact_json) > 2500:
            fact_json = fact_json[:2500] + "\n ..."
        lines.append(fact_json)
    if assessment_request.collection_failures:
        lines.append("")
        lines.append("Collection failures (not measurements):")
        lines.extend(
            f"- {failure[:300]}"
            for failure in assessment_request.collection_failures[:10]
        )

    lines.append("")
    lines.append("--- Evidence ---")
    for pkg in assessment_request.evidence:
        if not pkg.valid_for_requirements:
            continue
        lines.append(f"=== {pkg.capability_name} ({pkg.evidence_name}) ===")

        usable_facts = [fact.to_dict() for fact in pkg.facts if fact.usable]
        if usable_facts:
            lines.append("Canonical facts listed above; raw payload omitted.")
            lines.append("")
            continue

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
