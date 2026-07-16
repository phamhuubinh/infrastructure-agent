from __future__ import annotations

from src.model.mock_assessment_adapter import MockAssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage


class TestMockAssessmentAdapter:
    def test_assess_returns_summary(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(raw_request="check server health")
        result = adapter.assess(req)

        assert "check server health" in result
        assert "Evidence collected: 0" in result
        assert "Successful: 0" in result
        assert "Failed: 0" in result
        assert "Evidence complete: False" in result

    def test_assess_with_evidence(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="check cpu",
            intent="CPU_ASSESSMENT",
            evidence=(
                EvidencePackage(
                    capability_name="CPU Information",
                    evidence_name="CPU",
                    success=True,
                    data={"cores": 4, "usage": 25},
                ),
                EvidencePackage(
                    capability_name="Memory Information",
                    evidence_name="MEMORY",
                    success=True,
                    data={"total_gb": 16, "used_gb": 8},
                ),
            ),
        )
        result = adapter.assess(req)

        assert "check cpu" in result
        assert "CPU_ASSESSMENT" in result
        assert "Evidence collected: 2" in result
        assert "Successful: 2" in result
        assert "Failed: 0" in result

    def test_assess_with_failed_evidence(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="check disk",
            intent="DISK_ASSESSMENT",
            evidence=(
                EvidencePackage(
                    capability_name="Disk Info",
                    evidence_name="DISK",
                    success=False,
                    error="Permission denied",
                ),
                EvidencePackage(
                    capability_name="Disk Info",
                    evidence_name="DISK",
                    success=True,
                    data={"/": {"used": 50}},
                ),
            ),
        )
        result = adapter.assess(req)

        assert "Evidence collected: 2" in result
        assert "Successful: 1" in result
        assert "Failed: 1" in result

    def test_assess_with_missing_evidence(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="full analysis",
            intent="MACHINE_ASSESSMENT",
            evidence_complete=False,
            missing_evidence=("CPU Info", "Memory Info"),
        )
        result = adapter.assess(req)

        assert "Evidence complete: False" in result
        assert "Missing evidence: CPU Info, Memory Info" in result

    def test_assess_without_missing_evidence(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="full analysis",
            intent="MACHINE_ASSESSMENT",
            evidence_complete=True,
            missing_evidence=(),
        )
        result = adapter.assess(req)

        assert "Evidence complete: True" in result
        assert "Missing evidence" not in result

    def test_assess_raw_high_confidence_returns_yes(self) -> None:
        adapter = MockAssessmentAdapter()
        result = adapter.assess_raw("check server cpu memory disk health")
        assert result == "yes"

    def test_assess_raw_low_confidence_returns_mock_message(self) -> None:
        adapter = MockAssessmentAdapter()
        result = adapter.assess_raw("gibberish xyzzy")
        assert (
            result == "I'm a mock assistant. I can help with infrastructure questions."
        )

    def test_assess_raw_empty_string(self) -> None:
        adapter = MockAssessmentAdapter()
        result = adapter.assess_raw("")
        assert (
            result == "I'm a mock assistant. I can help with infrastructure questions."
        )

    def test_assess_raw_medium_confidence_returns_yes(self) -> None:
        adapter = MockAssessmentAdapter()
        result = adapter.assess_raw("cpu memory")
        assert result == "yes"

    def test_assess_includes_intent(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="check disk",
            intent="DISK_ASSESSMENT",
        )
        result = adapter.assess(req)
        assert "DISK_ASSESSMENT" in result

    def test_assess_with_no_evidence_tuple(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(raw_request="test")
        result = adapter.assess(req)
        assert "Evidence collected: 0" in result
        assert "Successful: 0" in result
        assert "Failed: 0" in result

    def test_assess_all_failed_evidence(self) -> None:
        adapter = MockAssessmentAdapter()
        req = AssessmentRequest(
            raw_request="check all",
            intent="MACHINE_ASSESSMENT",
            evidence=(
                EvidencePackage(
                    capability_name="CPU",
                    evidence_name="CPU",
                    success=False,
                    error="Timeout",
                ),
                EvidencePackage(
                    capability_name="Memory",
                    evidence_name="MEMORY",
                    success=False,
                    error="No access",
                ),
            ),
        )
        result = adapter.assess(req)
        assert "Evidence collected: 2" in result
        assert "Successful: 0" in result
        assert "Failed: 2" in result
