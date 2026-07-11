from __future__ import annotations

import json

from src.pipeline.assessment_request import AssessmentRequest


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

# Default prompt version used by the system.
_ACTIVE_PROMPT = COMPACT_PROMPT


def set_prompt_version(version: str) -> None:
    """Switch the active prompt version at runtime.

    Args:
        version: One of "compact", "minimal", "structured".
    """
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
    payload: dict[str, object] = {
        "role": "infrastructure assessment engine",
        "instruction": _ACTIVE_PROMPT,
        "user_request": assessment_request.raw_request,
        "investigation_intent": assessment_request.intent,
        "evidence_completeness": {
            "complete": assessment_request.evidence_complete,
            "missing": list(assessment_request.missing_evidence),
        },
    }

    evidence_list: list[dict[str, object]] = []
    for pkg in assessment_request.evidence:
        entry: dict[str, object] = {
            "capability": pkg.capability_name,
            "evidence": pkg.evidence_name,
            "success": pkg.success,
        }
        if pkg.success:
            entry["data"] = pkg.data
        else:
            entry["error"] = pkg.error or "unknown error"
        evidence_list.append(entry)

    payload["evidence"] = evidence_list

    return json.dumps(payload)
