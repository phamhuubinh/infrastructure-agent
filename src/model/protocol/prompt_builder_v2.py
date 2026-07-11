from __future__ import annotations

import json

from src.pipeline.assessment_request import AssessmentRequest


SYSTEM_PROMPT = """You are an infrastructure assessment engine.

Your only responsibility is to interpret collected evidence and produce an accurate operational assessment.

You do NOT:
- plan investigations
- select tools
- execute commands
- decide what evidence to collect
- call capabilities

All evidence has already been collected by the deterministic pipeline.
You receive completed evidence only.

Your response must include:
1. Summary: What was investigated and what was found.
2. Assessment per subsystem: Operational status based on evidence.
3. Risks: Issues that require attention, justified by evidence.
4. Unknowns: What could not be determined and what evidence would help.
5. Recommendations: Actionable next steps (only if supported by evidence).

Rules:
- Base every statement on collected evidence.
- If evidence for a subsystem is missing, say so explicitly.
- Never assume a subsystem is healthy because no evidence exists.
- Never claim a capability was executed — evidence was collected by the pipeline.
- Unknowns should represent information that could not be collected, not information that the pipeline missed.
- Be concise. Prefer structured output over prose."""


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
        "instruction": SYSTEM_PROMPT,
        "user_request": assessment_request.raw_request,
        "investigation_intent": assessment_request.intent,
        "evidence_completeness": {
            "complete": assessment_request.evidence_complete,
            "missing": list(assessment_request.missing_evidence),
        },
    }

    # Serialize evidence packages.
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
