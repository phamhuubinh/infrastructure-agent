from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.fact import Fact, FactFreshness, FactValidity
from src.pipeline.finding import Finding, FindingDecision
from src.pipeline.input_context_budget import (
    InputContextBudgetClass,
    InputContextBudgetError,
    InputContextBudgetPolicy,
)
from src.pipeline.provenance import Provenance

_REQUIRED_EVIDENCE_MARKER = "observed-load-average-0.73"


def _fact(fact_id: str, value: int) -> Fact:
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    return Fact(
        subject="system",
        metric="cpu.usage_percent",
        value=value,
        unit="percent",
        observed_at=now,
        collected_at=now,
        source="linux",
        target="monitor",
        validity=FactValidity.VALID,
        freshness=FactFreshness.FRESH,
        confidence=1.0,
        provenance=Provenance(
            source="linux",
            capability="get_cpu",
            target="monitor",
            observed_at=now,
            source_reference="https://example.com/cpu",
        ),
        id=fact_id,
    )


def _oversized_request() -> AssessmentRequest:
    """Mandatory evidence plus oversized optional sections.

    Required evidence: one raw-required package whose payload carries the
    ``_REQUIRED_EVIDENCE_MARKER``.  Optional sections (findings, unknowns,
    collection failures) are inflated so the EVIDENCE_ASSISTED budget is
    exceeded and the lowest-priority optional section must be dropped.
    """

    evidence = EvidencePackage(
        capability_name="Load Information",
        evidence_name="Load",
        success=True,
        data={
            "marker": _REQUIRED_EVIDENCE_MARKER,
            "samples": [f"s{i}" for i in range(400)],
        },
    )
    findings = tuple(
        Finding(
            id=f"finding:{index}",
            type="cpu_saturation",
            score=0.9,
            decision=FindingDecision.SUPPORTED,
            severity="warning",
            explanation=f"finding {index}: " + "detail " * 80,
        )
        for index in range(15)
    )
    # Six long unknowns keep the prompt-level optional sections large while
    # staying small in the evidence serializer (each is truncated there), so
    # the required raw evidence package always fits the serializer budget.
    unknowns = tuple(f"unknown.metric.{index}." + "u" * 900 for index in range(6))
    failures = tuple(f"collector failure {index}: " + "f" * 350 for index in range(10))
    return AssessmentRequest(
        # A long but well-formed user request keeps the mandatory head large
        # enough that the optional sections overflow the class budget.
        raw_request="check cpu load on monitor " + "x" * 4_000,
        intent="CPU_ASSESSMENT",
        evidence=(evidence,),
        raw_evidence_required=True,
        findings=findings,
        unknowns=unknowns,
        collection_failures=failures,
        evidence_status="PARTIAL",
        allowed_claims=("fact:load",),
    )


def _dropped_sections(prompt: str) -> list[str]:
    marker = "Input context budget: "
    line = next(
        (text for text in prompt.splitlines() if text.startswith(marker)),
        None,
    )
    assert line is not None, "budget accounting line must be present"
    payload = json.loads(line[len(marker) :])
    return list(payload.get("dropped", ()))


def test_required_evidence_is_retained_while_optional_context_is_dropped() -> None:
    from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT

    request = _oversized_request()
    prompt = build_assessment_prompt(request)

    # Mandatory content survives: the original user request, hard
    # constraints, and the required raw evidence payload.
    assert "check cpu load on monitor" in prompt
    assert "Safety boundary: Orion is read-only" in prompt
    assert "Grounding rule" in prompt
    assert "Evidence status: PARTIAL" in prompt
    assert _REQUIRED_EVIDENCE_MARKER in prompt
    assert "=== Load Information (Load) ===" in prompt

    # The lowest-priority optional section (findings) is dropped
    # deterministically before the budget is exceeded; every dropped
    # section is reported and absent, every kept one is present.
    dropped = _dropped_sections(prompt)
    assert "findings" in dropped
    assert set(dropped) <= {"findings", "unknowns", "collection_failures"}
    headers = {
        "collection_failures": (
            "--- Scope limitations: collection failures (not measurements) ---"
        ),
        "unknowns": "--- Missing facts / unknowns (do not infer these) ---",
        "findings": "--- Deterministic findings ---",
    }
    for name, header in headers.items():
        assert (header in prompt) == (name not in dropped)

    # The complete model-visible input — fixed system instruction included
    # — stays within the class budget, and this case sits near the limit.
    complete = ORION_SYSTEM_PROMPT + prompt
    assert len(complete) <= InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars
    assert len(complete) > InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars - 2_000


def test_evidence_assisted_prompt_is_deterministic() -> None:
    first = build_assessment_prompt(_oversized_request())
    second = build_assessment_prompt(_oversized_request())

    assert first == second
    assert _dropped_sections(first) == _dropped_sections(second)


def test_mandatory_overflow_fails_deterministically() -> None:
    request = AssessmentRequest(
        raw_request="x" * (InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars + 1),
        intent="CPU_ASSESSMENT",
    )

    with pytest.raises(InputContextBudgetError, match="exceeding"):
        build_assessment_prompt(request)


def test_user_request_is_never_silently_truncated_when_it_fits() -> None:
    request_text = "Investigate the current CPU state on " + "monitor. " * 400
    request = AssessmentRequest(raw_request=request_text, intent="CPU_ASSESSMENT")
    prompt = build_assessment_prompt(request)

    assert request_text in prompt
    assert len(prompt) <= InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars


def test_fact_json_is_never_sliced_mid_field() -> None:
    facts = tuple(_fact(f"fact:index-{index}", index) for index in range(12))
    request = AssessmentRequest(
        raw_request="check cpu facts",
        intent="CPU_ASSESSMENT",
        facts=facts,
        allowed_claims=tuple(fact.id for fact in facts),
    )
    prompt = build_assessment_prompt(request)

    header = "--- Confirmed facts (you may cite these) ---"
    assert header in prompt
    body = prompt.split(header, 1)[1]
    lines = body.splitlines()
    start = next(index for index, line in enumerate(lines) if line.startswith("["))
    end = next(index for index, line in enumerate(lines) if line == "]")
    kept_facts = json.loads("\n".join(lines[start : end + 1]))
    assert isinstance(kept_facts, list)
    # Required confirmed evidence is never dropped by this input-budget
    # layer: every confirmed fact survives intact as valid JSON.
    assert len(kept_facts) == len(facts)
    assert "confirmed facts omitted" not in prompt
    for fact in kept_facts:
        assert set(fact) >= {"id", "metric", "value", "target", "validity"}


def test_budget_class_constant_is_evidence_assisted() -> None:
    assert (
        InputContextBudgetPolicy.EVIDENCE_ASSISTED.budget_class
        is InputContextBudgetClass.EVIDENCE_ASSISTED
    )


def test_evidence_assisted_complete_input_hits_budget_exactly() -> None:
    from src.model.protocol.orion_system_prompt import ORION_SYSTEM_PROMPT

    base = AssessmentRequest(raw_request="x", intent="CPU_ASSESSMENT")
    base_prompt = build_assessment_prompt(base)
    complete_base = len(ORION_SYSTEM_PROMPT) + len(base_prompt)
    pad = InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars - complete_base
    assert pad > 0

    # The complete model-visible input — fixed system instruction plus the
    # assembled prompt — lands exactly on the class budget.
    request = AssessmentRequest(raw_request="x" * (pad + 1), intent="CPU_ASSESSMENT")
    prompt = build_assessment_prompt(request)
    assert "x" * (pad + 1) in prompt
    assert len(ORION_SYSTEM_PROMPT) + len(prompt) == (
        InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars
    )

    # Optional context at the boundary is dropped deterministically, and
    # the accounting line reporting the drop is itself counted inside the
    # budget — including separators.
    finding = Finding(
        id="finding:boundary",
        type="cpu_saturation",
        score=0.9,
        decision=FindingDecision.SUPPORTED,
        severity="warning",
        explanation="boundary finding",
    )
    boundary_request = AssessmentRequest(
        raw_request="x" * (pad + 1 - 100),
        intent="CPU_ASSESSMENT",
        findings=(finding,),
    )
    boundary_prompt = build_assessment_prompt(boundary_request)
    assert "--- Deterministic findings ---" not in boundary_prompt
    assert "Input context budget:" in boundary_prompt
    assert len(ORION_SYSTEM_PROMPT) + len(boundary_prompt) <= (
        InputContextBudgetPolicy.EVIDENCE_ASSISTED.max_chars
    )

    # When the mandatory content fills the budget completely, even the
    # accounting line for a dropped optional section cannot fit — the call
    # is rejected deterministically instead of silently dropping accounting.
    with pytest.raises(InputContextBudgetError, match="exceeding"):
        build_assessment_prompt(
            AssessmentRequest(
                raw_request="x" * (pad + 1),
                intent="CPU_ASSESSMENT",
                findings=(finding,),
            )
        )

    # One more mandatory character fails deterministically before any
    # provider is invoked.
    with pytest.raises(InputContextBudgetError, match="exceeding"):
        build_assessment_prompt(
            AssessmentRequest(raw_request="x" * (pad + 2), intent="CPU_ASSESSMENT")
        )


def test_required_confirmed_facts_overflow_fails_deterministically() -> None:
    facts = tuple(_fact(f"fact:bulk-{index}", index) for index in range(24))
    request = AssessmentRequest(
        raw_request="x" * 12_000,
        intent="CPU_ASSESSMENT",
        facts=facts,
        allowed_claims=tuple(fact.id for fact in facts),
    )

    # Required confirmed evidence alone pushes the mandatory content past
    # the class budget: the call is rejected before provider invocation,
    # never silently truncated by this input-budget layer.
    with pytest.raises(InputContextBudgetError, match="exceeding"):
        build_assessment_prompt(request)
