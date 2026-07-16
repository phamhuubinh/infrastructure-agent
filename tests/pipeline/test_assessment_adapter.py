from __future__ import annotations

from src.pipeline.assessment_adapter import AssessmentAdapter
from src.pipeline.assessment_request import AssessmentRequest
from src.pipeline.evidence_package import EvidencePackage
from src.pipeline.intent_resolver import Intent
from src.pipeline.investigation_request import InvestigationRequest

_EXPECTED_CORES = 4
_EXPECTED_PACKAGES_3 = 3


class TestAssessmentAdapter:
    def test_build_full_request(self) -> None:
        inv = InvestigationRequest(
            raw_request="check server health",
            intent=Intent.MACHINE_ASSESSMENT,
        )
        inv.evidence = [
            EvidencePackage(
                capability_name="CPU Information",
                evidence_name="CPU",
                success=True,
                data={"cores": 4},
            ),
        ]
        inv.evidence_complete = True
        inv.missing_evidence = ()

        adapter = AssessmentAdapter()
        result = adapter.build(inv)

        assert isinstance(result, AssessmentRequest)
        assert result.raw_request == "check server health"
        assert result.intent == "MACHINE_ASSESSMENT"
        assert len(result.evidence) == 1
        assert result.evidence[0].data["cores"] == _EXPECTED_CORES
        assert result.evidence_complete is True
        assert result.missing_evidence == ()

    def test_build_no_intent(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        adapter = AssessmentAdapter()
        result = adapter.build(inv)
        assert result.intent == ""

    def test_build_empty_evidence(self) -> None:
        inv = InvestigationRequest(
            raw_request="check",
            intent=Intent.CPU_ASSESSMENT,
        )
        adapter = AssessmentAdapter()
        result = adapter.build(inv)
        assert result.evidence == ()

    def test_build_missing_evidence_listed(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        inv.missing_evidence = ("CPU Information", "Memory Information")
        result = AssessmentAdapter().build(inv)
        assert result.missing_evidence == ("CPU Information", "Memory Information")

    def test_build_evidence_incomplete(self) -> None:
        inv = InvestigationRequest(
            raw_request="check",
            intent=Intent.SERVICE_ASSESSMENT,
        )
        inv.evidence_complete = False
        inv.missing_evidence = ("Disk Information",)
        result = AssessmentAdapter().build(inv)
        assert result.evidence_complete is False
        assert result.missing_evidence == ("Disk Information",)

    def test_build_multiple_evidence_packages(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        inv.evidence = [
            EvidencePackage(capability_name="CPU", evidence_name="CPU", success=True),
            EvidencePackage(
                capability_name="RAM",
                evidence_name="Memory",
                success=True,
            ),
            EvidencePackage(
                capability_name="Disk",
                evidence_name="Disk",
                success=False,
                error="I/O error",
            ),
        ]
        result = AssessmentAdapter().build(inv)
        assert len(result.evidence) == _EXPECTED_PACKAGES_3
        assert result.evidence[0].capability_name == "CPU"
        assert result.evidence[1].capability_name == "RAM"
        assert result.evidence[2].error == "I/O error"

    def test_build_evidence_is_tuple_not_list(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        inv.evidence = [
            EvidencePackage(capability_name="CPU", evidence_name="CPU", success=True),
        ]
        result = AssessmentAdapter().build(inv)
        assert isinstance(result.evidence, tuple)
        assert len(result.evidence) == 1

    def test_build_produces_frozen_dataclass(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        result = AssessmentAdapter().build(inv)
        with pytest.raises(AttributeError):
            result.raw_request = "mutated"  # type: ignore[misc]

    def test_build_all_default_fields(self) -> None:
        inv = InvestigationRequest(raw_request="hello world")
        result = AssessmentAdapter().build(inv)
        assert result.raw_request == "hello world"
        assert result.intent == ""
        assert result.evidence == ()
        assert result.evidence_complete is False
        assert result.missing_evidence == ()

    def test_build_preserves_evidence_data_fidelity(self) -> None:
        inv = InvestigationRequest(raw_request="check")
        inv.evidence = [
            EvidencePackage(
                capability_name="CPU Information",
                evidence_name="CPU",
                success=True,
                data={"cores": 4, "model": "Intel Xeon"},
            ),
            EvidencePackage(
                capability_name="Memory Information",
                evidence_name="Memory",
                success=False,
                error="Connection refused",
            ),
        ]
        result = AssessmentAdapter().build(inv)
        assert result.evidence[0].data["cores"] == _EXPECTED_CORES
        assert result.evidence[0].data["model"] == "Intel Xeon"
        assert result.evidence[1].success is False
        assert result.evidence[1].error == "Connection refused"


import pytest  # noqa: E402
