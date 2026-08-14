from __future__ import annotations

from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.tool.capability_result import CapabilityStatus


class TestBuildAssessmentPrompt:
    def test_basic_structure(self) -> None:
        req = AssessmentRequest(
            raw_request="check the server health",
            intent="MACHINE_ASSESSMENT",
            evidence=(),
            evidence_complete=False,
        )
        prompt = build_assessment_prompt(req)
        assert "check the server health" in prompt
        assert "MACHINE_ASSESSMENT" in prompt
        assert "Evidence complete: False" in prompt

    def test_with_evidence(self) -> None:
        ev1 = EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU",
            success=True,
            data={"cores": 4, "model": "Intel"},
        )
        ev2 = EvidencePackage(
            capability_name="Memory Information",
            evidence_name="Memory",
            success=False,
            error="Failed to collect",
        )
        req = AssessmentRequest(
            raw_request="check server",
            intent="MACHINE_ASSESSMENT",
            evidence=(ev1, ev2),
            evidence_complete=False,
            missing_evidence=("Memory",),
        )
        prompt = build_assessment_prompt(req)

        assert "CPU Information" in prompt
        assert "Memory" in prompt
        assert "Missing evidence: Memory" in prompt
        # Failed evidence should not appear in content
        assert "Failed to collect" not in prompt

    def test_partial_evidence_is_not_presented_as_valid_measurement(self) -> None:
        evidence = EvidencePackage(
            capability_name="CPU",
            evidence_name="CPU",
            success=True,
            status=CapabilityStatus.PARTIAL,
            data={"cores": 0, "usage_percent": 0},
            error="CPU commands failed",
        )
        req = AssessmentRequest(
            raw_request="check cpu",
            evidence=(evidence,),
            evidence_complete=False,
            missing_evidence=("CPU",),
        )

        prompt = build_assessment_prompt(req)

        assert "=== CPU (CPU) ===" not in prompt
        assert "usage_percent=0" not in prompt

    def test_service_summary_does_not_invent_zero_counts(self) -> None:
        evidence = EvidencePackage(
            capability_name="Services",
            evidence_name="Services",
            success=True,
            data={},
        )
        req = AssessmentRequest(raw_request="check services", evidence=(evidence,))

        prompt = build_assessment_prompt(req)

        assert "total=0" not in prompt
        assert "running=0" not in prompt

    def test_empty_evidence(self) -> None:
        req = AssessmentRequest(raw_request="test")
        prompt = build_assessment_prompt(req)
        assert "test" in prompt
        assert "--- Evidence ---" in prompt

    def test_no_usable_facts_falls_back_to_full_json_not_key_guessing(self) -> None:
        # DR1-702: the compact per-evidence-type key-guessing summary was
        # removed. Packages with no usable Facts (e.g. a provider with no
        # fact normalizer) now render as full normalized JSON instead of a
        # hand-picked subset of fields.
        evidence = EvidencePackage(
            capability_name="CPU Information",
            evidence_name="CPU",
            success=True,
            data={"model": "Intel Xeon", "logical_cores": 8, "custom_field": "x"},
        )
        req = AssessmentRequest(
            raw_request="check cpu",
            evidence=(evidence,),
            raw_evidence_required=True,
        )

        prompt = build_assessment_prompt(req)

        assert "Intel Xeon" in prompt
        assert "custom_field" in prompt
        # The old compact "CPU: model=..., logical_cores=..." summary line
        # is gone; this is JSON now.
        assert '"model"' in prompt

    def test_no_intent(self) -> None:
        req = AssessmentRequest(raw_request="test")
        prompt = build_assessment_prompt(req)
        assert "test" in prompt

    def test_prompt_is_string(self) -> None:
        req = AssessmentRequest(raw_request="check")
        prompt = build_assessment_prompt(req)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_does_not_include_tool_info(self) -> None:
        req = AssessmentRequest(raw_request="check server")
        prompt = build_assessment_prompt(req)
        assert "available_resources" not in prompt
        assert "response_examples" not in prompt
        assert "capability_descriptions" not in prompt
        assert "actions_taken" not in prompt
        assert "knowledge" not in prompt
        assert "/api" not in prompt
        assert "child_tool" not in prompt.lower()

    def test_prompt_size(self) -> None:
        req = AssessmentRequest(
            raw_request="check the server health",
            intent="MACHINE_ASSESSMENT",
            evidence=(
                EvidencePackage(
                    capability_name="CPU",
                    evidence_name="CPU",
                    success=True,
                    data={"cores": 4},
                ),
                EvidencePackage(
                    capability_name="Memory",
                    evidence_name="Memory",
                    success=True,
                    data={"total": 8192},
                ),
            ),
        )
        prompt = build_assessment_prompt(req)
        assert len(prompt) < 5000, f"Prompt too large: {len(prompt)} bytes"


class TestEpic7PromptSections:
    def test_findings_and_unknowns_rendered(self) -> None:
        from src.pipeline.finding import Finding, FindingDecision

        finding = Finding(
            id="finding:cpu_saturation",
            type="cpu_saturation",
            score=0.9,
            decision=FindingDecision.SUPPORTED,
            severity="warning",
            explanation="CPU load per core is elevated.",
        )
        req = AssessmentRequest(
            raw_request="check cpu",
            intent="CPU_ASSESSMENT",
            findings=(finding,),
            unknowns=("cpu.iowait_percent",),
            evidence_status="PARTIAL",
        )
        prompt = build_assessment_prompt(req)
        assert "Deterministic findings" in prompt
        assert "cpu_saturation" in prompt
        assert "Missing facts / unknowns" in prompt
        assert "cpu.iowait_percent" in prompt
        assert "Evidence status: PARTIAL" in prompt

    def test_grounding_rule_present_when_allowed_claims(self) -> None:
        req = AssessmentRequest(
            raw_request="check cpu",
            intent="CPU_ASSESSMENT",
            allowed_claims=("fact:abc123",),
        )
        prompt = build_assessment_prompt(req)
        assert "Grounding rule" in prompt
