from __future__ import annotations

from src.pipeline.evidence_completeness import EvidenceCompleteness
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.evidence_requirement import EvidenceRequirement
from src.pipeline.investigation_request import InvestigationRequest


class TestEvidenceCompleteness:
    def test_all_required_collected(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
            EvidenceRequirement(name="Memory"),
        ]
        req.evidence = [
            EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=True, data={"cores": 4}),
            EvidencePackage(capability_name="Memory Information", evidence_name="Memory", success=True, data={"total_kb": 8192}),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is True
        assert req.missing_evidence == ()

    def test_missing_required_detected(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
            EvidenceRequirement(name="Memory"),
            EvidenceRequirement(name="Disk"),
        ]
        req.evidence = [
            EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=True, data={"cores": 4}),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is False
        assert "Memory" in req.missing_evidence
        assert "Disk" in req.missing_evidence

    def test_failed_evidence_not_counted(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
        ]
        req.evidence = [
            EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=False, error="Failed"),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is False
        assert "CPU" in req.missing_evidence

    def test_no_required_evidence(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = []
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is True
        assert req.missing_evidence == ()

    def test_optional_evidence_not_required(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
        ]
        req.optional_evidence = [
            EvidenceRequirement(name="Docker", required=False),
        ]
        req.evidence = [
            EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=True, data={"cores": 4}),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is True
        assert req.missing_evidence == ()

    def test_mixed_required_and_optional(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
            EvidenceRequirement(name="Memory"),
        ]
        req.optional_evidence = [
            EvidenceRequirement(name="Docker", required=False),
        ]
        req.evidence = [
            EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=True, data={"cores": 4}),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is False
        assert "Memory" in req.missing_evidence
        assert "Docker" not in req.missing_evidence

    def test_empty_collected(self) -> None:
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
        ]
        req.evidence = []
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is False
        assert len(req.missing_evidence) == 1

    def test_evidence_name_matches_requirement_name(self) -> None:
        """Evidence completeness matches by evidence_name, not capability_name."""
        req = InvestigationRequest(raw_request="test")
        req.required_evidence = [
            EvidenceRequirement(name="CPU"),
        ]
        req.evidence = [
            EvidencePackage(
                capability_name="cpu_information",
                evidence_name="CPU",
                success=True,
                data={"cores": 4},
            ),
        ]
        checker = EvidenceCompleteness()
        checker.check(req)
        assert req.evidence_complete is True
