from __future__ import annotations

from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest


class TestAssessmentRequest:
    def test_immutable(self) -> None:
        req = AssessmentRequest(raw_request="test")
        with pytest.raises(AttributeError):
            req.raw_request = "changed"  # type: ignore[misc]

    def test_minimal(self) -> None:
        req = AssessmentRequest(raw_request="check server")
        assert req.raw_request == "check server"
        assert req.intent == ""
        assert req.evidence == ()
        assert req.evidence_complete is False
        assert req.missing_evidence == ()

    def test_with_evidence(self) -> None:
        ev = EvidencePackage(capability_name="CPU Information", evidence_name="CPU", success=True)
        req = AssessmentRequest(
            raw_request="check server",
            intent="MACHINE_ASSESSMENT",
            evidence=(ev,),
            evidence_complete=True,
        )
        assert len(req.evidence) == 1
        assert req.evidence[0].capability_name == "CPU Information"

    def test_repr(self) -> None:
        req = AssessmentRequest(raw_request="check")
        assert "AssessmentRequest" in repr(req)


class TestAssessmentAdapter:
    def test_build_from_request(self) -> None:
        inv = InvestigationRequest(
            raw_request="check server",
            intent=Intent.MACHINE_ASSESSMENT,
        )
        inv.evidence = [
            EvidencePackage(capability_name="CPU", evidence_name="CPU", success=True, data={"cores": 4}),
        ]
        inv.evidence_complete = True
        inv.missing_evidence = ()

        adapter = AssessmentAdapter()
        result = adapter.build(inv)

        assert isinstance(result, AssessmentRequest)
        assert result.raw_request == "check server"
        assert result.intent == "MACHINE_ASSESSMENT"
        assert len(result.evidence) == 1
        assert result.evidence_complete is True
        assert result.missing_evidence == ()

    def test_no_intent(self) -> None:
        inv = InvestigationRequest(raw_request="test")
        adapter = AssessmentAdapter()
        result = adapter.build(inv)
        assert result.intent == ""

    def test_preserves_evidence_data(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        inv.evidence = [
            EvidencePackage(
                capability_name="CPU Information",
                evidence_name="CPU",
                success=True,
                data={"cores": 4, "model": "Intel"},
            ),
            EvidencePackage(
                capability_name="Memory Information",
                evidence_name="Memory",
                success=False,
                error="Failed to collect",
            ),
        ]
        adapter = AssessmentAdapter()
        result = adapter.build(inv)
        assert result.evidence[0].data["cores"] == 4
        assert result.evidence[1].success is False
        assert result.evidence[1].error == "Failed to collect"


import pytest  # noqa: E402, F811
