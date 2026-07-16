from __future__ import annotations

from src.model.protocol.prompt_builder_v2 import build_assessment_prompt
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage


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

    def test_empty_evidence(self) -> None:
        req = AssessmentRequest(raw_request="test")
        prompt = build_assessment_prompt(req)
        assert "test" in prompt
        assert "--- Evidence ---" in prompt

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
