from __future__ import annotations

import json

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
        data = json.loads(prompt)
        assert data["user_request"] == "check the server health"
        assert data["investigation_intent"] == "MACHINE_ASSESSMENT"
        assert data["evidence_completeness"]["complete"] is False
        assert "role" in data
        assert "instruction" in data

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
        data = json.loads(prompt)

        assert len(data["evidence"]) == 2
        assert data["evidence"][0]["capability"] == "CPU Information"
        assert data["evidence"][0]["success"] is True
        assert data["evidence"][0]["data"]["cores"] == 4

        assert data["evidence"][1]["success"] is False
        assert "error" in data["evidence"][1]
        assert data["evidence_completeness"]["missing"] == ["Memory"]

    def test_empty_evidence(self) -> None:
        req = AssessmentRequest(raw_request="test")
        prompt = build_assessment_prompt(req)
        data = json.loads(prompt)
        assert data["evidence"] == []

    def test_no_intent(self) -> None:
        req = AssessmentRequest(raw_request="test")
        prompt = build_assessment_prompt(req)
        data = json.loads(prompt)
        assert data["investigation_intent"] == ""

    def test_prompt_is_json(self) -> None:
        req = AssessmentRequest(raw_request="check")
        prompt = build_assessment_prompt(req)
        # Must be valid JSON
        data = json.loads(prompt)
        assert isinstance(data, dict)

    def test_prompt_does_not_include_tool_info(self) -> None:
        """The new prompt should not include tool routing or capability lists."""
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
        """The new prompt should be significantly smaller than the ReAct prompt."""
        req = AssessmentRequest(
            raw_request="check the server health",
            intent="MACHINE_ASSESSMENT",
            evidence=(
                EvidencePackage(capability_name="CPU", evidence_name="CPU", success=True, data={"cores": 4}),
                EvidencePackage(capability_name="Memory", evidence_name="Memory", success=True, data={"total": 8192}),
            ),
        )
        prompt = build_assessment_prompt(req)
        # Should be well under 5KB for a small investigation
        assert len(prompt) < 5000, f"Prompt too large: {len(prompt)} bytes"
