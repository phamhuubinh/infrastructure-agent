from __future__ import annotations

import json
import re
from typing import Any

from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT
from src.model.protocol.prompt_loader import PromptLoader
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_model_context import EvidenceModelContextSerializer
from src.pipeline.input_context_budget import (
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextBudgetPolicy,
)
from src.pipeline.intent_resolver import Intent

# Vietnamese characters with diacritics (Unicode range)
_VIETNAMESE_PATTERN = re.compile(
    r"[àáảãạâầấẩẫậăằắẳẵặèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ" r"ùúủũụưừứửữựỳýỷỹỵđ]",
    re.IGNORECASE,
)
_EXPLICIT_ENGLISH_RESPONSE = re.compile(
    r"(?:answer|reply|respond)\s+in\s+english|"
    r"(?:trả\s+lời|dịch)\s+(?:bằng|sang)\s+tiếng\s+anh|"
    r"(?:translate|translation)\s+(?:to|into)\s+english",
    re.IGNORECASE,
)
_EXPLICIT_VIETNAMESE_RESPONSE = re.compile(
    r"(?:answer|reply|respond)\s+in\s+vietnamese|"
    r"(?:trả\s+lời|dịch)\s+(?:bằng|sang)\s+tiếng\s+việt|"
    r"(?:translate|translation)\s+(?:to|into)\s+vietnamese",
    re.IGNORECASE,
)


def _detect_language(text: str) -> str:
    """Infer the requested response language, honouring explicit directives."""

    if _EXPLICIT_ENGLISH_RESPONSE.search(text):
        return "en"
    if _EXPLICIT_VIETNAMESE_RESPONSE.search(text):
        return "vi"
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


_EVIDENCE_STATUS_WORDING_VI: dict[str, str] = {
    "SUFFICIENT": "Bằng chứng đầy đủ cho yêu cầu này.",
    "PARTIAL": (
        "Bằng chứng chỉ thu được một phần. Một số chỉ số chưa được xác nhận — "
        "không được suy diễn chúng."
    ),
    "UNAVAILABLE": (
        "Không thu thập được bằng chứng cần thiết. Không được suy đoán trạng thái hệ thống."
    ),
    "STALE": (
        "Bằng chứng có thể đã cũ so với thời điểm hiện tại. Nêu rõ mốc thời gian quan sát."
    ),
    "CONTRADICTORY": (
        "Có mâu thuẫn số liệu giữa các nguồn cho cùng một chỉ số. "
        "Phải nêu rõ mâu thuẫn thay vì chọn một số liệu ngẫu nhiên."
    ),
    "NOT_APPLICABLE": "",
}

_EVIDENCE_STATUS_WORDING_EN: dict[str, str] = {
    "SUFFICIENT": "Evidence is sufficient for this request.",
    "PARTIAL": (
        "Evidence is only partially collected. Some metrics are unconfirmed — "
        "do not infer them."
    ),
    "UNAVAILABLE": (
        "Required evidence could not be collected. Do not guess system state."
    ),
    "STALE": "Evidence may be older than the current moment. State the observed time.",
    "CONTRADICTORY": (
        "Sources disagree on the same metric. State the contradiction explicitly "
        "instead of picking one number at random."
    ),
    "NOT_APPLICABLE": "",
}


def _evidence_status_preamble(evidence_status: str, lang: str) -> str:
    """DR1-708: canonical uncertainty wording keyed by evidence status."""

    table = _EVIDENCE_STATUS_WORDING_VI if lang == "vi" else _EVIDENCE_STATUS_WORDING_EN
    return table.get(evidence_status, "")


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
    model_context = EvidenceModelContextSerializer().serialize(assessment_request)

    lang = _detect_language(assessment_request.raw_request)
    if lang == "vi":
        instruction += (
            "\n\nQUAN TRỌNG: Bạn PHẢI trả lời TOÀN BỘ bằng tiếng Việt. "
            "Không được trả lời bằng bất kỳ ngôn ngữ nào khác (tiếng Anh, tiếng Trung, v.v.). "
            "Tất cả văn bản, giải thích, đánh giá, và khuyến nghị đều phải bằng tiếng Việt."
        )

    # DR1-701/DR1-702: findings and facts are grouped explicitly so the model
    # never has to infer confirmed vs. contradicting vs. missing from a flat
    # evidence blob.
    all_facts = {
        fact.id: fact
        for fact in (
            *assessment_request.facts,
            *(
                fact
                for package in assessment_request.evidence
                for fact in package.facts
            ),
        )
    }
    confirmed_facts = {
        fact_id: fact for fact_id, fact in all_facts.items() if fact.usable
    }
    contradicting_facts = {
        fact_id: fact
        for fact_id, fact in all_facts.items()
        if fact.validity.value == "contradictory"
    }

    def _facts_section() -> tuple[str, ...]:
        if not confirmed_facts:
            return ()
        compact_facts = model_context["facts"]
        assert isinstance(compact_facts, list)
        confirmed_compact = [
            fact for fact in compact_facts if fact["id"] in confirmed_facts
        ]
        # Confirmed facts are mandatory required evidence: they are rendered
        # in full (already compacted by the canonical evidence serializer) and
        # the class budget either keeps them intact or rejects the call —
        # this layer never pre-emptively drops them.
        return (
            "",
            "--- Confirmed facts (you may cite these) ---",
            json.dumps(confirmed_compact, indent=1, ensure_ascii=False),
        )

    def _findings_section() -> tuple[str, ...]:
        if not assessment_request.findings:
            return ()
        lines: list[str] = ["", "--- Deterministic findings ---"]
        for finding in assessment_request.findings[:15]:
            lines.append(
                f"- [{finding.decision.value}] {finding.type} "
                f"(severity={finding.severity}, id={finding.id}, "
                f"coverage={finding.coverage:.2f})"
            )
            if finding.explanation:
                lines.append(f"  {finding.explanation[:200]}")
        return tuple(lines)

    def _contradicting_section() -> tuple[str, ...]:
        if not contradicting_facts:
            return ()
        lines = [
            "",
            "--- Contradicting facts (state the contradiction, do not pick one) ---",
        ]
        for fact_id in sorted(contradicting_facts)[:10]:
            fact = contradicting_facts[fact_id]
            lines.append(f"- {fact.metric} @ {fact.target} (id={fact.id})")
        return tuple(lines)

    def _unknowns_section() -> tuple[str, ...]:
        if not assessment_request.unknowns:
            return ()
        return (
            "",
            "--- Missing facts / unknowns (do not infer these) ---",
            *(f"- {metric}" for metric in assessment_request.unknowns[:20]),
        )

    def _failures_section() -> tuple[str, ...]:
        if not assessment_request.collection_failures:
            return ()
        return (
            "",
            "--- Scope limitations: collection failures (not measurements) ---",
            *(
                f"- {failure[:300]}"
                for failure in assessment_request.collection_failures[:10]
            ),
        )

    def _grounding_section() -> tuple[str, ...]:
        if not assessment_request.allowed_claims:
            return ()
        return (
            "",
            "Grounding rule: every numeric value, target name, and severity you "
            "state must trace to one of the confirmed facts or findings above "
            f"(allowed ids: {len(assessment_request.allowed_claims)} available). "
            "Do not state a trend, health verdict, or action outside these facts/findings.",
        )

    def _evidence_section() -> tuple[str, ...]:
        lines: list[str] = ["", "--- Evidence ---"]
        compact_packages = model_context["packages"]
        assert isinstance(compact_packages, list)
        for package in compact_packages:
            if package["status"] not in {"valid", "valid_empty"} or package["stale"]:
                continue
            lines.append(f"=== {package['capability']} ({package['evidence']}) ===")
            if package["fact_ids"]:
                lines.append("Canonical facts listed above; raw payload omitted.")
            elif "raw" in package:
                lines.append(json.dumps(package["raw"], indent=1, ensure_ascii=False))
            else:
                lines.append("No model-visible raw evidence is available.")
            lines.append("")
        return tuple(lines)

    def _accounting_section() -> tuple[str, ...]:
        omitted = model_context["omitted"]
        assert isinstance(omitted, dict)
        if any(int(count) > 0 for count in omitted.values()):
            return (
                "Evidence context budget: "
                + json.dumps(omitted, ensure_ascii=False, sort_keys=True),
            )
        return ()

    def _tail_section() -> tuple[str, ...]:
        if lang == "vi":
            return (
                "--- End ---",
                "",
                "Trả lời bằng tiếng Việt. Đánh giá bằng Markdown. Không JSON/code blocks.",
            )
        return ("--- End ---", "", "Assess in Markdown. No JSON/code blocks.")

    mandatory_heads: list[str] = [
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
        mandatory_heads.append(
            f"Missing evidence: {', '.join(assessment_request.missing_evidence)}"
        )
    if assessment_request.evidence_status:
        preamble = _evidence_status_preamble(assessment_request.evidence_status, lang)
        mandatory_heads.append(f"Evidence status: {assessment_request.evidence_status}")
        if preamble:
            mandatory_heads.append(preamble)

    facts_section = _facts_section()
    contradicting_section = _contradicting_section()
    findings_section = _findings_section()
    unknowns_section = _unknowns_section()
    failures_section = _failures_section()
    grounding_section = _grounding_section()
    evidence_section = _evidence_section()
    accounting_section = _accounting_section()
    tail_section = _tail_section()

    # Mandatory content is never truncated: instructions, the fixed Orion
    # system instruction, the original user request, hard constraints
    # (safety boundary, evidence status, grounding rule), and required
    # evidence (facts, contradicting facts, packages).  Optional sections
    # are dropped one at a time from lowest semantic priority (findings,
    # then unknowns, then collection failures); each drop is reported in an
    # accounting line that is itself counted inside the budget.  If the
    # mandatory content alone cannot fit, the call is rejected before any
    # provider is invoked.
    budget = InputContextBudgetPolicy.for_class(
        InputContextBudgetClass.EVIDENCE_ASSISTED
    )
    optional_present = {
        "collection_failures": bool(failures_section),
        "unknowns": bool(unknowns_section),
        "findings": bool(findings_section),
    }

    def _budget_accounting_line(dropped: tuple[str, ...]) -> tuple[str, ...]:
        if not dropped:
            return ()
        return (
            "Input context budget: "
            + json.dumps(
                {"dropped": list(dropped)},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    def _assemble(dropped: tuple[str, ...]) -> str:
        # Every slice is an exact fragment of the final prompt; plain
        # concatenation makes len(prompt) equal the sum of the slice
        # lengths, so enforcement accounts for every character, separator,
        # and accounting line the model will see.
        slices: list[str] = ["\n".join(mandatory_heads)]

        def extend(lines: tuple[str, ...]) -> None:
            if lines:
                slices.append("\n" + "\n".join(lines))

        extend(facts_section)
        if "findings" not in dropped:
            extend(findings_section)
        extend(contradicting_section)
        if "unknowns" not in dropped:
            extend(unknowns_section)
        if "collection_failures" not in dropped:
            extend(failures_section)
        extend(grounding_section)
        extend(evidence_section)
        extend(accounting_section)
        extend(_budget_accounting_line(dropped))
        extend(tail_section)
        return "".join(slices)

    def _complete_chars(prompt: str) -> int:
        # Complete model-visible input: the fixed system instruction the
        # provider sends plus the assembled prompt.
        return len(ORION_SYSTEM_PROMPT) + len(prompt)

    dropped: tuple[str, ...] = ()
    for name in ("findings", "unknowns", "collection_failures"):
        prompt = _assemble(dropped)
        if _complete_chars(prompt) <= budget.max_chars:
            return prompt
        if not optional_present[name]:
            continue
        dropped = (*dropped, name)
    prompt = _assemble(dropped)
    if _complete_chars(prompt) > budget.max_chars:
        raise InputContextBudgetError(
            f"Mandatory input context for budget class "
            f"'{budget.budget_class.value}' is {_complete_chars(prompt)} "
            f"characters, exceeding the {budget.max_chars}-character budget."
        )
    return prompt
